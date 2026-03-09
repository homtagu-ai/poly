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
    // Expand to full height
    tg?.expand()
  }, [ready, tg])

  return (
    <div className="min-h-screen bg-bg-primary pb-20">
      <main className="px-4 pt-4">
        {children}
      </main>
      <Navbar />
    </div>
  )
}
