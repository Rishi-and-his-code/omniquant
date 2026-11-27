"""Pytest fixtures."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Configure test environment before importing app
TEST_DIR = Path(__file__).resolve().parent / "_tmp"
TEST_DIR.mkdir(exist_ok=True)
os.environ["DATA_DIR"] = str(TEST_DIR)
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DIR / 'test.db'}"
os.environ["AI_ENABLED"] = "false"
os.environ["AI_API_KEY"] = ""
os.environ["AI_MODEL"] = ""

from app.config import get_settings

get_settings.cache_clear()

from app.database import Base, get_db, init_db
from app.main import app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "omniquant_test.db"
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("AI_ENABLED", "false")
    get_settings.cache_clear()

    # Rebuild engine binding for this test DB
    from app import database as dbmod
    from app import models  # noqa: F401

    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    # Seed
    dbmod.engine = engine
    dbmod.SessionLocal = TestingSession
    init_db()

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    get_settings.cache_clear()
