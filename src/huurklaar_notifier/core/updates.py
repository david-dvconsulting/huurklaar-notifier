"""Updatecheck: vraagt eens per dag de laatste GitHub-release op en meldt of er een nieuwere versie is.

Ontwerpregels:
- Zonder login: `GET /repos/<repo>/releases/latest` is voor een publieke repo anoniem leesbaar. GitHub staat
  60 aanvragen per uur per IP toe; wij doen er één per dag.
- Mislukken is altijd stil. Geen netwerk, een time-out, een limiet, een 404 of rommel als antwoord geeft nooit
  een melding en nooit een crash; we proberen later opnieuw.
- `latest` slaat drafts en prereleases al over; we controleren het zelf nogmaals en negeren een tag die geen
  gewone release is.
- De link naar de releasepagina bouwen we zelf uit de tag; we vertrouwen er geen adres uit het antwoord voor.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from .. import __version__
from .version import is_newer, parse_version

REPO = "david-dvconsulting/huurklaar-notifier"
LATEST_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases"

TIMEOUT = 5.0
MAX_BODY = 2_000_000  # release-notes kunnen groot zijn; dit stopt enkel een misdragende server
DAY = 24 * 3600.0
RETRY_AFTER_ERROR = 3600.0  # offline of een fout: over een uur opnieuw (ver onder de limiet van 60 per uur)
RETRY_AFTER_RATE_LIMIT = 6 * 3600.0


class UpdateCheckError(Exception):
    """De check is mislukt; `retry_after` zegt na hoeveel seconden we het opnieuw proberen."""

    def __init__(self, message: str, retry_after: float = RETRY_AFTER_ERROR) -> None:
        super().__init__(message)
        self.retry_after = retry_after


@dataclass(frozen=True, slots=True)
class Release:
    version: str  # zonder voorloper-v, bv. 1.2.0
    url: str  # de releasepagina


def release_url(version: str) -> str:
    return f"{RELEASES_PAGE}/tag/v{version}"


def parse_release(data: object) -> Release | None:
    """Het antwoord van `releases/latest`. `None` = geen bruikbare release (draft, prerelease, vreemde tag)."""
    if not isinstance(data, dict):
        raise UpdateCheckError("antwoord is geen object")
    if data.get("draft") is True or data.get("prerelease") is True:
        return None
    tag = data.get("tag_name")
    if not isinstance(tag, str):
        raise UpdateCheckError("tag_name ontbreekt")
    try:
        version = parse_version(tag)
    except ValueError:
        return None
    if version.is_prerelease:
        return None
    return Release(str(version), release_url(str(version)))


def fetch_latest_release(url: str = LATEST_URL, timeout: float = TIMEOUT) -> Release | None:
    """Geeft de laatste release, `None` als die er niet is (of niet bruikbaar is); werpt `UpdateCheckError` bij een fout."""
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"HuurklaarMeldingen/{__version__}",  # GitHub weigert aanvragen zonder User-Agent
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (vast https-adres)
            body = resp.read(MAX_BODY + 1)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None  # nog geen release gepubliceerd
        if e.code in (403, 429):  # limiet bereikt (GitHub antwoordt met 403 of 429)
            raise UpdateCheckError("limiet bereikt", RETRY_AFTER_RATE_LIMIT) from None
        raise UpdateCheckError(f"onverwacht antwoord {e.code}") from None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        raise UpdateCheckError("geen verbinding") from None
    if len(body) > MAX_BODY:
        raise UpdateCheckError("antwoord te groot")
    try:
        data = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        raise UpdateCheckError("antwoord is geen geldige JSON") from None
    return parse_release(data)


def newer_than_current(release: Release | None, current: str = __version__) -> Release | None:
    """Enkel een release die strikt nieuwer is dan de draaiende versie is een update."""
    return release if release is not None and is_newer(release.version, current) else None
