"""`title_style`: wanneer de titel in de menubalk (Mac) rood wordt."""

from huurklaar_notifier.core.menu import title_for, title_style
from huurklaar_notifier.core.state import Status
from huurklaar_notifier.testing.fake_server import EMPTY, SAMPLE


def test_attention_met_te_laat_is_alert(controller):
    controller.poll()
    assert controller.state.status is Status.ATTENTION
    assert title_for(controller.state) == "1"
    assert title_style(controller.state) == "alert"


def test_attention_zonder_te_laat_is_normal(controller, server):
    server.body = {**SAMPLE, "counts": {"total": 2, "overdue": 0, "actionRequired": 1}}
    controller.poll()
    assert controller.state.status is Status.ATTENTION
    assert title_style(controller.state) == "normal"


def test_idle_is_normal(controller, server):
    server.body = EMPTY
    controller.poll()
    assert controller.state.status is Status.IDLE
    assert title_style(controller.state) == "normal"


def test_offline_met_oude_te_laat_snapshot_blijft_normal(controller):
    controller.poll()
    assert controller.state.snapshot.overdue == 1
    controller.state.status = Status.OFFLINE
    assert title_for(controller.state) == "!"
    assert title_style(controller.state) == "normal"


def test_auth_failed_en_niet_ingesteld_zijn_normal(controller):
    controller.state.status = Status.AUTH_FAILED
    assert title_style(controller.state) == "normal"
    controller.state.status = Status.NOT_CONFIGURED
    assert title_style(controller.state) == "normal"
