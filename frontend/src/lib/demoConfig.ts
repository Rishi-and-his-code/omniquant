/** Shared evaluation demonstration configuration (does not auto-run fetches or AI). */
export const DEMO_CONFIG = {
  symbol: 'RELIANCE.NS',
  startDate: '2023-01-01',
  endDate: '2025-12-31',
  initialCapital: 100_000,
  allocationPercent: 100,
  transactionCostPercent: 0.1,
  slippagePercent: 0.05,
  /** Prefer these saved strategy names when selecting the primary demo strategy. */
  preferredStrategyNames: [
    'AI Generated — EMA 20/50 Demo',
    'OmniQuant — EMA 20/50 Demo',
    'Demo EMA 20/50 UI',
    'Demo EMA 20/50',
    'AUDIT EMA 20/50',
  ],
  emaFast: 20,
  emaSlow: 50,
  secondaryEmaFast: 10,
  secondaryEmaSlow: 30,
  preferredSecondaryNames: [
    'OmniQuant — EMA 10/30 Comparison',
    'AUDIT EMA 10/30',
  ],
} as const

export function pickDemoStrategyId(
  strategies: {
    id: number
    name: string
    latest_version?: {
      id: number
      strategy_type: string
      dsl?: { parameters?: Record<string, number> }
    } | null
    versions: {
      id: number
      strategy_type: string
      dsl?: { parameters?: Record<string, number> }
    }[]
  }[],
  preferredNames: readonly string[],
  fast: number,
  slow: number,
): { strategyId: number; versionId: number } | null {
  for (const name of preferredNames) {
    const hit = strategies.find((s) => s.name === name)
    const version = hit?.latest_version ?? hit?.versions[0]
    if (hit && version) {
      return { strategyId: hit.id, versionId: version.id }
    }
  }
  for (const s of strategies) {
    for (const v of s.versions.length ? s.versions : s.latest_version ? [s.latest_version] : []) {
      if (v.strategy_type !== 'ema_crossover') continue
      const params = v.dsl?.parameters
      if (params?.fast_period === fast && params?.slow_period === slow) {
        return { strategyId: s.id, versionId: v.id }
      }
    }
  }
  return null
}
