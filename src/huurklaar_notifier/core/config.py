"""Niet-geheime instellingen en de reeds getoonde meldingen, in de datamap van de gebruiker.

De sleutel staat hier nooit in: die gaat via `SecretStore` naar de Keychain of Credential Manager.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    base_url: str = ""
    language: str = "auto"  # auto | nl | fr | en
    seen: list[str] = field(
        default_factory=list
    )  # ids van meldingen die al getoond zijn (geen persoonsgegevens)
    # Updatecheck (KAN-121): wanneer we weer mogen kijken (epochseconden, blijft na een herstart bewaard) en de
    # nieuwste gevonden versie, zodat de menuregel ook zonder netwerk blijft staan.
    update_next_check: float = 0.0
    update_version: str = ""


def _number(value: object) -> float:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else 0.0


class ConfigStore:
    def __init__(self, directory: Path) -> None:
        self._path = directory / "config.json"

    def load(self) -> Config:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            return Config(
                base_url=str(raw.get("base_url", "")),
                language=str(raw.get("language", "auto")),
                seen=[str(s) for s in raw.get("seen", [])][:500],
                update_next_check=_number(raw.get("update_next_check")),
                update_version=str(raw.get("update_version") or ""),
            )
        except (OSError, ValueError, AttributeError):
            return Config()

    def save(self, config: Config) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(config.__dict__, indent=2), encoding="utf-8")
        tmp.replace(self._path)
