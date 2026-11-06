"""Smoke test executed in a browser-UID container sharing the proxy namespace."""
import os
import socket

sink_ip = os.environ["QBC_SINK_IP"]

# A separate bridge peer is listening; the browser UID must not reach it.
try:
    socket.create_connection((sink_ip, 3129), timeout=1).close()
except OSError:
    pass
else:
    raise SystemExit("browser UID bypassed the loopback-only egress firewall")

# The sole allowed path is the local proxy. A non-allowlisted CONNECT must
# reach the proxy and be rejected before any DNS lookup or upstream socket.
with socket.create_connection(("127.0.0.1", 3128), timeout=2) as proxy:
    proxy.sendall(
        b"CONNECT denied.example:443 HTTP/1.1\r\n"
        b"Host: denied.example:443\r\n\r\n")
    response = b""
    while b"\r\n\r\n" not in response:
        chunk = proxy.recv(1024)
        if not chunk:
            break
        response += chunk
    if b"403" not in response:
        raise SystemExit("proxy did not enforce the task host allowlist")

print("proxy namespace firewall smoke test passed")
