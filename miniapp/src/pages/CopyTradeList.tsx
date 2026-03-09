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
    return (
      <div className="flex flex-col items-center justify-center py-20">
        <div className="spinner" />
        <p className="text-text-secondary text-sm mt-4">Loading configs...</p>
      </div>
    )
  }

  if (configs.length === 0) {
    return (
      <EmptyState
        icon={'\u{2699}\u{FE0F}'}
        title="No Copy Trade Configs"
        description="Create your first config to start copying whale trades automatically."
        action={{ label: '+ Create Config', onClick: () => navigate('/configs/new') }}
      />
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold text-text-primary">Copy Trade Configs</h1>
        <button onClick={() => navigate('/configs/new')} className="btn-primary text-xs !px-4 !py-2">
          + New
        </button>
      </div>

      <div className="space-y-3">
        {configs.map(cfg => (
          <Card key={cfg.id} onClick={() => navigate(`/configs/${cfg.id}`)} glow>
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <p className="font-semibold text-text-primary">
                    {cfg.tag || `${cfg.target_wallet.slice(0, 6)}...${cfg.target_wallet.slice(-4)}`}
                  </p>
                  <p className="text-xs text-text-muted font-mono mt-0.5">
                    {cfg.target_wallet.slice(0, 10)}...{cfg.target_wallet.slice(-6)}
                  </p>
                </div>
                <span className={cfg.is_active ? 'badge-active' : 'badge-paused'}>
                  {cfg.is_active ? 'Active' : 'Paused'}
                </span>
              </div>

              <div className="grid grid-cols-3 gap-2">
                {[
                  { label: 'Copy', value: cfg.copy_mode === 'percentage' ? `${cfg.copy_percentage}%` : `$${cfg.copy_percentage}` },
                  { label: 'Markets', value: String(cfg.markets_entered || 0) },
                  { label: 'Spent', value: `$${(cfg.total_spent_usd || 0).toFixed(0)}` },
                ].map(stat => (
                  <div key={stat.label} className="bg-bg-primary rounded-lg px-2.5 py-1.5 text-center" style={{ border: '1px solid #1c3040' }}>
                    <span className="block text-[10px] text-text-muted uppercase font-medium">{stat.label}</span>
                    <span className="block text-sm font-bold font-mono text-text-primary">{stat.value}</span>
                  </div>
                ))}
              </div>

              {cfg.total_spend_limit_usd != null && cfg.total_spend_limit_usd > 0 && (
                <ProgressBar
                  used={cfg.total_spent_usd || 0}
                  limit={cfg.total_spend_limit_usd}
                  label="Spend Limit"
                />
              )}
            </div>
          </Card>
        ))}
      </div>
    </div>
  )
}
