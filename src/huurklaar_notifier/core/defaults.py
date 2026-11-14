"""Standaardadressen van de Huurklaar-API en de webapp. GUI-vrij.

Het instellingenvenster toont `DEFAULT_BASE_URL` zolang er nog geen adres bewaard is. Wie een testomgeving of
lokale omgeving gebruikt, vervangt het adres in het venster.
"""

# Productie. Zodra KAN-123 (eigen API-domein) live staat, wordt dit https://api.huurklaar.be.
# Verander het hier, op één plaats.
DEFAULT_BASE_URL = "https://zf02fcpfvi.execute-api.eu-central-1.amazonaws.com"
DEFAULT_APP_URL = "https://app.huurklaar.be"

# Wie de app maakt en waar de broncode staat. Het menu-item "Over" opent `PROJECT_URL`. Dezelfde gegevens staan
# in pyproject.toml, scripts/build-mac.sh, scripts/make-version-file.py en de Inno Setup-installer.
AUTHOR = "DV Consulting"
PROJECT_URL = "https://github.com/david-dvconsulting/huurklaar-notifier"

# Per omgeving: het API-adres (zoals in de README) en het webadres van de app. Het menu-item "sleutel aanmaken"
# moet naar dezelfde omgeving openen als de sleutel waarmee de app meldingen ophaalt.
_APP_URL_BY_API = {
    DEFAULT_BASE_URL: DEFAULT_APP_URL,
    "https://gqncu23i4i.execute-api.eu-central-1.amazonaws.com": "https://app-dev.huurklaar.be",
}


def app_url_for(base_url: str) -> str:
    """Webadres van de app bij een API-adres. Een onbekend of leeg adres geeft de productie-app."""
    return _APP_URL_BY_API.get(base_url.strip().rstrip("/").lower(), DEFAULT_APP_URL)
