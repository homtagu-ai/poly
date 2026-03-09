"""
PolyHunter — Dynamic banner image generator using Pillow.

Generates branded dark-theme banners for Telegram notifications:
- Welcome banner (800x400)
- Trade result banner (800x300)

Images are cached by content hash to avoid regeneration.
"""
from __future__ import annotations

import hashlib
import io
import logging
import os
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Colour palette (matching poly-hunter.com dark theme)
# ---------------------------------------------------------------------------
BG_COLOR = (13, 17, 23)          # Deep dark navy
ACCENT_TEAL = (0, 210, 190)     # Teal/cyan accent
ACCENT_GREEN = (34, 197, 94)     # Profit green
ACCENT_RED = (239, 68, 68)       # Loss red
TEXT_PRIMARY = (230, 237, 243)    # Almost white
TEXT_SECONDARY = (139, 148, 158)  # Gray
DIVIDER_COLOR = (48, 54, 61)     # Subtle gray line

# ---------------------------------------------------------------------------
# Font helpers — fall back to default bitmap if no TTF available
# ---------------------------------------------------------------------------
_FONT_CACHE: dict[tuple[str, int], ImageFont.FreeTypeFont | ImageFont.ImageFont] = {}


def _get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Try to load a clean sans-serif font; fall back to PIL default."""
    key = ("bold" if bold else "regular", size)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]

    # Try common font paths across macOS / Linux / Windows
    candidates = []
    if bold:
        candidates = [
            "/System/Library/Fonts/SFNSTextCondensed-Bold.otf",
            "/System/Library/Fonts/Helvetica.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
        ]
    else:
        candidates = [
            "/System/Library/Fonts/SFNSTextCondensed-Regular.otf",
            "/System/Library/Fonts/Helvetica.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/TTF/DejaVuSans.ttf",
            "C:/Windows/Fonts/arial.ttf",
        ]

    for path in candidates:
        if os.path.exists(path):
            try:
                font = ImageFont.truetype(path, size)
                _FONT_CACHE[key] = font
                return font
            except Exception:
                continue

    # Final fallback: PIL default
    font = ImageFont.load_default()
    _FONT_CACHE[key] = font
    return font


# ---------------------------------------------------------------------------
# Image cache (in-memory, keyed by content hash)
# ---------------------------------------------------------------------------
_IMAGE_CACHE: dict[str, bytes] = {}
MAX_CACHE_SIZE = 50


def _cache_key(*parts) -> str:
    raw = "|".join(str(p) for p in parts)
    return hashlib.md5(raw.encode()).hexdigest()


def _get_cached(key: str) -> Optional[bytes]:
    return _IMAGE_CACHE.get(key)


def _set_cached(key: str, data: bytes) -> None:
    if len(_IMAGE_CACHE) >= MAX_CACHE_SIZE:
        # Evict oldest entry
        oldest = next(iter(_IMAGE_CACHE))
        del _IMAGE_CACHE[oldest]
    _IMAGE_CACHE[key] = data


# ---------------------------------------------------------------------------
# Draw helpers
# ---------------------------------------------------------------------------

def _draw_rounded_rect(draw: ImageDraw.ImageDraw, xy, radius, fill):
    """Draw a rounded rectangle (Pillow 9.x+ has this built in)."""
    try:
        draw.rounded_rectangle(xy, radius=radius, fill=fill)
    except AttributeError:
        # Fallback for older Pillow
        draw.rectangle(xy, fill=fill)


def _draw_gradient_bar(img: Image.Image, y: int, height: int = 4):
    """Draw a horizontal teal-to-transparent gradient bar."""
    draw = ImageDraw.Draw(img)
    w = img.width
    for x in range(w):
        alpha = max(0, 255 - int(x * 255 / w))
        r, g, b = ACCENT_TEAL
        draw.line([(x, y), (x, y + height)], fill=(r, g, b, min(alpha + 60, 255)))


# ---------------------------------------------------------------------------
# Welcome Banner (800 x 400)
# ---------------------------------------------------------------------------

def generate_welcome_banner(user_name: str = "Trader") -> bytes:
    """Generate a branded welcome banner. Returns PNG bytes."""
    ck = _cache_key("welcome", user_name)
    cached = _get_cached(ck)
    if cached:
        return cached

    W, H = 800, 400
    img = Image.new("RGBA", (W, H), BG_COLOR + (255,))
    draw = ImageDraw.Draw(img)

    # Top gradient accent bar
    _draw_gradient_bar(img, 0, height=6)

    # Logo / brand area
    font_title = _get_font(42, bold=True)
    font_subtitle = _get_font(22)
    font_name = _get_font(28, bold=True)
    font_small = _get_font(16)

    # "POLYHUNTER" title
    draw.text((40, 50), "POLYHUNTER", fill=ACCENT_TEAL, font=font_title)

    # Subtitle
    draw.text((40, 110), "Intelligent Copy Trading for Polymarket", fill=TEXT_SECONDARY, font=font_subtitle)

    # Divider line
    draw.line([(40, 160), (W - 40, 160)], fill=DIVIDER_COLOR, width=2)

    # Welcome message
    draw.text((40, 185), f"Welcome, {user_name}!", fill=TEXT_PRIMARY, font=font_name)

    # Feature bullets
    features = [
        "Mirror top-performing whale wallets automatically",
        "Full control over sizing, slippage & risk limits",
        "Real-time TP/SL monitoring with instant notifications",
        "21 configurable parameters per copy trade",
    ]
    y = 235
    for feat in features:
        draw.text((55, y), f"\u2022  {feat}", fill=TEXT_SECONDARY, font=font_small)
        y += 28

    # Bottom accent bar
    _draw_gradient_bar(img, H - 6, height=6)

    # Bottom right: version tag
    draw.text((W - 200, H - 30), "poly-hunter.com", fill=DIVIDER_COLOR, font=font_small)

    # Convert to PNG bytes
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    data = buf.getvalue()
    _set_cached(ck, data)
    return data


# ---------------------------------------------------------------------------
# Trade Result Banner (800 x 300)
# ---------------------------------------------------------------------------

def generate_trade_banner(
    market: str = "Unknown Market",
    side: str = "BUY",
    amount_usd: float = 0.0,
    price: float = 0.0,
    pnl: Optional[float] = None,
    success: bool = True,
) -> bytes:
    """Generate a trade result banner. Returns PNG bytes."""
    ck = _cache_key("trade", market, side, amount_usd, price, pnl, success)
    cached = _get_cached(ck)
    if cached:
        return cached

    W, H = 800, 300
    img = Image.new("RGBA", (W, H), BG_COLOR + (255,))
    draw = ImageDraw.Draw(img)

    accent = ACCENT_GREEN if success else ACCENT_RED
    status_text = "TRADE EXECUTED" if success else "TRADE FAILED"

    # Top accent bar
    draw.rectangle([(0, 0), (W, 6)], fill=accent)

    # Status badge
    font_badge = _get_font(14, bold=True)
    badge_w = 180
    _draw_rounded_rect(draw, [(30, 25), (30 + badge_w, 55)], radius=4, fill=accent)
    draw.text((40, 28), status_text, fill=BG_COLOR, font=font_badge)

    # Market name
    font_market = _get_font(26, bold=True)
    # Truncate market name if too long
    display_market = market if len(market) <= 50 else market[:47] + "..."
    draw.text((30, 70), display_market, fill=TEXT_PRIMARY, font=font_market)

    # Divider
    draw.line([(30, 115), (W - 30, 115)], fill=DIVIDER_COLOR, width=1)

    # Trade details grid
    font_label = _get_font(14)
    font_value = _get_font(22, bold=True)

    # Column 1: Side
    draw.text((40, 130), "SIDE", fill=TEXT_SECONDARY, font=font_label)
    side_color = ACCENT_GREEN if side.upper() == "BUY" else ACCENT_RED
    draw.text((40, 150), side.upper(), fill=side_color, font=font_value)

    # Column 2: Amount
    draw.text((220, 130), "AMOUNT", fill=TEXT_SECONDARY, font=font_label)
    draw.text((220, 150), f"${amount_usd:,.2f}", fill=TEXT_PRIMARY, font=font_value)

    # Column 3: Price
    draw.text((440, 130), "PRICE", fill=TEXT_SECONDARY, font=font_label)
    draw.text((440, 150), f"${price:.4f}", fill=TEXT_PRIMARY, font=font_value)

    # Column 4: P&L (if provided)
    if pnl is not None:
        draw.text((640, 130), "P&L", fill=TEXT_SECONDARY, font=font_label)
        pnl_color = ACCENT_GREEN if pnl >= 0 else ACCENT_RED
        pnl_sign = "+" if pnl >= 0 else ""
        draw.text((640, 150), f"{pnl_sign}${abs(pnl):,.2f}", fill=pnl_color, font=font_value)

    # Bottom bar
    draw.rectangle([(0, H - 4), (W, H)], fill=accent)

    # Bottom: timestamp placeholder
    font_small = _get_font(12)
    draw.text((30, H - 25), "PolyHunter Copy Trading", fill=DIVIDER_COLOR, font=font_small)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    data = buf.getvalue()
    _set_cached(ck, data)
    return data


# ---------------------------------------------------------------------------
# Quick test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Generate test images to verify
    welcome = generate_welcome_banner("TestUser")
    print(f"Welcome banner: {len(welcome):,} bytes")

    trade = generate_trade_banner(
        market="Will Trump win the 2024 election?",
        side="BUY",
        amount_usd=500.0,
        price=0.6234,
    )
    print(f"Trade banner: {len(trade):,} bytes")

    # Save for visual inspection
    with open("/tmp/ph_welcome.png", "wb") as f:
        f.write(welcome)
    with open("/tmp/ph_trade.png", "wb") as f:
        f.write(trade)
    print("Saved to /tmp/ph_welcome.png and /tmp/ph_trade.png")
