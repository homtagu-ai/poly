export interface UserProfile {
  telegram_user_id: number
  telegram_username: string | null
  language: string
  is_verified: boolean
  created_at: string
}

export interface CopyTradeConfig {
  id: string
  telegram_user_id: number
  target_wallet: string
  tag: string
  is_active: boolean
  copy_mode: 'percentage' | 'fixed'
  copy_percentage: number
  copy_fixed_amount: number | null
  buy_order_type: 'market' | 'limit'
  buy_slippage_pct: number
  copy_buy: boolean
  sell_order_type: 'market' | 'limit'
  sell_slippage_pct: number
  copy_sell: boolean
  tp_mode: 'percentage' | 'price'
  tp_value: number | null
  sl_mode: 'percentage' | 'price'
  sl_value: number | null
  below_min_buy_at_min: boolean
  ignore_trades_under_usd: number
  min_price: number | null
  max_price: number | null
  total_spend_limit_usd: number | null
  min_per_trade_usd: number | null
  max_per_trade_usd: number | null
  max_per_yes_no_usd: number | null
  max_per_market_usd: number | null
  max_markets: number | null
  limit_price_offset: number
  limit_order_duration: number
  total_spent_usd: number
  markets_entered: number
  created_at: string
  updated_at: string
}

export interface Position {
  id: string
  config_id: string
  market_slug: string
  condition_id: string
  token_id: string
  side: 'YES' | 'NO'
  entry_price: number
  shares: number
  cost_basis_usd: number
  current_price: number | null
  unrealized_pnl: number
  is_open: boolean
  opened_at: string
}

export interface TradeLogEntry {
  id: string
  telegram_user_id: number
  config_id: string | null
  action: string
  market_slug: string | null
  signal_source: string | null
  signal_price: number | null
  execution_price: number | null
  slippage_pct: number | null
  order_size_usd: number | null
  shares: number | null
  outcome: string | null
  polymarket_order_id: string | null
  failure_reason: string | null
  created_at: string
}
