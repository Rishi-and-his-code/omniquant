"""OmniQuant FastAPI application entrypoint."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.database import check_db, init_db
from app.routes import ai, backtests, market_data, strategies
from app.schemas.common import HealthResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("omniquant")

settings = get_settings()

app = FastAPI(
    title="OmniQuant API",
    description="AI-assisted algorithmic trading research and backtesting platform (MVP)",
    version=settings.app_version,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Narrow CORS for local Vite development
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api = FastAPI(title="OmniQuant API Internal")
# Mount routes under /api via include on main with prefix


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):  # noqa: ARG001
    detail = exc.detail
    if isinstance(detail, dict) and "code" in detail:
        return JSONResponse(status_code=exc.status_code, content={"error": detail})
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": "HTTP_ERROR", "message": str(detail), "details": None}},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):  # noqa: ARG001
    details = []
    for err in exc.errors():
        item = {k: v for k, v in err.items() if k != "ctx"}
        ctx = err.get("ctx")
        if ctx:
            item["ctx"] = {k: (str(v) if not isinstance(v, (str, int, float, bool, type(None))) else v) for k, v in ctx.items()}
        details.append(item)
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Request validation failed.",
                "details": details,
            }
        },
    )


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    logger.info("OmniQuant MVP v%s started", settings.app_version)


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok" if check_db() else "degraded",
        version=settings.app_version,
        database=check_db(),
        ai_configured=settings.ai_configured,
        ai_enabled=settings.ai_enabled,
    )


app.include_router(market_data.router, prefix="/api")
app.include_router(strategies.router, prefix="/api")
app.include_router(backtests.router, prefix="/api")
app.include_router(ai.router, prefix="/api")


# Static frontend (Docker / production). In local backend-only mode this may be absent.
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
if not STATIC_DIR.exists():
    # Also check /app/static for Docker layout
    alt = Path("/app/static")
    if alt.exists():
        STATIC_DIR = alt


def _mount_frontend() -> None:
    if not STATIC_DIR.exists():
        logger.info("No frontend static directory at %s — API-only mode", STATIC_DIR)
        return

    assets = STATIC_DIR / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        # Never swallow API routes (already registered above)
        if full_path.startswith("api/") or full_path in ("docs", "redoc", "openapi.json"):
            raise HTTPException(
                status_code=404,
                detail={"code": "NOT_FOUND", "message": "API route not found", "details": None},
            )
        candidate = STATIC_DIR / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        index = STATIC_DIR / "index.html"
        if index.exists():
            return FileResponse(index)
        raise HTTPException(status_code=404, detail="Not found")


_mount_frontend()
