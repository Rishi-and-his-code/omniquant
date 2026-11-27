"""Test manual CSV import into OmniQuant local market data cache."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from app.config import Settings
from app.services.market_data_service import MarketDataService
from scripts.import_csv import import_csv_file


def _service(tmp_path: Path) -> MarketDataService:
    settings = Settings(
        data_dir=tmp_path,
        database_url=f"sqlite:///{tmp_path / 'unused.db'}",
        ai_enabled=False,
        ai_api_key="",
        ai_model="",
    )
    return MarketDataService(settings)


def test_import_generic_csv_and_verify_cache_hit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Point settings data_dir to tmp_path
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    # Create synthetic external CSV simulating Investing.com or Google Finance export
    raw_csv = tmp_path / "raw_reliance.csv"
    dates = pd.date_range("2022-10-01", "2025-12-31", freq="B")
    sample_df = pd.DataFrame(
        {
            "Date": dates.strftime("%Y-%m-%d"),
            "Open": [2000.0 + i * 0.5 for i in range(len(dates))],
            "High": [2010.0 + i * 0.5 for i in range(len(dates))],
            "Low": [1990.0 + i * 0.5 for i in range(len(dates))],
            "Close": [2005.0 + i * 0.5 for i in range(len(dates))],
            "Vol.": ["1.2M"] * len(dates),
        }
    )
    sample_df.to_csv(raw_csv, index=False)

    # Run import
    svc = _service(tmp_path)
    csv_path, meta_path, meta = import_csv_file(raw_csv, symbol="RELIANCE.NS", service=svc)

    assert csv_path.exists()
    assert meta_path.exists()
    assert meta["symbol"] == "RELIANCE.NS"
    assert meta["available_start"] == "2022-10-03"

    # Now verify MarketDataService finds it without network calls

    def fail_network(*args, **kwargs):
        raise AssertionError("Network was unexpectedly contacted!")

    svc._fetch_provider = fail_network  # type: ignore[method-assign]

    result = svc.get_history("RELIANCE.NS", date(2023, 1, 1), date(2025, 12, 31))

    assert result.cache_status == "cached"
    assert result.available_start == "2022-10-03"
    assert len(result.df) == len(dates)


def test_banknifty_is_not_inferred_as_nifty() -> None:
    from scripts.import_csv import infer_symbol_from_path

    assert infer_symbol_from_path(Path("BANKNIFTY.csv")) == "^NSEBANK"
    assert infer_symbol_from_path(Path("NIFTY.csv")) == "^NSEI"


def test_coverage_flag_cannot_claim_dates_the_file_lacks(tmp_path: Path) -> None:
    raw_csv = tmp_path / "raw_reliance.csv"
    raw_csv.write_text(
        "Date,Open,High,Low,Close,Volume\n"
        "2023-01-02,10,11,9,10.5,1000\n"
        "2023-01-03,10,11,9,10.5,1000\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="does not include"):
        import_csv_file(
            raw_csv,
            symbol="RELIANCE.NS",
            service=_service(tmp_path),
            coverage_start="2022-10-01",
        )
