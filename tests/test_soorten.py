"""Meldingen per soort (KAN-284): uitgezette soorten geven geen melding, maar blijven gezien en in het menu."""

import time

import pytest

from huurklaar_notifier.core.controller import Controller
from huurklaar_notifier.core.i18n import translate
from huurklaar_notifier.testing.fake_server import EMPTY, FAKE_KEY, SAMPLE
from huurklaar_notifier.testing.fakes import FakePlatform

NU = time.mktime((2026, 11, 14, 10, 0, 0, 0, 0, -1))


class NepKlok:
    def __init__(self, nu: float = NU) -> None:
        self.nu = nu

    def __call__(self) -> float:
        return self.nu


def _item(soort: str, i: int) -> dict:
    return {**SAMPLE["items"][0], "id": f"{soort}-{i}", "kind": soort, "title": f"Nieuw {soort} {i}"}


def _antwoord(*items: dict) -> dict:
    n = len(items)
    return {**SAMPLE, "items": list(items), "counts": {"total": n, "overdue": 0, "actionRequired": n}}


@pytest.fixture
def klok():
    return NepKlok()


@pytest.fixture
def c(tmp_path, server, klok):
    ctl = Controller(FakePlatform(tmp_path), clock=klok)
    ctl.configure(server.url, FAKE_KEY)
    return ctl


def test_uitgevinkte_soort_geeft_geen_melding_maar_wordt_wel_gezien(c, server):
    server.body = EMPTY
    c.poll()
    c.toggle_kind("complaint")
    server.body = _antwoord(_item("complaint", 0), _item("task", 0))
    assert [t.title for t in c.poll().toasts] == ["Nieuw task 0"]
    assert "complaint-0" in c.config.seen


def test_samenvatting_telt_de_uitgevinkte_soort_niet_mee(c, server):
    server.body = EMPTY
    c.poll()
    c.toggle_kind("complaint")
    # Vijf nieuwe items: met drie uitgezet zijn er twee over, dus geen samenvatting maar twee gewone meldingen.
    server.body = _antwoord(
        _item("task", 0),
        _item("task", 1),
        _item("complaint", 0),
        _item("complaint", 1),
        _item("complaint", 2),
    )
    assert [t.title for t in c.poll().toasts] == ["Nieuw task 0", "Nieuw task 1"]


def test_samenvatting_telt_enkel_de_aangezette_meldingen(c, server):
    server.body = EMPTY
    c.poll()
    c.toggle_kind("complaint")
    server.body = _antwoord(*[_item("task", i) for i in range(4)], _item("complaint", 0))
    toasts = c.poll().toasts
    assert [t.title for t in toasts] == [translate("nl", "toast.summary", n=4)]


def test_opnieuw_aanvinken_meldt_alleen_wat_daarna_nieuw_is(c, server):
    server.body = EMPTY
    c.poll()
    c.toggle_kind("complaint")
    server.body = _antwoord(_item("complaint", 0))
    assert c.poll().toasts == []
    c.toggle_kind("complaint")  # weer aan
    assert c.config.muted_kinds == []
    assert c.poll().toasts == []  # wat al gezien was, komt niet als stortvloed
    server.body = _antwoord(_item("complaint", 0), _item("complaint", 1))
    assert [t.title for t in c.poll().toasts] == ["Nieuw complaint 1"]


def test_tijdens_een_pauze_telt_missed_de_uitgezette_soort_niet(c, server):
    server.body = EMPTY
    c.poll()
    c.toggle_kind("complaint")
    c.pause_for_hour()
    server.body = _antwoord(_item("complaint", 0), _item("task", 0))
    assert c.poll().toasts == []
    assert c.state.missed == 1
    assert "complaint-0" in c.config.seen


def test_een_herstart_houdt_de_uitgezette_soorten(c, tmp_path, klok):
    c.toggle_kind("complaint")
    c.toggle_kind("report")
    nieuw = Controller(FakePlatform(tmp_path), clock=klok)
    assert nieuw.config.muted_kinds == ["complaint", "report"]
    assert nieuw.view().muted_kinds == ("complaint", "report")
