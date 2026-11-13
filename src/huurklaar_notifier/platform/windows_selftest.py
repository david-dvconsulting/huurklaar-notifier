"""Extra controles voor Windows, in `--selftest` van de .exe: zitten alle bibliotheken erin (ook de verborgen
imports van PyInstaller), werkt de Credential Manager en het register? Er wordt geen melding getoond: een
hangende melding mag de test nooit blokkeren. Alles ruimt zichzelf op."""

from __future__ import annotations

import uuid
from collections.abc import Callable


def run(check: Callable[[bool, str], None]) -> None:
    def attempt(what: str, fn: Callable[[], bool]) -> None:
        try:
            check(bool(fn()), what)
        except Exception as e:  # noqa: BLE001  (type en tekst volstaan; nooit sleutels of gegevens)
            check(False, f"{what}: {type(e).__name__}: {e}")

    # Bibliotheken die PyInstaller niet vanzelf vindt.
    def imports() -> bool:
        import tkinter  # noqa: F401

        import pystray._win32  # noqa: F401
        import win11toast  # noqa: F401
        import winrt.windows.ui.notifications  # noqa: F401
        from PIL import Image  # noqa: F401

        return True

    attempt("bibliotheken (pystray, win11toast, winrt, tkinter, Pillow) zitten erin", imports)

    def icon() -> bool:
        from ..core.state import State
        from .windows_icon import badge_for, render_icon

        return render_icon(badge_for(State()), 64).size == (64, 64)

    attempt("tray-icoon tekenen", icon)

    def menu() -> bool:
        import pystray

        from ..core.menu import build_menu
        from ..core.state import State
        from .windows_menu import build_items

        entries = build_menu(State(), "nl", "auto", False)
        items = build_items(entries, pystray.MenuItem, pystray.Menu, pystray.Menu.SEPARATOR, lambda e: None)
        return len(pystray.Menu(*items).items) > 5

    attempt("menu omzetten naar pystray", menu)

    def credential_manager() -> bool:
        import keyring

        from .keyring_store import KeyringSecretStore

        name = type(keyring.get_keyring()).__name__
        store = KeyringSecretStore(service=f"be.huurklaar.meldingen.selftest.{uuid.uuid4().hex}")
        value = "hkn_selftest_" + uuid.uuid4().hex
        try:
            store.set(value)
            ok = store.get() == value
        finally:
            store.delete()
        return ok and store.get() is None and "WinVault" in name

    attempt("sleutel in de Credential Manager (WinVault)", credential_manager)

    def autostart() -> bool:
        from .windows_registry import RunKeyAutostart

        a = RunKeyAutostart(
            lambda: '"C:\\Test\\x.exe"', value_name="HuurklaarMeldingenSelftest" + uuid.uuid4().hex[:6]
        )
        try:
            a.set_enabled(True)
            on = a.is_enabled()
        finally:
            a.set_enabled(False)
        return on and not a.is_enabled()

    attempt("start bij aanmelden aan en uit", autostart)
