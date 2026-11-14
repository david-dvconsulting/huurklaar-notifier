"""Het configbestand wordt thread-safe en atomair weggeschreven (NTF-03)."""

import json
import threading

from huurklaar_notifier.core.config import Config, ConfigStore


def _schrijf_gelijktijdig(store: ConfigStore) -> list[Exception]:
    """Twee threads die elk 200 keer opslaan. Geeft de fouten terug die in de threads optraden."""
    fouten: list[Exception] = []

    def schrijf(naam: str) -> None:
        try:
            for i in range(200):
                store.save(Config(base_url=naam, seen=[f"{naam}-{i}"]))
        except Exception as e:  # een fout in een thread zien we anders niet
            fouten.append(e)

    threads = [threading.Thread(target=schrijf, args=(naam,)) for naam in ("a", "b")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return fouten


def test_gelijktijdige_saves_geven_geen_fout_en_geldig_json(tmp_path):
    store = ConfigStore(tmp_path)
    assert _schrijf_gelijktijdig(store) == []
    geladen = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert geladen["base_url"] in ("a", "b")
    assert len(geladen["seen"]) == 1


def test_na_afloop_blijven_er_geen_tmp_bestanden_over(tmp_path):
    store = ConfigStore(tmp_path)
    assert _schrijf_gelijktijdig(store) == []
    assert list(tmp_path.glob("*.tmp")) == []


def test_paused_until_wordt_bewaard_en_geladen(tmp_path):
    store = ConfigStore(tmp_path)
    store.save(Config(paused_until=1234.5))
    assert store.load().paused_until == 1234.5


def test_ongeldige_paused_until_geeft_nul(tmp_path):
    for waarde in ("morgen", True, None, [1], {"a": 1}):
        (tmp_path / "config.json").write_text(json.dumps({"paused_until": waarde}), encoding="utf-8")
        assert ConfigStore(tmp_path).load().paused_until == 0.0
    (tmp_path / "config.json").write_text("{}", encoding="utf-8")
    assert ConfigStore(tmp_path).load().paused_until == 0.0


# -- meldingen per soort (KAN-284) ---------------------------------------------------------------
def test_muted_kinds_wordt_bewaard_en_geladen(tmp_path):
    store = ConfigStore(tmp_path)
    store.save(Config(muted_kinds=["complaint", "report"]))
    assert store.load().muted_kinds == ["complaint", "report"]


def test_ongeldige_muted_kinds_worden_tolerant_geladen(tmp_path):
    for waarde in ("klacht", 3, None, True, {"a": 1}, [1, 2, None, True]):
        (tmp_path / "config.json").write_text(json.dumps({"muted_kinds": waarde}), encoding="utf-8")
        assert ConfigStore(tmp_path).load().muted_kinds == [], waarde
    (tmp_path / "config.json").write_text("{}", encoding="utf-8")
    assert ConfigStore(tmp_path).load().muted_kinds == []


def test_muted_kinds_enkel_tekst_zonder_dubbelen_en_hoogstens_twintig(tmp_path):
    (tmp_path / "config.json").write_text(
        json.dumps({"muted_kinds": ["complaint", 5, "complaint", None, "task", False]}), encoding="utf-8"
    )
    assert ConfigStore(tmp_path).load().muted_kinds == ["complaint", "task"]
    veel = [f"soort{i}" for i in range(25)]
    (tmp_path / "config.json").write_text(json.dumps({"muted_kinds": veel}), encoding="utf-8")
    assert ConfigStore(tmp_path).load().muted_kinds == veel[:20]


# -- dagelijkse herinnering (KAN-285) ---------------------------------------------------------------
def test_daily_reminder_ontbreekt_of_ongeldig_geeft_aan(tmp_path):
    (tmp_path / "config.json").write_text("{}", encoding="utf-8")
    assert ConfigStore(tmp_path).load().daily_reminder is True
    for waarde in ("false", 0, 1, None, [], {"a": 1}):
        (tmp_path / "config.json").write_text(json.dumps({"daily_reminder": waarde}), encoding="utf-8")
        assert ConfigStore(tmp_path).load().daily_reminder is True, waarde


def test_daily_reminder_false_blijft_false_en_wordt_bewaard(tmp_path):
    (tmp_path / "config.json").write_text(json.dumps({"daily_reminder": False}), encoding="utf-8")
    assert ConfigStore(tmp_path).load().daily_reminder is False
    store = ConfigStore(tmp_path)
    store.save(Config(daily_reminder=False, last_reminder="2026-11-14"))
    geladen = store.load()
    assert geladen.daily_reminder is False and geladen.last_reminder == "2026-11-14"


def test_ongeldige_last_reminder_wordt_leeg(tmp_path):
    for waarde in ("gisteren", "2026-1-4", "2026-11-14T10:00", " 2026-11-14", 20261114, None, True, []):
        (tmp_path / "config.json").write_text(json.dumps({"last_reminder": waarde}), encoding="utf-8")
        assert ConfigStore(tmp_path).load().last_reminder == "", waarde
    (tmp_path / "config.json").write_text(json.dumps({"last_reminder": "2026-11-14"}), encoding="utf-8")
    assert ConfigStore(tmp_path).load().last_reminder == "2026-11-14"
