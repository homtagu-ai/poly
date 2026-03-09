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
    return <div className="flex justify-center py-16"><span className="text-2xl animate-pulse">Loading...</span></div>
  }

  if (positions.length === 0) {
    return (
      <EmptyState
        icon={'\u{1F4BC}'}
        title="No Open Positions"
        description="Your open positions will appear here once trades are executed."
      />
    )
  }

  const totalPnL = positions.reduce((sum, p) => sum + (p.unrealized_pnl || 0), 0)
  const totalCost = positions.reduce((sum, p) => sum + (p.cost_basis_usd || 0), 0)

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">{'\u{1F4BC}'} Open Positions</h1>
        <span className="text-sm text-text-secondary">{positions.length} open</span>
      </div>

      {/* Summary Card */}
      <Card className="flex items-center justify-between">
        <div>
          <p className="text-text-secondary text-xs">Total Cost Basis</p>
          <p className="text-lg font-bold font-mono">${totalCost.toFixed(2)}</p>
        </div>
        <div className="text-right">
          <p className="text-text-secondary text-xs">Unrealized P&L</p>
          <PnLBadge value={totalPnL} percentage={totalCost > 0 ? (totalPnL / totalCost) * 100 : 0} size="md" />
        </div>
      </Card>

      {/* Position List */}
      <div className="space-y-3">
        {positions.map(pos => {
          const pnlPct = pos.cost_basis_usd > 0 ? (pos.unrealized_pnl / pos.cost_basis_usd) * 100 : 0
          return (
            <Card key={pos.id} className="space-y-2">
              <div className="flex items-center justify-between">
                <div>
                  <p className="font-semibold text-sm">{pos.market_slug}</p>
                  <div className="flex items-center gap-2 mt-0.5">
                    <span className={`text-xs font-medium px-1.5 py-0.5 rounded ${
                      pos.side === 'YES'
                        ? 'bg-accent-green/20 text-accent-green'
                        : 'bg-accent-red/20 text-accent-red'
                    }`}>
                      {pos.side}
                    </span>
                    <span className="text-xs text-text-secondary">
                      {pos.shares.toFixed(2)} shares @ ${pos.entry_price.toFixed(3)}
                    </span>
                  </div>
                </div>
                <div className="text-right">
                  <PnLBadge value={pos.unrealized_pnl} percentage={pnlPct} size="sm" />
                  <p className="text-xs text-text-secondary mt-0.5">
                    Cost: ${pos.cost_basis_usd.toFixed(2)}
                  </p>
                </div>
              </div>

              {pos.current_price !== null && (
                <div className="flex justify-between text-xs text-text-secondary">
                  <span>Entry: ${pos.entry_price.toFixed(3)}</span>
                  <span>Current: ${pos.current_price.toFixed(3)}</span>
                </div>
              )}
            </Card>
          )
        })}
      </div>
    </div>
  )
}
