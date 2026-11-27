"""Financial performance metrics for backtest results."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def safe_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if np.isnan(f) or np.isinf(f):
        return None
    return f


def compute_drawdown_curve(equity: pd.Series) -> pd.Series:
    """Return drawdown as negative fractions (0 to -1)."""
    peak = equity.cummax()
    # Avoid division by zero
    with np.errstate(divide="ignore", invalid="ignore"):
        dd = equity / peak - 1.0
    dd = dd.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return dd


def max_drawdown_percent(equity: pd.Series) -> float:
    """Maximum drawdown as a positive loss magnitude percentage."""
    dd = compute_drawdown_curve(equity)
    mdd = float(dd.min())  # most negative
    return abs(mdd) * 100.0


def sharpe_ratio(daily_returns: pd.Series, periods: int = 252) -> float | None:
    """Annualized Sharpe with risk-free rate = 0."""
    r = daily_returns.dropna()
    if len(r) < 2:
        return None
    std = float(r.std(ddof=1))
    if std == 0.0 or np.isnan(std):
        return None
    mean = float(r.mean())
    return safe_float(mean / std * np.sqrt(periods))


def win_rate_percent(pnl_list: list[float]) -> float | None:
    if not pnl_list:
        return None
    wins = sum(1 for p in pnl_list if p > 0)
    return wins / len(pnl_list) * 100.0


def profit_factor(pnl_list: list[float]) -> float | None:
    if not pnl_list:
        return None
    gains = sum(p for p in pnl_list if p > 0)
    losses = sum(p for p in pnl_list if p < 0)
    if losses == 0:
        return None  # undefined / infinite
    return safe_float(gains / abs(losses))


def compute_metrics(
    *,
    initial_capital: float,
    equity_curve: pd.Series,
    trade_pnls: list[float],
    buy_and_hold_return_percent: float | None,
) -> dict[str, Any]:
    final_equity = float(equity_curve.iloc[-1]) if len(equity_curve) else initial_capital
    net_pnl = final_equity - initial_capital
    total_return = (final_equity / initial_capital - 1.0) * 100.0 if initial_capital else 0.0
    mdd = max_drawdown_percent(equity_curve) if len(equity_curve) else 0.0

    daily_returns = equity_curve.pct_change().dropna()
    sharpe = sharpe_ratio(daily_returns)
    wr = win_rate_percent(trade_pnls)
    pf = profit_factor(trade_pnls)

    notes: list[str] = []
    if wr is None:
        notes.append("Win rate unavailable: no completed trades.")
    if pf is None and trade_pnls:
        if all(p >= 0 for p in trade_pnls):
            notes.append("Profit factor undefined: no losing completed trades.")
        elif all(p <= 0 for p in trade_pnls):
            notes.append("Profit factor undefined: no winning completed trades.")
    if pf is None and not trade_pnls:
        notes.append("Profit factor unavailable: no completed trades.")
    if sharpe is None:
        notes.append("Sharpe ratio unavailable: insufficient return variance or observations.")

    return {
        "initial_capital": float(initial_capital),
        "final_equity": float(final_equity),
        "net_profit_loss": float(net_pnl),
        "total_return_percent": float(total_return),
        "max_drawdown_percent": float(mdd),
        "completed_trades": len(trade_pnls),
        "win_rate_percent": wr,
        "profit_factor": pf,
        "sharpe_ratio": sharpe,
        "buy_and_hold_return_percent": buy_and_hold_return_percent,
        "notes": notes,
    }
