interface ProgressBarProps {
  used: number
  limit: number
  label?: string
  showValues?: boolean
}

export default function ProgressBar({ used, limit, label, showValues = true }: ProgressBarProps) {
  const percentage = limit > 0 ? Math.min((used / limit) * 100, 100) : 0
  const color = percentage > 90 ? 'bg-accent-red' : percentage > 70 ? 'bg-accent-yellow' : 'bg-accent-teal'

  return (
    <div className="w-full">
      {(label || showValues) && (
        <div className="flex justify-between text-xs text-text-secondary mb-1">
          {label && <span>{label}</span>}
          {showValues && <span>${used.toFixed(2)} / ${limit.toFixed(2)}</span>}
        </div>
      )}
      <div className="h-2 bg-bg-tertiary rounded-full overflow-hidden">
        <div
          className={`h-full ${color} rounded-full transition-all duration-500`}
          style={{ width: `${percentage}%` }}
        />
      </div>
    </div>
  )
}
