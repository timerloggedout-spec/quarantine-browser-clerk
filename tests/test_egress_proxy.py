import socket
import subprocess

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


def test_connect_proxy_consumes_headers_before_relay(monkeypatch):
    import socket
    import socketserver
    import threading

    from clerk.allowlist import Allowlist
    from clerk.egress_proxy import _ProxyHandler, _ThreadedServer

    class Echo(socketserver.BaseRequestHandler):
        def handle(self):
            data = self.request.recv(4)
            self.request.sendall(data)

    upstream = socketserver.ThreadingTCPServer(
        ("127.0.0.1", 0), Echo)
    upstream_thread = threading.Thread(
        target=upstream.serve_forever, daemon=True)
    upstream_thread.start()

    original_connect = socket.create_connection

    def local_upstream(address, timeout=None, source_address=None):
        if address == ("127.0.0.1", 443):
            address = ("127.0.0.1", upstream.server_address[1])
        return original_connect(address, timeout, source_address)

    monkeypatch.setattr(
        "clerk.egress_proxy.resolve_public",
        lambda host, port: ["127.0.0.1"])
    monkeypatch.setattr(
        "clerk.egress_proxy.socket.create_connection",
        local_upstream)

    proxy = _ThreadedServer(("127.0.0.1", 0), _ProxyHandler)
    proxy.allowlist = Allowlist(["example.test"])
    proxy_thread = threading.Thread(
        target=proxy.serve_forever, daemon=True)
    proxy_thread.start()
    try:
        with original_connect(proxy.server_address, timeout=3) as client:
            client.sendall(
                b"CONNECT example.test:443 HTTP/1.1\r\n"
                b"Host: example.test:443\r\n"
                b"Proxy-Connection: keep-alive\r\n\r\n")
            response = b""
            while b"\r\n\r\n" not in response:
                response += client.recv(1024)
            assert b"200 Connection Established" in response
            client.sendall(b"ping")
            assert client.recv(4) == b"ping"
    finally:
        proxy.shutdown()
        proxy.server_close()
        upstream.shutdown()
        upstream.server_close()


def test_proxy_firewall_only_allows_browser_to_local_proxy(monkeypatch):
    from clerk.egress_proxy import configure_egress_firewall

    calls = []

    def fake_run(args, **kwargs):
        calls.append(list(args))
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr("clerk.egress_proxy.subprocess.run", fake_run)
    configure_egress_firewall()

    assert ["iptables", "-F", "INPUT"] in calls
    assert ["iptables", "-F", "OUTPUT"] in calls
    assert ["iptables", "-A", "OUTPUT", "-o", "lo", "-p", "tcp",
            "--dport", "3128", "-j", "ACCEPT"] in calls
    assert ["iptables", "-A", "OUTPUT", "-m", "owner",
            "--uid-owner", "10002", "-j", "ACCEPT"] in calls
    assert ["iptables", "-A", "OUTPUT", "-j", "DROP"] in calls


def test_proxy_main_drops_privileges_before_serving(monkeypatch):
    import os
    from clerk import egress_proxy

    calls = []

    class FakeServer:
        def __init__(self, address, handler):
            calls.append(("bind", address))

        def serve_forever(self):
            calls.append(("serve",))

    monkeypatch.setattr(egress_proxy.os, "geteuid", lambda: 0)
    monkeypatch.setattr(
        egress_proxy, "configure_egress_firewall",
        lambda: calls.append(("firewall",)))
    monkeypatch.setattr(egress_proxy.os, "setgid",
                        lambda value: calls.append(("gid", value)))
    monkeypatch.setattr(egress_proxy.os, "setuid",
                        lambda value: calls.append(("uid", value)))
    monkeypatch.setattr(egress_proxy, "_ThreadedServer", FakeServer)
    monkeypatch.setenv("QBC_ALLOWED_DOMAINS", '["example.test"]')

    assert egress_proxy.main() == 0
    assert calls.index(("firewall",)) < calls.index(("gid", 10002))
    assert calls.index(("gid", 10002)) < calls.index(("uid", 10002))
    assert calls.index(("uid", 10002)) < calls.index(("serve",))
