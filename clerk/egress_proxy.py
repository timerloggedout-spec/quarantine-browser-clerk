"""Allowlist-only HTTPS CONNECT proxy for disposable task containers.

The browser container sits on an internal Docker network with no direct
internet route. Its only egress peer is this proxy container, which has a
separate external bridge interface. CONNECT is limited to HTTPS/443,
explicit task allowlists, and globally routable destination IPs.
"""
from __future__ import annotations

import ipaddress
import json
import os
import select
import socket
import socketserver
from urllib.parse import urlsplit

from .allowlist import Allowlist


def resolve_public(host: str, port: int = 443) -> list[str]:
    """Resolve once and reject the entire answer if any address is non-public.

    The proxy connects to the returned numeric address, not the hostname,
    preventing a second DNS lookup between policy check and connect.
    """
    try:
        records = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise PermissionError(f"DNS resolution failed for {host}") from exc
    addresses: list[str] = []
    for record in records:
        address = ipaddress.ip_address(record[4][0])
        if not address.is_global:
            raise PermissionError(
                f"non-public destination address rejected for {host}")
        value = str(address)
        if value not in addresses:
            addresses.append(value)
    if not addresses:
        raise PermissionError(f"no public address for {host}")
    return addresses


class _ProxyHandler(socketserver.StreamRequestHandler):
    rbufsize = 0
    def _deny(self, code: int, reason: str) -> None:
        body = (reason + "\n").encode()
        self.wfile.write(
            f"HTTP/1.1 {code} {reason}\r\n".encode()
            + b"Connection: close\r\n"
            + f"Content-Length: {len(body)}\r\n".encode()
            + b"Content-Type: text/plain\r\n\r\n"
            + body)

    def handle(self) -> None:
        self.connection.settimeout(20)
        try:
            request = self.rfile.readline(8192).decode(
                "ascii", "strict").strip()
            parts = request.split()
            if len(parts) != 3 or parts[0].upper() != "CONNECT":
                self._deny(405, "HTTPS CONNECT only")
                return
            header_bytes = 0
            while True:
                line = self.rfile.readline(8192)
                if not line:
                    return
                header_bytes += len(line)
                if header_bytes > 16384:
                    self._deny(431, "proxy headers too large")
                    return
                if line in (b"\r\n", b"\n"):
                    break
            target = parts[1]
            parsed = urlsplit("//" + target)
            host = (parsed.hostname or "").lower().rstrip(".")
            port = parsed.port or 443
            if not host or parsed.username or parsed.password or port != 443:
                self._deny(403, "destination rejected")
                return
            allowlist: Allowlist = self.server.allowlist  # type: ignore[attr-defined]
            if not allowlist.allows("https://" + host + "/"):
                self._deny(403, "host not in task allowlist")
                return
            try:
                addresses = resolve_public(host, port)
            except PermissionError as exc:
                self._deny(403, str(exc))
                return

            upstream = None
            for address in addresses:
                try:
                    upstream = socket.create_connection(
                        (address, port), timeout=10)
                    break
                except OSError:
                    continue
            if upstream is None:
                self._deny(502, "upstream unavailable")
                return

            with upstream:
                self.wfile.write(
                    b"HTTP/1.1 200 Connection Established\r\n"
                    b"Proxy-Agent: quarantine-browser-clerk\r\n\r\n")
                self.connection.settimeout(None)
                upstream.settimeout(None)
                sockets = (self.connection, upstream)
                while True:
                    readable, _, exceptional = select.select(
                        sockets, (), sockets, 60)
                    if exceptional or not readable:
                        break
                    closed = False
                    for source in readable:
                        try:
                            chunk = source.recv(65536)
                        except OSError:
                            closed = True
                            break
                        if not chunk:
                            closed = True
                            break
                        destination = (
                            upstream if source is self.connection
                            else self.connection)
                        destination.sendall(chunk)
                    if closed:
                        break
        except (UnicodeError, ValueError, OSError):
            return


class _ThreadedServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main() -> int:
    raw = os.environ.get("QBC_ALLOWED_DOMAINS", "[]")
    domains = json.loads(raw)
    if not isinstance(domains, list) or not domains:
        raise SystemExit("QBC_ALLOWED_DOMAINS must be a non-empty JSON array")
    server = _ThreadedServer(
        ("0.0.0.0", int(os.environ.get("QBC_PROXY_PORT", "3128"))),
        _ProxyHandler)
    server.allowlist = Allowlist(domains)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
