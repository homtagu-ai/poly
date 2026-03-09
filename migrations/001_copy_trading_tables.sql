-- ============================================================================
-- PolyHunter Copy Trading — Database Migration
-- Run in Supabase SQL Editor
-- ============================================================================

-- 1. telegram_users — Links Telegram user ID to Supabase profile
CREATE TABLE IF NOT EXISTS public.telegram_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    telegram_user_id BIGINT UNIQUE NOT NULL,
    telegram_username TEXT,
    telegram_chat_id BIGINT NOT NULL,
    supabase_user_id UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    is_verified BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_telegram_users_tg_id ON public.telegram_users(telegram_user_id);

-- RLS
ALTER TABLE public.telegram_users ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role full access on telegram_users"
    ON public.telegram_users FOR ALL
    USING (auth.role() = 'service_role');


-- 2. user_trading_credentials — Encrypted CLOB API keys
CREATE TABLE IF NOT EXISTS public.user_trading_credentials (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    telegram_user_id BIGINT NOT NULL REFERENCES public.telegram_users(telegram_user_id) ON DELETE CASCADE,
    encrypted_blob BYTEA NOT NULL,
    iv BYTEA NOT NULL,
    auth_tag BYTEA NOT NULL,
    key_version INTEGER NOT NULL DEFAULT 1,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT now(),
    last_used_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_creds_tg_user ON public.user_trading_credentials(telegram_user_id);

ALTER TABLE public.user_trading_credentials ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role full access on user_trading_credentials"
    ON public.user_trading_credentials FOR ALL
    USING (auth.role() = 'service_role');


-- 3. copy_trade_configs — One row per copy trade setup (all 19 PolyCop settings)
CREATE TABLE IF NOT EXISTS public.copy_trade_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    telegram_user_id BIGINT NOT NULL REFERENCES public.telegram_users(telegram_user_id) ON DELETE CASCADE,

    -- Target
    target_wallet TEXT NOT NULL DEFAULT '',
    tag TEXT DEFAULT '',
    is_active BOOLEAN DEFAULT FALSE,

    -- Sizing
    copy_mode TEXT DEFAULT 'percentage' CHECK (copy_mode IN ('percentage', 'fixed')),
    copy_percentage DECIMAL DEFAULT 100,
    copy_fixed_amount DECIMAL,

    -- Buy Settings
    buy_order_type TEXT DEFAULT 'market' CHECK (buy_order_type IN ('market', 'limit')),
    buy_slippage_pct DECIMAL DEFAULT 5.0,
    copy_buy BOOLEAN DEFAULT TRUE,

    -- Sell Settings
    sell_order_type TEXT DEFAULT 'market' CHECK (sell_order_type IN ('market', 'limit')),
    sell_slippage_pct DECIMAL DEFAULT 5.0,
    copy_sell BOOLEAN DEFAULT TRUE,

    -- Take Profit / Stop Loss
    tp_mode TEXT DEFAULT 'percentage' CHECK (tp_mode IN ('percentage', 'price')),
    tp_value DECIMAL,
    sl_mode TEXT DEFAULT 'percentage' CHECK (sl_mode IN ('percentage', 'price')),
    sl_value DECIMAL,

    -- Filters
    below_min_buy_at_min BOOLEAN DEFAULT TRUE,
    ignore_trades_under_usd DECIMAL DEFAULT 0,
    min_price DECIMAL,
    max_price DECIMAL,

    -- Limits
    total_spend_limit_usd DECIMAL,
    min_per_trade_usd DECIMAL,
    max_per_trade_usd DECIMAL,
    max_per_yes_no_usd DECIMAL,
    max_per_market_usd DECIMAL,
    max_markets INTEGER,

    -- Running State (updated by the bot during operation)
    total_spent_usd DECIMAL DEFAULT 0,
    markets_entered INTEGER DEFAULT 0,
    last_signal_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_ctc_tg_user ON public.copy_trade_configs(telegram_user_id);
CREATE INDEX IF NOT EXISTS idx_ctc_target ON public.copy_trade_configs(target_wallet);
CREATE INDEX IF NOT EXISTS idx_ctc_active ON public.copy_trade_configs(is_active) WHERE is_active = TRUE;

ALTER TABLE public.copy_trade_configs ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role full access on copy_trade_configs"
    ON public.copy_trade_configs FOR ALL
    USING (auth.role() = 'service_role');


-- 4. copy_trade_positions — Tracks positions opened by copy trading
CREATE TABLE IF NOT EXISTS public.copy_trade_positions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    config_id UUID NOT NULL REFERENCES public.copy_trade_configs(id) ON DELETE CASCADE,
    telegram_user_id BIGINT NOT NULL,

    market_slug TEXT NOT NULL,
    condition_id TEXT NOT NULL DEFAULT '',
    token_id TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('YES', 'NO')),

    entry_price DECIMAL NOT NULL,
    shares DECIMAL NOT NULL,
    cost_basis_usd DECIMAL NOT NULL,

    current_price DECIMAL,
    unrealized_pnl DECIMAL DEFAULT 0,

    is_open BOOLEAN DEFAULT TRUE,
    exit_price DECIMAL,
    exit_reason TEXT,
    realized_pnl DECIMAL,

    opened_at TIMESTAMPTZ DEFAULT now(),
    closed_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_ctp_config ON public.copy_trade_positions(config_id);
