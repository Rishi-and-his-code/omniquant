import Plot from 'react-plotly.js'
import type { OHLCVBar, TradeMarker } from '../../types'

interface Props {
  bars: OHLCVBar[]
  indicators?: Record<string, (number | null)[]>
  markers?: TradeMarker[]
  height?: number
  showVolume?: boolean
  showRsi?: boolean
}

const layoutBase = {
  paper_bgcolor: '#151D2B',
  plot_bgcolor: '#151D2B',
  font: { color: '#94A3B8', size: 11, family: 'Inter, sans-serif' },
  margin: { l: 48, r: 24, t: 24, b: 40 },
  xaxis: {
    gridcolor: '#253246',
    rangeslider: { visible: false },
  },
  yaxis: { gridcolor: '#253246', side: 'right' as const },
  legend: { orientation: 'h' as const, y: 1.08, x: 0 },
  dragmode: 'zoom' as const,
}

export function CandlestickChart({
  bars,
  indicators = {},
  markers = [],
  height = 420,
  showVolume = true,
  showRsi = false,
}: Props) {
  const dates = bars.map((b) => b.date)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const traces: any[] = [
    {
      type: 'candlestick',
      x: dates,
      open: bars.map((b) => b.open),
      high: bars.map((b) => b.high),
      low: bars.map((b) => b.low),
      close: bars.map((b) => b.close),
      name: 'OHLC',
      increasing: { line: { color: '#10B981' } },
      decreasing: { line: { color: '#EF4444' } },
      xaxis: 'x',
      yaxis: 'y',
    },
  ]

  for (const [name, values] of Object.entries(indicators)) {
    if (name.startsWith('rsi')) continue
    traces.push({
      type: 'scatter',
      mode: 'lines',
      x: dates,
      y: values,
      name: name.toUpperCase(),
      line: { width: 1.4 },
      xaxis: 'x',
      yaxis: 'y',
    })
  }

  const buys = markers.filter((m) => m.side === 'buy')
  const sells = markers.filter((m) => m.side === 'sell')
  if (buys.length) {
    traces.push({
      type: 'scatter',
      mode: 'markers',
      x: buys.map((m) => m.date),
      y: buys.map((m) => m.price),
      name: 'Buy',
      marker: { symbol: 'triangle-up', size: 11, color: '#10B981' },
      text: buys.map((m) => `Buy ${m.quantity} @ ${m.price.toFixed(2)}`),
      hoverinfo: 'text+x',
    })
  }
  if (sells.length) {
    traces.push({
      type: 'scatter',
      mode: 'markers',
      x: sells.map((m) => m.date),
      y: sells.map((m) => m.price),
      name: 'Sell',
      marker: { symbol: 'triangle-down', size: 11, color: '#EF4444' },
      text: sells.map((m) => `Sell ${m.quantity} @ ${m.price.toFixed(2)}`),
      hoverinfo: 'text+x',
    })
  }

  const hasRsi = showRsi && Object.keys(indicators).some((k) => k.startsWith('rsi'))
  const rows = showVolume || hasRsi ? (hasRsi && showVolume ? 3 : 2) : 1

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const layout: Record<string, any> = {
    ...layoutBase,
    height,
    grid: rows > 1 ? { rows, columns: 1, pattern: 'independent' } : undefined,
  }

  if (showVolume) {
    traces.push({
      type: 'bar',
      x: dates,
      y: bars.map((b) => b.volume ?? 0),
      name: 'Volume',
      marker: { color: '#334155' },
      xaxis: 'x2',
      yaxis: 'y2',
    })
    layout.xaxis = { ...layoutBase.xaxis, matches: undefined }
    layout.xaxis2 = { gridcolor: '#253246', matches: 'x' }
    layout.yaxis = { ...layoutBase.yaxis, domain: hasRsi ? [0.45, 1] : [0.3, 1] }
    layout.yaxis2 = {
      gridcolor: '#253246',
      title: 'Vol',
      domain: hasRsi ? [0.22, 0.38] : [0, 0.22],
    }
  }

  if (hasRsi) {
    const rsiKey = Object.keys(indicators).find((k) => k.startsWith('rsi'))!
    traces.push({
      type: 'scatter',
      mode: 'lines',
      x: dates,
      y: indicators[rsiKey],
      name: rsiKey.toUpperCase(),
      line: { color: '#818CF8', width: 1.3 },
      xaxis: showVolume ? 'x3' : 'x2',
      yaxis: showVolume ? 'y3' : 'y2',
    })
    if (showVolume) {
      layout.xaxis3 = { gridcolor: '#253246', matches: 'x' }
      layout.yaxis3 = { gridcolor: '#253246', domain: [0, 0.16], range: [0, 100] }
    } else {
      layout.yaxis = { ...layoutBase.yaxis, domain: [0.3, 1] }
      layout.yaxis2 = { gridcolor: '#253246', domain: [0, 0.22], range: [0, 100] }
      layout.xaxis2 = { gridcolor: '#253246', matches: 'x' }
    }
  }

  return (
    <Plot
      data={traces}
      layout={layout}
      config={{ responsive: true, displayModeBar: true, displaylogo: false }}
      style={{ width: '100%' }}
      useResizeHandler
    />
  )
}

export function LineChart({
  series,
  height = 280,
  colors,
  yTitle,
}: {
  series: { name: string; points: { date: string; value: number }[] }[]
  height?: number
  colors?: string[]
  yTitle?: string
}) {
  const defaultColors = ['#6366F1', '#94A3B8', '#10B981']
  return (
    <Plot
      data={series.map((s, i) => ({
        type: 'scatter',
        mode: 'lines',
        name: s.name,
        x: s.points.map((p) => p.date),
        y: s.points.map((p) => p.value),
        line: { color: (colors || defaultColors)[i % defaultColors.length], width: 1.6 },
      }))}
      layout={{
        ...layoutBase,
        height,
        yaxis: { ...layoutBase.yaxis, title: yTitle },
      }}
      config={{ responsive: true, displayModeBar: false, displaylogo: false }}
      style={{ width: '100%' }}
      useResizeHandler
    />
  )
}
