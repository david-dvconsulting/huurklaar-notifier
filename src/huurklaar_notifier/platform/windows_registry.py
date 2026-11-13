"""Windows-register: 'start bij aanmelden' en de AppUserModelID voor meldingen. Alles onder HKCU.

Het `winreg`-module wordt aangereikt, zodat dit bestand ook op een Mac met een nep-register getest wordt.
Er wordt nooit onder HKLM geschreven: geen beheerdersrechten en alleen voor de huidige gebruiker.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "HuurklaarMeldingen"  # dezelfde naam gebruikt de installer (installer/huurklaar-meldingen.iss)
AUMID = "be.huurklaar.meldingen"
AUMID_KEY = rf"Software\Classes\AppUserModelId\{AUMID}"
APP_NAME = "Huurklaar Meldingen"


def _winreg() -> Any:
    import winreg

    return winreg


class RunKeyAutostart:
    """Zet de app onder `HKCU\\...\\Run`. `command` geeft de opdrachtregel die Windows bij aanmelden start."""

    def __init__(self, command: Callable[[], str], winreg: Any = None, value_name: str = RUN_VALUE) -> None:
        self._command = command
        self._winreg = winreg
        self._name = value_name

    @property
    def _w(self) -> Any:
        return self._winreg or _winreg()

    def is_enabled(self) -> bool:
        w = self._w
        try:
            with w.OpenKey(w.HKEY_CURRENT_USER, RUN_KEY, 0, w.KEY_READ) as key:
                w.QueryValueEx(key, self._name)
            return True
        except FileNotFoundError:
            return False

    def set_enabled(self, enabled: bool) -> None:
        w = self._w
        if not enabled:
            try:
                with w.OpenKey(w.HKEY_CURRENT_USER, RUN_KEY, 0, w.KEY_SET_VALUE) as key:
                    w.DeleteValue(key, self._name)
            except FileNotFoundError:
                pass  # al weg is ook goed
            return
        with w.CreateKeyEx(w.HKEY_CURRENT_USER, RUN_KEY, 0, w.KEY_SET_VALUE) as key:
            w.SetValueEx(key, self._name, 0, w.REG_SZ, self._command())


def run_command(frozen: bool, executable: str) -> str:
    """De opdrachtregel voor 'start bij aanmelden'. Gebundeld: de .exe zelf; in ontwikkeling: `pythonw -m`.

    Het pad staat tussen aanhalingstekens: een gebruikersnaam met een spatie ('Jan Peeters') breekt anders het pad.
    """
    if frozen:
        return f'"{executable}"'
    return f'"{executable}" -m huurklaar_notifier'


def register_app_id(display_name: str = APP_NAME, icon_path: str | None = None, winreg: Any = None) -> None:
    """Registreert de AppUserModelID zodat een melding onder onze naam verschijnt in plaats van 'Python'.

    Zonder deze sleutel kent Windows het id niet en valt het terug op een andere naam of toont het niets.
    """
    w = winreg or _winreg()
    with w.CreateKeyEx(w.HKEY_CURRENT_USER, AUMID_KEY, 0, w.KEY_SET_VALUE) as key:
        w.SetValueEx(key, "DisplayName", 0, w.REG_SZ, display_name)
        if icon_path:
            w.SetValueEx(key, "IconUri", 0, w.REG_SZ, icon_path)
