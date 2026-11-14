"""Windows-URL-schema: register, argument, named pipe en argparse. Zonder Windows te testen (AF_UNIX op de Mac)."""

import shutil
import socket
import sys
import tempfile
import threading
import uuid
from pathlib import Path

import pytest

from fake_winreg import FakeWinreg
from huurklaar_notifier import __main__ as entry
from huurklaar_notifier.platform.windows_link import (
    SCHEME,
    LinkServer,
    link_from_argv,
    pipe_address,
    send_link,
)
from huurklaar_notifier.platform.windows_registry import (
    URL_SCHEME_KEY,
    link_command,
    register_url_scheme,
    unregister_url_scheme,
)

LINK = f"{SCHEME}://koppel?api=https%3A%2F%2Fapi.example.test&key=hkn_voorbeeld"
EXE = r"C:\Users\Jan Peeters\App\Huurklaar Meldingen.exe"


# -- register ---------------------------------------------------------------------------------
def test_url_schema_schrijft_alle_vier_de_waarden():
    w = FakeWinreg()
    register_url_scheme(link_command(True, EXE), icon=EXE, winreg=w)
    assert w.keys[("HKCU", URL_SCHEME_KEY)][""] == "URL:Huurklaar Meldingen"
    assert w.keys[("HKCU", URL_SCHEME_KEY)]["URL Protocol"] == ""
    assert w.keys[("HKCU", URL_SCHEME_KEY + r"\DefaultIcon")][""] == f'"{EXE}",0'
    assert w.keys[("HKCU", URL_SCHEME_KEY + r"\shell\open\command")][""] == f'"{EXE}" "%1"'


def test_url_schema_schrijft_enkel_onder_hkcu():
    w = FakeWinreg()
    register_url_scheme(link_command(True, EXE), icon=EXE, winreg=w)
    assert w.keys
    assert all(root == "HKCU" for root, _ in w.keys)


def test_link_opdracht_staat_tussen_aanhalingstekens_met_spatie_in_pad():
    assert link_command(True, EXE) == f'"{EXE}" "%1"'
    assert (
        link_command(False, "C:/Py thon/pythonw.exe") == '"C:/Py thon/pythonw.exe" -m huurklaar_notifier "%1"'
    )


def test_url_schema_zonder_icoon_slaat_defaulticon_over():
    w = FakeWinreg()
    register_url_scheme("x", winreg=w)
    assert ("HKCU", URL_SCHEME_KEY + r"\DefaultIcon") not in w.keys


def test_url_schema_opnieuw_registreren_overschrijft():
    w = FakeWinreg()
    register_url_scheme("oud", winreg=w)
    register_url_scheme("nieuw", winreg=w)
    assert w.keys[("HKCU", URL_SCHEME_KEY + r"\shell\open\command")][""] == "nieuw"


def test_url_schema_verwijderen_ruimt_alles_op_en_faalt_niet_als_het_ontbreekt():
    w = FakeWinreg()
    register_url_scheme(link_command(True, EXE), icon=EXE, winreg=w)
    unregister_url_scheme(winreg=w)
    assert w.keys == {}
    unregister_url_scheme(winreg=w)  # er is niets meer: ook goed


# -- argument en pipenaam ---------------------------------------------------------------------
def test_link_uit_argv():
    assert link_from_argv(["--x", LINK]) == LINK
    assert link_from_argv(["HUURKLAAR-MELDINGEN://koppel?a=b"]) == "HUURKLAAR-MELDINGEN://koppel?a=b"
    assert link_from_argv([]) is None
    assert link_from_argv(["--selftest", "https://example.test"]) is None


def test_pipenaam_is_veilig_en_per_gebruiker():
    assert pipe_address("jan") == r"\\.\pipe\HuurklaarMeldingen-jan"
    naam = pipe_address(r"DOMEIN\Jan Peeters/..")
    assert naam.startswith(r"\\.\pipe\HuurklaarMeldingen-")
    suffix = naam.removeprefix(r"\\.\pipe\HuurklaarMeldingen-")
    assert suffix and all(c.isalnum() or c in "-_." for c in suffix)
    assert pipe_address("jan") != pipe_address("piet")


