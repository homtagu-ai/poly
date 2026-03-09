import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import Card from '../components/Card'
import EmptyState from '../components/EmptyState'
import { historyApi } from '../api/endpoints'

const ACTION_STYLES: Record<string, { icon: string; color: string; bg: string }> = {
  buy: { icon: '\u{2191}', color: '#10b981', bg: 'rgba(16,185,129,0.12)' },
  sell: { icon: '\u{2193}', color: '#ef4444', bg: 'rgba(239,68,68,0.12)' },
  tp_hit: { icon: '\u{1F3AF}', color: '#3ba5b5', bg: 'rgba(59,165,181,0.12)' },
  sl_hit: { icon: '\u{1F6E1}', color: '#f59e0b', bg: 'rgba(245,158,11,0.12)' },
}

export default function History() {
  const [page, setPage] = useState(1)

  const { data: trades = [], isLoading } = useQuery({
    queryKey: ['history', page],
    queryFn: () => historyApi.list(page, 20),
  })

  if (isLoading && page === 1) {
    return (
      <div className="flex flex-col items-center justify-center py-20">
        <div className="spinner" />
        <p className="text-text-secondary text-sm mt-4">Loading history...</p>
      </div>
    )
  }

  if (trades.length === 0 && page === 1) {
    return (
      <EmptyState
        icon={'\u{1F4C8}'}
        title="No Trade History"
        description="Your trade history will appear here once trades are executed."
      />
    )
  }

  const getOutcomeStyle = (outcome: string | null) => {
    if (!outcome) return { color: '#507080' }
    switch (outcome.toLowerCase()) {
      case 'filled':
      case 'success':
        return { color: '#10b981' }
      case 'failed':
      case 'error':
        return { color: '#ef4444' }
      case 'partial':
        return { color: '#f59e0b' }
      default:
        return { color: '#507080' }
    }
  }

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-bold text-text-primary">Trade History</h1>

      <div className="space-y-2">
        {trades.map(trade => {
          const style = ACTION_STYLES[trade.action.toLowerCase()] || { icon: '\u{25CB}', color: '#507080', bg: 'rgba(80,112,128,0.12)' }
          const outcomeStyle = getOutcomeStyle(trade.outcome)
          return (
            <Card key={trade.id}>
              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2.5">
                    <span
                      className="w-7 h-7 rounded-lg flex items-center justify-center text-xs font-bold"
                      style={{ background: style.bg, color: style.color }}
                    >
                      {style.icon}
                    </span>
                    <span className="font-semibold text-sm text-text-primary uppercase">{trade.action}</span>
                  </div>
                  <span
                    className="text-xs font-semibold px-2 py-0.5 rounded-md"
                    style={{ color: outcomeStyle.color, background: `${outcomeStyle.color}18` }}
                  >
                    {trade.outcome || 'pending'}
                  </span>
                </div>

                {trade.market_slug && (
                  <p className="text-xs text-text-secondary truncate pl-[38px]">{trade.market_slug}</p>
                )}

                <div className="flex justify-between text-xs font-mono text-text-muted pl-[38px]">
                  <div className="flex gap-3">
                    {trade.order_size_usd != null && <span>${trade.order_size_usd.toFixed(2)}</span>}
                    {trade.execution_price != null && <span>@ ${trade.execution_price.toFixed(3)}</span>}
                    {trade.shares != null && <span>{trade.shares.toFixed(2)} sh</span>}
                  </div>
                  <span>{new Date(trade.created_at).toLocaleDateString()}</span>
                </div>

                {trade.failure_reason && (
                  <p className="text-xs text-accent-red pl-[38px] mt-0.5">{trade.failure_reason}</p>
                )}
              </div>
            </Card>
          )
        })}
      </div>

      {/* Pagination */}
      <div className="flex justify-center items-center gap-4 py-4">
        <button
          onClick={() => setPage(p => Math.max(1, p - 1))}
          disabled={page === 1}
          className="btn-secondary text-xs !px-4 !py-2 disabled:opacity-30"
        >
          Previous
        </button>
        <span className="text-text-muted text-xs font-mono">Page {page}</span>
        <button
          onClick={() => setPage(p => p + 1)}
          disabled={trades.length < 20}
          className="btn-secondary text-xs !px-4 !py-2 disabled:opacity-30"
        >
          Next
        </button>
      </div>
    </div>
  )
}
