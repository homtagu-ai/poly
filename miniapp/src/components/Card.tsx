import { ReactNode } from 'react'

interface CardProps {
  children: ReactNode
  className?: string
  onClick?: () => void
  glow?: boolean
  animated?: boolean
}

export default function Card({ children, className = '', onClick, glow, animated }: CardProps) {
  if (animated) {
    return (
      <div className="card-animated-border" onClick={onClick} role={onClick ? 'button' : undefined}>
        <div className={`p-4 ${className}`}>
          {children}
        </div>
      </div>
    )
  }

  return (
    <div
      className={`card ${glow ? 'card-glow' : ''} ${onClick ? 'card-clickable cursor-pointer' : ''} ${className}`}
      onClick={onClick}
    >
      {children}
    </div>
  )
}
