import { ReactNode } from 'react'

interface CardProps {
  children: ReactNode
  className?: string
  onClick?: () => void
}

export default function Card({ children, className = '', onClick }: CardProps) {
  return (
    <div
      className={`card ${onClick ? 'cursor-pointer active:opacity-80' : ''} ${className}`}
      onClick={onClick}
    >
      {children}
    </div>
  )
}
