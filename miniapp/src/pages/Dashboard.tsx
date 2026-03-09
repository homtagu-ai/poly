import { useQuery } from '@tanstack/react-query'
import Card from '../components/Card'
import PnLBadge from '../components/PnLBadge'
import ProgressBar from '../components/ProgressBar'
import { configApi, positionApi } from '../api/endpoints'
import { useNavigate } from 'react-router-dom'
import { useTelegram } from '../hooks/useTelegram'

export default function Dashboard() {
  const navigate = useNavigate()
  const { user } = useTelegram()

  const { data: configs = [] } = useQuery({
    queryKey: ['configs'],
    queryFn: configApi.list,
  })

  const { data: positions = [] } = useQuery({
    queryKey: ['positions'],
    queryFn: positionApi.list,
    refetchInterval: 30_000,
  })

  const activeConfigs = configs.filter(c => c.is_active)
  const totalSpent = configs.reduce((sum, c) => sum + (c.total_spent_usd || 0), 0)
  const totalPnL = positions.reduce((sum, p) => sum + (p.unrealized_pnl || 0), 0)

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">
            {'\u{1F3AF}'} PolyHunter
          </h1>
          <p className="text-text-secondary text-sm">
            Welcome, {user?.first_name || 'Trader'}
          </p>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-2 gap-3">
        <Card>
          <p className="text-text-secondary text-xs mb-1">Active Configs</p>
          <p className="text-2xl font-bold text-accent-teal">{activeConfigs.length}</p>
        </Card>
        <Card>
          <p className="text-text-secondary text-xs mb-1">Open Positions</p>
          <p className="text-2xl font-bold">{positions.length}</p>
        </Card>
        <Card>
          <p className="text-text-secondary text-xs mb-1">Total Spent</p>
          <p className="text-xl font-bold font-mono">${totalSpent.toFixed(2)}</p>
        </Card>
        <Card>
          <p className="text-text-secondary text-xs mb-1">Unrealized P&L</p>
          <PnLBadge value={totalPnL} size="md" />
        </Card>
      </div>

      {/* Quick Actions */}
      <div className="flex gap-3">
        <button onClick={() => navigate('/configs/new')} className="btn-primary flex-1">
          {'\u{2795}'} New Config
        </button>
        <button onClick={() => navigate('/positions')} className="btn-secondary flex-1">
          {'\u{1F4BC}'} Positions
        </button>
      </div>

      {/* Active Configs Preview */}
      {activeConfigs.length > 0 && (
        <div>
          <h2 className="text-sm font-semibold text-text-secondary mb-2 uppercase tracking-wider">
            Active Configs
          </h2>
          <div className="space-y-2">
            {activeConfigs.slice(0, 3).map(cfg => (
              <Card key={cfg.id} onClick={() => navigate(`/configs/${cfg.id}`)} className="flex items-center justify-between">
                <div>
                  <p className="font-medium">{cfg.tag || `${cfg.target_wallet.slice(0, 6)}...${cfg.target_wallet.slice(-4)}`}</p>
                  <p className="text-xs text-text-secondary">
                    {cfg.copy_mode === 'percentage' ? `${cfg.copy_percentage}%` : `$${cfg.copy_percentage}`} copy
                  </p>
                </div>
                <div className="text-right">
                  <span className="badge-active">Active</span>
                  {cfg.total_spend_limit_usd && (
                    <div className="mt-1 w-24">
                      <ProgressBar used={cfg.total_spent_usd} limit={cfg.total_spend_limit_usd} showValues={false} />
                    </div>
                  )}
                </div>
              </Card>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
