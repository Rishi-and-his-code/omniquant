# OmniQuant Evaluation Guide

## Launch (Docker)

```bash
cp .env.example .env
docker compose up --build -d
```

Open: http://localhost:8000

Useful:

```bash
docker compose ps
docker compose logs -f
# reopen later without wiping data
docker compose restart
# stop without deleting volume
docker compose down
```

Do **not** use `docker compose down -v` during evaluation (removes DB/cache).

## Local development (without Docker)

```bash
# backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
cp .env.example .env
cd backend && PYTHONPATH=. uvicorn app.main:app --reload --port 8000

# frontend (separate terminal)
cd frontend && npm install && npm run dev
```

## Demonstration script (≈10–12 minutes)

1. Open the research terminal at http://localhost:8000  
2. Explain architecture: AI for language only; Python for money math.  
3. **Market Explorer** → select `RELIANCE.NS` → Fetch data (or use cache).  
4. Show candlesticks, SMA/EMA/RSI, cache status label.  
5. **Strategy Studio** → Manual: EMA 20/50 → Save.  
   - If AI configured: AI Builder with “Create an EMA crossover using periods 20 and 50.”  
6. **Send to Backtest Lab**.  
7. Configure 2023-01-01 → recent completed day; capital ₹100,000; costs 0.10% / 0.05%.  
8. **Run Backtest** — explain next-day-open execution.  
9. Walk metrics, equity vs buy-and-hold, drawdown, trade markers, trade table.  
10. If AI available: **Analyze with AI**; otherwise open any prior report from History.  
11. Change a parameter → new version → second backtest.  
12. **Research History** → reopen previous run (no recompute).  
13. Mention future scope: robustness, paper trading, multi-asset (out of MVP).

## Offline / AI fallback

```bash
cd backend && PYTHONPATH=. python scripts/prepare_demo.py
```

Caches RELIANCE/TCS/INFY and seeds demo strategies. If Yahoo is blocked, use cached datasets (timestamp shown in UI). Manual workflow works with `AI_ENABLED=false`.

## Swagger

http://localhost:8000/docs

## Image portability (optional)

```bash
docker save omniquant:0.1.0 -o omniquant-image.tar
docker load -i omniquant-image.tar
```

The archive does not include the persistent volume, cache, or AI keys.
