"""Indicator unit tests."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.services.indicators import ema, rsi, sma


def test_sma_manual():
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    out = sma(s, 3)
    assert np.isnan(out.iloc[0]) and np.isnan(out.iloc[1])
    assert out.iloc[2] == pytest.approx(2.0)
    assert out.iloc[3] == pytest.approx(3.0)
    assert out.iloc[4] == pytest.approx(4.0)


def test_sma_invalid_period():
    with pytest.raises(ValueError):
        sma(pd.Series([1.0, 2.0]), 1)


def test_ema_warmup_and_trend():
    s = pd.Series([10.0] * 5 + [20.0] * 5)
    out = ema(s, 3)
    assert out.iloc[:2].isna().all()
    assert out.iloc[3] > out.iloc[2] or not np.isnan(out.iloc[3])
    # Later values should rise toward 20
    assert out.iloc[-1] > out.iloc[5]


def test_rsi_flat_prices():
    s = pd.Series([100.0] * 30)
    out = rsi(s, 14)
    # After warm-up, flat → RSI 50
    valid = out.dropna()
    assert len(valid) > 0
    assert all(abs(v - 50.0) < 1e-6 for v in valid)


def test_rsi_all_gains():
    s = pd.Series([float(i) for i in range(1, 40)])
    out = rsi(s, 14)
    # Strong uptrend → RSI near 100
    assert out.dropna().iloc[-1] > 70


def test_rsi_invalid_period():
    with pytest.raises(ValueError):
        rsi(pd.Series([1.0, 2.0, 3.0]), 1)
