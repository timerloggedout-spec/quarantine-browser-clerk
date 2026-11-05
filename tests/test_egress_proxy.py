import socket

import pytest

from clerk.egress_proxy import resolve_public


def test_resolve_public_accepts_public_ip(monkeypatch):
    monkeypatch.setattr(
        socket, "getaddrinfo",
        lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM,
                          6, "", ("93.184.216.34", 443))])
    assert resolve_public("example.test") == ["93.184.216.34"]


@pytest.mark.parametrize("address", [
    "127.0.0.1", "10.0.0.8", "192.168.1.10",
    "169.254.169.254", "::1", "fc00::1",
])
def test_resolve_public_rejects_non_global_addresses(
        monkeypatch, address):
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    monkeypatch.setattr(
        socket, "getaddrinfo",
        lambda *a, **k: [(family, socket.SOCK_STREAM,
                          6, "", (address, 443))])
    with pytest.raises(PermissionError):
        resolve_public("internal.test")


def test_mixed_dns_answer_is_rejected(monkeypatch):
    monkeypatch.setattr(
        socket, "getaddrinfo",
        lambda *a, **k: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "",
             ("93.184.216.34", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "",
             ("127.0.0.1", 443)),
        ])
    with pytest.raises(PermissionError):
        resolve_public("rebinding.test")
