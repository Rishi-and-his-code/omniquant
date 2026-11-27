# OmniQuant

**Quantitative Research Terminal** — university minor-project MVP.

OmniQuant is an AI-assisted algorithmic trading research platform for Indian equities. Users explore historical market data, build validated strategy templates, run deterministic backtests, and optionally obtain AI research commentary.

This repository is a **working prototype** for mid-project evaluation — not the full production SRS.

## MVP features

- Historical daily OHLCV via yfinance + local CSV cache
- Interactive Plotly candlesticks with SMA / EMA / RSI
- Validated Strategy DSL (SMA crossover, EMA crossover, RSI mean reversion)
- Manual strategy builder + optional AI natural-language generation
- Deterministic long-only backtester (next-day open execution, fees, slippage)
- Performance metrics, equity / drawdown charts, trade history
- SQLite persistence for strategies, backtests, AI reports
- Single-container Docker deployment

## Stack

| Layer | Technology |
|-------|------------|
| Frontend | React, Vite, TypeScript, Tailwind CSS, Plotly |
| Backend | FastAPI, Pydantic v2, SQLAlchemy, Pandas, NumPy |
| Data | yfinance, SQLite, CSV cache |
| AI | OpenAI-compatible HTTP API (optional) |
| Ops | Docker Compose |

## Architecture principle

**AI never calculates financial metrics.**  
Deterministic Python simulates trades and computes returns. AI only maps language → DSL and narrates already-computed results.

## Quick start (Docker)

```bash
git clone git@github.com:Rishi-and-his-code/omniquant.git
cd omniquant
cp .env.example .env
docker compose up --build -d
```

Open **http://localhost:8000**

API docs: http://localhost:8000/docs

## Local development

Prerequisites: Python 3.11, Node.js 20+, npm.

```bash
cp .env.example .env
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt

# terminal 1
cd backend && PYTHONPATH=. uvicorn app.main:app --reload --port 8000

# terminal 2
cd frontend && npm install && npm run dev
```

Frontend: http://localhost:5173 (proxies `/api` → `:8000`)

## Environment variables

See `.env.example`.

| Variable | Purpose |
|----------|---------|
| `AI_ENABLED` | `true` to allow AI routes |
| `AI_BASE_URL` | OpenAI-compatible base URL |
| `AI_API_KEY` | Server-side only — never commit |
| `AI_MODEL` | Model id |
| `DATA_DIR` | SQLite + cache directory |

LM Studio on Mac host from Docker: `AI_BASE_URL=http://host.docker.internal:1234/v1`

## Prepare evaluation cache

```bash
source .venv/bin/activate
cd backend && PYTHONPATH=. python scripts/prepare_demo.py
```

## Tests

```bash
source .venv/bin/activate
cd backend && PYTHONPATH=. pytest -q
cd ../frontend && npm run build
```

## Backtesting assumptions

- Daily adjusted OHLC (`auto_adjust=True`) — research approximation, not exact historical prints
- Long only, whole shares, one position
- Signal at close → execute next open
- Transaction cost and slippage as percent per side (UI shows human percent; engine uses fraction = percent/100)
- Positions open at end are marked to market; not force-closed
- Buy-and-hold benchmark uses the same cost / sizing conventions

## Known limitations

- Single instrument per backtest
- No shorting, leverage, intraday, or broker integration
- AI optional; unavailable state is shown honestly
- Parameter sensitivity heatmap deferred (P2)
- Plotly bundle is large; acceptable for local demo

## Project docs

- [Implementation plan](docs/IMPLEMENTATION_PLAN.md)
- [Architecture](docs/ARCHITECTURE.md)
- [API reference](docs/API_REFERENCE.md)
- [Evaluation guide](docs/EVALUATION_GUIDE.md)

## Team

Rishi Kachhadia · Shivansh Patel · Priyanshi Joshi  
Supervisor: Mr. Gaurav Gaharwar

## Disclaimer

OmniQuant is a historical quantitative research and simulated backtesting platform. Historical performance does not guarantee future results. Not investment advice.
