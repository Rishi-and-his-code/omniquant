# OmniQuant API Reference (MVP)

Base path: `/api`  
Interactive docs: `/docs`

## Health

`GET /api/health`

Returns application status, DB availability, AI configuration flags (never credentials).

## Instruments

`GET /api/instruments`

Seeded NSE equities and indices with `is_tradable` flags.

## Market data

`GET /api/market-data?symbol=&start_date=&end_date=&refresh=&sma=&ema=&rsi_period=`

Returns OHLCV bars, indicators, cache status, fingerprint, warnings.

## Strategies

- `GET /api/strategies`
- `POST /api/strategies` — body: `{ name, description?, dsl }`
- `GET /api/strategies/{id}`
- `POST /api/strategies/{id}/versions` — body: `{ dsl }`

## AI

- `GET /api/ai/status`
- `POST /api/ai/generate-strategy` — body: `{ prompt }`

## Backtests

- `POST /api/backtests`
- `GET /api/backtests`
- `GET /api/backtests/{id}`
- `POST /api/backtests/{id}/analyze`
- `GET /api/backtests/{id}/reports`
- `GET /api/ai-reports`

## Errors

```json
{
  "error": {
    "code": "MARKET_DATA_UNAVAILABLE",
    "message": "…",
    "details": null
  }
}
```