# -- server en client -------------------------------------------------------------------------
@pytest.fixture
def address():
    if sys.platform == "win32":
        yield rf"\\.\pipe\HuurklaarMeldingen-test-{uuid.uuid4().hex}"
        return
    # Een socketpad is beperkt tot ~100 tekens: tmp_path is daarvoor te lang.
    d = Path(tempfile.mkdtemp(prefix="hk"))
    try:
        yield str(d / "s")
    finally:
        shutil.rmtree(d, ignore_errors=True)


FAMILY = "AF_PIPE" if sys.platform == "win32" else "AF_UNIX"


@pytest.fixture
def server(address):
    got: list[str] = []
    event = threading.Event()

    def on_link(url: str) -> None:
        got.append(url)
        event.set()

    srv = LinkServer(address, on_link, family=FAMILY, read_timeout=0.5)
    srv.start()
    srv.got, srv.event = got, event
    try:
        yield srv
    finally:
        srv.stop(timeout=2)
        assert srv._thread is None


def test_rondreis_geeft_de_link_door(server, address):
    assert send_link(LINK, address, family=FAMILY, timeout=2)
    assert server.event.wait(timeout=2)
    assert server.got == [LINK]


def test_bericht_zonder_schema_wordt_genegeerd(server, address):
    assert send_link("https://example.test/iets", address, family=FAMILY, timeout=2)
    assert send_link(LINK, address, family=FAMILY, timeout=2)
    assert server.event.wait(timeout=2)
    assert server.got == [LINK]


def test_te_lang_bericht_wordt_genegeerd_en_de_server_blijft_werken(server, address):
    send_link(f"{SCHEME}:" + "x" * 10_000, address, family=FAMILY, timeout=2)  # mag falen aan clientzijde
    assert send_link(LINK, address, family=FAMILY, timeout=2)
    assert server.event.wait(timeout=2)
    assert server.got == [LINK]


def test_fout_in_on_link_stopt_de_server_niet(address):
    event = threading.Event()
    calls: list[str] = []

    def on_link(url: str) -> None:
        calls.append(url)
        if len(calls) == 1:
            raise RuntimeError("boem")
        event.set()

    srv = LinkServer(address, on_link, family=FAMILY, read_timeout=0.5)
    srv.start()
    try:
        assert send_link(LINK, address, family=FAMILY, timeout=2)
        assert send_link(LINK, address, family=FAMILY, timeout=2)
        assert event.wait(timeout=2)
    finally:
        srv.stop(timeout=2)


@pytest.mark.skipif(sys.platform == "win32", reason="AF_UNIX-socket: enkel buiten Windows")
def test_client_die_niets_stuurt_blokkeert_de_server_niet(server, address):
    stil = socket.socket(socket.AF_UNIX)
    stil.connect(address)
    try:
        assert send_link(LINK, address, family=FAMILY, timeout=3)
        assert server.event.wait(timeout=3)
    finally:
        stil.close()
    assert server.got == [LINK]


def test_stop_deblokkeert_de_wachtende_accept(address):
    srv = LinkServer(address, lambda _u: None, family=FAMILY)
    srv.start()
    thread = srv._thread
    srv.stop(timeout=2)
    assert thread is not None and not thread.is_alive()


def test_send_link_geeft_false_als_niemand_luistert(address):
    assert send_link(LINK, address, family=FAMILY, timeout=1) is False


# -- __main__ ---------------------------------------------------------------------------------
def test_main_aanvaardt_een_link_en_geeft_ze_door_op_windows(monkeypatch):
    import types

    gezien: list = []
    fake = types.ModuleType("huurklaar_notifier.platform.windows")
    fake.run = lambda link=None: gezien.append(link) or 0
    fake.forget = lambda: 0
    monkeypatch.setitem(sys.modules, "huurklaar_notifier.platform.windows", fake)
    monkeypatch.setattr(sys, "platform", "win32")
    assert entry.main([LINK]) == 0
    assert entry.main([]) == 0
    assert gezien == [LINK, None]


def test_main_negeert_de_link_op_de_mac(monkeypatch):
    import types

    gezien: list = []
    fake = types.ModuleType("huurklaar_notifier.platform.macos")
    fake.run = lambda: gezien.append("run")
    monkeypatch.setitem(sys.modules, "huurklaar_notifier.platform.macos", fake)
    monkeypatch.setattr(sys, "platform", "darwin")
    assert entry.main([LINK]) == 0
    assert gezien == ["run"]


def test_main_versie_werkt(capsys):
    assert entry.main(["--version"]) == 0
    assert capsys.readouterr().out.strip()
