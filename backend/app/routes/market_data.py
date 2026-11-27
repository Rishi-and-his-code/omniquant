"""Market data and instruments routes."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Instrument
from app.schemas.market_data import InstrumentOut, MarketDataResponse
from app.services.market_data_service import MarketDataError, MarketDataService

router = APIRouter(tags=["market-data"])


@router.get("/instruments", response_model=list[InstrumentOut])
def list_instruments(db: Session = Depends(get_db)) -> list[Instrument]:
    return list(db.execute(select(Instrument).order_by(Instrument.id)).scalars().all())


@router.get("/market-data", response_model=MarketDataResponse)
def get_market_data(
    symbol: str = Query(...),
    start_date: date = Query(...),
    end_date: date = Query(...),
    refresh: bool = Query(False),
    sma: list[int] | None = Query(None),
    ema: list[int] | None = Query(None),
    rsi_period: int | None = Query(None, ge=2, le=250),
    db: Session = Depends(get_db),
) -> MarketDataResponse:
    if end_date <= start_date:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_DATE_RANGE", "message": "end_date must be after start_date", "details": None},
        )
    if (end_date - start_date).days > 3650:
        raise HTTPException(
            status_code=400,
            detail={"code": "DATE_RANGE_TOO_LARGE", "message": "Requested range exceeds 10 years", "details": None},
        )

    instrument = db.execute(
        select(Instrument).where(Instrument.symbol == symbol)
    ).scalar_one_or_none()
    if instrument is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "INSTRUMENT_NOT_FOUND", "message": f"Unknown symbol: {symbol}", "details": None},
        )

    warmup = 0
    for p in (sma or []) + (ema or []):
        warmup = max(warmup, p + 5)
    if rsi_period:
        warmup = max(warmup, rsi_period + 5)

    svc = MarketDataService()
    try:
        result = svc.get_history(
            symbol,
            start_date,
            end_date,
            refresh=refresh,
            warmup_days=warmup,
        )
    except MarketDataError as exc:
        raise HTTPException(
            status_code=502 if exc.code == "MARKET_DATA_UNAVAILABLE" else 400,
            detail={"code": exc.code, "message": exc.message, "details": exc.details},
        ) from exc

    # Slice display to requested range (indicators computed on full frame then sliced)
    full = result.df
    mask = (full["date"].dt.date >= start_date) & (full["date"].dt.date <= end_date)
    # Cap incomplete day already handled; also filter to effective available
    display = full.loc[mask].copy().reset_index(drop=True)
    if display.empty:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "MARKET_DATA_RANGE",
                "message": "No observations in the requested date range.",
                "details": None,
            },
        )

    # Compute indicators on full history then align to display dates
    indicators_full = svc.compute_indicators(
        full, sma_periods=sma or [20, 50], ema_periods=ema or [20, 50], rsi_period=rsi_period or 14
    )
    date_set = set(display["date"].dt.date.tolist())
    indicators: dict[str, list[float | None]] = {}
    for name, values in indicators_full.items():
        aligned: list[float | None] = []
        for idx, row_date in enumerate(full["date"].dt.date.tolist()):
            if row_date in date_set:
                aligned.append(values[idx])
        indicators[name] = aligned

    return MarketDataResponse(
        instrument=InstrumentOut.model_validate(instrument),
        bars=svc.bars_payload(display),
        indicators=indicators,
        source=result.source,
        price_adjustment=result.price_adjustment,
        cache_status=result.cache_status,
        retrieved_at=result.retrieved_at or datetime.now(timezone.utc).isoformat(),
        requested_start=start_date.isoformat(),
        requested_end=end_date.isoformat(),
        available_start=display["date"].iloc[0].date().isoformat(),
        available_end=display["date"].iloc[-1].date().isoformat(),
        fingerprint=result.fingerprint,
        warnings=result.warnings,
        metadata=result.metadata,
    )
