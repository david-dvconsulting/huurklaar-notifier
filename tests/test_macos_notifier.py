"""Id's en gedrag van `MacNotifier` (het gedrag enkel op macOS, met een nep-center)."""

import logging
import sys

import pytest

from huurklaar_notifier.platform.macos_ids import request_id


def test_request_id_heeft_vaste_uitvoer_met_prefix():
    assert request_id("task-1") == "hk-task-1"
    assert request_id("summary") == "hk-summary"


def test_request_id_zelfde_sleutel_geeft_zelfde_id():
    assert request_id("task:a:1") == request_id("task:a:1")


def test_request_id_verschillende_sleutels_geven_verschillende_ids():
    assert request_id("task-1") != request_id("task-2")


@pytest.mark.skipif(sys.platform != "darwin", reason="AppKit bestaat enkel op macOS")
class TestMacNotifier:
    @pytest.fixture
    def parts(self):
        pytest.importorskip("UserNotifications")
        from huurklaar_notifier.core.state import Toast
        from huurklaar_notifier.platform.macos import MacNotifier

        class FakeCenter:
            def __init__(self):
                self.added = []
                self.removed = []
                self.fail = False

            def addNotificationRequest_withCompletionHandler_(self, request, handler):
                if self.fail:
                    raise RuntimeError("geheim-titel")
                self.added.append(request)

            def removeDeliveredNotificationsWithIdentifiers_(self, ids):
                if self.fail:
                    raise RuntimeError("geheim-sleutel")
                self.removed.append(list(ids))

        center = FakeCenter()
        return center, MacNotifier(center=center), Toast

    def test_notify_gebruikt_sleutel_als_id_en_groep_als_thread(self, parts):
        center, notifier, Toast = parts
        notifier.notify(Toast("Titel", "Tekst", "https://example.test/x", "task-1", "task"))
        (request,) = center.added
        assert request.identifier() == "hk-task-1"
        assert request.content().threadIdentifier() == "task"
        assert request.content().userInfo()["url"] == "https://example.test/x"

    def test_notify_met_dezelfde_sleutel_geeft_dezelfde_id(self, parts):
        center, notifier, Toast = parts
        notifier.notify(Toast("A", "a", None, "task-1", "task"))
        notifier.notify(Toast("B", "b", None, "task-1", "task"))
        assert center.added[0].identifier() == center.added[1].identifier()

    def test_withdraw_roept_center_aan_met_juiste_ids(self, parts):
        center, notifier, _ = parts
        notifier.withdraw(["task-1", "complaint-2"])
        assert center.removed == [["hk-task-1", "hk-complaint-2"]]

    def test_fout_in_center_wordt_opgevangen_en_log_bevat_enkel_fouttype(self, parts, caplog):
        center, notifier, Toast = parts
        center.fail = True
        with caplog.at_level(logging.WARNING):
            notifier.notify(Toast("geheim-titel", "tekst", None, "geheim-sleutel", "task"))
            notifier.withdraw(["geheim-sleutel"])
        assert "RuntimeError" in caplog.text
        assert "geheim" not in caplog.text
