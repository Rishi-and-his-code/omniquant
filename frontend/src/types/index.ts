export interface Instrument {
  id: number
  symbol: string
  name: string
  instrument_type: string
  exchange: string
  currency: string
  is_tradable: boolean
}

export interface OHLCVBar {
  date: string
  open: number
  high: number
  low: number
  close: number
  volume: number | null
}

export interface MarketDataResponse {
  instrument: Instrument
  bars: OHLCVBar[]
  indicators: Record<string, (number | null)[]>
  source: string
  price_adjustment: string
  cache_status: string
  retrieved_at: string
  requested_start: string
  requested_end: string
  available_start: string | null
  available_end: string | null
  fingerprint: string
  warnings: string[]
}

export interface StrategyDSL {
  schema_version: 1
  name: string
  strategy_type: 'sma_crossover' | 'ema_crossover' | 'rsi_mean_reversion'
  parameters: Record<string, number>
  position_type: 'long_only'
}

export interface StrategyVersion {
  id: number
  strategy_id: number
  version_number: number
  strategy_type: string
  dsl: StrategyDSL
  rules: { entry: string; exit: string }
  created_at: string
}

export interface Strategy {
  id: number
  name: string
  description: string | null
  status: string
  created_at: string
  updated_at: string
  latest_version: StrategyVersion | null
  versions: StrategyVersion[]
}

export interface PerformanceMetrics {
  initial_capital: number
  final_equity: number
  net_profit_loss: number
  total_return_percent: number
  max_drawdown_percent: number
  completed_trades: number
  win_rate_percent: number | null
  profit_factor: number | null
  sharpe_ratio: number | null
  buy_and_hold_return_percent: number | null
  notes: string[]
}

export interface CurvePoint {
  date: string
  value: number
}

export interface Trade {
  id?: number
  entry_signal_date: string
  entry_date: string
  exit_signal_date: string
  exit_date: string
  entry_price: number
  exit_price: number
  quantity: number
  entry_fee: number
  exit_fee: number
  total_cost: number
  profit_loss: number
  return_percent: number
}

export interface TradeMarker {
  date: string
  price: number
  side: 'buy' | 'sell'
  quantity: number
}

export interface OpenPosition {
  entry_signal_date: string
  entry_date: string
  quantity: number
  entry_price: number
  mark_price: number
  market_value: number
  unrealized_pnl: number
  note: string
}

export interface BacktestResult {
  id: number
  status: string
  strategy_version_id: number
  strategy_name: string | null
  strategy_type: string | null
  strategy_version_number: number | null
  symbol: string
  instrument_name: string | null
  start_date: string
  end_date: string
  initial_capital: number
  allocation_percent: number
  transaction_cost_percent: number
  slippage_percent: number
  execution_policy: string
  price_basis: string
  metrics: PerformanceMetrics | null
  equity_curve: CurvePoint[]
  drawdown_curve: CurvePoint[]
  benchmark_curve: CurvePoint[]
  trades: Trade[]
  open_position: OpenPosition | null
  trade_markers: TradeMarker[]
  chart_data: OHLCVBar[]
  data_metadata: Record<string, unknown>
  warnings: string[]
  error_message: string | null
  created_at: string
  completed_at: string | null
}

export interface BacktestSummary {
  id: number
  status: string
  symbol: string
  strategy_name: string | null
  strategy_type: string | null
  strategy_version_number: number | null
  start_date: string
  end_date: string
  initial_capital: number
  total_return_percent: number | null
  max_drawdown_percent: number | null
  completed_trades: number | null
  created_at: string
  completed_at: string | null
}

export interface AIReport {
  id: number
  backtest_id: number
  report_type: string
  report: {
    summary: string
    strengths: string[]
    weaknesses: string[]
    risk_observations: string[]
    suggested_improvements: string[]
    recommended_tests: string[]
    limitations: string[]
  }
  model_name: string
  created_at: string
}

export interface HealthResponse {
  status: string
  version: string
  database: boolean
  ai_configured: boolean
  ai_enabled: boolean
}

export interface ApiError {
  error: {
    code: string
    message: string
    details?: unknown
  }
}
