import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import Card from '../components/Card'
import EmptyState from '../components/EmptyState'
import ProgressBar from '../components/ProgressBar'
import { configApi } from '../api/endpoints'

export default function CopyTradeList() {
  const navigate = useNavigate()
  const { data: configs = [], isLoading } = useQuery({
    queryKey: ['configs'],
    queryFn: configApi.list,
  })

  if (isLoading) {
    return <div className="flex justify-center py-16"><span className="text-2xl animate-pulse">Loading...</span></div>
  }

  if (configs.length === 0) {
    return (
      <EmptyState
        icon={'\u{2699}\u{FE0F}'}
        title="No Copy Trade Configs"
        description="Create your first config to start copying whale trades automatically."
        action={{ label: '\u{2795} Create Config', onClick: () => navigate('/configs/new') }}
      />
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">{'\u{2699}\u{FE0F}'} Copy Trade Configs</h1>
        <button onClick={() => navigate('/configs/new')} className="btn-primary text-sm">
          {'\u{2795}'} New
        </button>
      </div>

      <div className="space-y-3">
        {configs.map(cfg => (
          <Card key={cfg.id} onClick={() => navigate(`/configs/${cfg.id}`)} className="space-y-2">
            <div className="flex items-center justify-between">
              <div>
                <p className="font-semibold">
                  {cfg.tag || `${cfg.target_wallet.slice(0, 6)}...${cfg.target_wallet.slice(-4)}`}
                </p>
                <p className="text-xs text-text-secondary font-mono">
                  {cfg.target_wallet.slice(0, 10)}...{cfg.target_wallet.slice(-6)}
                </p>
              </div>
              <span className={cfg.is_active ? 'badge-active' : 'badge-paused'}>
                {cfg.is_active ? '\u{1F7E2} Active' : '\u{1F534} Paused'}
              </span>
            </div>

            <div className="grid grid-cols-3 gap-2 text-xs text-text-secondary">
              <div>
                <span className="block text-text-muted">Copy</span>
                {cfg.copy_mode === 'percentage' ? `${cfg.copy_percentage}%` : `$${cfg.copy_percentage}`}
              </div>
              <div>
                <span className="block text-text-muted">Markets</span>
                {cfg.markets_entered || 0}
              </div>
              <div>
                <span className="block text-text-muted">Spent</span>
                ${(cfg.total_spent_usd || 0).toFixed(2)}
              </div>
            </div>

            {cfg.total_spend_limit_usd && cfg.total_spend_limit_usd > 0 && (
              <ProgressBar
                used={cfg.total_spent_usd || 0}
                limit={cfg.total_spend_limit_usd}
                label="Spend Limit"
              />
            )}
          </Card>
        ))}
      </div>
    </div>
  )
}
