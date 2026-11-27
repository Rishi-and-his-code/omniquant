"""OpenAI-compatible AI provider for strategy generation and analysis."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI

from app.config import Settings, get_settings
from app.schemas.strategy import parse_strategy_dsl, strategy_rules_text

logger = logging.getLogger(__name__)

STRATEGY_SYSTEM_PROMPT = """You are OmniQuant's strategy compiler for a university research prototype.

Convert the user's natural-language trading idea into ONE of exactly three supported Strategy DSL JSON objects.

Supported strategies ONLY:
1) sma_crossover — parameters: fast_period (int 2-250), slow_period (int 2-250), fast < slow
2) ema_crossover — parameters: fast_period (int 2-250), slow_period (int 2-250), fast < slow
3) rsi_mean_reversion — parameters: period (int 2-250), lower (0-100), upper (0-100), lower < upper

Rules:
- position_type must be "long_only"
- schema_version must be 1
- Respond with a JSON object ONLY (no markdown fences)
- If the request matches a supported strategy, return:
  {"status":"ok","dsl":{...full strategy object...},"message":null}
- If the request requires unsupported indicators, short selling, leverage, multi-condition logic, or anything outside the three templates, return:
  {"status":"unsupported","dsl":null,"message":"clear explanation of what is unsupported"}
- NEVER silently drop unsupported conditions (e.g. MACD confirmation). Mark as unsupported instead.
- Do not invent parameters outside the schema.
"""

ANALYSIS_SYSTEM_PROMPT = """You are OmniQuant's research analyst for historical simulated backtests.

You receive ACTUAL calculated metrics from a deterministic backtesting engine.
You MUST NOT invent, alter, or recalculate numeric metrics.
You MUST NOT give real-money trading advice or guarantee future performance.
Frame the output as AI-assisted historical research only.

When comparing strategy total return to buy-and-hold / benchmark return, state the comparison accurately
using only the provided metric values. If the strategy underperformed the benchmark, say so clearly.

