"""Market data retrieval, validation, and CSV caching via yfinance."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote as url_quote

import urllib.error
import urllib.request

import pandas as pd
import yfinance as yf

from app.config import Settings, get_settings
from app.services.indicators import ema, series_to_nullable_list, sma, rsi

logger = logging.getLogger(__name__)

PRICE_ADJUSTMENT = "adjusted_close_basis"
SOURCE = "yahoo_finance"


class MarketDataError(Exception):
    def __init__(self, code: str, message: str, details: Any = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details


@dataclass
class MarketDataResult:
    df: pd.DataFrame
    source: str
    price_adjustment: str
    cache_status: str
    retrieved_at: str
    requested_start: str
    requested_end: str
    available_start: str | None
    available_end: str | None
    fingerprint: str
    warnings: list[str]
    metadata: dict[str, Any]


def _to_iso(d: date | datetime | pd.Timestamp) -> str:
    if isinstance(d, datetime):
        return d.date().isoformat()
    if isinstance(d, pd.Timestamp):
        return d.date().isoformat()
    return d.isoformat()


def _normalize_ohlcv(raw: pd.DataFrame, symbol: str) -> pd.DataFrame:
    if raw is None or raw.empty:
        raise MarketDataError(
            "MARKET_DATA_EMPTY",
            f"No historical data returned for {symbol}.",
        )

    df = raw.copy()

    # Flatten MultiIndex columns if present (yfinance sometimes returns them)
    if isinstance(df.columns, pd.MultiIndex):
        # Prefer the OHLCV level; drop ticker level when present
        level0 = df.columns.get_level_values(0)
        if "Close" in level0 or "close" in [str(c).lower() for c in level0]:
            df.columns = level0
        else:
            df.columns = df.columns.get_level_values(-1)

    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]

    rename_map = {
        "adj_close": "close",
        "adjclose": "close",
    }
    df = df.rename(columns=rename_map)

    required = ["open", "high", "low", "close"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise MarketDataError(
            "MARKET_DATA_INVALID",
            f"Missing required columns for {symbol}: {missing}",
            details={"columns": list(df.columns)},
        )

    if "volume" not in df.columns:
        df["volume"] = pd.NA

    # Index → date column
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)
    df = df.reset_index()
    date_col = df.columns[0]
    df = df.rename(columns={date_col: "date"})
    df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None).dt.normalize()

    df = df[["date", "open", "high", "low", "close", "volume"]].copy()
    df = df.sort_values("date").drop_duplicates(subset=["date"], keep="last")

    for col in ["open", "high", "low", "close"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df["volume"] = pd.to_numeric(df["volume"], errors="coerce")

    # Drop rows with invalid OHLC
    before = len(df)
    valid = (
        df[["open", "high", "low", "close"]].notna().all(axis=1)
        & (df[["open", "high", "low", "close"]] > 0).all(axis=1)
        & df[["open", "high", "low", "close"]].apply(
            lambda r: np_finite_row(r), axis=1
        )
    )
    # High/low consistency
    hl_ok = (df["high"] >= df[["open", "close", "low"]].max(axis=1) - 1e-9) & (
        df["low"] <= df[["open", "close", "high"]].min(axis=1) + 1e-9
    )
    # Softer HL check: high >= max(o,c) and low <= min(o,c), high >= low
    hl_ok = (df["high"] >= df[["open", "close"]].max(axis=1) - 1e-6) & (
        df["low"] <= df[["open", "close"]].min(axis=1) + 1e-6
    ) & (df["high"] >= df["low"] - 1e-6)

    df = df[valid & hl_ok].copy()
    dropped = before - len(df)
    if df.empty:
        raise MarketDataError(
            "MARKET_DATA_INVALID",
            f"All observations for {symbol} failed validation.",
        )

    df = df.reset_index(drop=True)
    return df, dropped


def np_finite_row(row: pd.Series) -> bool:
    import numpy as np

    return bool(np.isfinite(row.astype(float)).all())


def _fingerprint(df: pd.DataFrame, symbol: str, adjustment: str) -> str:
    payload = (
        f"{symbol}|{adjustment}|"
        f"{df['date'].iloc[0].date().isoformat()}|"
        f"{df['date'].iloc[-1].date().isoformat()}|"
        f"{len(df)}|"
        f"{df['close'].iloc[0]:.6f}|{df['close'].iloc[-1]:.6f}|"
        f"{df['close'].sum():.6f}"
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:32]


def _cache_key(symbol: str, start: date, end: date, adjustment: str) -> str:
    safe_symbol = symbol.replace("^", "IDX_").replace(".", "_")
    raw = f"{safe_symbol}|{start.isoformat()}|{end.isoformat()}|{adjustment}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


class MarketDataService:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.cache_dir = self.settings.cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get_history(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
        *,
        refresh: bool = False,
        allow_cache_fallback: bool = True,
        warmup_days: int = 0,
    ) -> MarketDataResult:
        warnings: list[str] = []

        # Avoid incomplete current-day candle: cap end at yesterday (UTC)
        today = datetime.now(timezone.utc).date()
        effective_end = min(end_date, today - timedelta(days=1))
        if effective_end < end_date:
            warnings.append(
                f"End date capped to last completed session ({effective_end.isoformat()})."
            )

        fetch_start = start_date - timedelta(days=max(warmup_days, 0) + 10)
        # yfinance end is exclusive → add one day for inclusive user end
        provider_end_exclusive = effective_end + timedelta(days=1)

        key = _cache_key(symbol, fetch_start, effective_end, PRICE_ADJUSTMENT)
        cache_csv = self.cache_dir / f"{key}.csv"
        cache_meta = self.cache_dir / f"{key}.meta.json"

        if not refresh and cache_csv.exists() and cache_meta.exists():
            try:
                result = self._load_cache(cache_csv, cache_meta, start_date, effective_end)
                return result
            except Exception as exc:
                logger.warning("Cache load failed for %s: %s", symbol, exc)
                warnings.append("Local cache was unreadable; fetching from provider.")

        # Prefer a covering local cache before hitting the network (evaluation / offline)
        if not refresh:
            cached = self._find_best_cache(symbol, start_date, effective_end)
            if cached is not None:
                cached.warnings = list(cached.warnings) + [
                    "Serving validated local cache (network fetch skipped)."
                ]
                return cached

        try:
            df_raw, fetch_source = self._fetch_provider(symbol, fetch_start, provider_end_exclusive)
            df, dropped = _normalize_ohlcv(df_raw, symbol)
            if dropped:
                warnings.append(f"Dropped {dropped} invalid OHLC row(s) during validation.")

            retrieved_at = datetime.now(timezone.utc).isoformat()
            fp = _fingerprint(df, symbol, PRICE_ADJUSTMENT)
            meta = {
                "symbol": symbol,
                "requested_start": start_date.isoformat(),
                "requested_end": end_date.isoformat(),
                "fetch_start": fetch_start.isoformat(),
                "effective_end": effective_end.isoformat(),
                "available_start": df["date"].iloc[0].date().isoformat(),
                "available_end": df["date"].iloc[-1].date().isoformat(),
                "retrieved_at": retrieved_at,
                "source": fetch_source,
                "price_adjustment": PRICE_ADJUSTMENT,
                "cache_key": key,
                "fingerprint": fp,
                "row_count": len(df),
            }
            self._write_cache(cache_csv, cache_meta, df, meta)

            # Slice to warmup+range for return (keep full cached)
            return MarketDataResult(
                df=df,
                source=fetch_source,
                price_adjustment=PRICE_ADJUSTMENT,
                cache_status="fresh",
                retrieved_at=retrieved_at,
                requested_start=start_date.isoformat(),
                requested_end=end_date.isoformat(),
                available_start=meta["available_start"],
                available_end=meta["available_end"],
                fingerprint=fp,
                warnings=warnings,
                metadata=meta,
            )
        except MarketDataError:
            if allow_cache_fallback:
                fallback = self._find_best_cache(symbol, start_date, effective_end)
                if fallback is not None:
                    fallback.warnings.append(
                        "Provider fetch failed; serving matching local cache."
                    )
                    fallback.cache_status = "fallback_cache"
                    return fallback
            raise
        except Exception as exc:
            logger.exception("Market data fetch failed for %s", symbol)
            if allow_cache_fallback:
                fallback = self._find_best_cache(symbol, start_date, effective_end)
                if fallback is not None:
                    fallback.warnings.append(
                        f"Provider error ({type(exc).__name__}); serving matching local cache."
                    )
                    fallback.cache_status = "fallback_cache"
                    return fallback
            raise MarketDataError(
                "MARKET_DATA_UNAVAILABLE",
                f"Historical market data could not be retrieved for {symbol}.",
                details={"reason": str(exc)},
            ) from exc

    def _fetch_provider(
        self, symbol: str, start: date, end_exclusive: date
    ) -> tuple[pd.DataFrame, str]:
        """Prefer Yahoo chart API (reliable User-Agent), fall back to yfinance."""
        last_err: Exception | None = None
        try:
            df = self._fetch_yahoo_chart(symbol, start, end_exclusive)
            if df is not None and not df.empty:
                return df, "yahoo_chart_api"
        except Exception as exc:
            last_err = exc
            logger.warning("Yahoo chart API failed for %s: %s", symbol, exc)

        for attempt in range(self.settings.market_data_max_retries + 1):
            try:
                ticker = yf.Ticker(symbol)
                df = ticker.history(
                    start=start.isoformat(),
                    end=end_exclusive.isoformat(),
                    interval="1d",
                    auto_adjust=True,
                    actions=False,
                    timeout=self.settings.market_data_timeout_seconds,
                )
                if df is not None and not df.empty:
                    return df, "yfinance"
                last_err = MarketDataError(
                    "MARKET_DATA_EMPTY",
                    f"No historical data returned for {symbol}.",
                )
            except MarketDataError:
                raise
            except Exception as exc:
                last_err = exc
                logger.warning(
                    "yfinance attempt %s failed for %s: %s",
                    attempt + 1,
                    symbol,
                    exc,
                )
                time.sleep(0.5 * (attempt + 1))
        if isinstance(last_err, MarketDataError):
            raise last_err
        raise MarketDataError(
            "MARKET_DATA_UNAVAILABLE",
            f"Historical market data could not be retrieved for {symbol}.",
            details={"reason": str(last_err)},
        )

    def _fetch_yahoo_chart(
        self, symbol: str, start: date, end_exclusive: date
    ) -> pd.DataFrame:
        """Direct Yahoo Finance chart API with browser User-Agent.

        Uses adjclose when present so prices remain on an adjusted basis
        consistent with the research approximation documented in the UI.
        """
        period1 = int(datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc).timestamp())
        period2 = int(
            datetime.combine(end_exclusive, datetime.min.time(), tzinfo=timezone.utc).timestamp()
        )
        url = (
            f"https://query1.finance.yahoo.com/v8/finance/chart/{url_quote(symbol)}"
            f"?period1={period1}&period2={period2}&interval=1d&events=history"
        )
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json",
        }
        # urllib is more reliable against Yahoo rate-limits than some HTTP clients here
        payload = None
        last_http_err: Exception | None = None
        for attempt in range(self.settings.market_data_max_retries + 2):
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(
                    req, timeout=self.settings.market_data_timeout_seconds
                ) as resp:
                    raw = resp.read().decode("utf-8")
                    payload = json.loads(raw)
                    break
            except urllib.error.HTTPError as exc:
                last_http_err = exc
                wait = 3.0 * (attempt + 1) if exc.code == 429 else 1.0 * (attempt + 1)
                logger.warning(
                    "Yahoo HTTP %s for %s (attempt %s)", exc.code, symbol, attempt + 1
                )
                time.sleep(wait)
            except Exception as exc:
                last_http_err = exc
                time.sleep(1.0 * (attempt + 1))
        if payload is None:
            raise MarketDataError(
                "MARKET_DATA_UNAVAILABLE",
                f"Historical market data could not be retrieved for {symbol}.",
                details={"reason": str(last_http_err)},
            )

        result = (payload.get("chart") or {}).get("result")
        if not result:
            err = (payload.get("chart") or {}).get("error")
            raise MarketDataError(
                "MARKET_DATA_EMPTY",
                f"No historical data returned for {symbol}.",
                details=err,
            )
        block = result[0]
        timestamps = block.get("timestamp") or []
        indicators = (block.get("indicators") or {}).get("quote") or [{}]
        quote = indicators[0]
        adj = ((block.get("indicators") or {}).get("adjclose") or [{}])[0].get("adjclose")

        opens = quote.get("open") or []
        highs = quote.get("high") or []
        lows = quote.get("low") or []
        closes = quote.get("close") or []
        volumes = quote.get("volume") or []

        rows = []
        for i, ts in enumerate(timestamps):
            o, h, l, c = (
                opens[i] if i < len(opens) else None,
                highs[i] if i < len(highs) else None,
                lows[i] if i < len(lows) else None,
                closes[i] if i < len(closes) else None,
            )
            if None in (o, h, l, c):
                continue
            # Prefer adjusted close scaling when adjclose is available
            adj_c = adj[i] if adj and i < len(adj) and adj[i] is not None else None
            if adj_c is not None and c not in (0, None):
                factor = adj_c / c
                o, h, l, c = o * factor, h * factor, l * factor, adj_c
            vol = volumes[i] if i < len(volumes) else None
            rows.append(
                {
                    "Date": datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None),
                    "Open": o,
                    "High": h,
                    "Low": l,
                    "Close": c,
                    "Volume": vol,
                }
            )
        if not rows:
            raise MarketDataError(
                "MARKET_DATA_EMPTY",
                f"No historical data returned for {symbol}.",
            )
        return pd.DataFrame(rows).set_index("Date")

    def _write_cache(
        self, csv_path: Path, meta_path: Path, df: pd.DataFrame, meta: dict
    ) -> None:
        out = df.copy()
        out["date"] = out["date"].dt.strftime("%Y-%m-%d")
        out.to_csv(csv_path, index=False)
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    def _load_cache(
        self,
        csv_path: Path,
        meta_path: Path,
        requested_start: date,
        effective_end: date,
    ) -> MarketDataResult:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        df = pd.read_csv(csv_path, parse_dates=["date"])
        df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None).dt.normalize()
        for col in ["open", "high", "low", "close", "volume"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        return MarketDataResult(
            df=df,
            source=meta.get("source", SOURCE),
            price_adjustment=meta.get("price_adjustment", PRICE_ADJUSTMENT),
            cache_status="cached",
            retrieved_at=meta.get("retrieved_at", ""),
            requested_start=requested_start.isoformat(),
            requested_end=effective_end.isoformat(),
            available_start=meta.get("available_start"),
            available_end=meta.get("available_end"),
            fingerprint=meta.get("fingerprint", ""),
            warnings=[],
            metadata=meta,
        )

    def _find_best_cache(
        self, symbol: str, start: date, end: date
    ) -> MarketDataResult | None:
        best: MarketDataResult | None = None
        best_overlap = -1
        for meta_path in self.cache_dir.glob("*.meta.json"):
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                if meta.get("symbol") != symbol:
                    continue
                if meta.get("price_adjustment") != PRICE_ADJUSTMENT:
                    continue
                csv_path = meta_path.with_suffix("").with_suffix(".csv")
                # meta is *.meta.json → stem handling
                csv_path = Path(str(meta_path).replace(".meta.json", ".csv"))
                if not csv_path.exists():
                    continue
                result = self._load_cache(csv_path, meta_path, start, end)
                avail_s = date.fromisoformat(result.available_start) if result.available_start else None
                avail_e = date.fromisoformat(result.available_end) if result.available_end else None
                if not avail_s or not avail_e:
                    continue
                overlap_start = max(start, avail_s)
                overlap_end = min(end, avail_e)
                overlap = (overlap_end - overlap_start).days
                if overlap > best_overlap and overlap > 30:
                    best_overlap = overlap
                    best = result
            except Exception:
                continue
        return best

    def slice_for_backtest(
        self, result: MarketDataResult, start: date, end: date
    ) -> pd.DataFrame:
        df = result.df.copy()
        mask = (df["date"].dt.date >= start) & (df["date"].dt.date <= end)
        sliced = df.loc[mask].copy()
        if sliced.empty:
            raise MarketDataError(
                "MARKET_DATA_RANGE",
                "No observations fall within the requested backtest window.",
            )
        return sliced.reset_index(drop=True)

    def bars_payload(self, df: pd.DataFrame) -> list[dict[str, Any]]:
        rows = []
        for _, r in df.iterrows():
            vol = r["volume"]
            volume = None if pd.isna(vol) else float(vol)
            rows.append(
                {
                    "date": r["date"].date().isoformat(),
                    "open": float(r["open"]),
                    "high": float(r["high"]),
                    "low": float(r["low"]),
                    "close": float(r["close"]),
                    "volume": volume,
                }
            )
        return rows

    def compute_indicators(
        self,
        df: pd.DataFrame,
        *,
        sma_periods: list[int] | None = None,
        ema_periods: list[int] | None = None,
        rsi_period: int | None = None,
    ) -> dict[str, list[float | None]]:
        out: dict[str, list[float | None]] = {}
        close = df["close"]
        for p in sma_periods or []:
            out[f"sma_{p}"] = series_to_nullable_list(sma(close, p))
        for p in ema_periods or []:
            out[f"ema_{p}"] = series_to_nullable_list(ema(close, p))
        if rsi_period:
            out[f"rsi_{rsi_period}"] = series_to_nullable_list(rsi(close, rsi_period))
        return out
