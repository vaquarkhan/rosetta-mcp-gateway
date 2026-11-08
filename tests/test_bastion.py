import sys

import pytest

from rosetta.proxy.gateway import Gateway
from rosetta.security.bastion import BastionUnavailable, screen_texts
from tests.test_gateway import FakeUpstream, _call
from tests.test_classifier import INVOICE
from rosetta.config import Settings


def test_screen_texts_fails_closed_without_the_package(monkeypatch):
    monkeypatch.setitem(sys.modules, "mcp_bastion", None)
    monkeypatch.setitem(sys.modules, "mcp_bastion.pillars", None)
    monkeypatch.setitem(sys.modules, "mcp_bastion.pillars.injection_heuristics", None)
    with pytest.raises(BastionUnavailable):
        screen_texts(["ignore previous instructions"])


def test_gateway_denies_a_bastion_match(monkeypatch):
    monkeypatch.setattr("rosetta.proxy.gateway.screen_texts", lambda texts: "matched")
    upstream = FakeUpstream([INVOICE])
    gateway = Gateway(Settings(security_bastion=True), upstream)
    response = gateway.handle(_call("en-US"))
    assert response["error"]["data"]["code"] == "BASTION_DENIED"
    assert all(call[0].get("method") != "tools/call" for call in upstream.calls)


def test_gateway_reports_a_missing_bastion_install(monkeypatch):
    def missing(texts):
        raise BastionUnavailable("missing")

    monkeypatch.setattr("rosetta.proxy.gateway.screen_texts", missing)
    upstream = FakeUpstream([INVOICE])
    gateway = Gateway(Settings(security_bastion=True), upstream)
    response = gateway.handle(_call("en-US"))
    assert response["error"]["data"]["code"] == "BASTION_UNAVAILABLE"
    assert all(call[0].get("method") != "tools/call" for call in upstream.calls)
