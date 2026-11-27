"""Strategy DSL validation tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.strategy import parse_strategy_dsl


def test_valid_sma():
    dsl = parse_strategy_dsl(
        {
            "schema_version": 1,
            "name": "SMA Crossover",
            "strategy_type": "sma_crossover",
            "parameters": {"fast_period": 20, "slow_period": 50},
            "position_type": "long_only",
        }
    )
    assert dsl.strategy_type == "sma_crossover"


def test_valid_ema():
    dsl = parse_strategy_dsl(
        {
            "schema_version": 1,
            "name": "EMA",
            "strategy_type": "ema_crossover",
            "parameters": {"fast_period": 10, "slow_period": 30},
            "position_type": "long_only",
        }
    )
    assert dsl.parameters.fast_period == 10


def test_valid_rsi():
    dsl = parse_strategy_dsl(
        {
            "schema_version": 1,
            "name": "RSI",
            "strategy_type": "rsi_mean_reversion",
            "parameters": {"period": 14, "lower": 30, "upper": 70},
            "position_type": "long_only",
        }
    )
    assert dsl.parameters.lower == 30


def test_fast_ge_slow_rejected():
    with pytest.raises((ValidationError, ValueError)):
        parse_strategy_dsl(
            {
                "schema_version": 1,
                "name": "Bad",
                "strategy_type": "sma_crossover",
                "parameters": {"fast_period": 50, "slow_period": 20},
                "position_type": "long_only",
            }
        )


def test_negative_period_rejected():
    with pytest.raises((ValidationError, ValueError)):
        parse_strategy_dsl(
            {
                "schema_version": 1,
                "name": "Bad",
                "strategy_type": "ema_crossover",
                "parameters": {"fast_period": -1, "slow_period": 20},
                "position_type": "long_only",
            }
        )


def test_invalid_rsi_thresholds():
    with pytest.raises((ValidationError, ValueError)):
        parse_strategy_dsl(
            {
                "schema_version": 1,
                "name": "Bad",
                "strategy_type": "rsi_mean_reversion",
                "parameters": {"period": 14, "lower": 70, "upper": 30},
                "position_type": "long_only",
            }
        )


def test_unknown_strategy_type():
    with pytest.raises(ValueError):
        parse_strategy_dsl(
            {
                "schema_version": 1,
                "name": "Bad",
                "strategy_type": "macd_magic",
                "parameters": {},
                "position_type": "long_only",
            }
        )


def test_unsupported_extra_fields():
    with pytest.raises((ValidationError, ValueError)):
        parse_strategy_dsl(
            {
                "schema_version": 1,
                "name": "Bad",
                "strategy_type": "sma_crossover",
                "parameters": {"fast_period": 20, "slow_period": 50, "macd": True},
                "position_type": "long_only",
            }
        )
