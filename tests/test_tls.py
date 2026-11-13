import ssl
import sys

import pytest

from huurklaar_notifier.core import tls


@pytest.mark.skipif(sys.platform == "win32", reason="Windows gebruikt de certificaatwinkel van het systeem")
def test_buiten_windows_komen_de_certificaten_van_certifi():
    ctx = tls.ssl_context()
    assert ctx.verify_mode is ssl.CERT_REQUIRED and ctx.check_hostname
    assert (
        ctx.cert_store_stats()["x509_ca"] > 50
    )  # zonder CA-bestand zou dit 0 zijn (de oorzaak van 'Geen verbinding')


def test_zonder_certifi_valt_het_terug_op_de_standaard(monkeypatch):
    monkeypatch.setitem(sys.modules, "certifi", None)  # import geeft ImportError
    ctx = tls.ssl_context()
    assert ctx.verify_mode is ssl.CERT_REQUIRED and ctx.check_hostname
