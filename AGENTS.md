# OmniQuant — Agent Instructions

AI-assisted algorithmic trading research terminal (university minor-project MVP). Users explore Indian equity OHLCV data, build validated strategy templates (SMA/EMA crossover, RSI mean reversion), run deterministic long-only backtests, and optionally get AI research commentary. AI never calculates financial metrics — all numbers come from the deterministic engine.

## Project layout

```
backend/
  app/
    main.py            # FastAPI entrypoint, SPA fallback, CORS
    config.py          # pydantic-settings from .env
    database.py        # SQLAlchemy engine, seed data, get_db dependency
    models.py          # ORM: User, Instrument, Strategy, StrategyVersion,
                       #       BacktestRun, BacktestTrade, AIReport
    utils.py
    routes/            # ai, backtests, market_data, strategies
    schemas/           # Pydantic v2 request/response + Strategy DSL
    services/          # backtest_engine, indicators, market_data_service,
                       #   ai_provider, performance_metrics
  tests/               # pytest suite (synthetic OHLC fixtures)
  scripts/prepare_demo.py  # pre-cache market data for offline demo
  requirements.txt
frontend/
  src/
    pages/             # MarketExplorer, StrategyStudio, BacktestLab, ResearchHistory
    components/        # charts/, layout/, ui/
    services/api.ts    # REST client
    context/AppContext.tsx
    types/index.ts
  package.json         # Vite + React 19 + TypeScript + Tailwind v4 + Plotly
data/                  # runtime: SQLite DB + CSV cache (gitignored)
compose.yaml           # single-service Docker Compose
Dockerfile             # multi-stage: node build → python:3.11-slim
```

## Dev environment

Prerequisites: Python 3.11, Node.js 20+, npm.

```
cp .env.example .env
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt

# Terminal 1 — backend
cd backend && PYTHONPATH=. uvicorn app.main:app --reload --port 8000

# Terminal 2 — frontend
cd frontend && npm install && npm run dev
```

Frontend on :5173 proxies `/api` to :8000 (see `frontend/vite.config.ts`).

Docker (single container, evaluation mode):
```
docker compose up --build -d
# App + API at http://localhost:8000
```

## Build & test

```
# Backend tests (from repo root, venv active)
cd backend && PYTHONPATH=. pytest -q

# Frontend type-check + build
cd frontend && npm run build

# Frontend lint
cd frontend && npm run lint          # oxlint
```

Test fixtures use synthetic OHLC data and in-memory SQLite (`conftest.py` creates `tests/_tmp/`, overrides `get_db`). Never commit test DB files.

## Key env vars (.env)

| Variable | Required | Notes |
|----------|----------|-------|
| `AI_ENABLED` | no | `true` to enable AI routes |
| `AI_BASE_URL` | if AI | OmniRoute gateway, default `http://127.0.0.1:20128/v1` |
| `AI_API_KEY` | if AI | OmniRoute key, server-side only, never commit |
| `AI_MODEL` | if AI | model id served by OmniRoute |
| `AI_FALLBACK_BASE_URL` | if fallback | OpenRouter, used only after OmniRoute fails or times out |
| `AI_FALLBACK_API_KEY` | if fallback | OpenRouter key, server-side only, never commit |
| `AI_FALLBACK_MODEL` | if fallback | OpenRouter model id |
| `DATA_DIR` | no | defaults to `./data` |
| `DATABASE_URL` | no | defaults to `sqlite:///./data/omniquant.db` |

`ai_configured` is true when AI is enabled and either OmniRoute (`AI_BASE_URL`, `AI_API_KEY`, `AI_MODEL`) or OpenRouter (`AI_FALLBACK_*`) is complete. Health never returns a key. A successful unsupported or invalid model answer does not switch providers.

## Conventions

- **Backend imports**: `from app.config import ...`, `from app.services.X import ...`. PYTHONPATH must include `backend/`.
- **Strategy DSL**: three types only (`sma_crossover`, `ema_crossover`, `rsi_mean_reversion`). Validated via discriminated-union Pydantic models in `schemas/strategy.py`. Extra fields forbidden. Periods 2–250, fast < slow, lower < upper within 0–100.
- **Execution policy**: signal at close → execute next open ± slippage. Warm-up bars excluded from equity history. Final-bar signals do not execute.
- **Percent convention**: user-facing percentages (e.g. 0.10 means 0.10%) converted to fractions (÷100) inside the engine.
- **Errors**: all API errors wrapped in `{"error": {"code": "...", "message": "...", "details": ...}}`.
- **Models**: SQLAlchemy 2.0 `Mapped[]` + `mapped_column` style. `from __future__ import annotations` in every module.
- **Frontend**: React Router, `clsx` for classnames, Lucide icons, `react-plotly.js` for charts. Tailwind v4 via `@tailwindcss/vite` plugin.
- **DB seeding**: `init_db()` in `database.py` creates demo user + 9 instruments (7 equities, 2 indices) on startup. Indices are `is_tradable=False`.

## Pitfalls

- **yfinance 429s**: Yahoo frequently rate-limits. Use `scripts/prepare_demo.py` to pre-cache data under `data/cache/`. The backtest flow must work offline from cache.
- **PYTHONPATH**: backend tests and uvicorn both require `PYTHONPATH=.` when run from `backend/`. Without it, `from app.X` imports fail.
- **get_settings LRU cache**: `config.py` caches settings via `@lru_cache`. Tests must call `get_settings.cache_clear()` after changing env vars (see `conftest.py`).
- **SQLite test isolation**: `conftest.py` replaces the engine and `get_db` dependency per test via `app.dependency_overrides`. The override is cleared in fixture teardown — don't skip that.
- **Docker data persistence**: `compose.yaml` bind-mounts `./data` to `/app/data`. Never run `docker compose down -v` — it destroys the SQLite DB and cache.
- **Frontend static in Docker**: Vite build output goes to `frontend/dist/`, Docker copies it to `/app/backend/static/`. FastAPI serves it via SPA fallback in `main.py`. The `static/` dir won't exist in local dev — that's normal (API-only mode).
- **No authentication**: single demo user (id=1) hardcoded in seed. All routes assume user_id=1.
