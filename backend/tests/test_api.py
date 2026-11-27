"""API integration tests with fixtures (no live market/AI required)."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pandas as pd


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    data = r.json()
    assert data["database"] is True
    assert data["ai_configured"] is False
    assert "version" in data


def test_instruments(client):
    r = client.get("/api/instruments")
    assert r.status_code == 200
    symbols = {i["symbol"] for i in r.json()}
    assert "RELIANCE.NS" in symbols
    assert "^NSEI" in symbols
    nifty = next(i for i in r.json() if i["symbol"] == "^NSEI")
    assert nifty["is_tradable"] is False


def test_strategy_create_and_version(client):
    body = {
        "name": "My SMA",
        "description": "test",
        "dsl": {
            "schema_version": 1,
            "name": "My SMA",
            "strategy_type": "sma_crossover",
            "parameters": {"fast_period": 20, "slow_period": 50},
            "position_type": "long_only",
        },
    }
    r = client.post("/api/strategies", json=body)
    assert r.status_code == 201
    sid = r.json()["id"]
    assert r.json()["latest_version"]["version_number"] == 1

    r2 = client.post(
        f"/api/strategies/{sid}/versions",
        json={
            "dsl": {
                "schema_version": 1,
                "name": "My SMA",
                "strategy_type": "sma_crossover",
                "parameters": {"fast_period": 10, "slow_period": 40},
                "position_type": "long_only",
            }
        },
    )
    assert r2.status_code == 201
    assert r2.json()["version_number"] == 2


def test_strategy_validation_failure(client):
    r = client.post(
        "/api/strategies",
        json={
            "name": "Bad",
            "dsl": {
                "schema_version": 1,
                "name": "Bad",
                "strategy_type": "sma_crossover",
                "parameters": {"fast_period": 50, "slow_period": 20},
                "position_type": "long_only",
            },
        },
    )
    assert r.status_code == 422


def test_index_not_tradable(client):
    # Create strategy first
    s = client.post(
        "/api/strategies",
        json={
            "name": "EMA",
            "dsl": {
                "schema_version": 1,
                "name": "EMA",
                "strategy_type": "ema_crossover",
                "parameters": {"fast_period": 5, "slow_period": 10},
                "position_type": "long_only",
            },
        },
    ).json()
    vid = s["latest_version"]["id"]
    r = client.post(
        "/api/backtests",
        json={
            "strategy_version_id": vid,
            "symbol": "^NSEI",
            "start_date": "2023-01-01",
            "end_date": "2023-12-31",
            "initial_capital": 100000,
        },
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INSTRUMENT_NOT_TRADABLE"


def test_backtest_with_mocked_market_data(client):
    s = client.post(
        "/api/strategies",
        json={
            "name": "SMA",
            "dsl": {
                "schema_version": 1,
                "name": "SMA",
                "strategy_type": "sma_crossover",
                "parameters": {"fast_period": 2, "slow_period": 3},
                "position_type": "long_only",
            },
        },
    ).json()
    vid = s["latest_version"]["id"]

    dates = pd.date_range("2024-01-01", periods=40, freq="D")
    close = [100 + (i % 11) - 5 for i in range(40)]
    df = pd.DataFrame(
        {
            "date": dates,
            "open": close,
            "high": [c + 1 for c in close],
            "low": [c - 1 for c in close],
            "close": close,
            "volume": 1000,
        }
    )

    from types import SimpleNamespace

    fake = SimpleNamespace(
        df=df,
        source="test",
        price_adjustment="auto_adjust=True",
        cache_status="fresh",
        retrieved_at="2024-01-01T00:00:00Z",
        fingerprint="abc",
        warnings=[],
        metadata={"symbol": "RELIANCE.NS"},
    )

    with patch(
        "app.routes.backtests.MarketDataService.get_history",
        return_value=fake,
    ):
        r = client.post(
            "/api/backtests",
            json={
                "strategy_version_id": vid,
                "symbol": "RELIANCE.NS",
                "start_date": "2024-01-01",
                "end_date": "2024-02-05",
                "initial_capital": 100000,
                "allocation_percent": 100,
                "transaction_cost_percent": 0.1,
                "slippage_percent": 0.05,
            },
        )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "completed"
    assert body["metrics"] is not None
    assert "total_return_percent" in body["metrics"]

    # Persistence
    rid = body["id"]
    g = client.get(f"/api/backtests/{rid}")
    assert g.status_code == 200
    assert g.json()["id"] == rid


def test_ai_generate_when_disabled(client):
    r = client.post(
        "/api/ai/generate-strategy",
        json={"prompt": "Create a 20/50 EMA crossover strategy"},
    )
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "AI_UNAVAILABLE"