Return JSON ONLY with this shape:
{
  "summary": "string",
  "strengths": ["string"],
  "weaknesses": ["string"],
  "risk_observations": ["string"],
  "suggested_improvements": ["string"],
  "recommended_tests": ["string"],
  "limitations": ["string"]
}
"""


class AIProviderError(Exception):
    def __init__(self, code: str, message: str, details: Any = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details


class _TransportFailure(Exception):
    """The provider did not return a completion. The other provider may be tried."""

    def __init__(self, message: str, *, category: str = "transport", status: int | None = None):
        super().__init__(message)
        self.category = category
        self.status = status


_FAILOVER_STATUS = {408, 429, 500, 502, 503, 504}


class _AITarget:
    def __init__(self, role: str, base_url: str, api_key: str, model: str):
        self.role = role
        self.base_url = base_url
        self.api_key = api_key
        self.model = model


def _sanitize_provider_text(text: str, *, max_len: int = 280) -> str:
    """Strip secrets-like tokens and truncate for logs / safe details."""
    cleaned = re.sub(r"(?i)(bearer\s+)[^\s,]+", r"\1***", text or "")
    cleaned = re.sub(
        r"(?i)(api[_-]?key|authorization|token)\s*[:=]\s*[^\s,;]+",
        r"\1=***",
        cleaned,
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if len(cleaned) > max_len:
        return cleaned[: max_len - 1] + "…"
    return cleaned


def _provider_error_body(exc: APIStatusError) -> str:
    try:
        body = exc.response.json()
    except Exception:
        body = None
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            return str(err.get("message") or err.get("code") or body)
        if err:
            return str(err)
        return str(body)
    try:
        return exc.response.text or str(exc)
    except Exception:
        return str(exc)


def _classify_status_error(target: _AITarget, exc: APIStatusError) -> AIProviderError | _TransportFailure:
    status = exc.status_code
    raw = _sanitize_provider_text(_provider_error_body(exc))
    lower = raw.lower()
    details = {
        "provider": target.role,
        "status": status,
        "model": target.model,
        "provider_message": raw or None,
    }

    if status in _FAILOVER_STATUS:
        category = "rate_limit" if status == 429 else "provider_unavailable"
        return _TransportFailure(raw or f"HTTP {status}", category=category, status=status)

    if status in {401, 403}:
        return AIProviderError(
            "AI_AUTH_FAILED",
            "AI provider authentication failed. Check the configured API key.",
            details=details,
        )
    if status == 404:
        return AIProviderError(
            "AI_MODEL_UNAVAILABLE",
            "AI model or endpoint was not found. Check AI_BASE_URL and AI_MODEL.",
            details=details,
        )
    if status == 400:
        if "response_format" in lower or "json_object" in lower or "json schema" in lower:
            return AIProviderError(
                "AI_UNSUPPORTED_REQUEST",
                "AI provider rejected structured JSON request parameters.",
                details=details,
            )
        if "decisions model" in lower or "/api/alpha/decisions" in lower:
            return AIProviderError(
                "AI_MODEL_UNAVAILABLE",
                "Configured AI model does not support chat completions. Use a chat-compatible model id.",
                details=details,
            )
        if "model" in lower and any(
            token in lower for token in ("not found", "invalid", "does not exist", "unknown", "cannot be used")
        ):
            return AIProviderError(
                "AI_MODEL_UNAVAILABLE",
                "Configured AI model is unavailable or incompatible with chat completions.",
                details=details,
            )
        return AIProviderError(
            "AI_UNSUPPORTED_REQUEST",
            "AI provider rejected the request format or parameters.",
            details=details,
        )
    if status == 422:
        return AIProviderError(
            "AI_UNSUPPORTED_REQUEST",
            "AI provider rejected the request schema.",
            details=details,
        )

    return AIProviderError(
        "AI_PROVIDER_ERROR",
        "AI provider returned an unexpected error.",
        details=details,
    )


class AIModelProvider:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    def check_configuration(self) -> dict[str, Any]:
        return {
            "ai_enabled": self.settings.ai_enabled,
            "ai_configured": self.settings.ai_configured,
            "ai_fallback_configured": self.settings.ai_fallback_configured,
            "model": self.settings.ai_model or self.settings.ai_fallback_model or None,
            "base_url_set": bool(self.settings.ai_base_url),
        }

    def _targets(self) -> list[_AITarget]:
        targets: list[_AITarget] = []
        if self.settings.ai_primary_configured:
            targets.append(
                _AITarget(
                    "primary",
                    self.settings.ai_base_url,
                    self.settings.ai_api_key,
                    self.settings.ai_model,
                )
            )
        if self.settings.ai_fallback_configured:
            targets.append(
                _AITarget(
                    "fallback",
                    self.settings.ai_fallback_base_url,
                    self.settings.ai_fallback_api_key,
                    self.settings.ai_fallback_model,
                )
            )
        return targets

    def _complete(
        self,
        target: _AITarget,
        system: str,
        user: str,
        *,
        use_json_format: bool = True,
    ) -> str:
        client = OpenAI(
            api_key=target.api_key,
            base_url=target.base_url,
            timeout=self.settings.ai_timeout_seconds,
        )
        kwargs: dict[str, Any] = {
            "model": target.model,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if use_json_format:
            kwargs["response_format"] = {"type": "json_object"}

        try:
            resp = client.chat.completions.create(**kwargs)
        except (APITimeoutError, TimeoutError) as exc:
            raise _TransportFailure(str(exc), category="timeout") from exc
        except (APIConnectionError, ConnectionError) as exc:
            raise _TransportFailure(str(exc), category="unreachable") from exc
        except APIStatusError as exc:
            classified = _classify_status_error(target, exc)
            if (
                use_json_format
                and isinstance(classified, AIProviderError)
                and classified.code == "AI_UNSUPPORTED_REQUEST"
                and exc.status_code == 400
            ):
                raw = str((classified.details or {}).get("provider_message") or "").lower()
                if "response_format" in raw or "json_object" in raw or "json schema" in raw:
                    logger.warning(
                        "AI %s rejected response_format; retrying without structured JSON mode",
                        target.role,
                    )
                    return self._complete(target, system, user, use_json_format=False)
            if isinstance(classified, _TransportFailure):
                raise classified from exc
            raise classified from exc

        return resp.choices[0].message.content or ""

    def _chat_json(self, system: str, user: str) -> tuple[dict[str, Any], str]:
        targets = self._targets()
        if not targets:
            raise AIProviderError(
                "AI_UNAVAILABLE",
                "AI is disabled or credentials/model are not configured.",
            )
        last_transport: _TransportFailure | None = None
        last_reject: AIProviderError | None = None
        for target in targets:
            try:
                content = self._complete(target, system, user)
                return self._parse_json(content), target.model
            except _TransportFailure as exc:
                last_transport = exc
                logger.warning(
                    "AI %s provider transport failure (%s): %s",
                    target.role,
                    exc.category,
                    _sanitize_provider_text(str(exc)),
                )
                continue
            except AIProviderError as exc:
                # Non-transport rejection: do not hide behind another provider silently
                # unless primary is unreachable-style only. Auth/model/format errors stop here.
                last_reject = exc
                logger.warning(
                    "AI %s provider rejected request code=%s status=%s",
                    target.role,
                    exc.code,
                    (exc.details or {}).get("status") if isinstance(exc.details, dict) else None,
                )
                raise
            except json.JSONDecodeError as exc:
                raise AIProviderError(
                    "AI_INVALID_OUTPUT",
                    "AI returned malformed JSON.",
                    details={"provider": target.role},
                ) from exc

        if last_reject is not None:
            raise last_reject
        category = last_transport.category if last_transport else "transport"
        if category == "timeout":
            message = "AI provider timed out."
            code = "AI_TIMEOUT"
        elif category == "unreachable":
            message = "AI provider is unreachable from the application."
            code = "AI_UNREACHABLE"
        elif category == "rate_limit":
            message = "AI provider rate limit exceeded. Try again shortly."
            code = "AI_RATE_LIMITED"
        else:
            message = "AI provider request failed."
            code = "AI_PROVIDER_ERROR"
        raise AIProviderError(
            code,
            message,
            details={
                "reason": _sanitize_provider_text(str(last_transport) if last_transport else ""),
                "category": category,
                "status": last_transport.status if last_transport else None,
            },
        )

    def _parse_json(self, content: str) -> dict[str, Any]:
        text = content.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        # Recover leading/trailing prose around a JSON object when providers ignore JSON mode.
        if not text.startswith("{"):
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                text = text[start : end + 1]
        return json.loads(text)

    def generate_strategy(self, prompt: str) -> dict[str, Any]:
        data, model = self._chat_json(STRATEGY_SYSTEM_PROMPT, prompt)
        status = data.get("status")
        if status == "unsupported":
            return {
                "status": "unsupported",
                "message": data.get("message") or "Strategy request is unsupported.",
                "dsl": None,
                "rules": None,
                "model_name": model,
            }
        if status != "ok" or not data.get("dsl"):
            # One correction attempt
            correction = (
                "Your previous response was invalid. Return valid JSON with status ok "
                "and a complete dsl matching the schema, or status unsupported.\n"
                f"Previous response: {json.dumps(data)[:1500]}"
            )
            data, model = self._chat_json(STRATEGY_SYSTEM_PROMPT, prompt + "\n\n" + correction)

        if data.get("status") == "unsupported":
            return {
                "status": "unsupported",
                "message": data.get("message") or "Strategy request is unsupported.",
                "dsl": None,
                "rules": None,
                "model_name": model,
            }

        dsl_raw = data.get("dsl")
        if not isinstance(dsl_raw, dict):
            raise AIProviderError(
                "AI_INVALID_OUTPUT",
                "AI returned a response that could not be validated as Strategy DSL.",
            )
        try:
            parsed = parse_strategy_dsl(dsl_raw)
        except Exception as exc:
            # One more correction focused on validation error
            correction = (
                f"Validation error: {exc}. Fix the dsl JSON to satisfy the schema."
            )
            data2, model = self._chat_json(
                STRATEGY_SYSTEM_PROMPT, prompt + "\n\n" + correction
            )
            if data2.get("status") == "unsupported":
                return {
                    "status": "unsupported",
                    "message": data2.get("message"),
                    "dsl": None,
                    "rules": None,
                    "model_name": model,
                }
            try:
                parsed = parse_strategy_dsl(data2.get("dsl") or {})
            except Exception as exc2:
                raise AIProviderError(
                    "AI_INVALID_OUTPUT",
                    "AI-generated strategy failed independent validation.",
                    details={"reason": str(exc2)},
                ) from exc2

        return {
            "status": "ok",
            "message": None,
            "dsl": parsed.model_dump(),
            "rules": strategy_rules_text(parsed),
            "model_name": model,
        }

    def generate_analysis(self, context: dict[str, Any]) -> tuple[dict[str, Any], str, str]:
        user_payload = json.dumps(context, indent=2, default=str)
        prompt = (
            "Analyze this historical simulated backtest. "
            "Use only the provided metrics; do not invent numbers.\n\n"
            f"{user_payload}"
        )
        data, model = self._chat_json(ANALYSIS_SYSTEM_PROMPT, prompt)
        required = [
            "summary",
            "strengths",
            "weaknesses",
            "risk_observations",
            "suggested_improvements",
            "recommended_tests",
            "limitations",
        ]
        for key in required:
            if key not in data:
                raise AIProviderError(
                    "AI_INVALID_OUTPUT",
                    f"AI analysis missing required field: {key}",
                )
            if key != "summary" and not isinstance(data[key], list):
                raise AIProviderError(
                    "AI_INVALID_OUTPUT",
                    f"AI analysis field '{key}' must be a list.",
                )
        if not isinstance(data["summary"], str):
            raise AIProviderError("AI_INVALID_OUTPUT", "summary must be a string")
        report = {k: data[k] for k in required}
        return report, model, prompt
