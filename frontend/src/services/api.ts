import type {
  AIReport,
  ApiError,
  BacktestResult,
  BacktestSummary,
  HealthResponse,
  Instrument,
  MarketDataResponse,
  Strategy,
  StrategyDSL,
  StrategyVersion,
} from '../types'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers || {}),
    },
  })
  if (!res.ok) {
    let payload: ApiError | null = null
    try {
      payload = (await res.json()) as ApiError
    } catch {
      /* ignore */
    }
    const message = payload?.error?.message || `Request failed (${res.status})`
    const err = new Error(message) as Error & { code?: string; status?: number }
    err.code = payload?.error?.code
    err.status = res.status
    throw err
  }
  return res.json() as Promise<T>
}

export const api = {
  health: () => request<HealthResponse>('/api/health'),
  instruments: () => request<Instrument[]>('/api/instruments'),
  marketData: (params: {
    symbol: string
    start_date: string
    end_date: string
    refresh?: boolean
    sma?: number[]
    ema?: number[]
    rsi_period?: number
  }) => {
    const q = new URLSearchParams({
      symbol: params.symbol,
      start_date: params.start_date,
      end_date: params.end_date,
    })
    if (params.refresh) q.set('refresh', 'true')
    params.sma?.forEach((p) => q.append('sma', String(p)))
    params.ema?.forEach((p) => q.append('ema', String(p)))
    if (params.rsi_period) q.set('rsi_period', String(params.rsi_period))
    return request<MarketDataResponse>(`/api/market-data?${q}`)
  },
  strategies: () => request<Strategy[]>('/api/strategies'),
  createStrategy: (body: { name: string; description?: string; dsl: StrategyDSL }) =>
    request<Strategy>('/api/strategies', { method: 'POST', body: JSON.stringify(body) }),
  getStrategy: (id: number) => request<Strategy>(`/api/strategies/${id}`),
  createVersion: (id: number, dsl: StrategyDSL) =>
    request<StrategyVersion>(`/api/strategies/${id}/versions`, {
      method: 'POST',
      body: JSON.stringify({ dsl }),
    }),
  generateStrategy: (prompt: string) =>
    request<{
      status: string
      message: string | null
      dsl: StrategyDSL | null
      rules: { entry: string; exit: string } | null
      model_name: string | null
    }>('/api/ai/generate-strategy', {
      method: 'POST',
      body: JSON.stringify({ prompt }),
    }),
  aiStatus: () =>
    request<{ ai_enabled: boolean; ai_configured: boolean; model: string | null }>(
      '/api/ai/status',
    ),
  runBacktest: (body: {
    strategy_version_id: number
    symbol: string
    start_date: string
    end_date: string
    initial_capital: number
    allocation_percent: number
    transaction_cost_percent: number
    slippage_percent: number
  }) =>
    request<BacktestResult>('/api/backtests', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  backtests: () => request<BacktestSummary[]>('/api/backtests'),
  getBacktest: (id: number) => request<BacktestResult>(`/api/backtests/${id}`),
  analyzeBacktest: (id: number) =>
    request<AIReport>(`/api/backtests/${id}/analyze`, { method: 'POST' }),
  backtestReports: (id: number) => request<AIReport[]>(`/api/backtests/${id}/reports`),
  allReports: () => request<AIReport[]>('/api/ai-reports'),
}
