"""Het URL-schema `huurklaar-meldingen://koppel?api=<adres>&key=<sleutel>`, waarmee Huurklaar de app kan instellen.

GUI-vrij. Een link komt van buiten en is dus onbetrouwbaar: een webpagina kan er ook een openen. Daarom valideert
`parse_link` strikt, en de aanroeper vraagt altijd om bevestiging voordat er iets wijzigt.
"""

from __future__ import annotations

from urllib.parse import parse_qsl, urlsplit

from .api import validate_base_url, validate_key

SCHEME = "huurklaar-meldingen"
_ACTION = "koppel"
_MAX_LENGTH = 2048  # ruim voor een adres en een sleutel; stopt een misbruikte, enorme link


def parse_link(url: str) -> tuple[str, str] | None:
    """Geeft `(genormaliseerd API-adres, sleutel)` als de link geldig is, anders `None`. Werpt nooit een exceptie."""
    if not isinstance(url, str) or len(url) > _MAX_LENGTH:
        return None
    # Een losse '#' maakt een fragment, ook als het leeg is; die weigeren we dus op de tekst zelf.
    if "#" in url:
        return None
    try:
        parts = urlsplit(url)
        # max_num_fields en strict_parsing weren extra parameters en losse waarden zonder '=' af.
        params = parse_qsl(parts.query, keep_blank_values=True, strict_parsing=True, max_num_fields=2)
    except ValueError:
        return None
    # Sommige browsers voegen een slash toe: 'koppel/' is ook goed, '/x' niet.
    if parts.scheme != SCHEME or parts.netloc.lower() != _ACTION or parts.path not in ("", "/"):
        return None
    names = sorted(name for name, _ in params)
    if names != ["api", "key"]:
        return None
    values = dict(params)
    try:
        api = validate_base_url(values["api"])
        key = validate_key(values["key"])
        # Een poort als :99999 gaat door validate_base_url, maar werpt pas bij het lezen van `.port`.
        # We lezen hem hier, zodat link_host later nooit faalt.
        _ = urlsplit(api).port
    except ValueError:
        return None
    return api, key


def link_host(api: str) -> str:
    """De host om aan de gebruiker te tonen: hostnaam met eventuele poort, IPv6 tussen haken. Nooit gebruikersgegevens."""
    parts = urlsplit(api)
    host = parts.hostname or ""
    if ":" in host:  # IPv6-adres: haken zijn nodig om de poort te onderscheiden
        host = f"[{host}]"
    port = parts.port
    return f"{host}:{port}" if port is not None else host
