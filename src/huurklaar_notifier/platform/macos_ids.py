"""Id's voor macOS-meldingen, bewust zonder AppKit-import zodat ze ook op Windows-CI testbaar zijn."""

from __future__ import annotations

REQUEST_PREFIX = "hk-"


def request_id(key: str) -> str:
    """Stabiele id van een melding: dezelfde sleutel vervangt de vorige melding in het Berichtencentrum."""
    return REQUEST_PREFIX + key
