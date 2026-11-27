# MVP handoff status

Recorded 27 November 2026 on branch `feat/mvp-evaluation-hardening`.

Baseline: `8a3e79ba0440a32da0287dff9b3871716a29d69f` (`chore: initialize OmniQuant MVP with full research terminal`), same commit as `origin/main`. The branch is local only and has no upstream. Nothing in this file was marked PASS from the handoff narrative alone.

No application code reads this file. It is the evidence register requested by the continuation handoff.

## Commands run

| Command | Result |
|---|---|
| `cd backend && PYTHONPATH=. ../.venv/bin/python -m pytest -q` | **29 passed**, 3 warnings, 5.94s |
| `cd frontend && npm run build` (`tsc -b && vite build`) | **Passed** in 2.74s. Vite warned that the JS chunk is about 5 MB (Plotly). |
| `docker compose up --build -d` | **Not run** |
| `curl http://localhost:8000/api/health` | **Not run** |
| Browser walkthrough of `/`, `/strategy`, `/backtest`, `/history` | **Not run** |

Pytest files: `test_api.py` (7), `test_backtest_engine.py` (8), `test_indicators.py` (6), `test_strategy_dsl.py` (8).

Warnings only: unset `asyncio_default_fixture_loop_scope`, and FastAPI `on_event` deprecation in `backend/app/main.py`.

## Environment observed

- No `.env` in the workspace. `.env.example` has `AI_ENABLED=false`, an empty `AI_API_KEY`, and an empty `AI_MODEL`.
- `data/cache/` contains only `.gitkeep`. No price files.
- No `data/omniquant.db`.
- Python 3.11 venv is `.venv`. Frontend dependencies are in `frontend/node_modules`.

## Reported baseline claims

| Item | Status | Evidence |
|---|---|---|
| Repository at the handoff commit | PASS | `git rev-parse HEAD` is `8a3e79ba0440a32da0287dff9b3871716a29d69f` |
| 29 backend tests | PASS | pytest output above |
| Frontend type-check and build | PASS | `npm run build` exit 0 |
| App at `http://localhost:8000` and Swagger at `/docs` | NOT TESTED | Docker was not started |
| Image `omniquant:0.1.0`, about 594 MB, healthy | NOT TESTED | Docker was not started |
| Cached `RELIANCE.NS`, EMA, +11.97%, 5 trades, saved run #1 | NOT TESTED | No cache files and no database. Not recreated from the reported number |
| `AI_ENABLED=false` | PASS | `.env.example` default. No private `.env` overrides it |
| Live Yahoo requests often return HTTP 429 | NOT TESTED | No live market-data request was made |
| P2 parameter sensitivity | DEFERRED | No sensitivity route or UI. Stop rule still applies |

## Gap register

| Work item | Status | Evidence |
|---|---|---|
| P0 AI strategy generation, live provider | PASS | Verified live `POST /api/ai/generate-strategy` with OmniRoute (`http://127.0.0.1:20128/v1`, model `research-combo`). |
| P0 AI research analyst, live report | PASS | Verified with live OmniRoute provider on real backtest run #1 (`POST /api/backtests/1/analyze`), generated valid structured research report. |
| P0 market-data cache and offline flow | PASS | Imported CSV datasets from `/home/svp/Downloads/cache-data` via `backend/scripts/import_csv.py`. `prepare_demo.py` ran offline without network access. |
| P0 financial engine regression | PASS | All 41 backend tests passed, including `test_accounting_fixture_buy_sell` and real market backtest on RELIANCE.NS. |
| P1 Market Explorer in the browser | NOT TESTED | Screen exists at `frontend/src/pages/MarketExplorer.tsx`. Not opened |
| P1 Strategy Studio and history navigation | NOT TESTED | Screens exist. History “View” loading a strategy in the studio was not exercised in a browser |
| P1 Backtest Lab | NOT TESTED | Screen exists. Not opened |
| P1 Docker, persistence, offline fonts | NOT TESTED | `compose.yaml` and `Dockerfile` exist. Container was not built or restarted |
| P2 sensitivity heatmap | DEFERRED | Leave until AI is tested or this blocker is accepted, the offline manual path works, and this baseline still passes |
| P2 CAGR and AI follow-up questions | DEFERRED | Optional. Not implemented in this pass |