CREATE INDEX IF NOT EXISTS idx_ctp_open ON public.copy_trade_positions(is_open) WHERE is_open = TRUE;
CREATE INDEX IF NOT EXISTS idx_ctp_tg_user ON public.copy_trade_positions(telegram_user_id);

ALTER TABLE public.copy_trade_positions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role full access on copy_trade_positions"
    ON public.copy_trade_positions FOR ALL
    USING (auth.role() = 'service_role');


-- 5. trade_log — Immutable audit trail
CREATE TABLE IF NOT EXISTS public.trade_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    telegram_user_id BIGINT NOT NULL,
    config_id UUID REFERENCES public.copy_trade_configs(id) ON DELETE SET NULL,

    action TEXT NOT NULL,
    -- Valid actions: signal_received, validation_passed, validation_failed,
    --               order_placed, order_filled, order_rejected, order_cancelled,
    --               tp_triggered, sl_triggered, circuit_breaker_tripped

    market_slug TEXT,
    condition_id TEXT,
    signal_source TEXT,
    signal_price DECIMAL,
    execution_price DECIMAL,
    slippage_pct DECIMAL,
    order_size_usd DECIMAL,
    shares DECIMAL,
    outcome TEXT,

    polymarket_order_id TEXT,
    failure_reason TEXT,

    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_tlog_tg_user ON public.trade_log(telegram_user_id);
CREATE INDEX IF NOT EXISTS idx_tlog_created ON public.trade_log(created_at);
CREATE INDEX IF NOT EXISTS idx_tlog_config ON public.trade_log(config_id);

ALTER TABLE public.trade_log ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role full access on trade_log"
    ON public.trade_log FOR ALL
    USING (auth.role() = 'service_role');


-- 6. wallet_monitor_state — Tracks last known tx per target wallet
CREATE TABLE IF NOT EXISTS public.wallet_monitor_state (
    target_wallet TEXT PRIMARY KEY,
    last_tx_hash TEXT,
    last_block_number BIGINT,
    last_checked_at TIMESTAMPTZ DEFAULT now(),
    active_config_count INTEGER DEFAULT 0
);

ALTER TABLE public.wallet_monitor_state ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role full access on wallet_monitor_state"
    ON public.wallet_monitor_state FOR ALL
    USING (auth.role() = 'service_role');


-- ============================================================================
-- Helper function: auto-update updated_at on copy_trade_configs
-- ============================================================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_copy_trade_configs_updated_at
    BEFORE UPDATE ON public.copy_trade_configs
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_telegram_users_updated_at
    BEFORE UPDATE ON public.telegram_users
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
