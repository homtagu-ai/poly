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
      <h1 className="text-xl font-bold">{'\u{1F527}'} Settings</h1>

      {/* Profile Info */}
      <Card className="space-y-2">
        <h2 className="font-semibold text-sm text-text-secondary uppercase tracking-wider">Profile</h2>
        <div className="space-y-1.5">
          <div className="flex justify-between text-sm">
            <span className="text-text-secondary">Name</span>
            <span>{user?.first_name} {user?.last_name || ''}</span>
          </div>
          {user?.username && (
            <div className="flex justify-between text-sm">
              <span className="text-text-secondary">Username</span>
              <span className="font-mono">@{user.username}</span>
            </div>
          )}
          <div className="flex justify-between text-sm">
            <span className="text-text-secondary">Telegram ID</span>
            <span className="font-mono">{user?.id || profile?.telegram_user_id || '---'}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-text-secondary">Status</span>
            <span className={profile?.is_verified ? 'text-accent-green' : 'text-accent-yellow'}>
              {profile?.is_verified ? '\u{2705} Verified' : '\u{23F3} Pending'}
            </span>
          </div>
          {profile?.created_at && (
            <div className="flex justify-between text-sm">
              <span className="text-text-secondary">Joined</span>
              <span>{new Date(profile.created_at).toLocaleDateString()}</span>
            </div>
          )}
        </div>
      </Card>

      {/* Language Selection */}
      <Card className="space-y-3">
        <h2 className="font-semibold text-sm text-text-secondary uppercase tracking-wider">Language</h2>
        <div className="grid grid-cols-3 gap-2">
          {LANGUAGES.map(lang => {
            const isSelected = (profile?.language || 'en') === lang.code
            return (
              <button
                key={lang.code}
                onClick={() => languageMutation.mutate(lang.code)}
                className={`py-2 rounded-lg text-xs font-medium transition-colors ${
                  isSelected
                    ? 'bg-accent-teal text-bg-primary'
                    : 'bg-bg-tertiary text-text-secondary hover:text-text-primary'
                }`}
              >
                <span className="block text-lg mb-0.5">{lang.flag}</span>
                {lang.label}
              </button>
            )
          })}
        </div>
      </Card>

      {/* App Info */}
      <Card className="space-y-2">
        <h2 className="font-semibold text-sm text-text-secondary uppercase tracking-wider">About</h2>
        <div className="space-y-1.5 text-sm">
          <div className="flex justify-between">
            <span className="text-text-secondary">Version</span>
            <span>1.0.0</span>
          </div>
          <div className="flex justify-between">
            <span className="text-text-secondary">Build</span>
            <span className="font-mono text-text-muted">miniapp-v1</span>
          </div>
        </div>
      </Card>

      {/* Close App Button */}
      <button
        onClick={close}
        className="w-full py-3 text-center text-accent-red font-medium text-sm"
      >
        Close App
      </button>
    </div>
  )
}
