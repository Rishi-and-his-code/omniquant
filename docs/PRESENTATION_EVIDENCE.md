# Presentation-Ready Verified Information

Use these facts to update the 16-slide mid-evaluation deck.  
**Source of truth:** live AI verification on `main` after OmniRoute Docker connectivity fix (28 Nov 2026).

---

## Actual technology stack (verified)

| Layer | Technology |
|-------|------------|
| Frontend | React 19, TypeScript, Vite 8, Tailwind CSS 4, Lucide icons, React Router 7, Plotly.js / react-plotly.js |
| Backend | Python 3.11, FastAPI, Uvicorn, Pydantic v2, SQLAlchemy 2 |
| Data | Pandas, NumPy; Yahoo Finance chart API (primary) + yfinance (fallback); CSV cache |
| DB | SQLite |
| AI | OpenAI-compatible client; OmniRoute primary (`CODING` combo) + optional OpenRouter chat-model fallback |
| Ops | Docker multi-stage image `omniquant:0.1.0`, Compose bind-mount `./data`; container OmniRoute URL via `AI_DOCKER_BASE_URL` / `host.docker.internal` |
| Tests | pytest (**46 passed**), frontend `tsc` + Vite production build |

**Not used:** VectorBT, Backtrader, TA-Lib, Redux, cloud brokers.

---

## Actual market-data pipeline

1. Request symbol + inclusive dates.  
2. Prefer covering **local CSV cache** when `refresh=false`.  
3. Else fetch Yahoo **chart API** with browser User-Agent; fallback **yfinance**.  
4. Validate OHLCV (positive finite prices, H/L consistency); do not fabricate missing bars.  
5. Price basis: **adjusted close scaling** (`adjusted_close_basis` / `adjusted_ohlc`).  
6. Label UI as historical adjusted data, not live quotes.  
7. Cache metadata includes symbol, ranges, fingerprint, retrieval timestamp, source.

**Cached demo instruments on this host:** RELIANCE.NS, TCS.NS, INFY.NS  
**Approx. coverage:** 2022-10-03 → 2025-12-31 (802 rows including warm-up); displayed window 2023-01-02 → 2025-12-31 = **740** daily bars for RELIANCE.

---

## Actual strategy methodology

Templates:

| Type | Entry | Exit | Defaults |
|------|-------|------|----------|
| `sma_crossover` | Fast SMA crosses above slow | Fast crosses below slow | 20 / 50 |
| `ema_crossover` | Fast EMA crosses above slow | Fast crosses below slow | 20 / 50 |
| `rsi_mean_reversion` | RSI crosses below lower | RSI crosses above upper | 14 / 30 / 70 |

**Indicators:** `backend/app/services/indicators.py`  
- SMA: rolling mean, min_periods=period  
- EMA: `ewm(span=period, adjust=False)`  
- RSI: Wilder smoothing  

**Real DSL example (from UI / API):**

```json
{
  "schema_version": 1,
  "name": "Demo EMA 20/50 UI",
  "strategy_type": "ema_crossover",
  "parameters": { "fast_period": 20, "slow_period": 50 },
  "position_type": "long_only"
}
```

Validation: Pydantic, `extra=forbid`, fast < slow, RSI lower < upper. Immutable `strategy_versions` rows.

---

## Actual backtesting methodology

| Aspect | Implementation |
|--------|----------------|
| Approach | Event-driven daily loop |
| Signal | At close using then-available indicators |
| Execution | Next trading day **open** ± slippage |
| Position | Long-only, whole shares, ≤1 open position |
| Fees | % of notional per side, included in sizing |
| Slippage | Buy `open*(1+s)`, sell `open*(1-s)` |
| Equity | Cash + qty × close |
| End open position | Marked to final close; not force-closed; not counted as completed trade |
| Benchmark | Same costs/sizing buy-and-hold, marked to market |

**Look-ahead check:** signal 2023-05-02 → buy 2023-05-03 at open×1.0005.

---

## Actual AI methodology (verified live)

| Item | Status |
|------|--------|
| Primary provider | OmniRoute on host port **20128** (`http://host.docker.internal:20128/v1` from Docker) |
| Model / combo | **`CODING`** (routes to an upstream chat model such as `gemini-3.8-flash-high`) |
| Fallback | OpenRouter optional; must be a **chat-completions** model. A previous “decisions” model id caused HTTP 400 and was cleared. |
| Minimal live chat | **PASS** from Mac host and from inside the OmniQuant container |
| Strategy generation | **PASS** — EMA 20/50, RSI 14/30/70, unsupported MACD/leverage/short correctly rejected |
| Analysis | **PASS** — report id **1** for backtest **6**; correctly states strategy underperformed buy-and-hold |
| Persistence | Report reopened from Research History after container recreate |
| Validation | Structured JSON (with JSON-mode retry fallback) → independent Pydantic Strategy DSL validation |
| No code execution | AI returns configuration JSON only |

