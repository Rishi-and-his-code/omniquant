"""Backtest execution, history, and AI analysis routes."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database import DEMO_USER, get_db
from app.models import (
    AIReport,
    BacktestRun,
    BacktestTrade,
    Instrument,
    StrategyVersion,
    User,
)
from app.schemas.backtest import (
    AIAnalysisReport,
    AIReportOut,
    BacktestCreateRequest,
    BacktestResultOut,
    BacktestSummaryOut,
    CurvePoint,
    OpenPositionOut,
    PerformanceMetrics,
    TradeMarker,
    TradeOut,
)
from app.schemas.strategy import parse_strategy_dsl, required_warmup, strategy_rules_text
from app.services.ai_provider import AIModelProvider, AIProviderError
from app.services.backtest_engine import BacktestConfig, BacktestEngine
from app.services.market_data_service import MarketDataError, MarketDataService
from app.utils import json_dumps, sanitize_numbers

router = APIRouter(tags=["backtests"])


def _demo_user(db: Session) -> User:
    return db.execute(select(User).where(User.email == DEMO_USER["email"])).scalar_one()


def _serialize_result(run: BacktestRun) -> BacktestResultOut:
    metrics = json.loads(run.metrics_json) if run.metrics_json else None
    sv = run.strategy_version
    strategy_name = sv.strategy.name if sv and sv.strategy else None
    return BacktestResultOut(
        id=run.id,
        status=run.status,
        strategy_version_id=run.strategy_version_id,
        strategy_name=strategy_name,
        strategy_type=sv.strategy_type if sv else None,
        strategy_version_number=sv.version_number if sv else None,
        symbol=run.instrument.symbol,
        instrument_name=run.instrument.name,
        start_date=run.start_date.isoformat(),
        end_date=run.end_date.isoformat(),
        initial_capital=run.initial_capital,
        allocation_percent=run.allocation_percent,
        transaction_cost_percent=run.transaction_cost_percent,
        slippage_percent=run.slippage_percent,
        execution_policy=run.execution_policy,
        price_basis=run.price_basis,
        metrics=PerformanceMetrics(**metrics) if metrics else None,
        equity_curve=[CurvePoint(**p) for p in (json.loads(run.equity_curve_json or "[]"))],
        drawdown_curve=[CurvePoint(**p) for p in (json.loads(run.drawdown_curve_json or "[]"))],
        benchmark_curve=[CurvePoint(**p) for p in (json.loads(run.benchmark_curve_json or "[]"))],
        trades=[
            TradeOut(
                id=t.id,
                entry_signal_date=t.entry_signal_date.isoformat(),
                entry_date=t.entry_date.isoformat(),
                exit_signal_date=t.exit_signal_date.isoformat(),
                exit_date=t.exit_date.isoformat(),
                entry_price=t.entry_price,
                exit_price=t.exit_price,
                quantity=t.quantity,
                entry_fee=t.entry_fee,
                exit_fee=t.exit_fee,
                total_cost=t.total_cost,
                profit_loss=t.profit_loss,
                return_percent=t.return_percent,
            )
            for t in run.trades
        ],
        open_position=(
            OpenPositionOut(**json.loads(run.open_position_json))
            if run.open_position_json
            else None
        ),
        trade_markers=[
            TradeMarker(**m)
            for m in (
                json.loads(run.market_data_metadata_json or "{}").get("trade_markers") or []
            )
        ],
        chart_data=json.loads(run.chart_data_json or "[]"),
        data_metadata={
            k: v
            for k, v in json.loads(run.market_data_metadata_json or "{}").items()
            if k != "trade_markers"
        },
        warnings=json.loads(run.warnings_json or "[]"),
        error_message=run.error_message,
        created_at=run.created_at,
        completed_at=run.completed_at,
    )


@router.post("/backtests", response_model=BacktestResultOut, status_code=201)
def create_backtest(body: BacktestCreateRequest, db: Session = Depends(get_db)) -> BacktestResultOut:
    sv = db.execute(
        select(StrategyVersion)
        .options(selectinload(StrategyVersion.strategy))
        .where(StrategyVersion.id == body.strategy_version_id)
    ).scalar_one_or_none()
    if sv is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "STRATEGY_VERSION_NOT_FOUND",
                "message": "Strategy version not found",
                "details": None,
            },
        )

    instrument = db.execute(
        select(Instrument).where(Instrument.symbol == body.symbol)
    ).scalar_one_or_none()
    if instrument is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "INSTRUMENT_NOT_FOUND", "message": "Instrument not found", "details": None},
        )
    if not instrument.is_tradable:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "INSTRUMENT_NOT_TRADABLE",
                "message": f"{instrument.symbol} is an index and cannot be backtested as an equity in this MVP.",
                "details": None,
            },
        )

    now = datetime.now(timezone.utc)
    run = BacktestRun(
        strategy_version_id=sv.id,
        instrument_id=instrument.id,
        start_date=body.start_date,
        end_date=body.end_date,
        initial_capital=body.initial_capital,
        allocation_percent=body.allocation_percent,
        transaction_cost_percent=body.transaction_cost_percent,
        slippage_percent=body.slippage_percent,
        status="running",
        execution_policy="next_open",
        price_basis="adjusted_ohlc",
        created_at=now,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    try:
        dsl = parse_strategy_dsl(json.loads(sv.dsl_json))
        warmup = required_warmup(dsl)
        mds = MarketDataService()
        md = mds.get_history(
            instrument.symbol,
            body.start_date,
            body.end_date,
            warmup_days=warmup + 30,
        )
        engine = BacktestEngine()
        config = BacktestConfig(
            strategy=dsl,
            start_date=body.start_date,
            end_date=body.end_date,
            initial_capital=body.initial_capital,
            allocation_percent=body.allocation_percent,
            transaction_cost_percent=body.transaction_cost_percent,
            slippage_percent=body.slippage_percent,
        )
        result = engine.run(md.df, config)

        meta = {
            **md.metadata,
            "fingerprint": md.fingerprint,
            "cache_status": md.cache_status,
            "source": md.source,
            "price_adjustment": md.price_adjustment,
            "retrieved_at": md.retrieved_at,
            "trade_markers": result.trade_markers,
        }

        run.status = "completed"
        run.metrics_json = json_dumps(sanitize_numbers(result.metrics))
        run.equity_curve_json = json_dumps(sanitize_numbers(result.equity_curve))
        run.drawdown_curve_json = json_dumps(sanitize_numbers(result.drawdown_curve))
        run.benchmark_curve_json = json_dumps(sanitize_numbers(result.benchmark_curve))
        run.open_position_json = (
            json_dumps(sanitize_numbers(result.open_position)) if result.open_position else None
        )
        run.chart_data_json = json_dumps(sanitize_numbers(result.chart_data))
        run.warnings_json = json_dumps(result.warnings + md.warnings)
        run.market_data_fingerprint = md.fingerprint
        run.market_data_metadata_json = json_dumps(sanitize_numbers(meta))
        run.completed_at = datetime.now(timezone.utc)
        run.error_message = None

        for t in result.trades:
            db.add(
                BacktestTrade(
                    backtest_id=run.id,
                    instrument_id=instrument.id,
                    entry_signal_date=datetime.fromisoformat(t["entry_signal_date"]).date()
                    if isinstance(t["entry_signal_date"], str)
                    else t["entry_signal_date"],
                    entry_date=datetime.fromisoformat(t["entry_date"]).date()
                    if isinstance(t["entry_date"], str)
                    else t["entry_date"],
                    exit_signal_date=datetime.fromisoformat(t["exit_signal_date"]).date()
                    if isinstance(t["exit_signal_date"], str)
                    else t["exit_signal_date"],
                    exit_date=datetime.fromisoformat(t["exit_date"]).date()
                    if isinstance(t["exit_date"], str)
                    else t["exit_date"],
                    entry_price=t["entry_price"],
                    exit_price=t["exit_price"],
                    quantity=t["quantity"],
                    entry_fee=t["entry_fee"],
                    exit_fee=t["exit_fee"],
                    total_cost=t["total_cost"],
                    profit_loss=t["profit_loss"],
                    return_percent=t["return_percent"],
                    created_at=datetime.now(timezone.utc),
                )
            )
        db.commit()
    except MarketDataError as exc:
        run.status = "failed"
        run.error_message = exc.message
        run.completed_at = datetime.now(timezone.utc)
        db.commit()
        raise HTTPException(
            status_code=502,
            detail={"code": exc.code, "message": exc.message, "details": exc.details},
        ) from exc
    except Exception as exc:
        run.status = "failed"
        run.error_message = "Backtest execution failed."
        run.completed_at = datetime.now(timezone.utc)
        db.commit()
        raise HTTPException(
            status_code=500,
            detail={
                "code": "BACKTEST_FAILED",
                "message": "Backtest execution failed.",
                "details": {"reason": str(exc)},
            },
        ) from exc

    run = db.execute(
        select(BacktestRun)
        .options(
            selectinload(BacktestRun.trades),
            selectinload(BacktestRun.instrument),
            selectinload(BacktestRun.strategy_version).selectinload(StrategyVersion.strategy),
        )
        .where(BacktestRun.id == run.id)
    ).scalar_one()
    return _serialize_result(run)


@router.get("/backtests", response_model=list[BacktestSummaryOut])
def list_backtests(db: Session = Depends(get_db)) -> list[BacktestSummaryOut]:
    rows = (
        db.execute(
            select(BacktestRun)
            .options(
                selectinload(BacktestRun.instrument),
                selectinload(BacktestRun.strategy_version).selectinload(StrategyVersion.strategy),
            )
            .order_by(BacktestRun.created_at.desc())
        )
        .scalars()
        .all()
    )
    out: list[BacktestSummaryOut] = []
    for r in rows:
        metrics = json.loads(r.metrics_json) if r.metrics_json else {}
        sv = r.strategy_version
        out.append(
            BacktestSummaryOut(
                id=r.id,
                status=r.status,
                symbol=r.instrument.symbol,
                strategy_name=sv.strategy.name if sv and sv.strategy else None,
                strategy_type=sv.strategy_type if sv else None,
                strategy_version_number=sv.version_number if sv else None,
                start_date=r.start_date.isoformat(),
                end_date=r.end_date.isoformat(),
                initial_capital=r.initial_capital,
                total_return_percent=metrics.get("total_return_percent"),
                max_drawdown_percent=metrics.get("max_drawdown_percent"),
                completed_trades=metrics.get("completed_trades"),
                created_at=r.created_at,
                completed_at=r.completed_at,
            )
        )
    return out


@router.get("/backtests/{backtest_id}", response_model=BacktestResultOut)
def get_backtest(backtest_id: int, db: Session = Depends(get_db)) -> BacktestResultOut:
    run = db.execute(
        select(BacktestRun)
        .options(
            selectinload(BacktestRun.trades),
            selectinload(BacktestRun.instrument),
            selectinload(BacktestRun.strategy_version).selectinload(StrategyVersion.strategy),
        )
        .where(BacktestRun.id == backtest_id)
    ).scalar_one_or_none()
    if run is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "BACKTEST_NOT_FOUND", "message": "Backtest not found", "details": None},
        )
    return _serialize_result(run)


@router.post("/backtests/{backtest_id}/analyze", response_model=AIReportOut)
def analyze_backtest(backtest_id: int, db: Session = Depends(get_db)) -> AIReportOut:
    run = db.execute(
        select(BacktestRun)
        .options(
            selectinload(BacktestRun.trades),
            selectinload(BacktestRun.instrument),
            selectinload(BacktestRun.strategy_version).selectinload(StrategyVersion.strategy),
        )
        .where(BacktestRun.id == backtest_id)
    ).scalar_one_or_none()
    if run is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "BACKTEST_NOT_FOUND", "message": "Backtest not found", "details": None},
        )
    if run.status != "completed":
        raise HTTPException(
            status_code=400,
            detail={
                "code": "BACKTEST_NOT_COMPLETED",
                "message": "Only completed backtests can be analyzed.",
                "details": None,
            },
        )

    sv = run.strategy_version
    dsl = parse_strategy_dsl(json.loads(sv.dsl_json))
    metrics = json.loads(run.metrics_json or "{}")
    context = {
        "strategy_name": sv.strategy.name,
        "strategy_version": sv.version_number,
        "strategy_type": sv.strategy_type,
        "rules": strategy_rules_text(dsl),
        "instrument": {"symbol": run.instrument.symbol, "name": run.instrument.name},
        "period": {"start": run.start_date.isoformat(), "end": run.end_date.isoformat()},
        "configuration": {
            "initial_capital": run.initial_capital,
            "allocation_percent": run.allocation_percent,
            "transaction_cost_percent": run.transaction_cost_percent,
            "slippage_percent": run.slippage_percent,
            "execution_policy": run.execution_policy,
            "price_basis": run.price_basis,
        },
        "metrics": metrics,
        "completed_trades": len(run.trades),
        "trade_summary": [
            {
                "entry_date": t.entry_date.isoformat(),
                "exit_date": t.exit_date.isoformat(),
                "profit_loss": t.profit_loss,
                "return_percent": t.return_percent,
            }
            for t in run.trades[:25]
        ],
        "open_position": json.loads(run.open_position_json) if run.open_position_json else None,
        "warnings": json.loads(run.warnings_json or "[]"),
        "data_limitations": [
            "Prices are adjusted historical OHLC from yfinance (auto_adjust=True).",
            "Simulation is a simplified research approximation, not exact execution.",
            "Historical performance does not guarantee future results.",
        ],
    }

    provider = AIModelProvider()
    try:
        report, model, prompt = provider.generate_analysis(context)
    except AIProviderError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": exc.code, "message": exc.message, "details": exc.details},
        ) from exc

    user = _demo_user(db)
    row = AIReport(
        user_id=user.id,
        backtest_id=run.id,
        report_type="backtest_analysis",
        prompt=prompt,
        report_json=json_dumps(report),
        model_name=model,
        created_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return AIReportOut(
        id=row.id,
        backtest_id=row.backtest_id,
        report_type=row.report_type,
        report=AIAnalysisReport(**json.loads(row.report_json)),
        model_name=row.model_name,
        created_at=row.created_at,
        prompt=None,
    )


@router.get("/backtests/{backtest_id}/reports", response_model=list[AIReportOut])
def list_reports(backtest_id: int, db: Session = Depends(get_db)) -> list[AIReportOut]:
    rows = (
        db.execute(
            select(AIReport)
            .where(AIReport.backtest_id == backtest_id)
            .order_by(AIReport.created_at.desc())
        )
        .scalars()
        .all()
    )
    return [
        AIReportOut(
            id=r.id,
            backtest_id=r.backtest_id,
            report_type=r.report_type,
            report=AIAnalysisReport(**json.loads(r.report_json)),
            model_name=r.model_name,
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.get("/ai-reports", response_model=list[AIReportOut])
def list_all_reports(db: Session = Depends(get_db)) -> list[AIReportOut]:
    rows = (
        db.execute(select(AIReport).order_by(AIReport.created_at.desc()).limit(100))
        .scalars()
        .all()
    )
    return [
        AIReportOut(
            id=r.id,
            backtest_id=r.backtest_id,
            report_type=r.report_type,
            report=AIAnalysisReport(**json.loads(r.report_json)),
            model_name=r.model_name,
            created_at=r.created_at,
        )
        for r in rows
    ]
