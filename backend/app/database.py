"""SQLAlchemy engine, session, and database initialization."""

from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timezone

from sqlalchemy import create_engine, event, select, text
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.config import get_settings

settings = get_settings()

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record) -> None:  # noqa: ARG001
    if settings.database_url.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


DEMO_USER = {
    "name": "OmniQuant Demo User",
    "email": "demo@omniquant.local",
}

SEED_INSTRUMENTS = [
    ("RELIANCE.NS", "Reliance Industries", "equity", "NSE", "INR", True),
    ("TCS.NS", "Tata Consultancy Services", "equity", "NSE", "INR", True),
    ("INFY.NS", "Infosys", "equity", "NSE", "INR", True),
    ("HDFCBANK.NS", "HDFC Bank", "equity", "NSE", "INR", True),
    ("ICICIBANK.NS", "ICICI Bank", "equity", "NSE", "INR", True),
    ("SBIN.NS", "State Bank of India", "equity", "NSE", "INR", True),
    ("ITC.NS", "ITC Limited", "equity", "NSE", "INR", True),
    ("^NSEI", "NIFTY 50", "index", "NSE", "INR", False),
    ("^NSEBANK", "NIFTY BANK", "index", "NSE", "INR", False),
]


def init_db() -> None:
    """Create tables and seed demo user + instruments (idempotent)."""
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)

    with SessionLocal() as db:
        from app.models import Instrument, User

        user = db.execute(select(User).where(User.email == DEMO_USER["email"])).scalar_one_or_none()
        if user is None:
            user = User(
                name=DEMO_USER["name"],
                email=DEMO_USER["email"],
                created_at=datetime.now(timezone.utc),
            )
            db.add(user)

        for symbol, name, itype, exchange, currency, tradable in SEED_INSTRUMENTS:
            existing = db.execute(
                select(Instrument).where(Instrument.symbol == symbol)
            ).scalar_one_or_none()
            if existing is None:
                db.add(
                    Instrument(
                        symbol=symbol,
                        name=name,
                        instrument_type=itype,
                        exchange=exchange,
                        currency=currency,
                        is_tradable=tradable,
                    )
                )
        db.commit()


def check_db() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
