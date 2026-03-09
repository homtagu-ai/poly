import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import Card from '../components/Card'
import { userApi } from '../api/endpoints'
import { useTelegram } from '../hooks/useTelegram'

const LANGUAGES = [
  { code: 'en', label: 'English', flag: '\u{1F1EC}\u{1F1E7}' },
  { code: 'ru', label: '\u{0420}\u{0443}\u{0441}\u{0441}\u{043A}\u{0438}\u{0439}', flag: '\u{1F1F7}\u{1F1FA}' },
  { code: 'ja', label: '\u{65E5}\u{672C}\u{8A9E}', flag: '\u{1F1EF}\u{1F1F5}' },
  { code: 'ko', label: '\u{D55C}\u{AD6D}\u{C5B4}', flag: '\u{1F1F0}\u{1F1F7}' },
  { code: 'zh-TW', label: '\u{7E41}\u{9AD4}\u{4E2D}\u{6587}', flag: '\u{1F1F9}\u{1F1FC}' },
  { code: 'fr', label: 'Fran\u{00E7}ais', flag: '\u{1F1EB}\u{1F1F7}' },
  { code: 'es', label: 'Espa\u{00F1}ol', flag: '\u{1F1EA}\u{1F1F8}' },
  { code: 'pt', label: 'Portugu\u{00EA}s', flag: '\u{1F1E7}\u{1F1F7}' },
  { code: 'ar', label: '\u{0627}\u{0644}\u{0639}\u{0631}\u{0628}\u{064A}\u{0629}', flag: '\u{1F1F8}\u{1F1E6}' },
]

export default function Settings() {
  const queryClient = useQueryClient()
  const { user, close } = useTelegram()

  const { data: profile } = useQuery({
    queryKey: ['me'],
    queryFn: userApi.getMe,
  })

  const languageMutation = useMutation({
    mutationFn: (language: string) => userApi.updateSettings({ language }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['me'] })
    },
  })

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-bold text-text-primary">Settings</h1>

      {/* Profile Info */}
      <Card glow>
        <div className="space-y-3">
          <p className="section-header">Profile</p>
          <div className="space-y-2">
            {[
              { label: 'Name', value: `${user?.first_name || ''} ${user?.last_name || ''}`.trim() || '---' },
              user?.username ? { label: 'Username', value: `@${user.username}`, mono: true } : null,
              { label: 'Telegram ID', value: String(user?.id || profile?.telegram_user_id || '---'), mono: true },
              {
                label: 'Status',
                value: profile?.is_verified ? 'Verified' : 'Pending',
                color: profile?.is_verified ? '#10b981' : '#f59e0b',
              },
              profile?.created_at ? { label: 'Joined', value: new Date(profile.created_at).toLocaleDateString() } : null,
            ].filter(Boolean).map((row) => (
              <div key={row!.label} className="flex justify-between items-center text-sm">
                <span className="text-text-muted">{row!.label}</span>
                <span
                  className={`text-text-primary ${(row as { mono?: boolean }).mono ? 'font-mono' : ''}`}
                  style={(row as { color?: string }).color ? { color: (row as { color: string }).color } : {}}
                >
                  {row!.value}
                </span>
              </div>
            ))}
          </div>
        </div>
      </Card>

      {/* Language Selection */}
      <Card>
        <div className="space-y-3">
          <p className="section-header">Language</p>
          <div className="grid grid-cols-3 gap-2">
            {LANGUAGES.map(lang => {
              const isSelected = (profile?.language || 'en') === lang.code
              return (
                <button
                  key={lang.code}
                  onClick={() => languageMutation.mutate(lang.code)}
                  className="py-2.5 rounded-xl text-xs font-medium transition-all duration-200"
                  style={isSelected ? {
                    background: 'linear-gradient(135deg, rgba(59,165,181,0.2), rgba(13,211,206,0.1))',
                    border: '1px solid rgba(59,165,181,0.4)',
                    color: '#3edbd5',
                  } : {
                    background: '#142230',
                    border: '1px solid #1c3040',
                    color: '#8ba8be',
                  }}
                >
                  <span className="block text-lg mb-0.5">{lang.flag}</span>
                  {lang.label}
                </button>
              )
            })}
          </div>
        </div>
      </Card>

      {/* App Info */}
      <Card>
        <div className="space-y-2">
          <p className="section-header">About</p>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-text-muted">Version</span>
              <span className="text-text-secondary">1.0.0</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">Build</span>
              <span className="font-mono text-text-muted">miniapp-v1</span>
            </div>
          </div>
        </div>
      </Card>

      {/* Close App */}
      <button
        onClick={close}
        className="w-full py-3 text-center font-medium text-sm rounded-xl transition-colors"
        style={{ color: '#ef4444', background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.15)' }}
      >
        Close App
      </button>
    </div>
  )
}
