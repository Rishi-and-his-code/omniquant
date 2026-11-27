"""Strategy CRUD and immutable versioning."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database import DEMO_USER, get_db
from app.models import Strategy, StrategyVersion, User
from app.schemas.strategy import (
    StrategyCreateRequest,
    StrategyOut,
    StrategyVersionCreateRequest,
    StrategyVersionOut,
    parse_strategy_dsl,
    strategy_rules_text,
)

router = APIRouter(prefix="/strategies", tags=["strategies"])


def _demo_user(db: Session) -> User:
    user = db.execute(select(User).where(User.email == DEMO_USER["email"])).scalar_one()
    return user


def _version_out(v: StrategyVersion) -> StrategyVersionOut:
    dsl = json.loads(v.dsl_json)
    parsed = parse_strategy_dsl(dsl)
    return StrategyVersionOut(
        id=v.id,
        strategy_id=v.strategy_id,
        version_number=v.version_number,
        strategy_type=v.strategy_type,
        dsl=dsl,
        rules=strategy_rules_text(parsed),
        created_at=v.created_at,
    )


def _strategy_out(s: Strategy, include_versions: bool = True) -> StrategyOut:
    versions = sorted(s.versions, key=lambda x: x.version_number)
    version_outs = [_version_out(v) for v in versions] if include_versions else []
    latest = version_outs[-1] if version_outs else None
    return StrategyOut(
        id=s.id,
        name=s.name,
        description=s.description,
        status=s.status,
        created_at=s.created_at,
        updated_at=s.updated_at,
        latest_version=latest,
        versions=version_outs,
    )


@router.get("", response_model=list[StrategyOut])
def list_strategies(db: Session = Depends(get_db)) -> list[StrategyOut]:
    rows = (
        db.execute(
            select(Strategy)
            .options(selectinload(Strategy.versions))
            .order_by(Strategy.updated_at.desc())
        )
        .scalars()
        .all()
    )
    return [_strategy_out(s) for s in rows]


@router.post("", response_model=StrategyOut, status_code=201)
def create_strategy(body: StrategyCreateRequest, db: Session = Depends(get_db)) -> StrategyOut:
    user = _demo_user(db)
    parsed = parse_strategy_dsl(body.dsl)
    now = datetime.now(timezone.utc)
    strategy = Strategy(
        user_id=user.id,
        name=body.name,
        description=body.description,
        status="active",
        created_at=now,
        updated_at=now,
    )
    db.add(strategy)
    db.flush()
    version = StrategyVersion(
        strategy_id=strategy.id,
        version_number=1,
        strategy_type=parsed.strategy_type,
        dsl_json=json.dumps(parsed.model_dump()),
        created_at=now,
    )
    db.add(version)
    db.commit()
    db.refresh(strategy)
    strategy = db.execute(
        select(Strategy)
        .options(selectinload(Strategy.versions))
        .where(Strategy.id == strategy.id)
    ).scalar_one()
    return _strategy_out(strategy)


@router.get("/{strategy_id}", response_model=StrategyOut)
def get_strategy(strategy_id: int, db: Session = Depends(get_db)) -> StrategyOut:
    strategy = db.execute(
        select(Strategy)
        .options(selectinload(Strategy.versions))
        .where(Strategy.id == strategy_id)
    ).scalar_one_or_none()
    if strategy is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "STRATEGY_NOT_FOUND", "message": "Strategy not found", "details": None},
        )
    return _strategy_out(strategy)


@router.post("/{strategy_id}/versions", response_model=StrategyVersionOut, status_code=201)
def create_version(
    strategy_id: int,
    body: StrategyVersionCreateRequest,
    db: Session = Depends(get_db),
) -> StrategyVersionOut:
    strategy = db.execute(
        select(Strategy)
        .options(selectinload(Strategy.versions))
        .where(Strategy.id == strategy_id)
    ).scalar_one_or_none()
    if strategy is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "STRATEGY_NOT_FOUND", "message": "Strategy not found", "details": None},
        )
    parsed = parse_strategy_dsl(body.dsl)
    next_num = max((v.version_number for v in strategy.versions), default=0) + 1
    now = datetime.now(timezone.utc)
    version = StrategyVersion(
        strategy_id=strategy.id,
        version_number=next_num,
        strategy_type=parsed.strategy_type,
        dsl_json=json.dumps(parsed.model_dump()),
        created_at=now,
    )
    strategy.updated_at = now
    # Optionally sync name from DSL
    if parsed.name and parsed.name != strategy.name:
        strategy.name = parsed.name
    db.add(version)
    db.commit()
    db.refresh(version)
    return _version_out(version)
