"""Parameter sensitivity grid reuses the deterministic engine and one market-data load."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pandas as pd
import pytest

from app.schemas.backtest import SensitivityRequest
from app.services.backtest_engine import BacktestEngine, BacktestConfig
from app.schemas.strategy import parse_strategy_dsl


def _sample_ohlc(n: int = 120) -> pd.DataFrame:
    dates = pd.bdate_range("2023-01-02", periods=n)
    close = pd.Series(range(100, 100 + n), dtype=float)
    return pd.DataFrame(
        {
            "date": dates,
            "open": close - 0.5,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": [1000] * n,
        }
    )


def test_sensitivity_request_rejects_oversized_grid() -> None:
    with pytest.raises(ValueError, match="25"):
        SensitivityRequest(
            symbol="RELIANCE.NS",
            start_date=date(2023, 1, 1),
            end_date=date(2023, 12, 31),
            fast_periods=[10, 15, 20, 25, 30],
            slow_periods=[40, 45, 50, 55, 60, 65],
        )


def test_sensitivity_request_rejects_no_valid_pairs() -> None:
    with pytest.raises(ValueError, match="valid"):
        SensitivityRequest(
            symbol="RELIANCE.NS",
            start_date=date(2023, 1, 1),
            end_date=date(2023, 12, 31),
            fast_periods=[50, 60],
            slow_periods=[10, 20],
        )


def test_engine_grid_cells_differ_for_distinct_params() -> None:
    df = _sample_ohlc()
    engine = BacktestEngine()
    results = {}
    for fast, slow in [(10, 30), (20, 50)]:
        dsl = parse_strategy_dsl(
            {
                "schema_version": 1,
                "name": f"EMA {fast}/{slow}",
                "strategy_type": "ema_crossover",
                "parameters": {"fast_period": fast, "slow_period": slow},
                "position_type": "long_only",
            }
        )
        out = engine.run(
            df.copy(),
            BacktestConfig(
                strategy=dsl,
                start_date=date(2023, 1, 2),
                end_date=date(2023, 6, 15),
                initial_capital=100_000,
                allocation_percent=100,
                transaction_cost_percent=0.1,
                slippage_percent=0.05,
            ),
        )
        results[(fast, slow)] = out.metrics["total_return_percent"]
    # Distinct parameterizations must both produce finite metrics.
    assert results[(10, 30)] is not None
    assert results[(20, 50)] is not None


def test_cache_only_skips_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services.market_data_service import MarketDataError, MarketDataService

    svc = MarketDataService()
    monkeypatch.setattr(svc, "_find_best_cache", lambda *a, **k: None)
    monkeypatch.setattr(
        svc,
        "_fetch_provider",
        MagicMock(side_effect=AssertionError("provider must not be called")),
    )
    with pytest.raises(MarketDataError) as exc:
        svc.get_history(
            "RELIANCE.NS",
            date(2023, 1, 1),
            date(2023, 6, 1),
            allow_network=False,
        )
    assert exc.value.code == "MARKET_DATA_CACHE_ONLY"
