-- ============================================================================
-- PolyHunter Copy Trading — Migration 002: Language & Limit Order Parameters
-- Run in Supabase SQL Editor after 001_copy_trading_tables.sql
-- ============================================================================

-- 1. Add user language preference to telegram_users
ALTER TABLE public.telegram_users
    ADD COLUMN IF NOT EXISTS language TEXT DEFAULT 'en';

-- 2. Add limit-order parameters to copy_trade_configs
ALTER TABLE public.copy_trade_configs
    ADD COLUMN IF NOT EXISTS limit_price_offset DECIMAL DEFAULT 0.0,
    ADD COLUMN IF NOT EXISTS limit_order_duration INTEGER DEFAULT 90;

-- 3. Constraints: limit_price_offset must be between -0.99 and 0.99
ALTER TABLE public.copy_trade_configs
    ADD CONSTRAINT chk_limit_price_offset
        CHECK (limit_price_offset BETWEEN -0.99 AND 0.99);

-- 4. Constraints: limit_order_duration must be >= 90 seconds
ALTER TABLE public.copy_trade_configs
    ADD CONSTRAINT chk_limit_order_duration
        CHECK (limit_order_duration >= 90);
