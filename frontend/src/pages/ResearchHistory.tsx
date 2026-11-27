import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Alert, Button, Panel } from '../components/ui/primitives'
import { useApp } from '../context/AppContext'
import { formatPct } from '../lib/format'
import { api } from '../services/api'
import type { AIReport, BacktestSummary, Strategy } from '../types'

type Tab = 'strategies' | 'backtests' | 'reports'

export function ResearchHistory() {
  const navigate = useNavigate()
  const { setPendingStrategyVersionId, setPendingBacktestId } = useApp()
  const [tab, setTab] = useState<Tab>('strategies')
  const [strategies, setStrategies] = useState<Strategy[]>([])
  const [backtests, setBacktests] = useState<BacktestSummary[]>([])
  const [reports, setReports] = useState<AIReport[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedReport, setSelectedReport] = useState<AIReport | null>(null)

  useEffect(() => {
    setLoading(true)
    void Promise.all([api.strategies(), api.backtests(), api.allReports()])
      .then(([s, b, r]) => {
        setStrategies(s)
        setBacktests(b)
        setReports(r)
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load history'))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold">Research History</h1>
        <p className="mt-1 text-sm text-oq-secondary">
          Reopen saved strategies, completed backtests, and stored AI reports.
        </p>
      </div>

      <div className="flex gap-2">
        {(
          [
            ['strategies', 'Saved Strategies'],
            ['backtests', 'Backtest History'],
            ['reports', 'AI Reports'],
          ] as const
        ).map(([id, label]) => (
          <Button key={id} variant={tab === id ? 'primary' : 'secondary'} onClick={() => setTab(id)}>
            {label}
          </Button>
        ))}
      </div>

      {error && <Alert tone="error">{error}</Alert>}
      {loading && <Alert tone="info">Loading research history…</Alert>}

      {tab === 'strategies' && (
        <Panel title="Strategies">
          <div className="space-y-2">
            {!loading && strategies.length === 0 && (
              <p className="text-sm text-oq-muted">No strategies saved.</p>
            )}
            {strategies.map((s) => (
              <div
                key={s.id}
                className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-oq-border bg-oq-elevated px-3 py-2"
              >
                <div>
                  <div className="text-sm font-medium">{s.name}</div>
                  <div className="text-xs text-oq-muted">
                    {s.latest_version?.strategy_type} · v{s.latest_version?.version_number} ·
                    updated {new Date(s.updated_at).toLocaleString()}
                  </div>
                </div>
                <div className="flex gap-2">
                  <Button
                    variant="ghost"
                    onClick={() => {
                      setPendingStrategyVersionId(s.latest_version?.id ?? null)
                      navigate('/strategy')
                    }}
                  >
                    View
                  </Button>
                  <Button
                    variant="secondary"
                    onClick={() => {
                      setPendingStrategyVersionId(s.latest_version?.id ?? null)
                      navigate('/backtest')
                    }}
                  >
                    Run backtest
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </Panel>
      )}

      {tab === 'backtests' && (
        <Panel title="Backtests">
          <div className="overflow-auto">
            <table className="w-full text-left text-xs">
              <thead className="text-oq-muted">
                <tr>
                  {['ID', 'Status', 'Symbol', 'Strategy', 'Period', 'Return', 'Max DD', 'Trades', ''].map(
                    (h) => (
                      <th key={h} className="px-2 py-1.5">
                        {h}
                      </th>
                    ),
                  )}
                </tr>
              </thead>
              <tbody className="font-mono-num">
                {backtests.map((b) => (
                  <tr key={b.id} className="border-t border-oq-border/60">
                    <td className="px-2 py-1.5">{b.id}</td>
                    <td className="px-2 py-1.5 capitalize">{b.status}</td>
                    <td className="px-2 py-1.5">{b.symbol}</td>
                    <td className="px-2 py-1.5">
                      {b.strategy_name} v{b.strategy_version_number}
                    </td>
                    <td className="px-2 py-1.5">
                      {b.start_date} → {b.end_date}
                    </td>
                    <td className="px-2 py-1.5">{formatPct(b.total_return_percent)}</td>
                    <td className="px-2 py-1.5">
                      {b.max_drawdown_percent == null ? 'N/A' : `${b.max_drawdown_percent.toFixed(2)}%`}
                    </td>
                    <td className="px-2 py-1.5">{b.completed_trades ?? '—'}</td>
                    <td className="px-2 py-1.5">
                      <Button
                        variant="ghost"
                        disabled={b.status !== 'completed'}
                        onClick={() => {
                          setPendingBacktestId(b.id)
                          navigate('/backtest')
                        }}
                      >
                        Open
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {backtests.length === 0 && (
              <p className="mt-2 text-sm text-oq-muted">No backtests yet.</p>
            )}
          </div>
        </Panel>
      )}

      {tab === 'reports' && (
        <div className="grid gap-4 lg:grid-cols-2">
          <Panel title="Stored reports">
            <div className="space-y-2">
              {reports.length === 0 && (
                <p className="text-sm text-oq-muted">No AI reports stored yet.</p>
              )}
              {reports.map((r) => (
                <button
                  key={r.id}
                  type="button"
                  className="block w-full rounded-md border border-oq-border bg-oq-elevated px-3 py-2 text-left hover:border-oq-accent/50"
                  onClick={() => setSelectedReport(r)}
                >
                  <div className="text-sm">Backtest #{r.backtest_id}</div>
                  <div className="text-xs text-oq-muted">
                    {r.model_name} · {new Date(r.created_at).toLocaleString()}
                  </div>
                </button>
              ))}
            </div>
          </Panel>
          <Panel title="Report detail">
            {!selectedReport && (
              <p className="text-sm text-oq-muted">Select a report to reopen without calling the AI provider.</p>
            )}
            {selectedReport && (
              <div className="space-y-3 text-sm">
                <p className="text-oq-secondary">{selectedReport.report.summary}</p>
                {(
                  [
                    ['Strengths', selectedReport.report.strengths],
                    ['Weaknesses', selectedReport.report.weaknesses],
                    ['Risk observations', selectedReport.report.risk_observations],
                    ['Suggested improvements', selectedReport.report.suggested_improvements],
                    ['Recommended tests', selectedReport.report.recommended_tests],
                    ['Limitations', selectedReport.report.limitations],
                  ] as const
                ).map(([title, items]) => (
                  <div key={title}>
                    <div className="text-xs uppercase text-oq-muted">{title}</div>
                    <ul className="mt-1 list-disc pl-5 text-oq-secondary">
                      {items.map((i) => (
                        <li key={i}>{i}</li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            )}
          </Panel>
        </div>
      )}
    </div>
  )
}
