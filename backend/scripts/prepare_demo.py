#!/usr/bin/env python3
"""Prepare local demo cache, seed strategies, and optionally run a sample backtest."""

from __future__ import annotations

import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

# Ensure backend package is importable; persist data at repo root ./data
BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

import os

os.environ.setdefault("DATA_DIR", str(PROJECT_ROOT / "data"))
os.environ.setdefault("DATABASE_URL", f"sqlite:///{PROJECT_ROOT / 'data' / 'omniquant.db'}")

from app.config import get_settings

get_settings.cache_clear()

from app.database import SessionLocal, init_db
from app.models import Instrument, Strategy, StrategyVersion, User
from app.schemas.strategy import parse_strategy_dsl
from app.services.backtest_engine import BacktestConfig, BacktestEngine
from app.services.market_data_service import MarketDataError, MarketDataService
from sqlalchemy import select


DEMO_SYMBOLS = ["RELIANCE.NS", "TCS.NS", "INFY.NS"]
START = date(2023, 1, 1)
END = date(2025, 12, 31)

TEMPLATES = [
    {
        "name": "Demo SMA 20/50",
        "dsl": {
            "schema_version": 1,
            "name": "Demo SMA 20/50",
            "strategy_type": "sma_crossover",
            "parameters": {"fast_period": 20, "slow_period": 50},
            "position_type": "long_only",
        },
    },
    {
        "name": "Demo EMA 20/50",
        "dsl": {
            "schema_version": 1,
            "name": "Demo EMA 20/50",
            "strategy_type": "ema_crossover",
            "parameters": {"fast_period": 20, "slow_period": 50},
            "position_type": "long_only",
        },
    },
    {
        "name": "Demo RSI 14",
        "dsl": {
            "schema_version": 1,
            "name": "Demo RSI 14",
            "strategy_type": "rsi_mean_reversion",
            "parameters": {"period": 14, "lower": 30, "upper": 70},
            "position_type": "long_only",
        },
    },
]


def main() -> int:
    settings = get_settings()
    print(f"Data dir: {settings.data_dir.resolve()}")
    init_db()
    svc = MarketDataService(settings)

    ok = []
    fail = []
    for symbol in DEMO_SYMBOLS:
        print(f"\nFetching {symbol} {START} → {END} (+warmup)...")
        try:
            result = svc.get_history(symbol, START, END, refresh=True, warmup_days=80)
            print(
                f"  OK  rows={len(result.df)} cache={result.cache_status} "
                f"range={result.available_start}→{result.available_end}"
            )
            ok.append(symbol)
        except MarketDataError as exc:
            print(f"  FAIL {exc.code}: {exc.message}")
            fail.append(symbol)

    with SessionLocal() as db:
        user = db.execute(select(User)).scalars().first()
        for tmpl in TEMPLATES:
            existing = db.execute(
                select(Strategy).where(Strategy.name == tmpl["name"])
            ).scalar_one_or_none()
            if existing:
                print(f"Strategy already exists: {tmpl['name']}")
                continue
            parsed = parse_strategy_dsl(tmpl["dsl"])
            now = datetime.now(timezone.utc)
            s = Strategy(
                user_id=user.id,
                name=tmpl["name"],
                description="Prepared demo template",
                status="active",
                created_at=now,
                updated_at=now,
            )
            db.add(s)
            db.flush()
            db.add(
                StrategyVersion(
                    strategy_id=s.id,
                    version_number=1,
                    strategy_type=parsed.strategy_type,
                    dsl_json=json.dumps(parsed.model_dump()),
                    created_at=now,
                )
            )
            print(f"Created strategy: {tmpl['name']}")
        db.commit()

        # Optional reproducible demo backtest if RELIANCE cached
        if "RELIANCE.NS" in ok:
            md = svc.get_history("RELIANCE.NS", START, END, warmup_days=80)
            strategy = parse_strategy_dsl(TEMPLATES[1]["dsl"])
            engine = BacktestEngine()
            result = engine.run(
                md.df,
                BacktestConfig(
                    strategy=strategy,
                    start_date=START,
                    end_date=min(END, date.fromisoformat(md.available_end)),
                    initial_capital=100_000,
                ),
            )
            print("\nDemo backtest (EMA 20/50 on RELIANCE.NS):")
            print(f"  status={result.status}")
            print(f"  return={result.metrics['total_return_percent']:.2f}%")
            print(f"  trades={result.metrics['completed_trades']}")
            print(f"  max_dd={result.metrics['max_drawdown_percent']:.2f}%")

    print("\nSummary")
    print(f"  cached OK: {ok}")
    print(f"  failed: {fail}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
