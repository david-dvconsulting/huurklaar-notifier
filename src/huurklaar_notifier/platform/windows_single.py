"""Één exemplaar tegelijk: een benoemde mutex. Dezelfde naam staat als `AppMutex` in de installer, zodat de
installer en de uninstaller waarschuwen als de app nog draait."""

from __future__ import annotations

MUTEX_NAME = "HuurklaarMeldingenSingleInstance"
_ERROR_ALREADY_EXISTS = 183
_held: object | None = None  # de handle moet leven zolang het proces leeft


def acquire() -> bool:
    """`True` als dit het enige exemplaar is."""
    global _held
    import ctypes

    kernel32 = ctypes.windll.kernel32
    _held = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    return kernel32.GetLastError() != _ERROR_ALREADY_EXISTS
