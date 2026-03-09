import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import Card from '../components/Card'
import EmptyState from '../components/EmptyState'
import { historyApi } from '../api/endpoints'

export default function History() {
  const [page, setPage] = useState(1)

  const { data: trades = [], isLoading } = useQuery({
    queryKey: ['history', page],
    queryFn: () => historyApi.list(page, 20),
  })

  if (isLoading && page === 1) {
    return <div className="flex justify-center py-16"><span className="text-2xl animate-pulse">Loading...</span></div>
  }

  if (trades.length === 0 && page === 1) {
    return (
      <EmptyState
        icon={'\u{1F4DC}'}
        title="No Trade History"
        description="Your trade history will appear here once trades are executed."
      />
    )
  }

  const getOutcomeColor = (outcome: string | null) => {
    if (!outcome) return 'text-text-secondary'
    switch (outcome.toLowerCase()) {
      case 'filled':
      case 'success':
        return 'text-accent-green'
      case 'failed':
      case 'error':
        return 'text-accent-red'
      case 'partial':
        return 'text-accent-yellow'
      default:
        return 'text-text-secondary'
    }
  }

  const getActionIcon = (action: string) => {
    switch (action.toLowerCase()) {
      case 'buy':
        return '\u{1F7E2}'
      case 'sell':
        return '\u{1F534}'
      case 'tp_hit':
        return '\u{1F3AF}'
      case 'sl_hit':
        return '\u{1F6D1}'
      default:
        return '\u{25CB}'
    }
  }

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold">{'\u{1F4DC}'} Trade History</h1>

      <div className="space-y-2">
        {trades.map(trade => (
          <Card key={trade.id} className="space-y-1">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span>{getActionIcon(trade.action)}</span>
                <span className="font-medium text-sm uppercase">{trade.action}</span>
              </div>
              <span className={`text-xs font-medium ${getOutcomeColor(trade.outcome)}`}>
                {trade.outcome || 'pending'}
              </span>
            </div>

            {trade.market_slug && (
              <p className="text-xs text-text-secondary truncate">{trade.market_slug}</p>
            )}

            <div className="flex justify-between text-xs text-text-secondary">
              <div className="flex gap-3">
                {trade.order_size_usd != null && (
                  <span>${trade.order_size_usd.toFixed(2)}</span>
                )}
                {trade.execution_price != null && (
                  <span>@ ${trade.execution_price.toFixed(3)}</span>
                )}
                {trade.shares != null && (
                  <span>{trade.shares.toFixed(2)} shares</span>
                )}
              </div>
              <span>{new Date(trade.created_at).toLocaleDateString()}</span>
            </div>

            {trade.failure_reason && (
              <p className="text-xs text-accent-red mt-1">{trade.failure_reason}</p>
            )}
          </Card>
        ))}
      </div>

      {/* Pagination */}
      <div className="flex justify-center gap-3 py-4">
        <button
          onClick={() => setPage(p => Math.max(1, p - 1))}
          disabled={page === 1}
          className="btn-secondary text-sm disabled:opacity-40"
        >
          Previous
        </button>
        <span className="text-text-secondary text-sm self-center">Page {page}</span>
        <button
          onClick={() => setPage(p => p + 1)}
          disabled={trades.length < 20}
          className="btn-secondary text-sm disabled:opacity-40"
        >
          Next
        </button>
      </div>
    </div>
  )
}
