"""Cache coverage: a partial overlap must not stand in for the requested window."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from app.config import Settings
from app.services import market_data_service as market_mod
from app.services.market_data_service import (
    PRICE_ADJUSTMENT,
    MarketDataError,
    MarketDataService,
)


def _service(tmp_path: Path) -> MarketDataService:
    settings = Settings(
        data_dir=tmp_path,
        database_url=f"sqlite:///{tmp_path / 'unused.db'}",
        ai_enabled=False,
        ai_api_key="",
        ai_model="",
    )
    return MarketDataService(settings)


def _seed(
    svc: MarketDataService,
    symbol: str,
    start: date,
    end: date,
    *,
    adjustment: str = PRICE_ADJUSTMENT,
) -> None:
    df = pd.DataFrame(
        {
            "date": pd.to_datetime([start, end]),
            "open": [10.0, 11.0],
            "high": [10.5, 11.5],
            "low": [9.5, 10.5],
            "close": [10.2, 11.2],
            "volume": [1000.0, 1100.0],
        }
    )
    meta = {
        "symbol": symbol,
        "available_start": start.isoformat(),
        "available_end": end.isoformat(),
        "price_adjustment": adjustment,
        "source": "test",
        "retrieved_at": "2026-01-01T00:00:00+00:00",
        "fingerprint": "test-fingerprint",
    }
    key = f"{symbol}-{start.isoformat()}-{end.isoformat()}".replace(".", "_").replace("^", "IDX_")
    svc._write_cache(svc.cache_dir / f"{key}.csv", svc.cache_dir / f"{key}.meta.json", df, meta)


def test_covering_cache_skips_the_network(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    _seed(svc, "RELIANCE.NS", date(2022, 12, 1), date(2025, 12, 31))

    def fail(*args, **kwargs):
        raise AssertionError("network")

    svc._fetch_provider = fail  # type: ignore[method-assign]

    result = svc.get_history("RELIANCE.NS", date(2023, 1, 1), date(2025, 12, 31))

    assert result.cache_status == "cached"
    assert result.available_start == "2022-12-01"
    assert any("local cache" in w for w in result.warnings)


def test_partial_overlap_is_not_a_cache_hit(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    _seed(svc, "RELIANCE.NS", date(2024, 6, 1), date(2024, 8, 1))
    calls: list[str] = []

    def fail(symbol: str, *args, **kwargs):
        calls.append(symbol)
        raise MarketDataError("MARKET_DATA_UNAVAILABLE", "provider down")

    svc._fetch_provider = fail  # type: ignore[method-assign]

    with pytest.raises(MarketDataError):
        svc.get_history(
            "RELIANCE.NS",
            date(2023, 1, 1),
            date(2025, 12, 31),
            allow_cache_fallback=True,
        )
    assert calls == ["RELIANCE.NS"]


def test_long_chart_request_stops_on_429_without_another_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    svc = _service(tmp_path)
    calls: list[date] = []
    monkeypatch.setattr(market_mod.time, "sleep", lambda *_args, **_kwargs: None)

    def window(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        calls.append(start)
        if len(calls) == 2:
            raise MarketDataError(
                "MARKET_DATA_UNAVAILABLE",
                "limited",
                details={"status": 429},
            )
        return pd.DataFrame(
            {"Open": [1.0], "High": [1.0], "Low": [1.0], "Close": [1.0], "Volume": [1.0]},
            index=pd.to_datetime([start]),
        )

    svc._fetch_yahoo_chart_window = window.__get__(svc, MarketDataService)  # type: ignore[method-assign]
    with pytest.raises(MarketDataError) as exc:
        svc._fetch_yahoo_chart("RELIANCE.NS", date(2023, 1, 1), date(2023, 9, 1))
    assert exc.value.details == {"status": 429}
    assert len(calls) == 2


def test_cache_does_not_substitute_symbol_or_price_basis(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    _seed(svc, "TCS.NS", date(2022, 1, 1), date(2025, 12, 31))
    _seed(
        svc,
        "RELIANCE.NS",
        date(2022, 1, 1),
        date(2025, 12, 31),
        adjustment="raw_close",
    )
    calls: list[str] = []

    def fail(symbol: str, *args, **kwargs):
        calls.append(symbol)
        raise MarketDataError("MARKET_DATA_UNAVAILABLE", "provider down")

    svc._fetch_provider = fail  # type: ignore[method-assign]

    with pytest.raises(MarketDataError):
        svc.get_history("RELIANCE.NS", date(2023, 1, 1), date(2025, 12, 31))
    assert calls == ["RELIANCE.NS"]
