import { ReactNode, useEffect } from 'react'
import Navbar from './Navbar'
import { useTelegram } from '../hooks/useTelegram'

interface LayoutProps {
  children: ReactNode
}

export default function Layout({ children }: LayoutProps) {
  const { ready, tg } = useTelegram()

  useEffect(() => {
    ready()
    tg?.expand()
    // Set TG header color to match our bg
    tg?.setHeaderColor('#0b1520')
    tg?.setBackgroundColor('#0b1520')
  }, [ready, tg])

  return (
    <div className="min-h-screen bg-bg-primary pb-20 relative overflow-hidden">
      {/* Subtle radial glow at top */}
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[600px] h-[300px] pointer-events-none"
        style={{ background: 'radial-gradient(ellipse at center, rgba(59,165,181,0.06) 0%, transparent 70%)' }}
      />
      <main className="relative z-10 px-4 pt-4">
        {children}
      </main>
      <Navbar />
    </div>
  )
}
