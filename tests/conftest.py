"""Repository-wide offline safety harness for tests."""

from __future__ import annotations

import socket
import urllib.request

import pytest


@pytest.fixture(autouse=True)
def _deny_real_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("SIRAJ_TEST_NETWORK_ACCESS_FORBIDDEN")

    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(urllib.request, "urlopen", denied)

