# Evaluation readiness checklist

## Pre-presentation (must)

- [ ] OmniRoute running on port 20128
- [ ] `docker compose up -d` → container **healthy**
- [ ] Open http://localhost:8000 — sidebar shows Backend connected + AI configured
- [ ] Market Explorer → **Load Demo Configuration** → **Fetch data** (cache-only) → candlesticks appear
- [ ] Strategy Studio → AI Builder optional; or open **AI Generated — EMA 20/50 Demo**
- [ ] Backtest Lab → **Load Demo Configuration** → **Run Backtest** (or reopen backtest **#7**)
- [ ] Show equity, drawdown, trades, open position
- [ ] Research History → AI Reports → reopen report for backtest **#6** (no new AI call)
- [ ] Optional: Run sensitivity grid (fast 10/20/30, slow 40/50/60)
- [ ] Optional live AI generate once (~30–60s); do not spam requests

## Startup

```bash
cd "/path/to/OMNIQUANT PROTOTYPE"
unset AI_ENABLED AI_BASE_URL AI_API_KEY AI_MODEL AI_FALLBACK_API_KEY AI_FALLBACK_MODEL AI_DOCKER_BASE_URL
docker compose up -d
```

App: http://localhost:8000 · Docs: http://localhost:8000/docs

## Cache preparation

- Required: `data/cache/` entries for RELIANCE.NS covering ~2022-10 → 2025-12
- Keep **Cache only** checked during demo unless intentionally refreshing
- Do not rely on live Yahoo; 429s are common

## AI setup

- `.env`: `AI_ENABLED=true`, `AI_API_KEY`, `AI_MODEL=CODING`
- Docker uses `AI_DOCKER_BASE_URL=http://host.docker.internal:20128/v1`
- Never commit `.env`

## Fallback demo (if OmniRoute down)

1. Market Explorer cache-only (still works)
2. Manual strategy / saved AI strategy (already in DB)
3. Run or reopen backtest #7
4. Reopen saved AI report #1 — say it was generated earlier, not live

## Known non-blockers

- CODING latency ~30–60s
- Strategy underperformed buy-and-hold (+15.97% vs +34.63%) — honest finding
- Sensitivity best cell (30/60) is in-sample only
