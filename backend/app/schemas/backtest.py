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
    cache_only: bool = False

    @model_validator(mode="after")
    def date_order(self) -> BacktestCreateRequest:
        if self.end_date <= self.start_date:
            raise ValueError("end_date must be after start_date")
        span = (self.end_date - self.start_date).days
        if span > 3650:
            raise ValueError("Backtest period cannot exceed ~10 years")
        return self


class SensitivityRequest(BaseModel):
    symbol: str
    start_date: date
    end_date: date
    strategy_type: Literal["sma_crossover", "ema_crossover"] = "ema_crossover"
    fast_periods: list[int] = Field(default_factory=lambda: [10, 20, 30])
    slow_periods: list[int] = Field(default_factory=lambda: [40, 50, 60])
    initial_capital: float = Field(default=100_000, gt=0, le=100_000_000)
    allocation_percent: float = Field(default=100, gt=0, le=100)
    transaction_cost_percent: float = Field(default=0.10, ge=0, le=5)
    slippage_percent: float = Field(default=0.05, ge=0, le=5)
    cache_only: bool = True

    @field_validator("fast_periods", "slow_periods")
    @classmethod
    def periods_bounds(cls, values: list[int]) -> list[int]:
        if not values:
            raise ValueError("At least one period is required")
        if len(values) > 10:
            raise ValueError("At most 10 periods per axis")
        cleaned: list[int] = []
        for v in values:
            if not isinstance(v, int) or v < 2 or v > 250:
                raise ValueError("Periods must be integers between 2 and 250")
            if v not in cleaned:
                cleaned.append(v)
        return cleaned

    @model_validator(mode="after")
    def validate_grid(self) -> SensitivityRequest:
        if self.end_date <= self.start_date:
            raise ValueError("end_date must be after start_date")
        valid = sum(1 for f in self.fast_periods for s in self.slow_periods if f < s)
        if valid == 0:
            raise ValueError("No valid fast/slow combinations (need fast < slow)")
        if valid > 25:
            raise ValueError("Grid exceeds the maximum of 25 valid combinations")
        return self


class SensitivityCell(BaseModel):
    fast_period: int
    slow_period: int
    valid: bool
    total_return_percent: float | None = None
    max_drawdown_percent: float | None = None
    sharpe_ratio: float | None = None
    completed_trades: int | None = None
    final_equity: float | None = None
    error: str | None = None


class SensitivityResponse(BaseModel):
    symbol: str
    strategy_type: str
    start_date: str
    end_date: str
    fast_periods: list[int]
    slow_periods: list[int]
    metric_note: str = "In-sample historical parameter sensitivity analysis."
    disclaimer: str = (
        "Best historical parameters do not establish future profitability. "
        "This is not walk-forward or out-of-sample research."
    )
    cache_status: str | None = None
    data_source: str | None = None
    combinations_evaluated: int
    cells: list[SensitivityCell]


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
