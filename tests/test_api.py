import pytest

from huurklaar_notifier.core.api import (
    ApiClient,
    AuthError,
    NetworkError,
    is_openable,
    validate_base_url,
    validate_key,
)
from huurklaar_notifier.core.models import ProtocolError
from huurklaar_notifier.testing.fake_server import FAKE_KEY


def test_fetch_ok_stuurt_sleutel_als_bearer(server):
    snap = ApiClient(server.url, FAKE_KEY).fetch()
    assert snap.total == 2 and snap.items[0].overdue
    assert server.requests[-1] == {"path": "/me/notifications", "auth": f"Bearer {FAKE_KEY}"}


def test_onbekende_sleutel_is_authfout(server):
    with pytest.raises(AuthError) as e:
        ApiClient(server.url, "hkn_onbekende_sleutel").fetch()
    assert "hkn_onbekende" not in str(e.value)


def test_serverfout_is_netwerkfout(server):
    server.status = 503
    with pytest.raises(NetworkError):
        ApiClient(server.url, FAKE_KEY).fetch()


def test_geen_verbinding():
    with pytest.raises(NetworkError):
        ApiClient("http://127.0.0.1:9", FAKE_KEY, timeout=1).fetch()


def test_ongeldig_antwoord(server):
    server.body = {"nope": 1}
    with pytest.raises(ProtocolError):
        ApiClient(server.url, FAKE_KEY).fetch()


@pytest.mark.parametrize(
    "url", ["http://example.com", "ftp://x.be", "https://u:p@x.be", "https://x.be/?a=1", "x.be", ""]
)
def test_ongeldig_adres(url):
    with pytest.raises(ValueError):
        validate_base_url(url)


def test_adres_genormaliseerd():
    assert validate_base_url(" https://api.example.test/ ") == "https://api.example.test"
    assert validate_base_url("http://localhost:3000") == "http://localhost:3000"


@pytest.mark.parametrize("key", ["", "abc", "hkn_ spatie in sleutel", "xyz_" + "a" * 40])
def test_ongeldige_sleutel(key):
    with pytest.raises(ValueError):
        validate_key(key)


def test_enkel_webadressen_openen():
    assert is_openable("https://app.example.test/tasks/1")
    assert not is_openable("file:///etc/passwd") and not is_openable("javascript:alert(1)")
