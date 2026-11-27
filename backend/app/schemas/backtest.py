"""Backtest request/response and AI analysis schemas."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class BacktestCreateRequest(BaseModel):
    strategy_version_id: int
    symbol: str
    start_date: date
    end_date: date
    initial_capital: float = Field(default=100_000, gt=0, le=100_000_000)
    allocation_percent: float = Field(default=100, gt=0, le=100)
    transaction_cost_percent: float = Field(default=0.10, ge=0, le=5)
    slippage_percent: float = Field(default=0.05, ge=0, le=5)

    @model_validator(mode="after")
    def date_order(self) -> BacktestCreateRequest:
        if self.end_date <= self.start_date:
            raise ValueError("end_date must be after start_date")
        span = (self.end_date - self.start_date).days
        if span > 3650:
            raise ValueError("Backtest period cannot exceed ~10 years")
        return self


class TradeOut(BaseModel):
    id: int | None = None
    entry_signal_date: str
    entry_date: str
    exit_signal_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    quantity: int
    entry_fee: float
    exit_fee: float
    total_cost: float
    profit_loss: float
    return_percent: float


class OpenPositionOut(BaseModel):
    entry_signal_date: str
    entry_date: str
    quantity: int
    entry_price: float
    mark_price: float
    market_value: float
    unrealized_pnl: float
    note: str = (
        "Marked to final close; hypothetical future exit fees are not deducted."
    )


class CurvePoint(BaseModel):
    date: str
    value: float


class TradeMarker(BaseModel):
    date: str
    price: float
    side: Literal["buy", "sell"]
    quantity: int


class PerformanceMetrics(BaseModel):
    initial_capital: float
    final_equity: float
    net_profit_loss: float
    total_return_percent: float
    max_drawdown_percent: float
    completed_trades: int
    win_rate_percent: float | None
    profit_factor: float | None
    sharpe_ratio: float | None
    buy_and_hold_return_percent: float | None
    notes: list[str] = Field(default_factory=list)


class BacktestResultOut(BaseModel):
    id: int
    status: str
    strategy_version_id: int
    strategy_name: str | None = None
    strategy_type: str | None = None
    strategy_version_number: int | None = None
    symbol: str
    instrument_name: str | None = None
    start_date: str
    end_date: str
    initial_capital: float
    allocation_percent: float
    transaction_cost_percent: float
    slippage_percent: float
    execution_policy: str
    price_basis: str
    metrics: PerformanceMetrics | None = None
    equity_curve: list[CurvePoint] = Field(default_factory=list)
    drawdown_curve: list[CurvePoint] = Field(default_factory=list)
    benchmark_curve: list[CurvePoint] = Field(default_factory=list)
    trades: list[TradeOut] = Field(default_factory=list)
    open_position: OpenPositionOut | None = None
    trade_markers: list[TradeMarker] = Field(default_factory=list)
    chart_data: list[dict[str, Any]] = Field(default_factory=list)
    data_metadata: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    error_message: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


class BacktestSummaryOut(BaseModel):
    id: int
    status: str
    symbol: str
    strategy_name: str | None
    strategy_type: str | None
    strategy_version_number: int | None
    start_date: str
    end_date: str
    initial_capital: float
    total_return_percent: float | None
    max_drawdown_percent: float | None
    completed_trades: int | None
    created_at: datetime
    completed_at: datetime | None


class AIAnalysisReport(BaseModel):
    summary: str
    strengths: list[str]
    weaknesses: list[str]
    risk_observations: list[str]
    suggested_improvements: list[str]
    recommended_tests: list[str]
    limitations: list[str]


class AIReportOut(BaseModel):
    id: int
    backtest_id: int
    report_type: str
    report: AIAnalysisReport
    model_name: str
    created_at: datetime
    prompt: str | None = None
