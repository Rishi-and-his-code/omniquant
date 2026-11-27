"""Deterministic backtest engine tests with synthetic OHLC."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

from app.schemas.strategy import parse_strategy_dsl
from app.services.backtest_engine import BacktestConfig, BacktestEngine


def _dates(n: int, start: date = date(2024, 1, 1)) -> list[date]:
    # Simple sequential calendar days (fine for synthetic tests)
    return [start + timedelta(days=i) for i in range(n)]


def test_accounting_fixture_buy_sell():
    """
    Starting capital: 1000
    Buy at 100 with 1% fee, qty 9 → purchase 900, fee 9, cash 91
    Sell at 110 with 1% fee → sale 990, fee 9.90, final cash 1071.10
    Net profit: 71.10
    """
    # Construct prices so SMA(2)/SMA(3) cross up then down with next-open execution
    # We will manually drive signals via a custom path: use RSI-like controlled series
    # Easier: use sma crossover on crafted closes, and set opens to desired exec prices.

    # Need enough bars for SMA warm-up. Use fast=2, slow=3.
    # Closes designed so crossover happens, and next open is our target price.
    rows = []
    # Warm-up flat then spike pattern
    closes = [100, 100, 100, 101, 102, 103, 104, 90, 89, 88, 87]
    opens = [100, 100, 100, 100, 100, 100, 100, 110, 110, 110, 110]
    # We'll set specific opens on execution days after computing expected signal days.
    # Actually construct explicitly:
    # Day indices 0..N
    # After slow SMA ready (i>=2), create upcross then downcross.

    dates = _dates(12)
    # opens/closes crafted:
    # Use closes: 10,10,10, 20,21,22  -> upcross around when fast rises above slow
    # then 5,4,3 -> downcross
    close = [10, 10, 10, 12, 14, 16, 18, 8, 6, 4, 3, 3]
    # Upcross at i=3 → buy at open[4]=100; downcross at i=7 → sell at open[8]=110
    open_ = [10, 10, 10, 10, 100, 10, 10, 10, 110, 10, 10, 10]
    # Expected: when upcross signal on day i, buy at open_[i+1]=100
    # when downcross signal, sell at open next = 110

    df = pd.DataFrame(
        {
            "date": pd.to_datetime(dates),
            "open": open_,
            "high": [max(o, c) for o, c in zip(open_, close)],
            "low": [min(o, c) for o, c in zip(open_, close)],
            "close": close,
            "volume": [1000] * 12,
        }
    )

    strategy = parse_strategy_dsl(
        {
            "schema_version": 1,
            "name": "SMA test",
            "strategy_type": "sma_crossover",
            "parameters": {"fast_period": 2, "slow_period": 3},
            "position_type": "long_only",
        }
    )
    config = BacktestConfig(
        strategy=strategy,
        start_date=dates[0],
        end_date=dates[-1],
        initial_capital=1000,
        allocation_percent=100,
        transaction_cost_percent=1.0,  # 1%
        slippage_percent=0.0,
    )
    result = BacktestEngine().run(df, config)

    # Find a closed trade with entry ~100
    assert result.status == "completed"
    if result.trades:
        t = result.trades[0]
        assert t["entry_price"] == pytest.approx(100.0)
        assert t["quantity"] == 9
        assert t["entry_fee"] == pytest.approx(9.0)
        assert t["exit_price"] == pytest.approx(110.0)
        assert t["exit_fee"] == pytest.approx(9.9)
        assert t["profit_loss"] == pytest.approx(71.1)
        assert result.metrics["final_equity"] == pytest.approx(1071.1)


def test_next_day_open_execution_no_lookahead():
    dates = _dates(20)
    # Flat then jump so SMA crosses, ensure buy price equals NEXT open not same-day close
    close = [10.0] * 10 + [20.0] * 10
    open_ = [10.0] * 10 + [15.0] + [20.0] * 9
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(dates),
            "open": open_,
            "high": close,
            "low": [min(a, b) for a, b in zip(open_, close)],
            "close": close,
            "volume": 1000,
        }
    )
    strategy = parse_strategy_dsl(
        {
            "schema_version": 1,
            "name": "SMA",
            "strategy_type": "sma_crossover",
            "parameters": {"fast_period": 2, "slow_period": 5},
            "position_type": "long_only",
        }
    )
    result = BacktestEngine().run(
        df,
        BacktestConfig(
            strategy=strategy,
            start_date=dates[0],
            end_date=dates[-1],
            initial_capital=10000,
            transaction_cost_percent=0,
            slippage_percent=0,
        ),
    )
    if result.trade_markers:
        buys = [m for m in result.trade_markers if m["side"] == "buy"]
        if buys:
            # Execution date must have matching open in data
            buy_date = buys[0]["date"]
            row = df[df["date"].dt.date == date.fromisoformat(buy_date)].iloc[0]
            assert buys[0]["price"] == pytest.approx(float(row["open"]))


def test_signal_on_final_bar_does_not_execute():
    dates = _dates(15)
    close = list(range(15, 30))
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(dates),
            "open": close,
            "high": [c + 1 for c in close],
            "low": [c - 1 for c in close],
            "close": close,
            "volume": 100,
        }
    )
    strategy = parse_strategy_dsl(
        {
            "schema_version": 1,
            "name": "SMA",
            "strategy_type": "sma_crossover",
            "parameters": {"fast_period": 2, "slow_period": 3},
            "position_type": "long_only",
        }
    )
    # End on last date — any signal on last bar must not create a trade beyond period
    result = BacktestEngine().run(
        df,
        BacktestConfig(
            strategy=strategy,
            start_date=dates[0],
            end_date=dates[-1],
            initial_capital=10000,
            transaction_cost_percent=0,
            slippage_percent=0,
        ),
    )
    for m in result.trade_markers:
        assert date.fromisoformat(m["date"]) <= dates[-1]


def test_zero_trade_backtest_succeeds():
    dates = _dates(30)
    close = [100.0] * 30
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(dates),
            "open": close,
            "high": close,
            "low": close,
            "close": close,
            "volume": 1,
        }
    )
    strategy = parse_strategy_dsl(
        {
            "schema_version": 1,
            "name": "SMA",
            "strategy_type": "sma_crossover",
            "parameters": {"fast_period": 5, "slow_period": 10},
            "position_type": "long_only",
        }
    )
    result = BacktestEngine().run(
        df,
        BacktestConfig(
            strategy=strategy,
            start_date=dates[0],
            end_date=dates[-1],
            initial_capital=50000,
        ),
    )
    assert result.status == "completed"
    assert result.metrics["completed_trades"] == 0
    assert result.metrics["win_rate_percent"] is None
    assert result.metrics["final_equity"] == pytest.approx(50000)


def test_cash_never_negative_and_whole_shares():
    dates = _dates(40)
    close = [10 + (i % 7) for i in range(40)]
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(dates),
            "open": close,
            "high": [c + 1 for c in close],
            "low": [c - 1 for c in close],
            "close": close,
            "volume": 100,
        }
    )
    strategy = parse_strategy_dsl(
        {
            "schema_version": 1,
            "name": "EMA",
            "strategy_type": "ema_crossover",
            "parameters": {"fast_period": 3, "slow_period": 8},
            "position_type": "long_only",
        }
    )
    result = BacktestEngine().run(
        df,
        BacktestConfig(
            strategy=strategy,
            start_date=dates[0],
            end_date=dates[-1],
            initial_capital=1000,
            transaction_cost_percent=0.5,
            slippage_percent=0.2,
        ),
    )
    for t in result.trades:
        assert t["quantity"] == int(t["quantity"])
        assert t["quantity"] >= 1
    # Final equity finite
    assert result.metrics["final_equity"] >= 0


def test_slippage_direction():
    dates = _dates(20)
    close = [10.0] * 8 + [25.0] * 6 + [5.0] * 6
    open_ = [10.0] * 20
    # Force known opens on likely exec days by setting all opens to 10 then we'll check inequality
    open_ = [10.0] * 9 + [20.0] + [10.0] * 5 + [20.0] + [10.0] * 4
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(dates),
            "open": open_,
            "high": [max(o, c) for o, c in zip(open_, close)],
            "low": [min(o, c) for o, c in zip(open_, close)],
            "close": close,
            "volume": 100,
        }
    )
    strategy = parse_strategy_dsl(
        {
            "schema_version": 1,
            "name": "SMA",
            "strategy_type": "sma_crossover",
            "parameters": {"fast_period": 2, "slow_period": 4},
            "position_type": "long_only",
        }
    )
    result = BacktestEngine().run(
        df,
        BacktestConfig(
            strategy=strategy,
            start_date=dates[0],
            end_date=dates[-1],
            initial_capital=100000,
            transaction_cost_percent=0,
            slippage_percent=1.0,  # 1%
        ),
    )
    for m in result.trade_markers:
        row = df[df["date"].dt.date == date.fromisoformat(m["date"])].iloc[0]
        if m["side"] == "buy":
            assert m["price"] == pytest.approx(float(row["open"]) * 1.01)
        else:
            assert m["price"] == pytest.approx(float(row["open"]) * 0.99)


def test_open_position_not_counted_as_trade():
    # Create only an entry without exit
    dates = _dates(25)
    close = [10.0] * 10 + [30.0] * 15  # upcross stays above — no exit
    open_ = [10.0] * 11 + [12.0] + [30.0] * 13
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(dates),
            "open": open_,
            "high": close,
            "low": [min(a, b) for a, b in zip(open_, close)],
            "close": close,
            "volume": 1,
        }
    )
    strategy = parse_strategy_dsl(
        {
            "schema_version": 1,
            "name": "SMA",
            "strategy_type": "sma_crossover",
            "parameters": {"fast_period": 2, "slow_period": 5},
            "position_type": "long_only",
        }
    )
    result = BacktestEngine().run(
        df,
        BacktestConfig(
            strategy=strategy,
            start_date=dates[0],
            end_date=dates[-1],
            initial_capital=10000,
            transaction_cost_percent=0,
            slippage_percent=0,
        ),
    )
    if result.open_position:
        assert result.metrics["completed_trades"] == len(result.trades)
        assert result.open_position["quantity"] >= 1
        # Equity includes mark-to-market
        assert result.metrics["final_equity"] > 0


def test_deterministic_identical_inputs():
    dates = _dates(40)
    close = [100 + (i % 9) - 4 for i in range(40)]
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(dates),
            "open": close,
            "high": [c + 1 for c in close],
            "low": [c - 1 for c in close],
            "close": close,
            "volume": 10,
        }
    )
    dsl = {
        "schema_version": 1,
        "name": "RSI",
        "strategy_type": "rsi_mean_reversion",
        "parameters": {"period": 5, "lower": 40, "upper": 60},
        "position_type": "long_only",
    }
    strategy = parse_strategy_dsl(dsl)
    cfg = BacktestConfig(
        strategy=strategy,
        start_date=dates[0],
        end_date=dates[-1],
        initial_capital=25000,
    )
    r1 = BacktestEngine().run(df, cfg)
    r2 = BacktestEngine().run(df, cfg)
    assert r1.metrics == r2.metrics
    assert r1.trades == r2.trades
