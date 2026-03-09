import { useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { configApi } from '../api/endpoints'
import { useTelegram } from '../hooks/useTelegram'
import type { CopyTradeConfig } from '../api/types'

const DEFAULT_CONFIG: Partial<CopyTradeConfig> = {
  target_wallet: '',
  tag: '',
  is_active: true,
  copy_mode: 'percentage',
  copy_percentage: 100,
  buy_order_type: 'market',
  buy_slippage_pct: 5,
  sell_order_type: 'market',
  sell_slippage_pct: 5,
  copy_buy: true,
  copy_sell: true,
  tp_value: null,
  sl_value: null,
  below_min_buy_at_min: true,
  ignore_trades_under_usd: 0,
  min_price: null,
  max_price: null,
  total_spend_limit_usd: null,
  min_per_trade_usd: null,
  max_per_trade_usd: null,
  max_per_yes_no_usd: null,
  max_per_market_usd: null,
  max_markets: null,
  limit_price_offset: 0,
  limit_order_duration: 90,
}

type Section = 'target' | 'copy' | 'risk' | 'limits' | 'advanced'

export default function CopyTradeEdit() {
  const { id } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { showMainButton, hideMainButton, showBackButton, hideBackButton, haptic } = useTelegram()
  const isNew = !id || id === 'new'

  const [form, setForm] = useState<Partial<CopyTradeConfig>>(DEFAULT_CONFIG)
  const [openSections, setOpenSections] = useState<Set<Section>>(new Set(['target', 'copy']))

  const { data: existing } = useQuery({
    queryKey: ['config', id],
    queryFn: () => configApi.list().then(configs => configs.find(c => c.id === id)),
    enabled: !isNew,
  })

  useEffect(() => {
    if (existing) setForm(existing)
  }, [existing])

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (isNew) {
        return configApi.create(form)
      } else {
        return configApi.update(id!, form)
      }
    },
    onSuccess: () => {
      haptic('medium')
      queryClient.invalidateQueries({ queryKey: ['configs'] })
      navigate('/configs')
    },
  })

  const handleSave = useCallback(() => {
    saveMutation.mutate()
  }, [saveMutation])

  useEffect(() => {
    showMainButton(isNew ? '\u{2728} Create Config' : '\u{1F4BE} Save Config', handleSave)
    showBackButton(() => navigate('/configs'))
    return () => {
      hideMainButton()
      hideBackButton()
    }
  }, [showMainButton, hideMainButton, showBackButton, hideBackButton, navigate, handleSave, isNew])

  const toggleSection = (s: Section) => {
    setOpenSections(prev => {
      const next = new Set(prev)
      next.has(s) ? next.delete(s) : next.add(s)
      return next
    })
  }

  const updateField = (key: string, value: unknown) => {
    setForm(prev => ({ ...prev, [key]: value }))
  }

  const SectionHeader = ({ section, label, icon }: { section: Section; label: string; icon: string }) => (
    <button
      onClick={() => toggleSection(section)}
      className="w-full flex items-center justify-between py-3 text-left"
    >
      <span className="font-semibold">
        {icon} {label}
      </span>
      <span className="text-text-secondary">{openSections.has(section) ? '\u{25BC}' : '\u{25B6}'}</span>
    </button>
  )

  return (
    <div className="space-y-2 pb-24">
      <h1 className="text-xl font-bold mb-4">
        {isNew ? '\u{2728} New Config' : `\u{2699}\u{FE0F} Edit: ${form.tag || 'Config'}`}
      </h1>

      {/* Target & ID */}
      <div className="card">
        <SectionHeader section="target" label="Target & Identification" icon={'\u{1F45B}'} />
        {openSections.has('target') && (
          <div className="space-y-3 pb-2">
            <div>
              <label className="text-xs text-text-secondary block mb-1">Target Wallet Address</label>
              <input
                type="text"
                value={form.target_wallet || ''}
                onChange={e => updateField('target_wallet', e.target.value)}
                placeholder="0x..."
                className="w-full bg-bg-tertiary rounded-lg px-3 py-2 text-sm font-mono text-text-primary placeholder-text-muted outline-none focus:ring-1 focus:ring-accent-teal"
              />
            </div>
            <div>
              <label className="text-xs text-text-secondary block mb-1">Tag / Label</label>
              <input
                type="text"
                value={form.tag || ''}
                onChange={e => updateField('tag', e.target.value)}
                placeholder="e.g., Top Whale"
                className="w-full bg-bg-tertiary rounded-lg px-3 py-2 text-sm text-text-primary placeholder-text-muted outline-none focus:ring-1 focus:ring-accent-teal"
              />
            </div>
          </div>
        )}
      </div>

      {/* Copy Settings */}
      <div className="card">
        <SectionHeader section="copy" label="Copy Settings" icon={'\u{1F4D0}'} />
        {openSections.has('copy') && (
          <div className="space-y-3 pb-2">
            <div>
              <label className="text-xs text-text-secondary block mb-1">Copy Percentage</label>
              <input
                type="number"
                value={form.copy_percentage ?? 100}
                onChange={e => updateField('copy_percentage', parseFloat(e.target.value) || 0)}
                className="w-full bg-bg-tertiary rounded-lg px-3 py-2 text-sm font-mono text-text-primary outline-none focus:ring-1 focus:ring-accent-teal"
              />
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm">Copy Buy</span>
              <button
                onClick={() => updateField('copy_buy', !form.copy_buy)}
                className={`w-12 h-6 rounded-full transition-colors ${form.copy_buy ? 'bg-accent-teal' : 'bg-bg-tertiary'}`}
              >
                <span className={`block w-5 h-5 rounded-full bg-white transform transition-transform ${form.copy_buy ? 'translate-x-6' : 'translate-x-0.5'}`} />
              </button>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm">Copy Sell</span>
              <button
                onClick={() => updateField('copy_sell', !form.copy_sell)}
                className={`w-12 h-6 rounded-full transition-colors ${form.copy_sell ? 'bg-accent-teal' : 'bg-bg-tertiary'}`}
              >
                <span className={`block w-5 h-5 rounded-full bg-white transform transition-transform ${form.copy_sell ? 'translate-x-6' : 'translate-x-0.5'}`} />
              </button>
            </div>
            <div>
              <label className="text-xs text-text-secondary block mb-1">Buy Order Type</label>
              <div className="flex gap-2">
                {(['market', 'limit'] as const).map(t => (
                  <button
                    key={t}
                    onClick={() => updateField('buy_order_type', t)}
                    className={`flex-1 py-2 rounded-lg text-sm font-medium transition-colors ${
                      form.buy_order_type === t ? 'bg-accent-teal text-bg-primary' : 'bg-bg-tertiary text-text-secondary'
                    }`}
                  >
                    {t.charAt(0).toUpperCase() + t.slice(1)}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <label className="text-xs text-text-secondary block mb-1">Buy Slippage %</label>
              <input
                type="number"
                step="0.5"
                value={form.buy_slippage_pct ?? 5}
                onChange={e => updateField('buy_slippage_pct', parseFloat(e.target.value) || 0)}
                className="w-full bg-bg-tertiary rounded-lg px-3 py-2 text-sm font-mono text-text-primary outline-none focus:ring-1 focus:ring-accent-teal"
              />
            </div>
          </div>
        )}
      </div>

      {/* Risk Management */}
      <div className="card">
        <SectionHeader section="risk" label="Risk Management" icon={'\u{1F6E1}\u{FE0F}'} />
        {openSections.has('risk') && (
          <div className="space-y-3 pb-2">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-text-secondary block mb-1">{'\u{1F3AF}'} Take Profit</label>
                <input
                  type="number"
                  value={form.tp_value ?? ''}
                  onChange={e => updateField('tp_value', e.target.value ? parseFloat(e.target.value) : null)}
                  placeholder="None"
                  className="w-full bg-bg-tertiary rounded-lg px-3 py-2 text-sm font-mono text-text-primary placeholder-text-muted outline-none focus:ring-1 focus:ring-accent-teal"
                />
              </div>
              <div>
                <label className="text-xs text-text-secondary block mb-1">{'\u{1F6D1}'} Stop Loss</label>
                <input
                  type="number"
                  value={form.sl_value ?? ''}
                  onChange={e => updateField('sl_value', e.target.value ? parseFloat(e.target.value) : null)}
                  placeholder="None"
                  className="w-full bg-bg-tertiary rounded-lg px-3 py-2 text-sm font-mono text-text-primary placeholder-text-muted outline-none focus:ring-1 focus:ring-accent-teal"
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-text-secondary block mb-1">Min Price</label>
                <input
                  type="number"
                  step="0.01"
                  value={form.min_price ?? ''}
                  onChange={e => updateField('min_price', e.target.value ? parseFloat(e.target.value) : null)}
                  placeholder="None"
                  className="w-full bg-bg-tertiary rounded-lg px-3 py-2 text-sm font-mono text-text-primary placeholder-text-muted outline-none focus:ring-1 focus:ring-accent-teal"
                />
              </div>
              <div>
                <label className="text-xs text-text-secondary block mb-1">Max Price</label>
                <input
                  type="number"
                  step="0.01"
                  value={form.max_price ?? ''}
                  onChange={e => updateField('max_price', e.target.value ? parseFloat(e.target.value) : null)}
                  placeholder="None"
                  className="w-full bg-bg-tertiary rounded-lg px-3 py-2 text-sm font-mono text-text-primary placeholder-text-muted outline-none focus:ring-1 focus:ring-accent-teal"
                />
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Spend Limits */}
      <div className="card">
        <SectionHeader section="limits" label="Spend Limits" icon={'\u{1F4B0}'} />
        {openSections.has('limits') && (
          <div className="space-y-3 pb-2">
            {[
              { key: 'total_spend_limit_usd', label: 'Total Spend Limit' },
              { key: 'min_per_trade_usd', label: 'Min Per Trade' },
              { key: 'max_per_trade_usd', label: 'Max Per Trade' },
              { key: 'max_per_yes_no_usd', label: 'Max Per Yes/No' },
              { key: 'max_per_market_usd', label: 'Max Per Market' },
              { key: 'max_markets', label: 'Max Markets' },
              { key: 'ignore_trades_under_usd', label: 'Ignore Trades Under $' },
            ].map(({ key, label }) => (
              <div key={key}>
                <label className="text-xs text-text-secondary block mb-1">{label}</label>
                <input
                  type="number"
                  step="1"
                  value={String((form as Record<string, unknown>)[key] ?? '')}
                  onChange={e => updateField(key, e.target.value ? parseFloat(e.target.value) : null)}
                  placeholder="None"
                  className="w-full bg-bg-tertiary rounded-lg px-3 py-2 text-sm font-mono text-text-primary placeholder-text-muted outline-none focus:ring-1 focus:ring-accent-teal"
                />
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Advanced */}
      <div className="card">
        <SectionHeader section="advanced" label="Advanced" icon={'\u{1F39A}\u{FE0F}'} />
        {openSections.has('advanced') && (
          <div className="space-y-3 pb-2">
            <div>
              <label className="text-xs text-text-secondary block mb-1">Sell Order Type</label>
              <div className="flex gap-2">
                {(['market', 'limit'] as const).map(t => (
                  <button
                    key={t}
                    onClick={() => updateField('sell_order_type', t)}
                    className={`flex-1 py-2 rounded-lg text-sm font-medium transition-colors ${
                      form.sell_order_type === t ? 'bg-accent-teal text-bg-primary' : 'bg-bg-tertiary text-text-secondary'
                    }`}
                  >
                    {t.charAt(0).toUpperCase() + t.slice(1)}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <label className="text-xs text-text-secondary block mb-1">Sell Slippage %</label>
              <input
                type="number"
                step="0.5"
                value={form.sell_slippage_pct ?? 5}
                onChange={e => updateField('sell_slippage_pct', parseFloat(e.target.value) || 0)}
                className="w-full bg-bg-tertiary rounded-lg px-3 py-2 text-sm font-mono text-text-primary outline-none focus:ring-1 focus:ring-accent-teal"
              />
            </div>
            <div>
              <label className="text-xs text-text-secondary block mb-1">Limit Price Offset (-0.99 to 0.99)</label>
              <input
                type="number"
                step="0.01"
                min="-0.99"
                max="0.99"
                value={form.limit_price_offset ?? 0}
                onChange={e => updateField('limit_price_offset', parseFloat(e.target.value) || 0)}
                className="w-full bg-bg-tertiary rounded-lg px-3 py-2 text-sm font-mono text-text-primary outline-none focus:ring-1 focus:ring-accent-teal"
              />
            </div>
            <div>
              <label className="text-xs text-text-secondary block mb-1">Limit Order Duration (seconds, min 90)</label>
              <input
                type="number"
                min="90"
                value={form.limit_order_duration ?? 90}
                onChange={e => updateField('limit_order_duration', parseInt(e.target.value) || 90)}
                className="w-full bg-bg-tertiary rounded-lg px-3 py-2 text-sm font-mono text-text-primary outline-none focus:ring-1 focus:ring-accent-teal"
              />
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm">Below Min: Buy at Min</span>
              <button
                onClick={() => updateField('below_min_buy_at_min', !form.below_min_buy_at_min)}
                className={`w-12 h-6 rounded-full transition-colors ${form.below_min_buy_at_min ? 'bg-accent-teal' : 'bg-bg-tertiary'}`}
              >
                <span className={`block w-5 h-5 rounded-full bg-white transform transition-transform ${form.below_min_buy_at_min ? 'translate-x-6' : 'translate-x-0.5'}`} />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
