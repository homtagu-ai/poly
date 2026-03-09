interface ProgressBarProps {
  used: number
  limit: number
  label?: string
  showValues?: boolean
}

export default function ProgressBar({ used, limit, label, showValues = true }: ProgressBarProps) {
  const percentage = limit > 0 ? Math.min((used / limit) * 100, 100) : 0

  // Gradient colors matching web app: teal -> yellow -> red
  const getBarStyle = () => {
    if (percentage > 90) return { background: '#ef4444' }
    if (percentage > 70) return { background: 'linear-gradient(90deg, #f59e0b, #ef4444)' }
    return { background: 'linear-gradient(90deg, #3ba5b5, #0dd3ce)' }
  }

  return (
    <div className="w-full">
      {(label || showValues) && (
        <div className="flex justify-between text-xs text-text-secondary mb-1.5">
          {label && <span className="font-medium">{label}</span>}
          {showValues && (
            <span className="font-mono text-text-muted">
              ${used.toFixed(2)} / ${limit.toFixed(2)}
            </span>
          )}
        </div>
      )}
      <div className="h-1.5 bg-bg-primary rounded-full overflow-hidden" style={{ border: '1px solid #1c3040' }}>
        <div
          className="h-full rounded-full transition-all duration-700 ease-out"
          style={{ width: `${percentage}%`, ...getBarStyle() }}
        />
      </div>
    </div>
  )
}
