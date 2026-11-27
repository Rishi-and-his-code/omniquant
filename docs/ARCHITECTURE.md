# OmniQuant Architecture

## Separation of concerns

| Responsibility | Owner |
|----------------|-------|
| Natural-language understanding → Strategy DSL | AI provider (optional) |
| Strategy DSL validation | Pydantic models |
| Market data retrieval / cache | `MarketDataService` + yfinance |
| Indicators (SMA / EMA / RSI) | Pandas / NumPy |
| Trade simulation & metrics | `BacktestEngine` + `performance_metrics` |
| Research report narrative | AI provider (optional) |
| Persistence | SQLite via SQLAlchemy |

AI never fabricates metrics and never executes arbitrary code. All numeric results come from the deterministic engine.

## Runtime layouts

### Local development

- Frontend: Vite on `:5173` with `/api` proxy → backend
- Backend: Uvicorn / FastAPI on `:8000`

### Docker (evaluation)

- Single container `omniquant:0.1.0`
- FastAPI serves `/api/*` and compiled SPA assets
- Persistent volume `omniquant-data` for SQLite + CSV cache

## Execution policy

1. Indicator evaluated at daily close  
2. Signal scheduled for next session  
3. Fill at next open ± slippage  
4. Fees applied on both sides  
5. Whole-share, long-only, one position at a time  

## Data

- Source: Yahoo Finance via yfinance (`auto_adjust=True`)
- Cache: CSV + JSON metadata under `data/cache/`
- Warm-up bars fetched for indicators but excluded from equity history before `start_date`
