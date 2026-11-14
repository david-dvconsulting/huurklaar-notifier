"""De dunne laag per platform. De kern kent enkel deze interfaces, nooit AppKit of Win32."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from ..core.state import Toast


class SecretStore(Protocol):
    def get(self) -> str | None: ...
    def set(self, value: str) -> None: ...
    def delete(self) -> None: ...


class Notifier(Protocol):
    def notify(self, toast: Toast) -> None:
        """Toont een melding; een klik opent `toast.url` (indien gegeven)."""

    def withdraw(self, keys: list[str]) -> None:
        """Trekt de meldingen met deze sleutels (`Toast.key`) in. Werpt nooit."""


class Autostart(Protocol):
    def is_enabled(self) -> bool: ...
    def set_enabled(self, enabled: bool) -> None: ...


class Platform(Protocol):
    secrets: SecretStore
    notifier: Notifier
    autostart: Autostart

    def data_dir(self) -> Path: ...
    def system_languages(self) -> list[str]: ...
    def open_url(self, url: str) -> None: ...
