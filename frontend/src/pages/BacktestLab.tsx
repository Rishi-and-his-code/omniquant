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
import { daysAgo, formatINR, formatNum, formatPct, isoDate } from '../lib/format'
import { api } from '../services/api'
import type { AIReport, BacktestResult, Strategy } from '../types'

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
  const [strategyId, setStrategyId] = useState<number | ''>('')
  const [versionId, setVersionId] = useState<number | ''>('')
  const [start, setStart] = useState('2023-01-01')
  const [end, setEnd] = useState(daysAgo(1))
  const [capital, setCapital] = useState(100000)
  const [allocation, setAllocation] = useState(100)
  const [cost, setCost] = useState(0.1)
  const [slippage, setSlippage] = useState(0.05)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<BacktestResult | null>(null)
  const [report, setReport] = useState<AIReport | null>(null)
  const [analyzing, setAnalyzing] = useState(false)

  const selectedStrategy = strategies.find((s) => s.id === strategyId)
  const versions = selectedStrategy?.versions || []

  useEffect(() => {
    void api.strategies().then((list) => {
      setStrategies(list)
      if (pendingStrategyVersionId) {
        const owner = list.find((s) => s.versions.some((v) => v.id === pendingStrategyVersionId))
        if (owner) {
          setStrategyId(owner.id)
          setVersionId(pendingStrategyVersionId)
        }
      } else if (list[0]) {
        setStrategyId(list[0].id)
        setVersionId(list[0].latest_version?.id ?? '')
      }
    })
  }, [pendingStrategyVersionId])

  useEffect(() => {
    if (!pendingBacktestId) return
    void api
      .getBacktest(pendingBacktestId)
      .then((r) => {
        setResult(r)
        setPendingBacktestId(null)
      })
      .catch(() => setPendingBacktestId(null))
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
      })
      setResult(res)
    } catch (e) {
      setResult(null)
      setError(e instanceof Error ? e.message : 'Backtest failed')
    } finally {
      setRunning(false)
    }
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
          <Button onClick={() => void run()} disabled={running}>
            {running ? 'Running simulation…' : 'Run Backtest'}
          </Button>
          <div className="text-xs text-oq-muted">
            Execution: next trading day open · Long only · Whole shares · Daily timeframe
          </div>
        </div>
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
                AI is not configured. Calculated metrics above remain available without AI.
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
            Configure a saved strategy version and run a backtest. Defaults: ₹100,000 capital, 0.10%
            transaction cost, 0.05% slippage per side. End date preset: {isoDate(new Date())}.
          </p>
        </Panel>
      )}
    </div>
  )
}
