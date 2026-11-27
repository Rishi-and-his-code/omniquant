import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from 'react'
import { api } from '../services/api'
import type { HealthResponse, Instrument } from '../types'

interface AppState {
  health: HealthResponse | null
  instruments: Instrument[]
  selectedSymbol: string
  setSelectedSymbol: (s: string) => void
  pendingStrategyVersionId: number | null
  setPendingStrategyVersionId: (id: number | null) => void
  pendingBacktestId: number | null
  setPendingBacktestId: (id: number | null) => void
  refreshHealth: () => Promise<void>
}

const Ctx = createContext<AppState | null>(null)

export function AppProvider({ children }: { children: ReactNode }) {
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [instruments, setInstruments] = useState<Instrument[]>([])
  const [selectedSymbol, setSelectedSymbol] = useState('RELIANCE.NS')
  const [pendingStrategyVersionId, setPendingStrategyVersionId] = useState<number | null>(null)
  const [pendingBacktestId, setPendingBacktestId] = useState<number | null>(null)

  const refreshHealth = async () => {
    try {
      setHealth(await api.health())
    } catch {
      setHealth(null)
    }
  }

  useEffect(() => {
    void refreshHealth()
    void api.instruments().then(setInstruments).catch(() => setInstruments([]))
    const t = setInterval(() => void refreshHealth(), 30000)
    return () => clearInterval(t)
  }, [])

  return (
    <Ctx.Provider
      value={{
        health,
        instruments,
        selectedSymbol,
        setSelectedSymbol,
        pendingStrategyVersionId,
        setPendingStrategyVersionId,
        pendingBacktestId,
        setPendingBacktestId,
        refreshHealth,
      }}
    >
      {children}
    </Ctx.Provider>
  )
}

export function useApp() {
  const v = useContext(Ctx)
  if (!v) throw new Error('useApp must be used within AppProvider')
  return v
}
