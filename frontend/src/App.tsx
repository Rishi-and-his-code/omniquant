import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AppShell } from './components/layout/AppShell'
import { AppProvider } from './context/AppContext'
import { BacktestLab } from './pages/BacktestLab'
import { MarketExplorer } from './pages/MarketExplorer'
import { ResearchHistory } from './pages/ResearchHistory'
import { StrategyStudio } from './pages/StrategyStudio'

export default function App() {
  return (
    <AppProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<AppShell />}>
            <Route path="/" element={<MarketExplorer />} />
            <Route path="/strategy" element={<StrategyStudio />} />
            <Route path="/backtest" element={<BacktestLab />} />
            <Route path="/history" element={<ResearchHistory />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </AppProvider>
  )
}
