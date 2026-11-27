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


_FAILOVER_STATUS = {408, 429, 500, 502, 503, 504}


class _AITarget:
    def __init__(self, role: str, base_url: str, api_key: str, model: str):
        self.role = role
        self.base_url = base_url
        self.api_key = api_key
        self.model = model


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

    def _complete(self, target: _AITarget, system: str, user: str) -> str:
        client = OpenAI(
            api_key=target.api_key,
            base_url=target.base_url,
            timeout=self.settings.ai_timeout_seconds,
        )
        try:
            resp = client.chat.completions.create(
                model=target.model,
                temperature=0.2,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                response_format={"type": "json_object"},
            )
        except (APITimeoutError, APIConnectionError, TimeoutError, ConnectionError) as exc:
            raise _TransportFailure(str(exc)) from exc
        except APIStatusError as exc:
            if exc.status_code in _FAILOVER_STATUS:
                raise _TransportFailure(str(exc)) from exc
            raise AIProviderError(
                "AI_PROVIDER_ERROR",
                "AI provider rejected the request.",
                details={"provider": target.role, "status": exc.status_code},
            ) from exc
        return resp.choices[0].message.content or ""

    def _chat_json(self, system: str, user: str) -> tuple[dict[str, Any], str]:
        targets = self._targets()
        if not targets:
            raise AIProviderError(
                "AI_UNAVAILABLE",
                "AI is disabled or credentials/model are not configured.",
            )
        last_transport: _TransportFailure | None = None
        for target in targets:
            try:
                content = self._complete(target, system, user)
                return self._parse_json(content), target.model
            except _TransportFailure as exc:
                last_transport = exc
                logger.warning("AI %s provider failed: %s", target.role, exc)
                continue
            except json.JSONDecodeError as exc:
                raise AIProviderError(
                    "AI_INVALID_OUTPUT",
                    "AI returned malformed JSON.",
                    details={"provider": target.role},
                ) from exc
        raise AIProviderError(
            "AI_PROVIDER_ERROR",
            "AI provider request failed.",
            details={"reason": str(last_transport)},
        )

    def _parse_json(self, content: str) -> dict[str, Any]:
        text = content.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
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
