from huurklaar_notifier.__main__ import main


def test_selftest_schrijft_uitkomst_naar_bestand(tmp_path):
    out = tmp_path / "uitkomst.txt"
    assert main(["--selftest", "--selftest-output", str(out)]) == 0
    assert out.read_text(encoding="utf-8").strip().endswith("selftest: OK")
