import time

import pytest

from huurklaar_notifier.core.controller import Controller
from huurklaar_notifier.testing.fake_server import FAKE_KEY, FakeServer
from huurklaar_notifier.testing.fakes import FakePlatform


@pytest.fixture
def server():
    with FakeServer() as s:
        yield s


def vroeg_op_de_dag() -> float:
    """08:00 lokale tijd: vóór de dagelijkse herinnering (KAN-285), zodat de bestaande tests niet van het uur afhangen."""
    t = time.localtime()
    return time.mktime((t.tm_year, t.tm_mon, t.tm_mday, 8, 0, 0, 0, 0, -1))


@pytest.fixture
def controller(tmp_path, server):
    c = Controller(FakePlatform(tmp_path), clock=vroeg_op_de_dag)
    c.configure(server.url, FAKE_KEY)
    return c
