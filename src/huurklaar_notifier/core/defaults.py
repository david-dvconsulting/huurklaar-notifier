"""Standaardadressen van de Huurklaar-API en de webapp. GUI-vrij.

Het instellingenvenster toont `DEFAULT_BASE_URL` zolang er nog geen adres bewaard is. Wie een testomgeving of
lokale omgeving gebruikt, vervangt het adres in het venster.
"""

# Productie. Zodra KAN-123 (eigen API-domein) live staat, wordt dit https://api.huurklaar.be.
# Verander het hier, op één plaats.
DEFAULT_BASE_URL = "https://zf02fcpfvi.execute-api.eu-central-1.amazonaws.com"
DEFAULT_APP_URL = "https://app.huurklaar.be"
