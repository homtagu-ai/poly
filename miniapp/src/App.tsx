import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import CopyTradeList from './pages/CopyTradeList'
import CopyTradeEdit from './pages/CopyTradeEdit'
import Positions from './pages/Positions'
import History from './pages/History'
import Settings from './pages/Settings'

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/configs" element={<CopyTradeList />} />
        <Route path="/configs/:id" element={<CopyTradeEdit />} />
        <Route path="/configs/new" element={<CopyTradeEdit />} />
        <Route path="/positions" element={<Positions />} />
        <Route path="/history" element={<History />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  )
}
