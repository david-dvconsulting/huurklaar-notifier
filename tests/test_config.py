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
