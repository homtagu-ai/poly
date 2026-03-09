import { useCallback } from 'react'

interface TelegramUser {
  id: number
  first_name: string
  last_name?: string
  username?: string
  language_code?: string
}

export function useTelegram() {
  const tg = typeof window !== 'undefined' ? window.Telegram?.WebApp : null

  const user: TelegramUser | null = tg?.initDataUnsafe?.user || null
  const initData: string = tg?.initData || ''
  const colorScheme = tg?.colorScheme || 'dark'

  const showMainButton = useCallback((text: string, onClick: () => void) => {
    if (!tg?.MainButton) return
    tg.MainButton.text = text
    tg.MainButton.onClick(onClick)
    tg.MainButton.show()
  }, [tg])

  const hideMainButton = useCallback(() => {
    tg?.MainButton?.hide()
  }, [tg])

  const showBackButton = useCallback((onClick: () => void) => {
    if (!tg?.BackButton) return
    tg.BackButton.onClick(onClick)
    tg.BackButton.show()
  }, [tg])

  const hideBackButton = useCallback(() => {
    tg?.BackButton?.hide()
  }, [tg])

  const haptic = useCallback((type: 'light' | 'medium' | 'heavy' = 'medium') => {
    tg?.HapticFeedback?.impactOccurred(type)
  }, [tg])

  const close = useCallback(() => {
    tg?.close()
  }, [tg])

  const ready = useCallback(() => {
    tg?.ready()
  }, [tg])

  return {
    tg,
    user,
    initData,
    colorScheme,
    showMainButton,
    hideMainButton,
    showBackButton,
    hideBackButton,
    haptic,
    close,
    ready,
  }
}
