interface PnLBadgeProps {
  value: number
  percentage?: number
  size?: 'sm' | 'md' | 'lg'
}

export default function PnLBadge({ value, percentage, size = 'md' }: PnLBadgeProps) {
  const isPositive = value >= 0
  const color = isPositive ? 'text-accent-green' : 'text-accent-red'
  const sign = isPositive ? '+' : ''
  const dot = isPositive ? '\u{1F7E2}' : '\u{1F534}'

  const sizeClasses = {
    sm: 'text-sm',
    md: 'text-base',
    lg: 'text-xl font-bold',
  }

  return (
    <span className={`${color} ${sizeClasses[size]} font-mono`}>
      {dot} {sign}${Math.abs(value).toFixed(2)}
      {percentage !== undefined && (
        <span className="text-text-secondary ml-1">
          ({sign}{Math.abs(percentage).toFixed(1)}%)
        </span>
      )}
    </span>
  )
}
