# Presentation-Ready Verified Information

Final mid-evaluation evidence for OmniQuant.  
**Source of truth:** live verification on `main` after evaluation-readiness work (28 Nov 2026).

---

## Actual project architecture

| Layer | Verified technology |
|-------|---------------------|
| Frontend | React 19, TypeScript, Vite 8, Tailwind CSS 4, Lucide, React Router, Plotly |
| Backend | Python 3.11, FastAPI, Uvicorn, Pydantic v2, SQLAlchemy 2 |
| Market data | Yahoo Finance **chart API** primary → yfinance fallback → CSV cache under `data/cache/` |
| Indicators | Shared `indicators.py` (SMA, EMA, Wilder RSI) |
| Strategy DSL | Validated templates: `sma_crossover`, `ema_crossover`, `rsi_mean_reversion` |
| Backtesting | Custom deterministic event-driven engine; next-open execution; long-only whole shares |
| AI | OpenAI-compatible OmniRoute (`CODING`); optional OpenRouter chat-model fallback |
| DB | SQLite (`users`, `instruments`, `strategies`, `strategy_versions`, `backtest_runs`, `backtest_trades`, `ai_reports`) |
| Deploy | Docker image `omniquant:0.1.0`; Compose bind-mounts `./data`; AI via `host.docker.internal:20128` |

---

## Actual market-data pipeline

1. Prefer covering **local CSV cache** (`cache_only` available for evaluation).
2. Else Yahoo chart API → yfinance fallback.
3. Validate OHLCV; adjusted-close basis.
4. Demo caches: RELIANCE.NS / TCS.NS / INFY.NS, ~2022-10-03 → 2025-12-31 (802 rows).

Primary demo window 2023-01-01 → 2025-12-31 yields **740** display bars for RELIANCE with cache-only fetch.

---

## Actual strategy methodology

| Type | Entry | Exit |
|------|-------|------|
| `sma_crossover` | Fast SMA crosses above slow | Fast crosses below slow |
| `ema_crossover` | Fast EMA crosses above slow | Fast crosses below slow |
| `rsi_mean_reversion` | RSI crosses below lower | RSI crosses above upper |

**Live AI-generated DSL example:**

```json
{
  "schema_version": 1,
  "name": "EMA Crossover",
  "strategy_type": "ema_crossover",
  "parameters": { "fast_period": 20, "slow_period": 50 },
  "position_type": "long_only"
}
```

---

## Actual backtesting methodology

- Signal at close → execute next session **open** ± slippage.
- Fees included in affordability; no negative cash; ≤1 open long position.
- Open end positions marked to final close (not force-closed).
- Benchmark: same capital/fees/slippage buy-and-hold.

---

## Verified primary demonstration backtest

| Field | Value |
|-------|-------|
| Backtest ID | **7** (cache-only re-run; matches prior #5/#6 economics) |
| Strategy | AI Generated — EMA 20/50 Demo |
| Instrument | RELIANCE.NS |
| Dates | 2023-01-01 → 2025-12-31 |
| Capital / alloc | ₹100,000 / 100% |
| Cost / slip | 0.10% / 0.05% per side |
| Cache | **cached** (network skipped) |
| Final equity | ₹115,972.01 |
| Net P&L | ₹15,972.01 |
| Total return | **+15.97%** |
| Max drawdown | **21.93%** |
| Sharpe | **0.43** |
| Win rate | **42.86%** |
| Profit factor | **1.50** |
| Trades | **7** |
| Buy & hold | **+34.63%** |
| Open position | 68 shares from 2025-10-23 |

---

## Verified secondary demonstration backtest

| Field | Value |
|-------|-------|
| Backtest ID | **8** |
| Strategy | OmniQuant — EMA 10/30 Comparison |
| Same period/costs as primary | yes |
| Total return | **+16.51%** |
| Completed trades | **12** |
| Final equity | ₹116,513.88 |

Changing EMA parameters produces a **new** deterministic calculation.

---

## Verified AI functionality

| Item | Status |
|------|--------|
| Provider | OmniRoute @ `:20128` |
| Model/combo | **`CODING`** |
| Strategy generation | **PASS** (~52s in final rehearsal) |
| Research analysis | **PASS** (report id **1** on backtest **6**) |
| Persistence | Reopened from Research History without a new model call |
| Limitation | Positive return but **underperformed** buy-and-hold; report states this correctly |

---

## Robustness testing (implemented)

- Endpoint: `POST /api/backtests/sensitivity`
- UI: Backtest Lab → Parameter sensitivity
- Default grid: fast 10/20/30 × slow 40/50/60 (9 valid cells)
- Metric: total return % (also max drawdown / Sharpe selectable)
- Cache-only verified; **20/50 cell = +15.97%** (matches primary engine)

| Fast\\Slow | 40 | 50 | 60 |
|------------|-----|-----|-----|
| 10 | 13.86 | 17.96 | 6.75 |
| 20 | 19.10 | **15.97** | 15.93 |
| 30 | 15.19 | 24.89 | 32.02 |

Labelled as **in-sample** only — not future profitability.

---

## Engineering evidence

| Metric | Result |
|--------|--------|
| Branch | `main` |
| Backend tests | **50 passed** |
| Frontend | `tsc` + production build **PASS** |
| Docker | `omniquant:0.1.0` healthy |
| Offline demo | Cache-only market + backtest **PASS** |
| Screenshots | `docs/evaluation-evidence/screenshots/01`–`12` |

---

## Implementation-status matrix

| Area | Status |
|------|--------|
| Market explore + cache-only | Implemented & verified |
| Manual + AI strategies + DSL | Implemented & verified |
| Deterministic backtest + metrics/charts | Implemented & verified |
| AI analysis + report persistence | Implemented & verified |
| Demo presets | Implemented & verified |
| Parameter sensitivity | Implemented & verified |
| Paper trading / brokers / multi-asset | Deferred |
