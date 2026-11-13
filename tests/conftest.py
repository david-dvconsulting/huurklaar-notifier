import pytest

from huurklaar_notifier.core.controller import Controller
from huurklaar_notifier.testing.fake_server import FAKE_KEY, FakeServer
from huurklaar_notifier.testing.fakes import FakePlatform


@pytest.fixture
def server():
    with FakeServer() as s:
        yield s


@pytest.fixture
def controller(tmp_path, server):
    c = Controller(FakePlatform(tmp_path))
    c.configure(server.url, FAKE_KEY)
    return c
