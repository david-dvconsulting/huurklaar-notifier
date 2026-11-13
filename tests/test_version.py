import importlib.util
from pathlib import Path

import pytest

from huurklaar_notifier.core.version import is_newer, parse_version

_spec = importlib.util.spec_from_file_location(
    "set_version", Path(__file__).resolve().parents[1] / "scripts" / "set-version.py"
)
set_version = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(set_version)


def test_parse_met_en_zonder_v():
    assert parse_version("v1.2.10") == parse_version("1.2.10") == parse_version("V1.2.10")
    assert parse_version("1.2").release == (1, 2, 0)
    assert str(parse_version("v1.2.0-rc.1")) == "1.2.0-rc.1"


@pytest.mark.parametrize("bad", ["", "v", "1.2.3.4", "abc", "1..2", "1.2.x", "v1.2.3-", "1.2.3 rc"])
def test_ongeldige_versies(bad):
    with pytest.raises(ValueError):
        parse_version(bad)


def test_tien_is_groter_dan_negen():
    assert is_newer("1.10", "1.9") and not is_newer("1.9", "1.10")
    assert is_newer("v1.2.10", "1.2.9")
    assert is_newer("2.0.0", "1.99.99")


def test_gelijk_is_niet_nieuwer():
    assert not is_newer("1.2.0", "1.2.0")
    assert not is_newer("v1.2", "1.2.0")


def test_prerelease_volgorde():
    assert is_newer("1.2.0", "1.2.0-rc.1")  # de release komt na zijn voorversie
    assert not is_newer("1.2.0-rc.1", "1.2.0")
    assert is_newer("1.2.0-rc.2", "1.2.0-rc.1")
    assert is_newer("1.2.0-rc.10", "1.2.0-rc.9")  # numeriek, niet tekstueel
    assert is_newer("1.2.0-rc.1", "1.1.9")
    assert is_newer("1.2.0-rc.1", "1.2.0-beta.5")


def test_bouwmetadata_telt_niet_mee():
    assert not is_newer("1.2.0+abc", "1.2.0")


def test_ongeldig_is_nooit_nieuwer():
    assert not is_newer("rommel", "1.0.0")
    assert not is_newer("2.0.0", "rommel")


def test_tag_naar_versie():
    assert set_version.version_from_tag("v1.2.3") == ("1.2.3", False)
    assert set_version.version_from_tag("v1.2.3-rc.2") == ("1.2.3-rc.2", True)
    for bad in ["1.2.3", "v1.2", "v1.2.3-beta", "v01.2.3", "v1.2.3-rc.0", "release-1", "v1.2.3 "]:
        with pytest.raises(ValueError):
            set_version.version_from_tag(bad)
