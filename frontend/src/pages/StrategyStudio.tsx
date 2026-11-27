import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Alert, Button, Input, Label, Panel, Select } from '../components/ui/primitives'
import { useApp } from '../context/AppContext'
import { api } from '../services/api'
import type { Strategy, StrategyDSL } from '../types'

type Mode = 'manual' | 'ai'
type StratType = StrategyDSL['strategy_type']

const EXAMPLES = [
  'Build a 20-day and 50-day moving average crossover strategy.',
  'Create an EMA crossover strategy using periods 10 and 30.',
  'Create an RSI strategy with period 14, oversold threshold 30, and overbought threshold 70.',
]

function defaultParams(t: StratType): Record<string, number> {
  if (t === 'rsi_mean_reversion') return { period: 14, lower: 30, upper: 70 }
  return { fast_period: 20, slow_period: 50 }
}

function buildDsl(name: string, type: StratType, params: Record<string, number>): StrategyDSL {
  return {
    schema_version: 1,
    name,
    strategy_type: type,
    parameters: params,
    position_type: 'long_only',
  }
}

function rulesFor(type: StratType, params: Record<string, number>) {
  if (type === 'sma_crossover') {
    return {
      entry: `Fast SMA(${params.fast_period}) crosses above Slow SMA(${params.slow_period})`,
      exit: `Fast SMA(${params.fast_period}) crosses below Slow SMA(${params.slow_period})`,
    }
  }
  if (type === 'ema_crossover') {
    return {
      entry: `Fast EMA(${params.fast_period}) crosses above Slow EMA(${params.slow_period})`,
      exit: `Fast EMA(${params.fast_period}) crosses below Slow EMA(${params.slow_period})`,
    }
  }
  return {
    entry: `RSI(${params.period}) crosses below ${params.lower}`,
    exit: `RSI(${params.period}) crosses above ${params.upper}`,
  }
}

