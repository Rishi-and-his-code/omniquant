"""OmniRoute is tried first. OpenRouter runs only after a transport failure."""

from __future__ import annotations

import json

import pytest

from app.config import Settings
from app.services.ai_provider import AIModelProvider, AIProviderError, _TransportFailure

EMA = {
    "schema_version": 1,
    "name": "EMA Crossover",
    "strategy_type": "ema_crossover",
    "parameters": {"fast_period": 20, "slow_period": 50},
    "position_type": "long_only",
}


def _settings() -> Settings:
    return Settings(
        data_dir="/tmp/omniquant-ai-test",
        database_url="sqlite:////tmp/omniquant-ai-test.db",
        ai_enabled=True,
        ai_base_url="http://127.0.0.1:20128/v1",
        ai_api_key="primary-secret",
        ai_model="omniroute-model",
        ai_fallback_base_url="https://openrouter.ai/api/v1",
        ai_fallback_api_key="fallback-secret",
        ai_fallback_model="openrouter-model",
    )


def _install(monkeypatch: pytest.MonkeyPatch, responder) -> list[str]:
    calls: list[str] = []

    def fake(self, target, system, user):
        calls.append(target.role)
        return responder(target)

    monkeypatch.setattr(AIModelProvider, "_complete", fake)
    return calls


def test_primary_success_does_not_call_openrouter(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _install(
        monkeypatch,
        lambda target: json.dumps({"status": "ok", "dsl": EMA, "message": None}),
    )

    result = AIModelProvider(_settings()).generate_strategy("Create an EMA crossover 20 and 50")

    assert calls == ["primary"]
    assert result["status"] == "ok"
    assert result["model_name"] == "omniroute-model"
    assert result["dsl"]["parameters"]["fast_period"] == 20


def test_timeout_uses_openrouter_once(monkeypatch: pytest.MonkeyPatch) -> None:
    def responder(target):
        if target.role == "primary":
            raise _TransportFailure("timed out")
        return json.dumps({"status": "ok", "dsl": EMA, "message": None})

    calls = _install(monkeypatch, responder)
    result = AIModelProvider(_settings()).generate_strategy("Create an EMA crossover 20 and 50")

    assert calls == ["primary", "fallback"]
    assert result["model_name"] == "openrouter-model"


def test_unsupported_answer_does_not_fall_back(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _install(
        monkeypatch,
        lambda target: json.dumps(
            {"status": "unsupported", "dsl": None, "message": "MACD is not supported."}
        ),
    )

    result = AIModelProvider(_settings()).generate_strategy("Add MACD confirmation")

    assert calls == ["primary"]
    assert result["status"] == "unsupported"


def test_malformed_json_does_not_fall_back(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _install(monkeypatch, lambda target: "not-json")

    with pytest.raises(AIProviderError) as exc:
        AIModelProvider(_settings()).generate_strategy("Create an EMA crossover")

    assert exc.value.code == "AI_INVALID_OUTPUT"
    assert calls == ["primary"]


def test_both_providers_down(monkeypatch: pytest.MonkeyPatch) -> None:
    def responder(target):
        raise _TransportFailure("down")

    calls = _install(monkeypatch, responder)

    with pytest.raises(AIProviderError) as exc:
        AIModelProvider(_settings()).generate_strategy("Create an EMA crossover")

    assert exc.value.code == "AI_PROVIDER_ERROR"
    assert calls == ["primary", "fallback"]


def test_disabled_provider_makes_no_call(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _install(monkeypatch, lambda target: "{}")
    settings = _settings()
    settings.ai_enabled = False

    with pytest.raises(AIProviderError) as exc:
        AIModelProvider(settings).generate_strategy("Create an EMA crossover")

    assert exc.value.code == "AI_UNAVAILABLE"
    assert calls == []


def test_configuration_report_hides_keys() -> None:
    report = AIModelProvider(_settings()).check_configuration()
    blob = json.dumps(report)
    assert "primary-secret" not in blob
    assert "fallback-secret" not in blob
    assert report["ai_configured"] is True
    assert report["ai_fallback_configured"] is True
