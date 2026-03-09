import { useQuery } from '@tanstack/react-query'
import Card from '../components/Card'
import PnLBadge from '../components/PnLBadge'
import EmptyState from '../components/EmptyState'
import { positionApi } from '../api/endpoints'

export default function Positions() {
  const { data: positions = [], isLoading } = useQuery({
    queryKey: ['positions'],
    queryFn: positionApi.list,
    refetchInterval: 30_000,
  })

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center py-20">
        <div className="spinner" />
        <p className="text-text-secondary text-sm mt-4">Loading positions...</p>
      </div>
    )
  }

  if (positions.length === 0) {
    return (
      <EmptyState
        icon={'\u{1F4CA}'}
        title="No Open Positions"
        description="Your open positions will appear here once trades are executed."
      />
    )
  }

  const totalPnL = positions.reduce((sum, p) => sum + (p.unrealized_pnl || 0), 0)
  const totalCost = positions.reduce((sum, p) => sum + (p.cost_basis_usd || 0), 0)

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-bold text-text-primary">Open Positions</h1>

      {/* Summary Card */}
      <Card glow>
        <div className="flex items-center justify-between">
          <div>
            <p className="section-header !mb-1">Cost Basis</p>
            <p className="text-xl font-bold font-mono text-text-primary">${totalCost.toFixed(2)}</p>
          </div>
          <div className="text-right">
            <p className="section-header !mb-1">Unrealized P&L</p>
            <PnLBadge value={totalPnL} percentage={totalCost > 0 ? (totalPnL / totalCost) * 100 : 0} size="md" />
          </div>
        </div>
      </Card>

      {/* Position List */}
      <div className="space-y-2">
        {positions.map(pos => {
          const pnlPct = pos.cost_basis_usd > 0 ? (pos.unrealized_pnl / pos.cost_basis_usd) * 100 : 0
          return (
            <Card key={pos.id}>
              <div className="space-y-2">
                <div className="flex items-start justify-between">
                  <div className="flex-1 mr-3">
                    <p className="font-semibold text-sm text-text-primary leading-tight">{pos.market_slug}</p>
                    <div className="flex items-center gap-2 mt-1.5">
                      <span
                        className="text-xs font-semibold px-2 py-0.5 rounded-md"
                        style={{
                          background: pos.side === 'YES' ? 'rgba(16,185,129,0.12)' : 'rgba(239,68,68,0.12)',
                          color: pos.side === 'YES' ? '#10b981' : '#ef4444',
                          border: `1px solid ${pos.side === 'YES' ? 'rgba(16,185,129,0.2)' : 'rgba(239,68,68,0.2)'}`,
                        }}
                      >
                        {pos.side}
                      </span>
                      <span className="text-xs text-text-muted font-mono">
                        {pos.shares.toFixed(2)} @ ${pos.entry_price.toFixed(3)}
                      </span>
                    </div>
                  </div>
                  <div className="text-right shrink-0">
                    <PnLBadge value={pos.unrealized_pnl} percentage={pnlPct} size="sm" />
                  </div>
                </div>

                {pos.current_price !== null && (
                  <div className="flex justify-between text-xs font-mono pt-1" style={{ borderTop: '1px solid #1c3040' }}>
                    <span className="text-text-muted">Entry <span className="text-text-secondary">${pos.entry_price.toFixed(3)}</span></span>
                    <span className="text-text-muted">Current <span className="text-text-primary">${pos.current_price.toFixed(3)}</span></span>
                  </div>
                )}
              </div>
            </Card>
          )
        })}
      </div>
    </div>
  )
}
