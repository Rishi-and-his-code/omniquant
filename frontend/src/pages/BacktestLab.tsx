import { useEffect, useMemo, useState } from 'react'
import { Download } from 'lucide-react'
import { CandlestickChart, LineChart } from '../components/charts/CandlestickChart'
import {
  Alert,
  Button,
  Input,
  Label,
  MetricCard,
  Panel,
  Select,
} from '../components/ui/primitives'
import { useApp } from '../context/AppContext'
import { DEMO_CONFIG, pickDemoStrategyId } from '../lib/demoConfig'
import { formatINR, formatNum, formatPct } from '../lib/format'
import { api } from '../services/api'
import type { AIReport, BacktestResult, Strategy } from '../types'

type SensitivityResult = Awaited<ReturnType<typeof api.sensitivity>>
type SensitivityMetric = 'total_return_percent' | 'max_drawdown_percent' | 'sharpe_ratio'

export function BacktestLab() {
  const {
    instruments,
    selectedSymbol,
    setSelectedSymbol,
    pendingStrategyVersionId,
    pendingBacktestId,
    setPendingBacktestId,
    health,
  } = useApp()

  const [strategies, setStrategies] = useState<Strategy[]>([])
  const [strategiesLoading, setStrategiesLoading] = useState(true)
  const [strategyId, setStrategyId] = useState<number | ''>('')
  const [versionId, setVersionId] = useState<number | ''>('')
  const [start, setStart] = useState<string>(DEMO_CONFIG.startDate)
  const [end, setEnd] = useState<string>(DEMO_CONFIG.endDate)
  const [capital, setCapital] = useState<number>(DEMO_CONFIG.initialCapital)
  const [allocation, setAllocation] = useState<number>(DEMO_CONFIG.allocationPercent)
  const [cost, setCost] = useState<number>(DEMO_CONFIG.transactionCostPercent)
  const [slippage, setSlippage] = useState<number>(DEMO_CONFIG.slippagePercent)
  const [cacheOnly, setCacheOnly] = useState(true)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<BacktestResult | null>(null)
  const [report, setReport] = useState<AIReport | null>(null)
  const [analyzing, setAnalyzing] = useState(false)
  const [sensitivity, setSensitivity] = useState<SensitivityResult | null>(null)
  const [sensitivityLoading, setSensitivityLoading] = useState(false)
  const [sensitivityMetric, setSensitivityMetric] = useState<SensitivityMetric>('total_return_percent')
  const [fastGrid, setFastGrid] = useState('10,20,30')
  const [slowGrid, setSlowGrid] = useState('40,50,60')

  const selectedStrategy = strategies.find((s) => s.id === strategyId)
  const versions = selectedStrategy?.versions || []

  useEffect(() => {
    setStrategiesLoading(true)
    void api
      .strategies()
      .then((list) => {
        setStrategies(list)
        if (pendingStrategyVersionId) {
          const owner = list.find((s) => s.versions.some((v) => v.id === pendingStrategyVersionId))
          if (owner) {
            setStrategyId(owner.id)
            setVersionId(pendingStrategyVersionId)
            return
          }
        }
        setStrategyId((current) => {
          if (current !== '') return current
          const demo = pickDemoStrategyId(
            list,
            DEMO_CONFIG.preferredStrategyNames,
            DEMO_CONFIG.emaFast,
            DEMO_CONFIG.emaSlow,
          )
          if (demo) {
            setVersionId(demo.versionId)
            return demo.strategyId
          }
          const first = list[0]
          if (first) setVersionId(first.latest_version?.id ?? '')
          return first?.id ?? ''
        })
      })
      .finally(() => setStrategiesLoading(false))
  }, [pendingStrategyVersionId])

  useEffect(() => {
    if (!pendingBacktestId) return
    const id = pendingBacktestId
    void (async () => {
      try {
        const r = await api.getBacktest(id)
        setResult(r)
        const reports = await api.backtestReports(id)
        setReport(reports[0] ?? null)
      } catch {
        setReport(null)
      } finally {
        setPendingBacktestId(null)
      }
    })()
  }, [pendingBacktestId, setPendingBacktestId])

  useEffect(() => {
    if (!strategyId) return
    const s = strategies.find((x) => x.id === strategyId)
    if (s?.latest_version && !versions.find((v) => v.id === versionId)) {
      setVersionId(s.latest_version.id)
    }
  }, [strategyId, strategies, versionId, versions])

  const tradable = useMemo(
    () => instruments.filter((i) => i.is_tradable),
    [instruments],
  )

  const loadDemoConfiguration = () => {
    setSelectedSymbol(DEMO_CONFIG.symbol)
    setStart(DEMO_CONFIG.startDate)
    setEnd(DEMO_CONFIG.endDate)
    setCapital(DEMO_CONFIG.initialCapital)
    setAllocation(DEMO_CONFIG.allocationPercent)
    setCost(DEMO_CONFIG.transactionCostPercent)
    setSlippage(DEMO_CONFIG.slippagePercent)
    setCacheOnly(true)
    setError(null)
    const demo = pickDemoStrategyId(
      strategies,
      DEMO_CONFIG.preferredStrategyNames,
      DEMO_CONFIG.emaFast,
      DEMO_CONFIG.emaSlow,
    )
    if (demo) {
      setStrategyId(demo.strategyId)
      setVersionId(demo.versionId)
    } else {
      setError(
        'Demo EMA 20/50 strategy not found yet. Generate or save an EMA 20/50 strategy in Strategy Studio first.',
      )
    }
  }

  const parsePeriodList = (raw: string): number[] =>
    raw
      .split(/[, ]+/)
      .map((x) => Number(x.trim()))
      .filter((n) => Number.isInteger(n) && n >= 2 && n <= 250)

  const run = async () => {
    if (!versionId) {
      setError('Select a saved strategy version first.')
      return
    }
    setRunning(true)
    setError(null)
    setReport(null)
    try {
      const res = await api.runBacktest({
        strategy_version_id: Number(versionId),
        symbol: selectedSymbol,
        start_date: start,
        end_date: end,
        initial_capital: capital,
        allocation_percent: allocation,
        transaction_cost_percent: cost,
        slippage_percent: slippage,
        cache_only: cacheOnly,
      })
      setResult(res)
    } catch (e) {
      setResult(null)
      setError(e instanceof Error ? e.message : 'Backtest failed')
    } finally {
      setRunning(false)
    }
  }

  const runSensitivity = async () => {
    const fast_periods = parsePeriodList(fastGrid)
    const slow_periods = parsePeriodList(slowGrid)
    if (!fast_periods.length || !slow_periods.length) {
      setError('Enter valid fast/slow period lists (integers 2–250).')
      return
    }
    setSensitivityLoading(true)
    setError(null)
    try {
      const res = await api.sensitivity({
        symbol: selectedSymbol,
        start_date: start,
        end_date: end,
        strategy_type: 'ema_crossover',
        fast_periods,
        slow_periods,
        initial_capital: capital,
        allocation_percent: allocation,
        transaction_cost_percent: cost,
        slippage_percent: slippage,
        cache_only: cacheOnly,
      })
      setSensitivity(res)
    } catch (e) {
      setSensitivity(null)
      setError(e instanceof Error ? e.message : 'Sensitivity analysis failed')
    } finally {
      setSensitivityLoading(false)
    }
  }

  const cellColor = (value: number | null | undefined, metric: SensitivityMetric) => {
    if (value == null || Number.isNaN(value)) return 'bg-oq-elevated text-oq-muted'
    if (metric === 'max_drawdown_percent') {
      const intensity = Math.min(Math.abs(value) / 40, 1)
      return intensity > 0.55 ? 'bg-red-900/50 text-oq-negative' : 'bg-red-950/30 text-oq-secondary'
    }
    if (value >= 0) {
      const intensity = Math.min(value / 30, 1)
      return intensity > 0.55 ? 'bg-emerald-900/50 text-oq-positive' : 'bg-emerald-950/30 text-oq-secondary'
    }
    const intensity = Math.min(Math.abs(value) / 30, 1)
    return intensity > 0.55 ? 'bg-red-900/50 text-oq-negative' : 'bg-red-950/30 text-oq-secondary'
  }

  const analyze = async () => {
    if (!result) return
    setAnalyzing(true)
    setError(null)
    try {
      const r = await api.analyzeBacktest(result.id)
      setReport(r)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'AI analysis failed')
    } finally {
      setAnalyzing(false)
    }
  }

  const exportTrades = () => {
    if (!result) return
    const header =
      'entry_date,exit_date,entry_price,exit_price,quantity,entry_fee,exit_fee,total_cost,profit_loss,return_percent'
    const rows = result.trades.map(
      (t) =>
        `${t.entry_date},${t.exit_date},${t.entry_price},${t.exit_price},${t.quantity},${t.entry_fee},${t.exit_fee},${t.total_cost},${t.profit_loss},${t.return_percent}`,
    )
    const blob = new Blob([[header, ...rows].join('\n')], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `backtest_${result.id}_trades.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  const m = result?.metrics
  const tone = (v: number | null | undefined) =>
    v == null ? 'neutral' : v >= 0 ? 'positive' : 'negative'

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold">Backtest Lab</h1>
        <p className="mt-1 text-sm text-oq-secondary">
          Deterministic long-only simulation · next-day open execution · adjusted OHLC research
          approximation.
        </p>
      </div>

      <Panel title="Configuration">
        <div className="grid gap-3 md:grid-cols-4">
          <div>
            <Label>Strategy</Label>
            <Select
              value={strategyId}
              onChange={(e) => setStrategyId(e.target.value ? Number(e.target.value) : '')}
            >
              <option value="">Select…</option>
              {strategies.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <Label>Version</Label>
            <Select
              value={versionId}
              onChange={(e) => setVersionId(e.target.value ? Number(e.target.value) : '')}
            >
              <option value="">Select…</option>
              {versions.map((v) => (
                <option key={v.id} value={v.id}>
                  v{v.version_number} · {v.strategy_type}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <Label>Instrument</Label>
            <Select value={selectedSymbol} onChange={(e) => setSelectedSymbol(e.target.value)}>
              {tradable.map((i) => (
                <option key={i.symbol} value={i.symbol}>
                  {i.symbol}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <Label>Initial capital (₹)</Label>
            <Input
              type="number"
              value={capital}
              onChange={(e) => setCapital(Number(e.target.value))}
            />
          </div>
          <div>
            <Label>Start date</Label>
            <Input type="date" value={start} onChange={(e) => setStart(e.target.value)} />
          </div>
          <div>
            <Label>End date</Label>
            <Input type="date" value={end} onChange={(e) => setEnd(e.target.value)} />
          </div>
          <div>
            <Label>Allocation %</Label>
            <Input
              type="number"
              value={allocation}
              onChange={(e) => setAllocation(Number(e.target.value))}
            />
          </div>
          <div>
            <Label>Txn cost % / side</Label>
            <Input type="number" step="0.01" value={cost} onChange={(e) => setCost(Number(e.target.value))} />
          </div>
          <div>
            <Label>Slippage % / side</Label>
            <Input
              type="number"
              step="0.01"
              value={slippage}
              onChange={(e) => setSlippage(Number(e.target.value))}
            />
          </div>
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <Button variant="secondary" onClick={loadDemoConfiguration} disabled={strategiesLoading}>
            Load Demo Configuration
          </Button>
          <Button onClick={() => void run()} disabled={running || strategiesLoading}>
            {running ? 'Running simulation…' : 'Run Backtest'}
          </Button>
          <label className="flex items-center gap-2 text-xs text-oq-secondary">
            <input
              type="checkbox"
              checked={cacheOnly}
              onChange={(e) => setCacheOnly(e.target.checked)}
            />
            Cache only
          </label>
          <div className="text-xs text-oq-muted">
            Execution: next trading day open · Long only · Whole shares · Daily timeframe
          </div>
        </div>
        {strategiesLoading && (
          <p className="mt-2 text-xs text-oq-muted">Loading saved strategies…</p>
        )}
      </Panel>

      {error && <Alert tone="error">{error}</Alert>}
      {running && (
        <Alert tone="info">
          Retrieving market data and running deterministic simulation. This may take a few
          seconds…
        </Alert>
      )}

      {result && m && (
        <>
          {result.warnings.length > 0 && (
            <Alert>
              {result.warnings.map((w) => (
                <div key={w}>{w}</div>
              ))}
            </Alert>
          )}

          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            <MetricCard label="Initial capital" value={formatINR(m.initial_capital)} />
            <MetricCard label="Final equity" value={formatINR(m.final_equity)} tone={tone(m.net_profit_loss)} />
            <MetricCard label="Net P&L" value={formatINR(m.net_profit_loss)} tone={tone(m.net_profit_loss)} />
            <MetricCard
              label="Total return"
              value={formatPct(m.total_return_percent)}
              tone={tone(m.total_return_percent)}
            />
            <MetricCard
              label="Max drawdown"
              value={`${formatNum(m.max_drawdown_percent)}%`}
              tone="negative"
            />
            <MetricCard label="Completed trades" value={String(m.completed_trades)} />
            <MetricCard label="Win rate" value={formatPct(m.win_rate_percent)} />
            <MetricCard label="Sharpe (ann.)" value={formatNum(m.sharpe_ratio)} />
            <MetricCard label="Profit factor" value={formatNum(m.profit_factor)} />
            <MetricCard
              label="Buy & hold"
              value={formatPct(m.buy_and_hold_return_percent)}
              tone={tone(m.buy_and_hold_return_percent)}
            />
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <Panel title="Equity curve">
              <LineChart
                series={[
                  { name: 'Strategy', points: result.equity_curve },
                  ...(result.benchmark_curve.length
                    ? [{ name: 'Buy & hold', points: result.benchmark_curve }]
                    : []),
                ]}
                yTitle="₹"
              />
            </Panel>
            <Panel title="Drawdown (%)">
              <LineChart
                series={[{ name: 'Drawdown', points: result.drawdown_curve }]}
                colors={['#EF4444']}
                yTitle="%"
              />
            </Panel>
          </div>

          <Panel title="Price with execution markers">
            <CandlestickChart
              bars={result.chart_data}
              markers={result.trade_markers}
              showVolume={false}
              height={380}
            />
          </Panel>

          {result.open_position && (
            <Panel title="Open position at end">
              <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6 text-sm">
                <div>
                  <div className="text-oq-muted text-xs">Entry date</div>
                  <div className="font-mono-num">{result.open_position.entry_date}</div>
                </div>
                <div>
                  <div className="text-oq-muted text-xs">Qty</div>
                  <div className="font-mono-num">{result.open_position.quantity}</div>
                </div>
                <div>
                  <div className="text-oq-muted text-xs">Entry price</div>
                  <div className="font-mono-num">{formatNum(result.open_position.entry_price)}</div>
                </div>
                <div>
                  <div className="text-oq-muted text-xs">Mark price</div>
                  <div className="font-mono-num">{formatNum(result.open_position.mark_price)}</div>
                </div>
                <div>
                  <div className="text-oq-muted text-xs">Market value</div>
                  <div className="font-mono-num">{formatINR(result.open_position.market_value)}</div>
                </div>
                <div>
                  <div className="text-oq-muted text-xs">Unrealized P&L</div>
                  <div className="font-mono-num">{formatINR(result.open_position.unrealized_pnl)}</div>
                </div>
              </div>
              <p className="mt-2 text-xs text-oq-muted">{result.open_position.note}</p>
            </Panel>
          )}

          <Panel
            title="Trade history"
            actions={
              <Button variant="ghost" onClick={exportTrades} disabled={!result.trades.length}>
                <Download size={14} /> CSV
              </Button>
            }
          >
            {result.trades.length === 0 ? (
              <p className="text-sm text-oq-muted">No completed round-trip trades.</p>
            ) : (
              <div className="max-h-80 overflow-auto">
                <table className="w-full text-left text-xs">
                  <thead className="sticky top-0 bg-oq-panel text-oq-muted">
                    <tr>
                      {[
                        'Entry',
                        'Exit',
                        'Entry px',
                        'Exit px',
                        'Qty',
                        'Fees',
                        'P&L',
                        'Return %',
                      ].map((h) => (
                        <th key={h} className="px-2 py-1.5">
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="font-mono-num">
                    {result.trades.map((t, i) => (
                      <tr key={i} className="border-t border-oq-border/60">
                        <td className="px-2 py-1">{t.entry_date}</td>
                        <td className="px-2 py-1">{t.exit_date}</td>
                        <td className="px-2 py-1">{t.entry_price.toFixed(2)}</td>
                        <td className="px-2 py-1">{t.exit_price.toFixed(2)}</td>
                        <td className="px-2 py-1">{t.quantity}</td>
                        <td className="px-2 py-1">{t.total_cost.toFixed(2)}</td>
                        <td
                          className={`px-2 py-1 ${t.profit_loss >= 0 ? 'text-oq-positive' : 'text-oq-negative'}`}
                        >
                          {t.profit_loss.toFixed(2)}
                        </td>
                        <td className="px-2 py-1">{t.return_percent.toFixed(2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>

          <Panel
            title="AI research analysis"
            actions={
              <Button
                onClick={() => void analyze()}
                disabled={analyzing || !health?.ai_configured}
              >
                {analyzing ? 'Analyzing…' : 'Analyze with AI'}
              </Button>
            }
          >
            {!health?.ai_configured && (
              <Alert tone="warning">
                AI is not configured. Set the OmniRoute provider in `.env`, with OpenRouter as
                timeout fallback. Calculated metrics above remain available without AI.
              </Alert>
            )}
            {report && (
              <div className="mt-3 space-y-3 text-sm">
                <p className="text-oq-secondary">{report.report.summary}</p>
                {(
                  [
                    ['Strengths', report.report.strengths],
                    ['Weaknesses', report.report.weaknesses],
                    ['Risk observations', report.report.risk_observations],
                    ['Suggested improvements', report.report.suggested_improvements],
                    ['Recommended tests', report.report.recommended_tests],
                    ['Limitations', report.report.limitations],
                  ] as const
                ).map(([title, items]) => (
                  <div key={title}>
                    <div className="text-xs uppercase tracking-wide text-oq-muted">{title}</div>
                    <ul className="mt-1 list-disc space-y-1 pl-5 text-oq-secondary">
                      {items.map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                    </ul>
                  </div>
                ))}
                <p className="text-[11px] text-oq-muted">
                  Model {report.model_name} · {new Date(report.created_at).toLocaleString()} ·
                  Historical simulated research only
                </p>
              </div>
            )}
          </Panel>
        </>
      )}

      {!result && !running && (
        <Panel>
          <p className="text-sm text-oq-secondary">
            Configure a saved strategy version and run a backtest. Demo defaults: RELIANCE.NS,
            2023-01-01 → 2025-12-31, ₹100,000 capital, 0.10% transaction cost, 0.05% slippage,
            cache-only market data.
          </p>
        </Panel>
      )}

      <Panel title="Parameter sensitivity (in-sample)">
        <p className="mb-3 text-xs text-oq-muted">
          Reuses the current instrument, dates, capital, fees, and slippage with the existing
          deterministic engine. Results are historical in-sample only — not proof of future
          performance.
        </p>
        <div className="grid gap-3 md:grid-cols-4">
          <div>
            <Label>Fast periods</Label>
            <Input value={fastGrid} onChange={(e) => setFastGrid(e.target.value)} />
          </div>
          <div>
            <Label>Slow periods</Label>
            <Input value={slowGrid} onChange={(e) => setSlowGrid(e.target.value)} />
          </div>
          <div>
            <Label>Heatmap metric</Label>
            <Select
              value={sensitivityMetric}
              onChange={(e) => setSensitivityMetric(e.target.value as SensitivityMetric)}
            >
              <option value="total_return_percent">Total return %</option>
              <option value="max_drawdown_percent">Max drawdown %</option>
              <option value="sharpe_ratio">Sharpe</option>
            </Select>
          </div>
          <div className="flex items-end">
            <Button onClick={() => void runSensitivity()} disabled={sensitivityLoading || running}>
              {sensitivityLoading ? 'Running grid…' : 'Run sensitivity'}
            </Button>
          </div>
        </div>
        {sensitivity && (
          <div className="mt-4 space-y-2">
            <div className="text-xs text-oq-secondary">
              {sensitivity.metric_note} · {sensitivity.combinations_evaluated} combinations ·{' '}
              {sensitivity.cache_status || 'cache n/a'} · {sensitivity.data_source || 'source n/a'}
            </div>
            <div className="overflow-auto">
              <table className="w-full min-w-[28rem] text-center text-xs">
                <thead>
                  <tr>
                    <th className="px-2 py-1 text-oq-muted">Fast \\ Slow</th>
                    {sensitivity.slow_periods.map((s) => (
                      <th key={s} className="px-2 py-1 text-oq-muted">
                        {s}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {sensitivity.fast_periods.map((f) => (
                    <tr key={f}>
                      <th className="px-2 py-1 text-oq-muted">{f}</th>
                      {sensitivity.slow_periods.map((s) => {
                        const cell = sensitivity.cells.find(
                          (c) => c.fast_period === f && c.slow_period === s,
                        )
                        if (!cell?.valid) {
                          return (
                            <td key={`${f}-${s}`} className="border border-oq-border/50 px-2 py-2 text-oq-muted">
                              —
                            </td>
                          )
                        }
                        const value = cell[sensitivityMetric]
                        return (
                          <td
                            key={`${f}-${s}`}
                            className={`border border-oq-border/50 px-2 py-2 font-mono-num ${cellColor(value, sensitivityMetric)}`}
                            title={cell.error || undefined}
                          >
                            {value == null ? 'n/a' : formatNum(value)}
                          </td>
                        )
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="text-[11px] text-oq-muted">{sensitivity.disclaimer}</p>
          </div>
        )}
      </Panel>
    </div>
  )
}
