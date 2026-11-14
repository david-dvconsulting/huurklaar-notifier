"""Waar draait de Mac-app vandaan, en wijst de LaunchAgent nog naar het juiste programma?

Bewust zonder AppKit of rumps, zodat alles ook op Windows-CI getest wordt. `macos.py` is een dunne laag.
"""

from __future__ import annotations

import logging
import plistlib
from pathlib import Path

log = logging.getLogger(__name__)


def is_transient_location(path: str) -> bool:
    """True voor een pad dat na een herstart niet meer bestaat: een gekoppelde dmg (`/Volumes/` vooraan)
    of een App Translocation (`/AppTranslocation/` ergens in het pad, gezet door Gatekeeper).

    `/Volumes/` moet vooraan staan: `/Users/x/Volumes/...` is een gewone map.
    """
    return path.startswith("/Volumes/") or "/AppTranslocation/" in path


def program_arguments(frozen: bool, executable: str) -> list[str]:
    """Gebundeld: de uitvoerbare file in de .app; in ontwikkeling: de module met de huidige Python."""
    return [executable] if frozen else [executable, "-m", "huurklaar_notifier"]


def _plist_bytes(label: str, program: list[str]) -> bytes:
    return plistlib.dumps({"Label": label, "ProgramArguments": program, "RunAtLoad": True})


def enable_launch_agent(path: Path, label: str, program: list[str], transient: bool) -> bool:
    """Schrijft de LaunchAgent. Vanaf een tijdelijk pad schrijft ze niets en geeft ze False terug."""
    if transient:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_plist_bytes(label, program))
    return True


def repair_launch_agent(path: Path, label: str, program: list[str], transient: bool) -> bool:
    """Zelfherstel bij de start: wijst een bestaande LaunchAgent naar een ander programma dan het huidige
    en staat de app nu op een vaste plaats, dan wordt ze herschreven. Geeft True als ze herschreven is.

    Een ontbrekende of onleesbare plist mag de start nooit laten crashen: dan gebeurt er niets (een
    ontbrekende plist betekent dat 'Start bij aanmelden' uit staat, en dat blijft zo).
    """
    if transient or not path.exists():
        return False
    try:
        current = plistlib.loads(path.read_bytes()).get("ProgramArguments")
        if current == program:
            return False
        path.write_bytes(_plist_bytes(label, program))
    except Exception as e:  # kapotte plist of schrijffout: enkel het type loggen
        log.warning("LaunchAgent herstellen mislukt: %s", type(e).__name__)
        return False
    return True
