interface PnLBadgeProps {
  value: number
  percentage?: number
  size?: 'sm' | 'md' | 'lg'
}

export default function PnLBadge({ value, percentage, size = 'md' }: PnLBadgeProps) {
  const isPositive = value >= 0
  const color = isPositive ? '#10b981' : '#ef4444'
  const bgColor = isPositive ? 'rgba(16,185,129,0.12)' : 'rgba(239,68,68,0.12)'
  const sign = isPositive ? '+' : ''

  const sizeClasses = {
    sm: 'text-sm px-2 py-0.5',
    md: 'text-base px-2.5 py-0.5',
    lg: 'text-lg font-bold px-3 py-1',
  }

  return (
    <span
      className={`inline-flex items-center gap-1 font-mono rounded-lg ${sizeClasses[size]}`}
      style={{ color, background: bgColor }}
    >
      <span className="w-1.5 h-1.5 rounded-full" style={{ background: color }} />
      {sign}${Math.abs(value).toFixed(2)}
      {percentage !== undefined && (
        <span className="text-text-secondary ml-0.5 text-xs">
          ({sign}{Math.abs(percentage).toFixed(1)}%)
        </span>
      )}
    </span>
  )
}
