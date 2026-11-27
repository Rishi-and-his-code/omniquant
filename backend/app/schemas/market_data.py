"""Market data and instrument schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class InstrumentOut(BaseModel):
    id: int
    symbol: str
    name: str
    instrument_type: str
    exchange: str
    currency: str
    is_tradable: bool

    model_config = {"from_attributes": True}


class OHLCVBar(BaseModel):
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None


class IndicatorSeries(BaseModel):
    name: str
    values: list[float | None]


class MarketDataResponse(BaseModel):
    instrument: InstrumentOut
    bars: list[OHLCVBar]
    indicators: dict[str, list[float | None]] = Field(default_factory=dict)
    source: str
    price_adjustment: str
    cache_status: str
    retrieved_at: str
    requested_start: str
    requested_end: str
    available_start: str | None
    available_end: str | None
    fingerprint: str
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
