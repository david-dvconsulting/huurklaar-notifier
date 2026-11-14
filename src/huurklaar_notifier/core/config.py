"""Niet-geheime instellingen en de reeds getoonde meldingen, in de datamap van de gebruiker.

De sleutel staat hier nooit in: die gaat via `SecretStore` naar de Keychain of Credential Manager.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from dataclasses import asdict, dataclass, field
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
    # Meldingen pauzeren (KAN-283): tot wanneer er geen meldingen komen (epochseconden, 0 = niet gepauzeerd).
    # Blijft na een herstart bewaard, anders zou afsluiten de pauze stilletjes opheffen.
    paused_until: float = 0.0
    # Meldingen per soort (KAN-284): soorten die de gebruiker uitgezet heeft. Items van zo'n soort krijgen
    # geen melding, maar blijven wel in het menu staan.
    muted_kinds: list[str] = field(default_factory=list)
    # Dagelijkse herinnering (KAN-285): standaard aan, ook voor bestaande installaties zonder dit veld.
    daily_reminder: bool = True
    # De lokale datum (YYYY-MM-DD) van de laatste herinnering. Blijft na een herstart bewaard, anders volgt er
    # een tweede herinnering op dezelfde dag.
    last_reminder: str = ""


MAX_MUTED_KINDS = 20  # ruim genoeg voor de bekende soorten; meer is een fout of misbruik van het bestand


_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _number(value: object) -> float:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else 0.0


def _kinds(value: object) -> list[str]:
    """Enkel tekstwaarden, zonder dubbelen en hoogstens `MAX_MUTED_KINDS`. Alles anders wordt genegeerd."""
    if not isinstance(value, list):
        return []
    return list(dict.fromkeys(v for v in value if isinstance(v, str)))[:MAX_MUTED_KINDS]


def _reminder_flag(value: object) -> bool:
    """Enkel een echte bool telt; alles anders (ook een ontbrekend veld) geeft de standaard: aan."""
    return value if isinstance(value, bool) else True


def _date(value: object) -> str:
    """Enkel een datum van de vorm YYYY-MM-DD; anders leeg."""
    return value if isinstance(value, str) and _DATE.fullmatch(value) else ""


class ConfigStore:
    def __init__(self, directory: Path) -> None:
        self._path = directory / "config.json"
        # Op Windows kan een gelijktijdige os.replace naar hetzelfde doel PermissionError geven,
        # dus saves binnen één proces lopen na elkaar, ook als een aanroeper geen lock neemt.
        self._lock = threading.Lock()

    def load(self) -> Config:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            return Config(
                base_url=str(raw.get("base_url", "")),
                language=str(raw.get("language", "auto")),
                seen=[str(s) for s in raw.get("seen", [])][:500],
                update_next_check=_number(raw.get("update_next_check")),
                update_version=str(raw.get("update_version") or ""),
                paused_until=_number(raw.get("paused_until")),
                muted_kinds=_kinds(raw.get("muted_kinds")),
                daily_reminder=_reminder_flag(raw.get("daily_reminder")),
                last_reminder=_date(raw.get("last_reminder")),
            )
        except (OSError, ValueError, AttributeError):
            return Config()

    def save(self, config: Config) -> None:
        data = json.dumps(asdict(config), indent=2)
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            # Eigen tijdelijk bestand per schrijfactie: ook een tweede proces botst dan niet op hetzelfde pad.
            fd, name = tempfile.mkstemp(dir=self._path.parent, prefix="config.", suffix=".tmp")
            tmp = Path(name)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(data)
                os.replace(tmp, self._path)
            finally:
                # Na een geslaagde replace bestaat het bestand niet meer; bij een fout ruimen we het hier op.
                tmp.unlink(missing_ok=True)
