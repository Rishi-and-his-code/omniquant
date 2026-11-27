# OmniQuant — Final verification report

Date: 28 Nov 2026

## Verdict

**READY FOR EVALUATION** (with optional live AI depending on OmniRoute uptime).

## Core checks

| Check | Result |
|-------|--------|
| Docker healthy | PASS |
| Cache-only RELIANCE market data (740 bars) | PASS |
| Primary EMA 20/50 backtest #7 (+15.97%, 7 trades) | PASS |
| Secondary EMA 10/30 backtest #8 (+16.51%, 12 trades) | PASS |
| Sensitivity 3×3 grid (20/50 = 15.97) | PASS |
| AI generate EMA 20/50 (~52s, CODING) | PASS |
| Saved AI report reopen (#1 / BT#6) | PASS |
| Backend tests | 50 passed |
| Frontend build | PASS |

## Demo records

- Strategy: `AI Generated — EMA 20/50 Demo` (id 9)
- Strategy: `OmniQuant — EMA 10/30 Comparison` (id 10)
- Backtests: #7 primary, #8 secondary
- AI report: #1 on backtest #6
