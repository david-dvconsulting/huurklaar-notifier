"""Maakt assets/AppIcon.ico (voor de .exe, de installer en de melding) uit hetzelfde logo als de Mac-app.

Draai met de venv (heeft enkel Pillow nodig, dus ook op Windows): python scripts/make-icons-windows.py
"""

from pathlib import Path

from huurklaar_notifier.platform.windows_icon import save_ico

save_ico(str(Path(__file__).resolve().parent.parent / "assets" / "AppIcon.ico"))
print("assets/AppIcon.ico gemaakt")
