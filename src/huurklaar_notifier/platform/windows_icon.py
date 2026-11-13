"""Het tray-icoon: het Huurklaar-logo met een kleine badge voor de toestand. Enkel Pillow, geen Windows nodig."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..core.state import State, Status

# Het huisje uit favicon.svg (viewBox 32x32), zelfde als op de Mac.
HOUSE = [(7, 15), (16, 7), (25, 15), (25, 25), (19, 25), (19, 19), (13, 19), (13, 25), (7, 25)]
TEAL = (0x0F, 0x76, 0x6E, 255)
WHITE = (255, 255, 255, 255)
AMBER = (0xD9, 0x77, 0x06, 255)
RED = (0xDC, 0x26, 0x26, 255)
GREY = (0x6B, 0x72, 0x80, 255)


@dataclass(frozen=True, slots=True)
class Badge:
    color: tuple[int, int, int, int]
    text: str  # leeg = enkel een stip


def badge_for(state: State) -> Badge | None:
    """Welke badge bij welke toestand: niets te doen = geen badge, taken = teller, rest = stip of '!'."""
    snap = state.snapshot
    if state.status is Status.ATTENTION and snap:
        n = snap.action_required or snap.total
        return Badge(RED if snap.overdue else AMBER, "9+" if n > 9 else str(n))
    if state.status in (Status.NOT_CONFIGURED, Status.AUTH_FAILED):
        return Badge(AMBER, "!")
    if state.status is Status.OFFLINE:
        return Badge(GREY, "")
    return None  # IDLE en DISABLED


def render_icon(badge: Badge | None, size: int = 64) -> Any:
    """Tekent het icoon als Pillow-afbeelding (RGBA). Pillow wordt pas hier geïmporteerd."""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, size - 1, size - 1), radius=size // 5, fill=TEAL)
    unit = size / 32
    d.polygon([(x * unit, y * unit) for x, y in HOUSE], fill=WHITE)
    if badge:
        r = size * (0.34 if badge.text else 0.22)
        cx, cy = size - r, size - r
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=badge.color, outline=WHITE, width=max(1, size // 32))
        if badge.text:
            font = ImageFont.load_default(size=int(r * (1.2 if len(badge.text) == 1 else 0.95)))
            d.text((cx, cy), badge.text, fill=WHITE, font=font, anchor="mm")
    return img


def save_ico(path: str, sizes: tuple[int, ...] = (16, 24, 32, 48, 64, 128, 256)) -> None:
    """Schrijft het .ico voor de .exe en de installer (zonder badge)."""
    render_icon(None, 256).save(path, format="ICO", sizes=[(s, s) for s in sizes])
