"""Deterministic long-only daily backtesting engine.

Execution policy (mandatory)
----------------------------
1. After each daily close, evaluate indicators and generate a signal.
2. That signal executes at the *next* trading day's open (slippage applied).
3. Warm-up bars before `start_date` never create trades or equity history.
4. Signals on the final bar of the requested window do not execute outside it.

Percent conventions
-------------------
User-facing percentages (e.g. 0.10 for 0.10%) are converted to fractions
internally: fraction = percent / 100.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

import numpy as np
import pandas as pd

from app.schemas.strategy import (
    EMACrossoverStrategy,
    RSIMeanReversionStrategy,
    SMACrossoverStrategy,
    parse_strategy_dsl,
)
from app.services.indicators import ema, rsi, sma
from app.services.performance_metrics import (
    compute_drawdown_curve,
    compute_metrics,
    safe_float,
)


SignalSide = Literal["buy", "sell"]


@dataclass
class PendingSignal:
    side: SignalSide
    signal_date: date


@dataclass
class OpenPosition:
    entry_signal_date: date
    entry_date: date
    quantity: int
    entry_price: float
    entry_fee: float


@dataclass
class ClosedTrade:
    entry_signal_date: date
    entry_date: date
    exit_signal_date: date
    exit_date: date
    entry_price: float
    exit_price: float
    quantity: int
    entry_fee: float
    exit_fee: float

    @property
    def total_cost(self) -> float:
        return self.entry_fee + self.exit_fee

    @property
    def profit_loss(self) -> float:
        return (
            self.quantity * self.exit_price
            - self.exit_fee
            - (self.quantity * self.entry_price + self.entry_fee)
        )

    @property
    def return_percent(self) -> float:
        cost_basis = self.quantity * self.entry_price + self.entry_fee
        if cost_basis == 0:
            return 0.0
        return self.profit_loss / cost_basis * 100.0


@dataclass
class BacktestConfig:
    strategy: SMACrossoverStrategy | EMACrossoverStrategy | RSIMeanReversionStrategy
    start_date: date
    end_date: date
    initial_capital: float
    allocation_percent: float = 100.0
    transaction_cost_percent: float = 0.10
    slippage_percent: float = 0.05

    @property
    def transaction_cost_fraction(self) -> float:
        return self.transaction_cost_percent / 100.0

    @property
    def slippage_fraction(self) -> float:
        return self.slippage_percent / 100.0

    @property
    def allocation_fraction(self) -> float:
        return self.allocation_percent / 100.0


@dataclass
class BacktestResult:
    status: str
    metrics: dict[str, Any]
    equity_curve: list[dict[str, float | str]]
    drawdown_curve: list[dict[str, float | str]]
    benchmark_curve: list[dict[str, float | str]]
    trades: list[dict[str, Any]]
    open_position: dict[str, Any] | None
    trade_markers: list[dict[str, Any]]
    chart_data: list[dict[str, Any]]
    warnings: list[str] = field(default_factory=list)
    data_metadata: dict[str, Any] = field(default_factory=dict)


def _crossover_up(prev_fast: float, prev_slow: float, cur_fast: float, cur_slow: float) -> bool:
    return prev_fast <= prev_slow and cur_fast > cur_slow


def _crossover_down(prev_fast: float, prev_slow: float, cur_fast: float, cur_slow: float) -> bool:
    return prev_fast >= prev_slow and cur_fast < cur_slow


def _finite(*vals: float | None) -> bool:
    for v in vals:
        if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))):
            return False
    return True


class BacktestEngine:
    """Standalone engine: accepts a DataFrame and validated strategy config."""

    def run(self, df: pd.DataFrame, config: BacktestConfig) -> BacktestResult:
        warnings: list[str] = []
        data = self._prepare_frame(df)
        indicators = self._compute_indicators(data, config.strategy)

        cash = float(config.initial_capital)
        position: OpenPosition | None = None
        pending: PendingSignal | None = None
        trades: list[ClosedTrade] = []
        markers: list[dict[str, Any]] = []
        equity_dates: list[date] = []
        equity_values: list[float] = []
        skipped_signals = 0

        # Iterate all rows (including warm-up) so indicators are correct;
        # only record equity / allow trades inside [start_date, end_date].
        for i in range(len(data)):
            row = data.iloc[i]
            d: date = row["date"].date() if hasattr(row["date"], "date") else row["date"]
            in_window = config.start_date <= d <= config.end_date

            # 1) Execute pending signal at today's open (only inside window)
            if pending is not None and in_window:
                cash, position, new_trade, marker, skip = self._execute_pending(
                    pending=pending,
                    open_price=float(row["open"]),
                    cash=cash,
                    position=position,
                    config=config,
                    exec_date=d,
                )
                if skip:
                    skipped_signals += 1
                if new_trade is not None:
                    trades.append(new_trade)
                if marker is not None:
                    markers.append(marker)
                pending = None

            # 2–3) Value portfolio at close (only inside window)
            if in_window:
                qty = position.quantity if position else 0
                equity = cash + qty * float(row["close"])
                equity_dates.append(d)
                equity_values.append(equity)

            # 4) Evaluate signal at close (warm-up allowed for indicator state;
            #    only schedule if current bar is inside window and not final
            #    bar of available data beyond which we cannot execute)
            if not in_window:
                continue

            # Do not schedule a signal that cannot execute next day inside window
            if i >= len(data) - 1:
                # Final available bar — signal would need a next day that may not exist
                # Also: if next calendar trading day would be after end_date, skip.
                continue

            next_d = data.iloc[i + 1]["date"]
            next_date = next_d.date() if hasattr(next_d, "date") else next_d
            if next_date > config.end_date:
                continue

            signal = self._evaluate_signal(indicators, i, config.strategy, position)
            if signal is not None:
                pending = PendingSignal(side=signal, signal_date=d)

        if skipped_signals:
            warnings.append(
                f"{skipped_signals} entry signal(s) skipped (insufficient cash / sizing)."
            )

        equity_series = pd.Series(equity_values, index=pd.to_datetime(equity_dates))
        if equity_series.empty:
            # No bars in window — still return a completed zero-activity result
            equity_series = pd.Series(
                [config.initial_capital],
                index=pd.to_datetime([config.start_date]),
            )
            warnings.append("No trading days in the selected window; equity held flat.")

        dd = compute_drawdown_curve(equity_series)

        open_pos_out = None
        if position is not None:
            mark = float(data.iloc[-1]["close"])
            # Prefer last in-window close
            in_win = data[
                (data["date"].dt.date >= config.start_date)
                & (data["date"].dt.date <= config.end_date)
            ]
            if not in_win.empty:
                mark = float(in_win.iloc[-1]["close"])
            open_pos_out = {
                "entry_signal_date": position.entry_signal_date.isoformat(),
                "entry_date": position.entry_date.isoformat(),
                "quantity": position.quantity,
                "entry_price": position.entry_price,
                "mark_price": mark,
                "market_value": position.quantity * mark,
                "unrealized_pnl": position.quantity * mark
                - (position.quantity * position.entry_price + position.entry_fee),
                "note": (
                    "Marked to final close; hypothetical future exit fees are not deducted."
                ),
            }
            warnings.append(
                "An open position remains at backtest end (not force-closed)."
            )

        # Benchmark: buy at first in-window open with same costs/sizing, mark to end
        benchmark_curve, bh_return = self._buy_and_hold_benchmark(
            data, config, equity_dates
        )

        trade_pnls = [t.profit_loss for t in trades]
        metrics = compute_metrics(
            initial_capital=config.initial_capital,
            equity_curve=equity_series,
            trade_pnls=trade_pnls,
            buy_and_hold_return_percent=bh_return,
        )

        chart_data = []
        in_win = data[
            (data["date"].dt.date >= config.start_date)
            & (data["date"].dt.date <= config.end_date)
        ]
        for _, r in in_win.iterrows():
            chart_data.append(
                {
                    "date": r["date"].date().isoformat(),
                    "open": float(r["open"]),
                    "high": float(r["high"]),
                    "low": float(r["low"]),
                    "close": float(r["close"]),
                    "volume": None if pd.isna(r.get("volume")) else float(r["volume"]),
                }
            )

        return BacktestResult(
            status="completed",
            metrics=metrics,
            equity_curve=[
                {"date": d.date().isoformat() if hasattr(d, "date") else str(d)[:10], "value": float(v)}
                for d, v in equity_series.items()
            ],
            drawdown_curve=[
                {
                    "date": d.date().isoformat() if hasattr(d, "date") else str(d)[:10],
                    "value": float(v) * 100.0,  # percent, negative
                }
                for d, v in dd.items()
            ],
            benchmark_curve=benchmark_curve,
            trades=[
                {
                    "entry_signal_date": t.entry_signal_date.isoformat(),
                    "entry_date": t.entry_date.isoformat(),
                    "exit_signal_date": t.exit_signal_date.isoformat(),
                    "exit_date": t.exit_date.isoformat(),
                    "entry_price": t.entry_price,
                    "exit_price": t.exit_price,
                    "quantity": t.quantity,
                    "entry_fee": t.entry_fee,
                    "exit_fee": t.exit_fee,
                    "total_cost": t.total_cost,
                    "profit_loss": t.profit_loss,
                    "return_percent": t.return_percent,
                }
                for t in trades
            ],
            open_position=open_pos_out,
            trade_markers=markers,
            chart_data=chart_data,
            warnings=warnings,
        )

    def _prepare_frame(self, df: pd.DataFrame) -> pd.DataFrame:
        data = df.copy()
        if "date" not in data.columns:
            raise ValueError("DataFrame must include a 'date' column")
        data["date"] = pd.to_datetime(data["date"]).dt.tz_localize(None).dt.normalize()
        for col in ["open", "high", "low", "close"]:
            data[col] = pd.to_numeric(data[col], errors="coerce")
        data = data.sort_values("date").drop_duplicates("date").reset_index(drop=True)
        if data[["open", "high", "low", "close"]].isna().any().any():
            raise ValueError("OHLC contains NaN values")
        return data

    def _compute_indicators(
        self,
        data: pd.DataFrame,
        strategy: SMACrossoverStrategy | EMACrossoverStrategy | RSIMeanReversionStrategy,
    ) -> dict[str, pd.Series]:
        close = data["close"]
        if strategy.strategy_type == "sma_crossover":
            return {
                "fast": sma(close, strategy.parameters.fast_period),
                "slow": sma(close, strategy.parameters.slow_period),
            }
        if strategy.strategy_type == "ema_crossover":
            return {
                "fast": ema(close, strategy.parameters.fast_period),
                "slow": ema(close, strategy.parameters.slow_period),
            }
        return {
            "rsi": rsi(close, strategy.parameters.period),
        }

    def _evaluate_signal(
        self,
        indicators: dict[str, pd.Series],
        i: int,
        strategy: SMACrossoverStrategy | EMACrossoverStrategy | RSIMeanReversionStrategy,
        position: OpenPosition | None,
    ) -> SignalSide | None:
        if i < 1:
            return None

        if strategy.strategy_type in ("sma_crossover", "ema_crossover"):
            pf, ps = indicators["fast"].iloc[i - 1], indicators["slow"].iloc[i - 1]
            cf, cs = indicators["fast"].iloc[i], indicators["slow"].iloc[i]
            if not _finite(pf, ps, cf, cs):
                return None
            if position is None and _crossover_up(float(pf), float(ps), float(cf), float(cs)):
                return "buy"
            if position is not None and _crossover_down(
                float(pf), float(ps), float(cf), float(cs)
            ):
                return "sell"
            return None

        # RSI mean reversion
        prev = indicators["rsi"].iloc[i - 1]
        cur = indicators["rsi"].iloc[i]
        if not _finite(prev, cur):
            return None
        lower = float(strategy.parameters.lower)  # type: ignore[union-attr]
        upper = float(strategy.parameters.upper)  # type: ignore[union-attr]
        if position is None and float(prev) >= lower and float(cur) < lower:
            return "buy"
        if position is not None and float(prev) <= upper and float(cur) > upper:
            return "sell"
        return None

    def _execute_pending(
        self,
        *,
        pending: PendingSignal,
        open_price: float,
        cash: float,
        position: OpenPosition | None,
        config: BacktestConfig,
        exec_date: date,
    ) -> tuple[float, OpenPosition | None, ClosedTrade | None, dict | None, bool]:
        slip = config.slippage_fraction
        fee_frac = config.transaction_cost_fraction
        skipped = False
        trade = None
        marker = None

        if pending.side == "buy":
            if position is not None:
                return cash, position, None, None, False
            exec_price = open_price * (1.0 + slip)
            # Max capital allocatable
            budget = min(cash, config.initial_capital * config.allocation_fraction)
            # quantity such that qty*price*(1+fee) <= budget
            if exec_price <= 0:
                return cash, position, None, None, True
            max_qty = int(budget // (exec_price * (1.0 + fee_frac)))
            # Also ensure remaining cash after purchase is non-negative
            while max_qty > 0:
                purchase = max_qty * exec_price
                fee = purchase * fee_frac
                if purchase + fee <= cash + 1e-9 and purchase + fee <= budget + 1e-9:
                    break
                max_qty -= 1
            if max_qty <= 0:
                return cash, position, None, None, True

            purchase = max_qty * exec_price
            fee = purchase * fee_frac
            cash = cash - purchase - fee
            position = OpenPosition(
                entry_signal_date=pending.signal_date,
                entry_date=exec_date,
                quantity=max_qty,
                entry_price=exec_price,
                entry_fee=fee,
            )
            marker = {
                "date": exec_date.isoformat(),
                "price": exec_price,
                "side": "buy",
                "quantity": max_qty,
            }
            return cash, position, None, marker, False

        # sell
        if position is None:
            return cash, position, None, None, False

        exec_price = open_price * (1.0 - slip)
        sale = position.quantity * exec_price
        fee = sale * fee_frac
        cash = cash + sale - fee
        trade = ClosedTrade(
            entry_signal_date=position.entry_signal_date,
            entry_date=position.entry_date,
            exit_signal_date=pending.signal_date,
            exit_date=exec_date,
            entry_price=position.entry_price,
            exit_price=exec_price,
            quantity=position.quantity,
            entry_fee=position.entry_fee,
            exit_fee=fee,
        )
        marker = {
            "date": exec_date.isoformat(),
            "price": exec_price,
            "side": "sell",
            "quantity": position.quantity,
        }
        return cash, None, trade, marker, False

    def _buy_and_hold_benchmark(
        self,
        data: pd.DataFrame,
        config: BacktestConfig,
        equity_dates: list[date],
    ) -> tuple[list[dict[str, Any]], float | None]:
        """Buy on first in-window open with same costs; mark to market; never sell."""
        in_win = data[
            (data["date"].dt.date >= config.start_date)
            & (data["date"].dt.date <= config.end_date)
        ]
        if in_win.empty:
            return [], None

        first = in_win.iloc[0]
        last = in_win.iloc[-1]
        open_price = float(first["open"])
        slip = config.slippage_fraction
        fee_frac = config.transaction_cost_fraction
        exec_price = open_price * (1.0 + slip)
        budget = config.initial_capital * config.allocation_fraction
        if exec_price <= 0:
            return [], None
        qty = int(budget // (exec_price * (1.0 + fee_frac)))
        while qty > 0:
            purchase = qty * exec_price
            fee = purchase * fee_frac
            if purchase + fee <= config.initial_capital + 1e-9:
                break
            qty -= 1
        if qty <= 0:
            return [], None

        purchase = qty * exec_price
        fee = purchase * fee_frac
        cash = config.initial_capital - purchase - fee

        curve = []
        for _, r in in_win.iterrows():
            d = r["date"].date().isoformat()
            eq = cash + qty * float(r["close"])
            curve.append({"date": d, "value": float(eq)})

        final_eq = cash + qty * float(last["close"])
        bh_return = (final_eq / config.initial_capital - 1.0) * 100.0
        return curve, safe_float(bh_return)


def run_backtest_from_dsl(
    df: pd.DataFrame,
    dsl: dict,
    *,
    start_date: date,
    end_date: date,
    initial_capital: float = 100_000,
    allocation_percent: float = 100,
    transaction_cost_percent: float = 0.10,
    slippage_percent: float = 0.05,
) -> BacktestResult:
    strategy = parse_strategy_dsl(dsl)
    config = BacktestConfig(
        strategy=strategy,
        start_date=start_date,
        end_date=end_date,
        initial_capital=initial_capital,
        allocation_percent=allocation_percent,
        transaction_cost_percent=transaction_cost_percent,
        slippage_percent=slippage_percent,
    )
    return BacktestEngine().run(df, config)