export function StrategyStudio() {
  const navigate = useNavigate()
  const { setPendingStrategyVersionId, pendingStrategyVersionId, health } = useApp()
  const [mode, setMode] = useState<Mode>('manual')
  const [strategies, setStrategies] = useState<Strategy[]>([])
  const [name, setName] = useState('My Strategy')
  const [type, setType] = useState<StratType>('ema_crossover')
  const [params, setParams] = useState(defaultParams('ema_crossover'))
  const [editingId, setEditingId] = useState<number | null>(null)
  const [prompt, setPrompt] = useState(EXAMPLES[1])
  const [aiMsg, setAiMsg] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [savedVersionId, setSavedVersionId] = useState<number | null>(null)
  const consumedPendingId = useRef(false)

  const dsl = useMemo(() => buildDsl(name, type, params), [name, type, params])
  const rules = useMemo(() => rulesFor(type, params), [type, params])

  const reload = () => api.strategies().then(setStrategies).catch(() => setStrategies([]))

  useEffect(() => {
    let cancelled = false
    void api
      .strategies()
      .then((list) => {
        if (cancelled || consumedPendingId.current) return
        setStrategies(list)
        if (pendingStrategyVersionId == null) return
        consumedPendingId.current = true
        const owner = list.find((s) =>
          s.versions.some((v) => v.id === pendingStrategyVersionId),
        )
        const version = owner?.versions.find((v) => v.id === pendingStrategyVersionId)
        if (owner && version) {
          setEditingId(owner.id)
          setName(version.dsl.name || owner.name)
          setType(version.dsl.strategy_type)
          setParams({ ...version.dsl.parameters })
          setSavedVersionId(version.id)
          setMode('manual')
        }
        setPendingStrategyVersionId(null)
      })
      .catch(() => {
        if (!cancelled) setStrategies([])
      })
    return () => {
      cancelled = true
    }
  }, [pendingStrategyVersionId, setPendingStrategyVersionId])

  const onTypeChange = (t: StratType) => {
    setType(t)
    setParams(defaultParams(t))
  }

  const save = async () => {
    setSaving(true)
    setError(null)
    try {
      if (editingId) {
        const v = await api.createVersion(editingId, dsl)
        setSavedVersionId(v.id)
      } else {
        const s = await api.createStrategy({ name, dsl })
        setEditingId(s.id)
        setSavedVersionId(s.latest_version?.id ?? null)
      }
      await reload()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  const generate = async () => {
    setGenerating(true)
    setAiMsg(null)
    setError(null)
    try {
      const res = await api.generateStrategy(prompt)
      if (res.status === 'unsupported') {
        setAiMsg(res.message || 'Unsupported strategy request.')
        return
      }
      if (res.status !== 'ok' || !res.dsl) {
        setError(res.message || 'AI generation failed')
        return
      }
      setName(res.dsl.name)
      setType(res.dsl.strategy_type)
      setParams(res.dsl.parameters)
      setAiMsg(`Generated via ${res.model_name || 'model'} — review before saving.`)
      setMode('manual')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'AI unavailable')
    } finally {
      setGenerating(false)
    }
  }

  const loadStrategy = (s: Strategy) => {
    const v = s.latest_version
    if (!v) return
    setEditingId(s.id)
    setName(s.name)
    setType(v.dsl.strategy_type)
    setParams(v.dsl.parameters)
    setSavedVersionId(v.id)
    setMode('manual')
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold">Strategy Studio</h1>
        <p className="mt-1 text-sm text-oq-secondary">
          Build validated Strategy DSL templates manually or with AI assistance.
        </p>
      </div>

      <div className="flex gap-2">
        <Button variant={mode === 'manual' ? 'primary' : 'secondary'} onClick={() => setMode('manual')}>
          Manual Builder
        </Button>
        <Button variant={mode === 'ai' ? 'primary' : 'secondary'} onClick={() => setMode('ai')}>
          AI Builder
        </Button>
      </div>

      {error && <Alert tone="error">{error}</Alert>}
      {aiMsg && <Alert tone="info">{aiMsg}</Alert>}

      {mode === 'ai' ? (
        <Panel title="Natural-language strategy generation">
          {!health?.ai_configured && (
            <Alert tone="warning">
              AI is not configured. Set AI_ENABLED plus the OmniRoute URL, key, and model in
              `.env`. OpenRouter is used only if OmniRoute fails or times out. The manual
              builder remains fully functional.
            </Alert>
          )}
          <Label>Prompt</Label>
          <textarea
            className="mt-1 min-h-28 w-full rounded-md border border-oq-border bg-oq-elevated p-3 text-sm text-oq-text outline-none focus:border-oq-accent"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
          />
          <div className="mt-3 flex flex-wrap gap-2">
            {EXAMPLES.map((ex) => (
              <Button key={ex} variant="ghost" className="text-xs" onClick={() => setPrompt(ex)}>
                {ex.slice(0, 48)}…
              </Button>
            ))}
          </div>
          <div className="mt-4">
            <Button onClick={() => void generate()} disabled={generating || !health?.ai_configured}>
              {generating ? 'Generating…' : 'Generate strategy'}
            </Button>
          </div>
        </Panel>
      ) : (
        <div className="grid gap-4 lg:grid-cols-3">
          <Panel title="Configuration" className="lg:col-span-1">
            <div className="space-y-3">
              <div>
                <Label>Strategy name</Label>
                <Input value={name} onChange={(e) => setName(e.target.value)} />
              </div>
              <div>
                <Label>Template</Label>
                <Select value={type} onChange={(e) => onTypeChange(e.target.value as StratType)}>
                  <option value="sma_crossover">SMA crossover</option>
                  <option value="ema_crossover">EMA crossover</option>
                  <option value="rsi_mean_reversion">RSI mean reversion</option>
                </Select>
              </div>
              {type !== 'rsi_mean_reversion' ? (
                <>
                  <div>
                    <Label>Fast period</Label>
                    <Input
                      type="number"
                      value={params.fast_period}
                      onChange={(e) =>
                        setParams((p) => ({ ...p, fast_period: Number(e.target.value) }))
                      }
                    />
                  </div>
                  <div>
                    <Label>Slow period</Label>
                    <Input
                      type="number"
                      value={params.slow_period}
                      onChange={(e) =>
                        setParams((p) => ({ ...p, slow_period: Number(e.target.value) }))
                      }
                    />
                  </div>
                </>
              ) : (
                <>
                  <div>
                    <Label>RSI period</Label>
                    <Input
                      type="number"
                      value={params.period}
                      onChange={(e) => setParams((p) => ({ ...p, period: Number(e.target.value) }))}
                    />
                  </div>
                  <div>
                    <Label>Lower threshold</Label>
                    <Input
                      type="number"
                      value={params.lower}
                      onChange={(e) => setParams((p) => ({ ...p, lower: Number(e.target.value) }))}
                    />
                  </div>
                  <div>
                    <Label>Upper threshold</Label>
                    <Input
                      type="number"
                      value={params.upper}
                      onChange={(e) => setParams((p) => ({ ...p, upper: Number(e.target.value) }))}
                    />
                  </div>
                </>
              )}
              <div className="flex flex-wrap gap-2 pt-2">
                <Button onClick={() => void save()} disabled={saving}>
                  {saving ? 'Saving…' : editingId ? 'Save new version' : 'Save strategy'}
                </Button>
                <Button
                  variant="secondary"
                  disabled={!savedVersionId}
                  onClick={() => {
                    setPendingStrategyVersionId(savedVersionId)
                    navigate('/backtest')
                  }}
                >
                  Send to Backtest Lab
                </Button>
                <Button
                  variant="ghost"
                  onClick={() => {
                    setEditingId(null)
                    setSavedVersionId(null)
                    setName('My Strategy')
                    onTypeChange('ema_crossover')
                  }}
                >
                  New
                </Button>
              </div>
            </div>
          </Panel>

          <div className="space-y-4 lg:col-span-2">
            <Panel title="Entry / Exit rules">
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="rounded-md border border-oq-positive/30 bg-oq-positive/5 p-3">
                  <div className="text-[11px] uppercase tracking-wide text-oq-positive">Entry</div>
                  <div className="mt-1 text-sm">{rules.entry}</div>
                </div>
                <div className="rounded-md border border-oq-negative/30 bg-oq-negative/5 p-3">
                  <div className="text-[11px] uppercase tracking-wide text-oq-negative">Exit</div>
                  <div className="mt-1 text-sm">{rules.exit}</div>
                </div>
              </div>
              <p className="mt-3 text-xs text-oq-muted">
                Long-only · Daily bars · Signals execute at next session open
              </p>
            </Panel>

            <Panel title="Strategy JSON preview">
              <pre className="max-h-64 overflow-auto rounded-md bg-oq-bg p-3 font-mono-num text-xs text-oq-secondary">
                {JSON.stringify(dsl, null, 2)}
              </pre>
            </Panel>

            <Panel title="Saved strategies">
              <div className="space-y-2">
                {strategies.length === 0 && (
                  <p className="text-sm text-oq-muted">No saved strategies yet.</p>
                )}
                {strategies.map((s) => (
                  <div
                    key={s.id}
                    className="flex items-center justify-between rounded-md border border-oq-border bg-oq-elevated px-3 py-2"
                  >
                    <div>
                      <div className="text-sm font-medium">{s.name}</div>
                      <div className="text-xs text-oq-muted">
                        {s.latest_version?.strategy_type} · v{s.latest_version?.version_number}
                      </div>
                    </div>
                    <Button variant="ghost" onClick={() => loadStrategy(s)}>
                      Open
                    </Button>
                  </div>
                ))}
              </div>
            </Panel>
          </div>
        </div>
      )}
    </div>
  )
}
