"""API-client: enkel `GET /me/notifications` met de alleen-lezen meldingssleutel."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from .. import __version__
from .models import ProtocolError, Snapshot, parse_snapshot
from .tls import ssl_context

KEY_PREFIX = "hkn_"
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
_MAX_BODY = 1_000_000  # een antwoord is hooguit enkele tientallen kB; dit stopt een misdragende server


class ApiError(Exception):
    """Basis. De boodschap bevat nooit de sleutel."""


class AuthError(ApiError):
    """401: sleutel onbekend, ingetrokken of verkeerd gevormd (de server maakt geen onderscheid)."""


class NetworkError(ApiError):
    """Geen verbinding, time-out of een serverfout: later opnieuw proberen."""


class InvalidUrlError(ValueError):
    """Het ingevoerde adres is niet bruikbaar. Subklasse van ValueError: bestaande `except ValueError` blijft werken."""


class InvalidKeyError(ValueError):
    """De ingevoerde meldingssleutel is niet bruikbaar (of er is er geen bewaard)."""


def validate_base_url(raw: str) -> str:
    """Normaliseert het adres van de Huurklaar-API of werpt een InvalidUrlError (een ValueError).

    Alleen https (de sleutel gaat in een header mee), behalve voor een lokale ontwikkelserver.
    """
    try:
        parts = urlsplit(raw.strip())
        host = parts.hostname
    except ValueError as e:
        # urlsplit werpt zelf een gewone ValueError, bv. bij "https://[::1" (onvolledig IPv6-adres).
        raise InvalidUrlError("geen geldig adres") from e
    if not host or parts.scheme not in ("https", "http"):
        raise InvalidUrlError("geen geldig adres")
    if parts.scheme == "http" and host not in _LOCAL_HOSTS:
        raise InvalidUrlError("enkel https is toegestaan")
    if parts.username or parts.password or parts.query or parts.fragment:
        raise InvalidUrlError("geen aanmeldgegevens, query of fragment in het adres")
    return f"{parts.scheme}://{parts.netloc}{parts.path.rstrip('/')}"


def validate_key(raw: str) -> str:
    """Geeft de opgeschoonde sleutel terug of werpt een InvalidKeyError (een ValueError)."""
    key = raw.strip()
    if not key.startswith(KEY_PREFIX) or len(key) < 12 or any(c.isspace() for c in key):
        raise InvalidKeyError("geen geldige meldingssleutel")
    return key


def is_openable(url: str) -> bool:
    """Een link uit het antwoord openen we enkel als het een gewone webadres is (nooit file:, javascript:, ...)."""
    parts = urlsplit(url)
    return parts.scheme in ("https", "http") and bool(parts.hostname)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    # urllib stuurt headers bij een redirect mee; de sleutel mag nooit naar een ander adres gaan.
    def redirect_request(self, *args, **kwargs):  # noqa: D401
        return None


class ApiClient:
    def __init__(self, base_url: str, key: str, timeout: float = 10.0) -> None:
        self._url = f"{validate_base_url(base_url)}/me/notifications"
        self._key = validate_key(key)
        self._timeout = timeout
        self._opener = urllib.request.build_opener(
            _NoRedirect, urllib.request.HTTPSHandler(context=ssl_context())
        )

    def fetch(self) -> Snapshot:
        req = urllib.request.Request(
            self._url,
            headers={
                "Authorization": f"Bearer {self._key}",
                "Accept": "application/json",
                "User-Agent": f"HuurklaarMeldingen/{__version__}",
            },
        )
        try:
            with self._opener.open(req, timeout=self._timeout) as resp:
                body = resp.read(_MAX_BODY + 1)
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise AuthError("sleutel geweigerd") from None
            if e.code == 429 or e.code >= 500:
                raise NetworkError(f"server antwoordde {e.code}") from None
            raise ApiError(f"onverwacht antwoord {e.code}") from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise NetworkError("geen verbinding") from None
        if len(body) > _MAX_BODY:
            raise ProtocolError("antwoord te groot")
        try:
            return parse_snapshot(json.loads(body))
        except (ValueError, UnicodeDecodeError):
            raise ProtocolError("antwoord is geen geldige JSON") from None
