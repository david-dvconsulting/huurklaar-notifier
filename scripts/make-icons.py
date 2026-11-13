"""Maakt de iconen uit het Huurklaar-logo (huisje op teal vlak, zelfde als de favicon van de web-app).

- assets/menubar.png (+@2x): enkel het huisje, zwart op transparant, als 'template image': macOS kleurt het
  zelf wit of zwart naargelang de menubalk, en grijs als het gedimd moet.
- assets/AppIcon.icns: het volledige logo (vlak met afgeronde hoeken) voor Finder, Dock en meldingen.

Draai met de venv (heeft pyobjc nodig): .venv/bin/python scripts/make-icons.py
"""

import subprocess
import tempfile
from pathlib import Path

from AppKit import (
    NSBezierPath,
    NSBitmapImageRep,
    NSColor,
    NSGraphicsContext,
    NSPNGFileType,
)

ROOT = Path(__file__).resolve().parent.parent / "assets"
# Het huisje uit favicon.svg (viewBox 32x32, y naar beneden).
HOUSE = [(7, 15), (16, 7), (25, 15), (25, 25), (19, 25), (19, 19), (13, 19), (13, 25), (7, 25)]
TEAL = (0x0F / 255, 0x76 / 255, 0x6E / 255)


def render(px: int, draw) -> NSBitmapImageRep:
    rep = NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(
        None, px, px, 8, 4, True, False, "NSCalibratedRGBColorSpace", 0, 0
    )
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.setCurrentContext_(NSGraphicsContext.graphicsContextWithBitmapImageRep_(rep))
    draw(px)
    NSGraphicsContext.restoreGraphicsState()
    return rep


def house_path(size: float, origin: float, unit: float) -> NSBezierPath:
    """Huisje met `unit` pixels per logo-eenheid; (7,7) komt op `origin`. Cocoa heeft y naar boven."""
    p = NSBezierPath.bezierPath()
    for i, (x, y) in enumerate(HOUSE):
        pt = (origin + (x - 7) * unit, size - (origin + (y - 7) * unit))
        p.moveToPoint_(pt) if i == 0 else p.lineToPoint_(pt)
    p.closePath()
    return p


def menubar(px: int):
    def draw(size):
        NSColor.blackColor().setFill()
        house_path(size, 0, size / 18).fill()

    return render(px, draw)


def app_icon(px: int):
    def draw(size):
        NSColor.colorWithCalibratedRed_green_blue_alpha_(*TEAL, 1).setFill()
        NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            ((0, 0), (size, size)), size / 4, size / 4
        ).fill()
        NSColor.whiteColor().setFill()
        house_path(size, size * 7 / 32, size / 32).fill()

    return render(px, draw)


def save(rep, path: Path) -> None:
    path.write_bytes(bytes(rep.representationUsingType_properties_(NSPNGFileType, {})))


if __name__ == "__main__":
    ROOT.mkdir(exist_ok=True)
    save(menubar(18), ROOT / "menubar.png")
    save(menubar(36), ROOT / "menubar@2x.png")
    with tempfile.TemporaryDirectory() as tmp:
        iconset = Path(tmp) / "AppIcon.iconset"
        iconset.mkdir()
        for base in (16, 32, 128, 256, 512):
            save(app_icon(base), iconset / f"icon_{base}x{base}.png")
            save(app_icon(base * 2), iconset / f"icon_{base}x{base}@2x.png")
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(ROOT / "AppIcon.icns")], check=True)
    print("iconen gemaakt in", ROOT)
