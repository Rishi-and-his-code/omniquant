import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Download, RefreshCw } from 'lucide-react'
import { CandlestickChart } from '../components/charts/CandlestickChart'
import { Alert, Button, Input, Label, Panel, Select } from '../components/ui/primitives'
import { useApp } from '../context/AppContext'
import { daysAgo, formatINR, formatPct, isoDate } from '../lib/format'
import { api } from '../services/api'
import type { MarketDataResponse } from '../types'

const presets = [
  { label: '3M', days: 90 },
  { label: '6M', days: 180 },
  { label: '1Y', days: 365 },
  { label: '2Y', days: 730 },
]

export function MarketExplorer() {
  const { instruments, selectedSymbol, setSelectedSymbol } = useApp()
  const navigate = useNavigate()
  const [start, setStart] = useState(daysAgo(365))
  const [end, setEnd] = useState(isoDate(new Date()))
  const [data, setData] = useState<MarketDataResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showSma, setShowSma] = useState(true)
  const [showEma, setShowEma] = useState(false)
  const [showRsi, setShowRsi] = useState(true)

  const instrument = instruments.find((i) => i.symbol === selectedSymbol)

  const summary = useMemo(() => {
    if (!data?.bars.length) return null
    const bars = data.bars
    const last = bars[bars.length - 1]
    const prev = bars.length > 1 ? bars[bars.length - 2] : null
    const change = prev ? last.close - prev.close : null
    const changePct = prev ? (change! / prev.close) * 100 : null
    return { last, prev, change, changePct }
  }, [data])

  const filteredIndicators = useMemo(() => {
    if (!data) return {}
    const out: Record<string, (number | null)[]> = {}
    for (const [k, v] of Object.entries(data.indicators)) {
      if (k.startsWith('sma') && showSma) out[k] = v
      if (k.startsWith('ema') && showEma) out[k] = v
      if (k.startsWith('rsi') && showRsi) out[k] = v
    }
    return out
  }, [data, showSma, showEma, showRsi])

  const fetchData = async (refresh = false) => {
    setLoading(true)
    setError(null)
    try {
      const res = await api.marketData({
        symbol: selectedSymbol,
        start_date: start,
        end_date: end,
        refresh,
        sma: [20, 50],
        ema: [20, 50],
        rsi_period: 14,
      })
      setData(res)
    } catch (e) {
      setData(null)
      setError(e instanceof Error ? e.message : 'Failed to load market data')
    } finally {
      setLoading(false)
    }
  }

  const exportCsv = () => {
    if (!data) return
    const header = 'date,open,high,low,close,volume'
    const rows = data.bars.map(
      (b) => `${b.date},${b.open},${b.high},${b.low},${b.close},${b.volume ?? ''}`,
    )
    const blob = new Blob([[header, ...rows].join('\n')], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${selectedSymbol}_${start}_${end}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="space-y-4">
      <div className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold">Market Explorer</h1>
          <p className="mt-1 text-sm text-oq-secondary">
            Historical adjusted daily OHLC for NSE equities and indices.
          </p>
        </div>
        {instrument?.is_tradable && (
          <Button
            variant="secondary"
            onClick={() => {
              setSelectedSymbol(selectedSymbol)
              navigate('/backtest')
            }}
          >
            Use in Backtest
          </Button>
        )}
      </div>

      <Panel>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-6">
          <div className="md:col-span-2">
            <Label>Instrument</Label>
            <Select
              value={selectedSymbol}
              onChange={(e) => setSelectedSymbol(e.target.value)}
            >
              {instruments.map((i) => (
                <option key={i.symbol} value={i.symbol}>
                  {i.symbol} — {i.name}
                  {!i.is_tradable ? ' (index)' : ''}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <Label>Start</Label>
            <Input type="date" value={start} onChange={(e) => setStart(e.target.value)} />
          </div>
          <div>
            <Label>End</Label>
            <Input type="date" value={end} onChange={(e) => setEnd(e.target.value)} />
          </div>
          <div className="flex flex-col justify-end gap-2 sm:flex-row md:col-span-2">
            <div className="flex gap-1">
              {presets.map((p) => (
                <Button
                  key={p.label}
                  variant="ghost"
                  className="px-2"
                  onClick={() => {
                    setStart(daysAgo(p.days))
                    setEnd(isoDate(new Date()))
                  }}
                >
                  {p.label}
                </Button>
              ))}
            </div>
            <Button onClick={() => void fetchData(false)} disabled={loading}>
              {loading ? 'Loading…' : 'Fetch data'}
            </Button>
            <Button variant="secondary" onClick={() => void fetchData(true)} disabled={loading}>
              <RefreshCw size={14} /> Refresh
            </Button>
          </div>
        </div>
      </Panel>

      {error && <Alert tone="error">{error}</Alert>}

      {!data && !loading && !error && (
        <Panel>
          <p className="text-sm text-oq-secondary">
            Select an instrument and date range, then fetch historical data. Values are adjusted
            historical OHLC — not live quotes.
          </p>
        </Panel>
      )}

      {data && summary && (
        <>
          <div className="grid gap-3 md:grid-cols-5">
            <Panel className="md:col-span-2">
              <div className="text-lg font-medium">{data.instrument.name}</div>
              <div className="font-mono-num text-sm text-oq-secondary">{data.instrument.symbol}</div>
              <div className="mt-2 text-xs text-oq-muted">
                {data.instrument.exchange} · {data.instrument.instrument_type} ·{' '}
                {data.instrument.currency}
              </div>
            </Panel>
            <Panel>
              <div className="text-[11px] uppercase text-oq-muted">Latest close (hist.)</div>
              <div className="mt-1 font-mono-num text-lg">{formatINR(summary.last.close)}</div>
            </Panel>
            <Panel>
              <div className="text-[11px] uppercase text-oq-muted">Session change</div>
              <div
                className={`mt-1 font-mono-num text-lg ${
                  (summary.change ?? 0) >= 0 ? 'text-oq-positive' : 'text-oq-negative'
                }`}
              >
                {formatPct(summary.changePct)}
              </div>
            </Panel>
            <Panel>
              <div className="text-[11px] uppercase text-oq-muted">Data status</div>
              <div className="mt-1 text-sm capitalize">{data.cache_status.replace('_', ' ')}</div>
              <div className="mt-1 text-[11px] text-oq-muted">
                {data.source} · {data.price_adjustment}
              </div>
            </Panel>
          </div>

          {data.warnings.length > 0 && (
            <Alert>
              {data.warnings.map((w) => (
                <div key={w}>{w}</div>
              ))}
            </Alert>
          )}

          <Panel
            title="Candlestick chart"
            actions={
              <div className="flex items-center gap-3 text-xs text-oq-secondary">
                <label className="flex items-center gap-1">
                  <input type="checkbox" checked={showSma} onChange={(e) => setShowSma(e.target.checked)} />
                  SMA
                </label>
                <label className="flex items-center gap-1">
                  <input type="checkbox" checked={showEma} onChange={(e) => setShowEma(e.target.checked)} />
                  EMA
                </label>
                <label className="flex items-center gap-1">
                  <input type="checkbox" checked={showRsi} onChange={(e) => setShowRsi(e.target.checked)} />
                  RSI
                </label>
                <Button variant="ghost" onClick={exportCsv}>
                  <Download size={14} /> CSV
                </Button>
              </div>
            }
          >
            <CandlestickChart
              bars={data.bars}
              indicators={filteredIndicators}
              showVolume
              showRsi={showRsi}
              height={480}
            />
            <p className="mt-2 text-[11px] text-oq-muted">
              Retrieved {data.retrieved_at || '—'} · Available{' '}
              {data.available_start} → {data.available_end}
            </p>
          </Panel>

          <Panel title="OHLCV table">
            <div className="max-h-72 overflow-auto">
              <table className="w-full text-left text-xs">
                <thead className="sticky top-0 bg-oq-panel text-oq-muted">
                  <tr>
                    {['Date', 'Open', 'High', 'Low', 'Close', 'Volume'].map((h) => (
                      <th key={h} className="px-2 py-1.5 font-medium">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="font-mono-num">
                  {[...data.bars].reverse().slice(0, 100).map((b) => (
                    <tr key={b.date} className="border-t border-oq-border/60">
                      <td className="px-2 py-1">{b.date}</td>
                      <td className="px-2 py-1">{b.open.toFixed(2)}</td>
                      <td className="px-2 py-1">{b.high.toFixed(2)}</td>
                      <td className="px-2 py-1">{b.low.toFixed(2)}</td>
                      <td className="px-2 py-1">{b.close.toFixed(2)}</td>
                      <td className="px-2 py-1">{b.volume ?? '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
        </>
      )}
    </div>
  )
}
