"""Tijdelijke locatie (dmg, translocatie) en zelfherstel van de LaunchAgent. Geen AppKit nodig."""

import plistlib
import sys

import pytest

from huurklaar_notifier.platform.macos_location import (
    enable_launch_agent,
    is_transient_location,
    program_arguments,
    repair_launch_agent,
)

LABEL = "be.example.test"
EXE = "Huurklaar Meldingen.app/Contents/MacOS/Huurklaar Meldingen"
NEW = [f"/Applications/{EXE}"]
OLD = [f"/Volumes/Huurklaar Meldingen/{EXE}"]


def write_plist(path, program):
    path.write_bytes(plistlib.dumps({"Label": LABEL, "ProgramArguments": program, "RunAtLoad": True}))


def program_of(path):
    return plistlib.loads(path.read_bytes())["ProgramArguments"]


@pytest.mark.parametrize(
    "path, expected",
    [
        (f"/Volumes/Huurklaar Meldingen/{EXE}", True),
        ("/private/var/folders/ab/cd/T/AppTranslocation/1234-ABCD/d/" + EXE, True),
        (f"/Applications/{EXE}", False),
        (f"/Users/iemand/Applications/{EXE}", False),
        (f"/Users/iemand/Volumes/{EXE}", False),  # "Volumes" niet aan het begin: gewone map
        (f"/Users/iemand/Downloads/{EXE}", False),  # zonder translocatie niet tijdelijk
    ],
)
def test_is_transient_location(path, expected):
    assert is_transient_location(path) is expected


def test_program_arguments_gebundeld_en_ontwikkeling():
    assert program_arguments(True, "/x/app") == ["/x/app"]
    assert program_arguments(False, "/x/python") == ["/x/python", "-m", "huurklaar_notifier"]


def test_verouderd_pad_wordt_hersteld(tmp_path):
    plist = tmp_path / "agent.plist"
    write_plist(plist, OLD)
    assert repair_launch_agent(plist, LABEL, NEW, transient=False) is True
    assert program_of(plist) == NEW


def test_huidig_pad_blijft_ongewijzigd(tmp_path):
    plist = tmp_path / "agent.plist"
    write_plist(plist, NEW)
    # Een extra regeleinde: een herschreven bestand verliest het, dus zo merken we herschrijven op.
    plist.write_bytes(plist.read_bytes() + b"\n")
    content = plist.read_bytes()
    assert repair_launch_agent(plist, LABEL, NEW, transient=False) is False
    assert plist.read_bytes() == content


def test_geen_plist_maakt_niets_aan(tmp_path):
    plist = tmp_path / "map" / "agent.plist"
    assert repair_launch_agent(plist, LABEL, NEW, transient=False) is False
    assert not plist.exists()
    assert not plist.parent.exists()


def test_tijdelijk_huidig_pad_herschrijft_niets(tmp_path):
    plist = tmp_path / "agent.plist"
    write_plist(plist, NEW)
    assert repair_launch_agent(plist, LABEL, OLD, transient=True) is False
    assert program_of(plist) == NEW


@pytest.mark.parametrize("inhoud", [b"geen plist", b"", b"\xff\xfe\x00"])
def test_onleesbare_plist_geeft_geen_exceptie(tmp_path, inhoud):
    plist = tmp_path / "agent.plist"
    plist.write_bytes(inhoud)
    assert repair_launch_agent(plist, LABEL, NEW, transient=False) is False
    assert plist.read_bytes() == inhoud


def test_plist_zonder_programma_wordt_hersteld(tmp_path):
    plist = tmp_path / "agent.plist"
    plist.write_bytes(plistlib.dumps({"Label": LABEL}))
    assert repair_launch_agent(plist, LABEL, NEW, transient=False) is True
    assert program_of(plist) == NEW


def test_inschakelen_vanaf_tijdelijk_pad_schrijft_niets(tmp_path):
    plist = tmp_path / "map" / "agent.plist"
    assert enable_launch_agent(plist, LABEL, OLD, transient=True) is False
    assert not plist.parent.exists()


def test_inschakelen_vanaf_vaste_plaats_schrijft_de_plist(tmp_path):
    plist = tmp_path / "map" / "agent.plist"
    assert enable_launch_agent(plist, LABEL, NEW, transient=False) is True
    assert program_of(plist) == NEW


@pytest.mark.skipif(sys.platform != "darwin", reason="macos.py importeert AppKit")
def test_set_enabled_vanaf_tijdelijk_pad_toont_de_boodschap(tmp_path, monkeypatch):
    pytest.importorskip("rumps")
    from huurklaar_notifier.platform import macos

    monkeypatch.setattr(sys, "executable", OLD[0])
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    calls = []
    autostart = macos.LaunchAgentAutostart(tmp_path / "agent.plist", on_transient=lambda: calls.append(1))
    autostart.set_enabled(True)
    assert calls == [1]
    assert not autostart.is_enabled()
