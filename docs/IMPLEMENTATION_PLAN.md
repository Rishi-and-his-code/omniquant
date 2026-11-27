# OmniQuant MVP — Implementation Plan

**Status:** Core MVP delivered  
**Version:** 0.1.0  
**Date:** 2026-11-27  
**Team:** Rishi Kachhadia, Shivansh Patel, Priyanshi Joshi

## Architecture

```
Browser → React Research Terminal → FastAPI (/api) →
  MarketDataService (Yahoo chart API + yfinance fallback + CSV cache)
  StrategyBuilder (Pydantic DSL + optional AI)
  BacktestEngine (deterministic, Pandas/NumPy)
  AIAnalysisService (OpenAI-compatible)
  SQLite persistence
```

AI is separated from deterministic financial calculations. Metrics always come from the backtest engine.

## Implementation phases

| Phase | Focus | Status |
|-------|-------|--------|
| 0 | Environment, Git, GitHub, plan | Done |
| 1 | Backend foundation + market data | Done |
| 2 | Indicators + Strategy DSL | Done |
| 3 | Deterministic backtesting | Done |
| 4 | Frontend research terminal | Done |
| 5 | AI integration | Done (optional; works when configured) |
| 6 | Docker packaging | Done |
| 7 | Optional sensitivity analysis | Deferred |
| 8 | Tests, docs, final validation | Done |

## Feature checklist (P0)

- [x] Historical market-data retrieval (Yahoo chart API + yfinance fallback)
- [x] Local CSV market-data cache
- [x] Interactive Plotly candlestick charts
- [x] SMA, EMA, RSI indicators
- [x] Manual strategy builder
- [x] Validated Strategy DSL
- [x] AI-assisted strategy generation (provider-dependent)
- [x] Deterministic backtesting engine
- [x] Performance metrics
- [x] Equity curve and trade history
- [x] SQLite persistence
- [x] Frontend/backend integration
- [x] Docker packaging
- [x] Private GitHub repository

## Testing

- Backend: 29 pytest tests passing (indicators, DSL, engine, API)
- Frontend: `tsc` + Vite production build passing
- Docker: `omniquant:0.1.0` builds; compose health check configured
- Genuine data: RELIANCE/TCS/INFY cached locally; sample EMA backtest completed (~12% return on RELIANCE 2023–2024)

## Known limitations

- Yahoo Finance can rate-limit; cache-first retrieval mitigates evaluation risk
- yfinance alone is unreliable in this environment; chart API preferred
- Single instrument per backtest; long-only; daily bars only
- AI requires user-supplied OpenAI-compatible credentials
- P2 sensitivity heatmap deferred

## Environment notes

- Host: macOS arm64
- Python 3.11 venv; Node 26 / npm 11
- GitHub account: `Rishi-and-his-code`
