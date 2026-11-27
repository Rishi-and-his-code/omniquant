"""Deterministic technical indicators using Pandas / NumPy.

Conventions
-----------
- SMA: simple rolling mean; NaN until `period` observations exist.
- EMA: pandas ewm(span=period, adjust=False) — common trading convention
  where alpha = 2 / (period + 1). NaN until the first `period` values seed.
- RSI: Wilder-style smoothing (RMA). First average gain/loss uses SMA of
  the first `period` changes; subsequent values use Wilder's recursive formula.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def sma(series: pd.Series, period: int) -> pd.Series:
    if period < 2:
        raise ValueError("SMA period must be >= 2")
    return series.astype(float).rolling(window=period, min_periods=period).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    """EMA with span=period, adjust=False (alpha = 2/(period+1)).

    Values before the first `period` observations are set to NaN so warm-up
    is visible as gaps rather than unstable early EMA values.
    """
    if period < 2:
        raise ValueError("EMA period must be >= 2")
    s = series.astype(float)
    raw = s.ewm(span=period, adjust=False, min_periods=period).mean()
    return raw


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Wilder-smoothed RSI.

    Handles zero average loss (RSI=100), zero average gain (RSI=0),
    and flat prices without producing Inf/NaN from division by zero
    once enough observations exist.
    """
    if period < 2:
        raise ValueError("RSI period must be >= 2")

    prices = series.astype(float)
    delta = prices.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)

    avg_gain = gain.copy()
    avg_loss = loss.copy()
    avg_gain.iloc[:] = np.nan
    avg_loss.iloc[:] = np.nan

    if len(prices) <= period:
        return pd.Series(np.nan, index=prices.index, dtype=float)

    # Seed with SMA of first `period` changes (indices 1..period)
    avg_gain.iloc[period] = gain.iloc[1 : period + 1].mean()
    avg_loss.iloc[period] = loss.iloc[1 : period + 1].mean()

    for i in range(period + 1, len(prices)):
        avg_gain.iloc[i] = (avg_gain.iloc[i - 1] * (period - 1) + gain.iloc[i]) / period
        avg_loss.iloc[i] = (avg_loss.iloc[i - 1] * (period - 1) + loss.iloc[i]) / period

    rs = pd.Series(np.nan, index=prices.index, dtype=float)
    rsi_vals = pd.Series(np.nan, index=prices.index, dtype=float)

    for i in range(period, len(prices)):
        g = avg_gain.iloc[i]
        l = avg_loss.iloc[i]
        if np.isnan(g) or np.isnan(l):
            continue
        if l == 0 and g == 0:
            rsi_vals.iloc[i] = 50.0  # flat market
        elif l == 0:
            rsi_vals.iloc[i] = 100.0
        elif g == 0:
            rsi_vals.iloc[i] = 0.0
        else:
            rs.iloc[i] = g / l
            rsi_vals.iloc[i] = 100.0 - (100.0 / (1.0 + rs.iloc[i]))

    return rsi_vals


def series_to_nullable_list(series: pd.Series) -> list[float | None]:
    """Convert a Series to JSON-safe floats with None for NaN/Inf."""
    out: list[float | None] = []
    for v in series:
        if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))):
            out.append(None)
        else:
            out.append(float(v))
    return out
