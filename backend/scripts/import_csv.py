#!/usr/bin/env python3
"""Import and validate historical market data CSV files into OmniQuant's local cache.

Supports single file or directory batch import. Normalizes dates, column names,
and formats from common export sources (Yahoo Finance, TradingView, Google Finance,
Investing.com, broker CSVs). Generates the required .csv and .meta.json cache entries.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# Ensure backend package is importable; persist data at repo root ./data
BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

import os

os.environ.setdefault("DATA_DIR", str(PROJECT_ROOT / "data"))
os.environ.setdefault("DATABASE_URL", f"sqlite:///{PROJECT_ROOT / 'data' / 'omniquant.db'}")

from app.config import get_settings
from app.services.market_data_service import (
    PRICE_ADJUSTMENT,
    MarketDataService,
    _cache_key,
    _fingerprint,
    _normalize_ohlcv,
)


KNOWN_SYMBOLS = {
    "RELIANCE": "RELIANCE.NS",
    "RELIANCE.NS": "RELIANCE.NS",
    "TCS": "TCS.NS",
    "TCS.NS": "TCS.NS",
    "INFY": "INFY.NS",
    "INFY.NS": "INFY.NS",
    "INFOSYS": "INFY.NS",
    "INFOSYS.NS": "INFY.NS",
    "HDFCBANK": "HDFCBANK.NS",
    "HDFCBANK.NS": "HDFCBANK.NS",
    "ICICIBANK": "ICICIBANK.NS",
    "ICICIBANK.NS": "ICICIBANK.NS",
    "HINDUNILVR": "HINDUNILVR.NS",
    "HINDUNILVR.NS": "HINDUNILVR.NS",
    "ITC": "ITC.NS",
    "ITC.NS": "ITC.NS",
    "NIFTY": "^NSEI",
    "^NSEI": "^NSEI",
    "BANKNIFTY": "^NSEBANK",
    "^NSEBANK": "^NSEBANK",
}


def clean_volume_str(val: Any) -> Any:
    """Parse numeric volume strings that may contain commas, K, M, or B suffixes."""
    if pd.isna(val):
        return np.nan
    if isinstance(val, (int, float)):
        return val
    s = str(val).strip().replace(",", "")
    if not s or s.lower() == "nan":
        return np.nan
    s_upper = s.upper()
    try:
        if s_upper.endswith("K"):
            return float(s_upper[:-1]) * 1_000
        elif s_upper.endswith("M"):
            return float(s_upper[:-1]) * 1_000_000
        elif s_upper.endswith("B"):
            return float(s_upper[:-1]) * 1_000_000_000
        return float(s)
    except ValueError:
        return np.nan


def clean_numeric_str(val: Any) -> Any:
    """Strip commas and whitespace from numeric fields."""
    if pd.isna(val):
        return np.nan
    if isinstance(val, (int, float)):
        return val
    s = str(val).strip().replace(",", "")
    try:
        return float(s)
    except ValueError:
        return np.nan


def infer_symbol_from_path(file_path: Path) -> str | None:
    stem = file_path.stem.upper().replace("-", "").replace("_", "").replace(" ", "")
    best: str | None = None
    best_len = -1
    for key, mapped in KNOWN_SYMBOLS.items():
        token = key.replace(".", "").replace("^", "")
        if token and token in stem and len(token) > best_len:
            best = mapped
            best_len = len(token)
    return best


def read_and_clean_raw_csv(file_path: Path) -> pd.DataFrame:
    df = pd.read_csv(file_path)
    if df.empty:
        raise ValueError(f"CSV file is empty: {file_path}")

    # Standardize column names
    col_map = {}
    for col in df.columns:
        c_clean = str(col).strip().lower().replace(" ", "_").replace(".", "")
        if c_clean in ["date", "timestamp", "time"]:
            col_map[col] = "date"
        elif c_clean in ["open", "open_price"]:
            col_map[col] = "open"
        elif c_clean in ["high", "high_price"]:
            col_map[col] = "high"
        elif c_clean in ["low", "low_price"]:
            col_map[col] = "low"
        elif c_clean in ["adj_close", "adjclose", "adjusted_close"]:
            col_map[col] = "adj_close"
        elif c_clean in ["close", "close_price", "last", "last_price", "price"]:
            col_map[col] = "close"
        elif c_clean in ["volume", "vol", "shares_traded", "total_traded_quantity"]:
            col_map[col] = "volume"

    df = df.rename(columns=col_map)

    # If adj_close exists, prefer it as close for adjusted_close_basis
    if "adj_close" in df.columns:
        df["close"] = df["adj_close"]

    if "date" not in df.columns:
        raise ValueError(f"Could not identify a date column in {file_path}. Columns found: {list(df.columns)}")

    # Clean numeric fields (strip commas etc)
    for num_col in ["open", "high", "low", "close"]:
        if num_col in df.columns:
            df[num_col] = df[num_col].apply(clean_numeric_str)

    if "volume" in df.columns:
        df["volume"] = df["volume"].apply(clean_volume_str)

    # Parse date and set as index for _normalize_ohlcv
    df["date"] = pd.to_datetime(df["date"], format="mixed", dayfirst=True, errors="coerce")
    df = df.dropna(subset=["date"])
    df = df.set_index("date")

    return df


def import_csv_file(
    file_path: Path,
    symbol: str | None = None,
    source: str = "manual_import",
    price_adjustment: str = PRICE_ADJUSTMENT,
    overwrite: bool = True,
    service: MarketDataService | None = None,
    coverage_start: date | str | None = None,
    coverage_end: date | str | None = None,
) -> tuple[Path, Path, dict]:
    svc = service or MarketDataService(get_settings())

    if not symbol:
        symbol = infer_symbol_from_path(file_path)
    if not symbol:
        raise ValueError(
            f"Could not infer ticker symbol for {file_path.name}. Please specify --symbol explicitly."
        )

    # Normalize symbol format if missing exchange
    if not symbol.endswith(".NS") and not symbol.startswith("^"):
        if symbol in KNOWN_SYMBOLS:
            symbol = KNOWN_SYMBOLS[symbol]
        else:
            symbol = f"{symbol}.NS"

    raw_df = read_and_clean_raw_csv(file_path)
    df, dropped = _normalize_ohlcv(raw_df, symbol)

    avail_start: date = df["date"].iloc[0].date()
    avail_end: date = df["date"].iloc[-1].date()

    requested_start = (
        date.fromisoformat(coverage_start)
        if isinstance(coverage_start, str)
        else (coverage_start or avail_start)
    )
    requested_end = (
        date.fromisoformat(coverage_end)
        if isinstance(coverage_end, str)
        else (coverage_end or avail_end)
    )
    if requested_start < avail_start or requested_end > avail_end:
        raise ValueError(
            f"{symbol} rows cover {avail_start.isoformat()} to {avail_end.isoformat()}, "
            f"which does not include {requested_start.isoformat()} to {requested_end.isoformat()}."
        )

    # The cache may only claim the dates that are actually in the file.
    key = _cache_key(symbol, avail_start, avail_end, price_adjustment)
    cache_csv = svc.cache_dir / f"{key}.csv"
    cache_meta = svc.cache_dir / f"{key}.meta.json"

    if not overwrite and cache_csv.exists() and cache_meta.exists():
        print(f"Skipping {symbol}: cache already exists at {cache_csv.name}")
        meta = json.loads(cache_meta.read_text(encoding="utf-8"))
        return cache_csv, cache_meta, meta

    fp = _fingerprint(df, symbol, price_adjustment)
    retrieved_at = datetime.now(timezone.utc).isoformat()

    meta = {
        "symbol": symbol,
        "requested_start": requested_start.isoformat(),
        "requested_end": requested_end.isoformat(),
        "fetch_start": avail_start.isoformat(),
        "effective_end": avail_end.isoformat(),
        "available_start": avail_start.isoformat(),
        "available_end": avail_end.isoformat(),
        "data_start": avail_start.isoformat(),
        "data_end": avail_end.isoformat(),
        "retrieved_at": retrieved_at,
        "source": source,
        "price_adjustment": price_adjustment,
        "cache_key": key,
        "fingerprint": fp,
        "row_count": len(df),
    }

    svc._write_cache(cache_csv, cache_meta, df, meta)
    return cache_csv, cache_meta, meta


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import historical market data CSV into OmniQuant local cache."
    )
    parser.add_argument("--file", "-f", type=Path, help="Path to single CSV file to import.")
    parser.add_argument("--dir", "-d", type=Path, help="Directory containing CSV files to import.")
    parser.add_argument(
        "--symbol", "-s", type=str, help="Ticker symbol (e.g. RELIANCE.NS). Required if --file without recognized name."
    )
    parser.add_argument(
        "--source", default="manual_import", help="Source attribution in cache metadata."
    )
    parser.add_argument(
        "--coverage-start",
        type=str,
        default=None,
        help="Require the file to contain this start date. The cache still records the real first row.",
    )
    parser.add_argument(
        "--coverage-end",
        type=str,
        default=None,
        help="Require the file to contain this end date. The cache still records the real last row.",
    )
    parser.add_argument(
        "--no-overwrite", action="store_true", help="Do not overwrite existing cached files."
    )

    args = parser.parse_args()

    if not args.file and not args.dir:
        parser.print_help()
        return 1

    targets: list[tuple[Path, str | None]] = []
    if args.file:
        if not args.file.exists():
            print(f"Error: File not found: {args.file}", file=sys.stderr)
            return 1
        targets.append((args.file, args.symbol))

    if args.dir:
        if not args.dir.exists() or not args.dir.is_dir():
            print(f"Error: Directory not found: {args.dir}", file=sys.stderr)
            return 1
        for p in sorted(args.dir.glob("*.csv")):
            targets.append((p, None))

    success = 0
    for file_path, sym in targets:
        try:
            csv_path, meta_path, meta = import_csv_file(
                file_path=file_path,
                symbol=sym,
                source=args.source,
                overwrite=not args.no_overwrite,
                coverage_start=args.coverage_start,
                coverage_end=args.coverage_end,
            )
            print(
                f"[SUCCESS] {meta['symbol']:<12} | "
                f"Range: {meta['available_start']} -> {meta['available_end']} | "
                f"Rows: {meta['row_count']:<4} | "
                f"Cache Key: {meta['cache_key']}"
            )
            print(f"          CSV:  {csv_path}")
            print(f"          Meta: {meta_path}")
            success += 1
        except Exception as exc:
            print(f"[FAILED]  {file_path.name}: {exc}", file=sys.stderr)

    print(f"\nImported {success}/{len(targets)} datasets.")
    return 0 if success > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
