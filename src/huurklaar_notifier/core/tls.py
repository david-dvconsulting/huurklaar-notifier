"""TLS-instellingen voor alle uitgaande verbindingen (de API en de updatecheck)."""

from __future__ import annotations

import ssl
import sys


def ssl_context() -> ssl.SSLContext:
    """Een context die ook werkt zonder systeemcertificaten.

    De Python van python.org en een met PyInstaller gebundelde app op macOS hebben geen CA-bestand: elke https-
    verbinding faalt dan met CERTIFICATE_VERIFY_FAILED, en de app meldt enkel 'Geen verbinding'. Daarom gebruiken
    we daar de certificaten van `certifi` (meegebundeld). Op Windows geldt de certificaatwinkel van het systeem,
    zodat ook een bedrijfsproxy met een eigen certificaat werkt.
    """
    if sys.platform != "win32":
        try:
            import certifi

            return ssl.create_default_context(cafile=certifi.where())
        except ImportError:
            pass
    return ssl.create_default_context()
