"""De dunne laag per platform. De kern kent enkel deze interfaces, nooit AppKit of Win32."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class SecretStore(Protocol):
    def get(self) -> str | None: ...
    def set(self, value: str) -> None: ...
    def delete(self) -> None: ...


class Notifier(Protocol):
    def notify(self, title: str, body: str, url: str | None) -> None:
        """Toont een melding; een klik opent `url` (indien gegeven)."""


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