**Generated EMA DSL (live):**

```json
{
  "schema_version": 1,
  "name": "ema_crossover",
  "strategy_type": "ema_crossover",
  "parameters": { "fast_period": 20, "slow_period": 50 },
  "position_type": "long_only"
}
```

**Root cause previously blocking AI:** Docker used `AI_BASE_URL=http://127.0.0.1:20128/v1` (unreachable inside the container), then fell back to an OpenRouter decisions-only model that rejected `/chat/completions` with HTTP 400 (“AI provider rejected the request.”).

**Slide wording:** “Natural-language strategy generation and research analysis run through a local OmniRoute OpenAI-compatible gateway; every DSL is validated before backtesting.”

---

## Recommended demonstration backtest (verified)

Use **Backtest ID 6** (AI-generated strategy) or **ID 5** (manual) — same economics on the same cache.

| Field | Value |
|-------|-------|
| Instrument | RELIANCE.NS |
| Strategy | AI Generated — EMA 20/50 Demo (`ema_crossover`) |
| Version | v1 |
| Parameters | fast=20, slow=50 |
| Dates | 2023-01-01 → 2025-12-31 |
| Candles in window | 740 |
| Data source | yahoo_chart_api (local cache) |
| Initial capital | ₹100,000 |
| Allocation | 100% |
| Txn cost | 0.10% / side |
| Slippage | 0.05% / side |
| Final equity | ₹115,972.01 |
| Net P&L | ₹15,972.01 |
| Total return | **+15.97%** |
| Max drawdown | **21.93%** |
| Sharpe (ann., rf=0) | **0.43** |
| Win rate | **42.86%** |
| Profit factor | **1.50** |
| Completed trades | **7** |
| Buy & hold | **+34.63%** |
| Open position | Yes — 68 shares, entry 2025-10-23, marked at final close |
| AI report | id **1**, model `CODING`, persisted |

**Do not** reuse “+11.97% / 5 trades” unless you explain it was an earlier shorter window (backtest #1).

---

## Engineering progress (verified numbers)

| Metric | Result |
|--------|--------|
| Git branch | `main` |
| Backend tests | **46 passed** |
| Frontend build | **PASS** |
| Docker image | `omniquant:0.1.0` ~**594 MB** |
| Container health | **healthy** |
| Core smoke | **PASS** (manual + AI path) |
| Live AI | **VERIFIED** (OmniRoute `CODING`) |

---

## Feature status for progress slide

| Area | Status |
|------|--------|
| Market explore + cache | Implemented & verified |
| Manual strategies + DSL + versions | Implemented & verified |
| Deterministic backtest + metrics + charts | Implemented & verified |
| Research history + restart persistence | Implemented & verified |
| Docker packaging | Implemented & verified |
| AI strategy generation | Implemented & **live verified** |
| AI research analysis + report persistence | Implemented & **live verified** |
| Robustness heatmap | Deferred (not in MVP demo) |
| Paper trading / brokers / intraday | Deferred (final product) |

---

## Screenshot locations (local, not auto-committed)

Directory: `docs/evaluation-evidence/screenshots/`

| File | Content |
|------|---------|
| `01-market-explorer.png` | RELIANCE cached chart + SMA/RSI |
| `02-manual-strategy-builder.png` | EMA DSL + rules |
| `03-ai-strategy-generation.png` | Live AI EMA 20/50 generation success |
| `04-strategy-dsl.png` | DSL preview after AI generation |
| `05-backtest-configuration.png` | Run config |
| `06-backtest-results.png` | Metrics + equity/drawdown |
| `07-equity-and-drawdown.png` | Same results view |
| `09-ai-research-report.png` | Saved AI report for backtest #6 |
| `11-research-history.png` | AI Reports tab with reopened report |
| `12-swagger-api.png` | FastAPI docs |

**Still optional:** trade history table (`08`). Robustness (`10`) N/A.

---

## Known limitations (say aloud)

- Adjusted OHLC research approximation, not exact exchange prints.  
- Strategy underperformed buy-and-hold in this RELIANCE sample — that is OK and honest (AI report states this correctly).  
- Yahoo live fetch may 429; demo should rely on cache.  
- OmniRoute must be running locally for live AI; Docker must use `host.docker.internal`, not container `127.0.0.1`.  
- `CODING` combo can take ~30–60s per generation — wait for the UI “Generating…” state.  
- Single instrument, long-only, daily bars.
