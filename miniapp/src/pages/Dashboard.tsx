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
    <div className="space-y-5">
      {/* Brand Header */}
      <div className="pt-1">
        <div className="flex items-center gap-3 mb-1">
          <div className="w-10 h-10 rounded-xl flex items-center justify-center"
            style={{ background: 'linear-gradient(135deg, #3ba5b5, #0dd3ce)' }}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 2L2 7l10 5 10-5-10-5z M2 17l10 5 10-5 M2 12l10 5 10-5" />
            </svg>
          </div>
          <div>
            <h1 className="text-xl font-extrabold text-gradient">PolyHunter</h1>
            <p className="text-text-secondary text-xs">
              Welcome back, {user?.first_name || 'Trader'}
            </p>
          </div>
        </div>
      </div>

      {/* Stats Grid — animated border on the hero card */}
      <Card animated className="!p-0">
        <div className="p-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <p className="section-header !mb-1">Active Configs</p>
              <p className="text-2xl font-extrabold text-gradient font-mono">{activeConfigs.length}</p>
            </div>
            <div>
              <p className="section-header !mb-1">Open Positions</p>
              <p className="text-2xl font-extrabold font-mono text-text-primary">{positions.length}</p>
            </div>
            <div>
              <p className="section-header !mb-1">Total Spent</p>
              <p className="text-lg font-bold font-mono text-text-primary">${totalSpent.toFixed(2)}</p>
            </div>
            <div>
              <p className="section-header !mb-1">Unrealized P&L</p>
              <PnLBadge value={totalPnL} size="md" />
            </div>
          </div>
        </div>
      </Card>

      {/* Quick Actions */}
      <div className="flex gap-3">
        <button onClick={() => navigate('/configs/new')} className="btn-primary flex-1 text-center">
          + New Config
        </button>
        <button onClick={() => navigate('/positions')} className="btn-secondary flex-1 text-center">
          Positions
        </button>
      </div>

      {/* Active Configs Preview */}
      {activeConfigs.length > 0 && (
        <div>
          <p className="section-header">Active Configs</p>
          <div className="space-y-2">
            {activeConfigs.slice(0, 3).map(cfg => (
              <Card key={cfg.id} onClick={() => navigate(`/configs/${cfg.id}`)} glow>
                <div className="flex items-center justify-between">
                  <div>
                    <p className="font-semibold text-sm text-text-primary">
                      {cfg.tag || `${cfg.target_wallet.slice(0, 6)}...${cfg.target_wallet.slice(-4)}`}
                    </p>
                    <p className="text-xs text-text-muted font-mono mt-0.5">
                      {cfg.copy_mode === 'percentage' ? `${cfg.copy_percentage}%` : `$${cfg.copy_percentage}`} copy
                    </p>
                  </div>
                  <div className="text-right flex flex-col items-end gap-1.5">
                    <span className="badge-active">Active</span>
                    {cfg.total_spend_limit_usd != null && cfg.total_spend_limit_usd > 0 && (
                      <div className="w-20">
                        <ProgressBar used={cfg.total_spent_usd} limit={cfg.total_spend_limit_usd} showValues={false} />
                      </div>
                    )}
                  </div>
                </div>
              </Card>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