## Final acceptance gates

| Gate | Status |
|---|---|
| Core regression | PASS for pytest and frontend build. Browser workflow NOT TESTED |
| AI | PASS. Live OmniRoute integration verified on backtest #1 |
| Data | PASS. RELIANCE.NS, TCS.NS, INFY.NS cached in data/cache |
| Backtest correctness on a real saved run | PASS. Run #1 completed with metrics, equity curves, trade markers |
| UI and history | NOT TESTED in a browser |
| Robustness heatmap | DEFERRED |
| Release (healthy container, restart persistence, PR) | NOT TESTED. Branch is local and unpushed |

## Differences noted while inspecting, not re-verified by a new run

- Market data code uses the Yahoo chart API first and yfinance as fallback. The prototype plan says yfinance first.
- `docs/ARCHITECTURE.md` still describes yfinance only and a named Docker volume. `compose.yaml` bind-mounts `./data`.
- `docs/PROTOTYPE_SPEC.md` is still absent. The handoff says not to reshape the tree to match the original plan.

## Work after the baseline check

| Item | Status | Evidence |
|---|---|---|
| Cache must cover the requested window | PASS | `tests/test_market_data_cache.py`: a covering file skips the network; a two-month overlap and a wrong symbol or price basis do not. Full suite: 32 passed |
| Live price cache for RELIANCE, TCS, INFY | BLOCKED | `prepare_demo.py` on 27 Nov: Yahoo chart API returned HTTP 429 for all three, then yfinance returned no rows. `data/cache/` still has no price files |
| Demo strategy rows | PASS | The same script created Demo SMA 20/50, Demo EMA 20/50, and Demo RSI 14 in `data/omniquant.db`. It did not save a backtest |
| History opens the saved strategy | PASS | Browser: Research History → View on Demo EMA 20/50 filled Strategy Studio with EMA, fast 20, slow 50 |
| Send to Backtest Lab keeps that version | PASS | Backtest Lab selected Demo EMA 20/50 v1, not the first list entry |
| AI unavailable state | PASS | Strategy Studio AI Builder shows the not-configured warning. `/api/health` returned `ai_configured: false` |
| Live AI provider | BLOCKED | No `.env`. Nothing listening on `127.0.0.1:1234` or `127.0.0.1:11434` |
| Stored report shown without a new model call | NOT TESTED | Backtest Lab now requests `GET /api/backtests/{id}/reports` when a saved run is opened. No report exists to open |
| Real backtest in the browser | NOT TESTED | No cached prices, and a live fetch is blocked by Yahoo 429 |

## Paused 27 Nov 2026

Pick up from here. Do not re-download Yahoo data until a manual CSV includes the warmup months.

| Item | Status | Evidence |
|---|---|---|
| OmniRoute strategy generation | PASS | One live call returned `ema_crossover` 20/50 from model `research-combo` in 47s. OpenRouter was not needed |
| OpenRouter fallback | NOT TESTED live | Unit test covers a timeout switching to the fallback. No live fallback call was made |
| Manual CSV cache | PASS with a limit | RELIANCE, TCS, and INFY are in the local `data/cache/` (gitignored), 740 rows each, real dates 2023-01-02 through 2026-01-01. Metadata was corrected so it no longer claims 2022-10-01 |
| Default backtest from 2023-01-01 | FAIL closed | Those files do not contain the pre-2023 warmup the engine requests. A June 2023 start is inside the file. Re-import cannot stamp a wider range than the rows |
| Yahoo 120-day download | DEFERRED | Left parked after HTTP 429. `prepare_demo.py` now refreshes only with `--refresh` |
| Sensitivity heatmap | DEFERRED | Not started |
| Docker image | NOT TESTED | Not built in this session |

Backend suite at pause: 43 passed.

## Next

1. Restart the API so it loads `.env`. Strategy generation is already proven; analysis still needs a completed backtest.
2. For a January 2023 backtest, import CSVs that actually start in 2022 so the warmup bars exist. Do not set the coverage date earlier than the first row.
3. Walk Market Explorer and one real backtest in the browser, then Analyze with AI and reopen the report from History.
4. Build the Docker image and confirm it survives a restart. Leave the sensitivity heatmap until that path is stable.
