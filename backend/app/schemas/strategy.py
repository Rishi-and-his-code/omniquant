"""Validated Strategy DSL and related API schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class SMACrossoverParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fast_period: int = Field(default=20, ge=2, le=250)
    slow_period: int = Field(default=50, ge=2, le=250)

    @model_validator(mode="after")
    def fast_lt_slow(self) -> SMACrossoverParams:
        if self.fast_period >= self.slow_period:
            raise ValueError("fast_period must be strictly smaller than slow_period")
        return self


class EMACrossoverParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fast_period: int = Field(default=20, ge=2, le=250)
    slow_period: int = Field(default=50, ge=2, le=250)

    @model_validator(mode="after")
    def fast_lt_slow(self) -> EMACrossoverParams:
        if self.fast_period >= self.slow_period:
            raise ValueError("fast_period must be strictly smaller than slow_period")
        return self


class RSIMeanReversionParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    period: int = Field(default=14, ge=2, le=250)
    lower: float = Field(default=30, ge=0, le=100)
    upper: float = Field(default=70, ge=0, le=100)

    @model_validator(mode="after")
    def lower_lt_upper(self) -> RSIMeanReversionParams:
        if self.lower >= self.upper:
            raise ValueError("lower RSI threshold must be strictly smaller than upper")
        return self


class SMACrossoverStrategy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    name: str = Field(min_length=1, max_length=200)
    strategy_type: Literal["sma_crossover"]
    parameters: SMACrossoverParams
    position_type: Literal["long_only"] = "long_only"


class EMACrossoverStrategy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    name: str = Field(min_length=1, max_length=200)
    strategy_type: Literal["ema_crossover"]
    parameters: EMACrossoverParams
    position_type: Literal["long_only"] = "long_only"


class RSIMeanReversionStrategy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    name: str = Field(min_length=1, max_length=200)
    strategy_type: Literal["rsi_mean_reversion"]
    parameters: RSIMeanReversionParams
    position_type: Literal["long_only"] = "long_only"


StrategyDSL = Annotated[
    Union[SMACrossoverStrategy, EMACrossoverStrategy, RSIMeanReversionStrategy],
    Field(discriminator="strategy_type"),
]


def parse_strategy_dsl(data: dict) -> SMACrossoverStrategy | EMACrossoverStrategy | RSIMeanReversionStrategy:
    """Parse and validate a strategy DSL dict."""
    strategy_type = data.get("strategy_type")
    if strategy_type == "sma_crossover":
        return SMACrossoverStrategy.model_validate(data)
    if strategy_type == "ema_crossover":
        return EMACrossoverStrategy.model_validate(data)
    if strategy_type == "rsi_mean_reversion":
        return RSIMeanReversionStrategy.model_validate(data)
    raise ValueError(f"Unsupported strategy_type: {strategy_type}")


def strategy_rules_text(dsl: SMACrossoverStrategy | EMACrossoverStrategy | RSIMeanReversionStrategy) -> dict[str, str]:
    """Human-readable entry/exit rules for UI display."""
    if dsl.strategy_type == "sma_crossover":
        p = dsl.parameters
        return {
            "entry": f"Fast SMA({p.fast_period}) crosses above Slow SMA({p.slow_period})",
            "exit": f"Fast SMA({p.fast_period}) crosses below Slow SMA({p.slow_period})",
        }
    if dsl.strategy_type == "ema_crossover":
        p = dsl.parameters
        return {
            "entry": f"Fast EMA({p.fast_period}) crosses above Slow EMA({p.slow_period})",
            "exit": f"Fast EMA({p.fast_period}) crosses below Slow EMA({p.slow_period})",
        }
    p = dsl.parameters  # type: ignore[assignment]
    return {
        "entry": f"RSI({p.period}) crosses below {p.lower}",
        "exit": f"RSI({p.period}) crosses above {p.upper}",
    }


def required_warmup(dsl: SMACrossoverStrategy | EMACrossoverStrategy | RSIMeanReversionStrategy) -> int:
    if dsl.strategy_type in ("sma_crossover", "ema_crossover"):
        return int(dsl.parameters.slow_period) + 5  # type: ignore[union-attr]
    return int(dsl.parameters.period) + 5  # type: ignore[union-attr]


class StrategyCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    dsl: dict

    @field_validator("dsl")
    @classmethod
    def validate_dsl(cls, v: dict) -> dict:
        parsed = parse_strategy_dsl(v)
        return parsed.model_dump()


class StrategyVersionCreateRequest(BaseModel):
    dsl: dict

    @field_validator("dsl")
    @classmethod
    def validate_dsl(cls, v: dict) -> dict:
        parsed = parse_strategy_dsl(v)
        return parsed.model_dump()


class StrategyVersionOut(BaseModel):
    id: int
    strategy_id: int
    version_number: int
    strategy_type: str
    dsl: dict
    rules: dict[str, str]
    created_at: datetime


class StrategyOut(BaseModel):
    id: int
    name: str
    description: str | None
    status: str
    created_at: datetime
    updated_at: datetime
    latest_version: StrategyVersionOut | None = None
    versions: list[StrategyVersionOut] = Field(default_factory=list)


class AIGenerateStrategyRequest(BaseModel):
    prompt: str = Field(min_length=5, max_length=2000)


class AIGenerateStrategyResponse(BaseModel):
    status: Literal["ok", "unsupported", "error"]
    message: str | None = None
    dsl: dict | None = None
    rules: dict[str, str] | None = None
    model_name: str | None = None
