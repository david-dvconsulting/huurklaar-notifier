import json

import pytest

from huurklaar_notifier.core.controller import Controller
from huurklaar_notifier.core.menu import build_menu
from huurklaar_notifier.core.updates import (
    DAY,
    RETRY_AFTER_ERROR,
    RETRY_AFTER_RATE_LIMIT,
    Release,
    UpdateCheckError,
    fetch_latest_release,
    newer_than_current,
    parse_release,
)
from huurklaar_notifier.testing.fake_github import FakeGithub, release
from huurklaar_notifier.testing.fakes import FakePlatform


@pytest.fixture
def github():
    with FakeGithub() as g:
        yield g


class Clock:
    def __init__(self) -> None:
        self.now = 1_000_000.0

    def __call__(self) -> float:
        return self.now


def make(tmp_path, github, current="1.0.0", clock=None):
    clock = clock or Clock()
    c = Controller(
        FakePlatform(tmp_path),
        clock=clock,
        update_fetch=lambda: fetch_latest_release(github.url, timeout=2),
        current_version=current,
    )
    return c, clock


# -- antwoorden van GitHub ---------------------------------------------------------


def test_nieuwere_release_wordt_gevonden(github):
    r = fetch_latest_release(github.url)
    assert r == Release(
        "1.2.0", "https://github.com/david-dvconsulting/huurklaar-notifier/releases/tag/v1.2.0"
    )
    assert github.requests[-1]["agent"].startswith("HuurklaarMeldingen/")
    assert github.requests[-1]["auth"] is None  # nooit een login


def test_link_komt_nooit_uit_het_antwoord(github):
    assert "evil" not in fetch_latest_release(github.url).url


def test_draft_en_prerelease_worden_genegeerd(github):
    github.body = release("v2.0.0", draft=True)
    assert fetch_latest_release(github.url) is None
    github.body = release("v2.0.0", prerelease=True)
    assert fetch_latest_release(github.url) is None
    github.body = release("v2.0.0-rc.1")  # tag van een voorversie, ook al staat de vlag niet goed
    assert fetch_latest_release(github.url) is None
    github.body = release("nightly")
    assert fetch_latest_release(github.url) is None


def test_geen_release_is_geen_fout(github):
    github.status = 404
    assert fetch_latest_release(github.url) is None


@pytest.mark.parametrize("status", [403, 429])
def test_limiet_bereikt(github, status):
    github.status = status
    with pytest.raises(UpdateCheckError) as e:
        fetch_latest_release(github.url)
    assert e.value.retry_after == RETRY_AFTER_RATE_LIMIT


def test_serverfout(github):
    github.status = 500
    with pytest.raises(UpdateCheckError) as e:
        fetch_latest_release(github.url)
    assert e.value.retry_after == RETRY_AFTER_ERROR


@pytest.mark.parametrize(
    "raw", [b"geen json", b"", b"\xff\xfe", b"[]", b"{}", json.dumps({"tag_name": 5}).encode()]
)
def test_ongeldig_antwoord(github, raw):
    github.raw = raw
    with pytest.raises(UpdateCheckError):
        fetch_latest_release(github.url)


def test_geen_netwerk():
    with pytest.raises(UpdateCheckError):
        fetch_latest_release("http://127.0.0.1:9/nergens", timeout=1)  # niets luistert op poort 9


def test_enkel_strikt_nieuwer_is_een_update():
    r = Release("1.2.0", "u")
    assert newer_than_current(r, "1.1.9") is r
    assert newer_than_current(r, "1.2.0") is None
    assert newer_than_current(r, "1.10.0") is None
    assert newer_than_current(None, "1.0.0") is None
    assert parse_release({"tag_name": "v1.2.0"}) is not None


# -- gedrag in de app --------------------------------------------------------------------


def test_menuregel_bij_nieuwe_versie_in_alle_talen(tmp_path, github):
    c, _ = make(tmp_path, github)
    assert c.update is None
    assert c.check_for_update() is True
    assert c.update.version == "1.2.0"
    for lang, text in (
        ("nl", "Nieuwe versie v1.2.0"),
        ("fr", "Nouvelle version v1.2.0"),
        ("en", "New version v1.2.0"),
    ):
        entry = build_menu(c.state, lang, "auto", False, c.update)[1]
        assert entry.label == text and entry.url == c.update.url
    assert all("versie v" not in e.label.lower() for e in build_menu(c.state, "nl", "auto", False, None))


def test_geen_menuregel_als_we_al_up_to_date_zijn(tmp_path, github):
    c, _ = make(tmp_path, github, current="1.2.0")
    c.check_for_update()
    assert c.update is None


def test_hoogstens_een_keer_per_dag(tmp_path, github):
    c, clock = make(tmp_path, github)
    assert c.check_for_update() is True
    assert len(github.requests) == 1
    clock.now += DAY - 60
    assert c.check_for_update() is False and len(github.requests) == 1
    clock.now += 120
    c.check_for_update()
    assert len(github.requests) == 2


def test_tijdstip_blijft_na_herstart(tmp_path, github):
    c, clock = make(tmp_path, github)
    c.check_for_update()
    again, _ = make(tmp_path, github, clock=clock)  # nieuwe start, zelfde datamap
    assert again.update.version == "1.2.0"  # ook zonder netwerk meteen zichtbaar
    assert again.check_for_update() is False and len(github.requests) == 1


def test_fouten_geven_nooit_een_melding(tmp_path, github):
    c, clock = make(tmp_path, github)
    for failure in (500, 403, 429, 404):
        github.status = failure
        clock.now += DAY
        c.check_for_update()
        assert c.update is None
    github.status, github.raw = 200, b"rommel"
    clock.now += DAY
    c.check_for_update()
    assert c.update is None
    assert c.platform.notifier.sent == [] and c.platform.opened == []


def test_fout_laat_een_bekende_update_staan_en_probeert_later_opnieuw(tmp_path, github):
    c, clock = make(tmp_path, github)
    c.check_for_update()
    github.status = 500
    clock.now += DAY
    assert c.check_for_update() is False
    assert c.update.version == "1.2.0"
    assert c.update_due_in() == RETRY_AFTER_ERROR
    github.status = 403
    clock.now += RETRY_AFTER_ERROR
    c.check_for_update()
    assert c.update_due_in() == RETRY_AFTER_RATE_LIMIT


def test_onverwachte_fout_in_de_fetch_crasht_niet(tmp_path):
    def boom():
        raise RuntimeError("kapot")

    c = Controller(FakePlatform(tmp_path), update_fetch=boom, current_version="1.0.0")
    assert c.check_for_update() is False and c.update is None


def test_geen_netwerk_is_stil(tmp_path):
    c = Controller(
        FakePlatform(tmp_path),
        update_fetch=lambda: fetch_latest_release("http://127.0.0.1:9/x", timeout=1),
        current_version="1.0.0",
    )
    assert c.check_for_update() is False and c.update is None


def test_na_bijwerken_verdwijnt_de_regel(tmp_path, github):
    c, clock = make(tmp_path, github)
    c.check_for_update()
    updated, _ = make(tmp_path, github, current="1.2.0", clock=clock)
    assert updated.update is None


def test_kapot_configbestand_geeft_geen_crash(tmp_path, github):
    (tmp_path / "config.json").write_text(json.dumps({"update_next_check": "morgen", "update_version": 5}))
    c, _ = make(tmp_path, github)
    assert c.check_for_update() in (True, False)
