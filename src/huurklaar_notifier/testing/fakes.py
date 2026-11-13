"""Nep-platform voor tests: alles in het geheugen."""

from __future__ import annotations

from pathlib import Path


class MemorySecrets:
    def __init__(self) -> None:
        self.value: str | None = None

    def get(self) -> str | None:
        return self.value

    def set(self, value: str) -> None:
        self.value = value

    def delete(self) -> None:
        self.value = None


class RecordingNotifier:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str | None]] = []

    def notify(self, title: str, body: str, url: str | None) -> None:
        self.sent.append((title, body, url))


class MemoryAutostart:
    def __init__(self) -> None:
        self.enabled = False

    def is_enabled(self) -> bool:
        return self.enabled

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled


class FakePlatform:
    def __init__(self, directory: Path, languages: list[str] | None = None) -> None:
        self.secrets = MemorySecrets()
        self.notifier = RecordingNotifier()
        self.autostart = MemoryAutostart()
        self.opened: list[str] = []
        self._dir = directory
        self._languages = languages or ["nl-BE"]

    def data_dir(self) -> Path:
        return self._dir

    def system_languages(self) -> list[str]:
        return self._languages

    def open_url(self, url: str) -> None:
        self.opened.append(url)
