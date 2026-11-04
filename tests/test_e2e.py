"""End-to-end proofs over local fixture servers.

T1: task in -> sandboxed browse -> extracted data + receipt
log out, disposable profile destroyed.
T2 (signature): the lookalike page aiming a fake re-login at
the agent is CONTAINED — one containment receipt, no
credential ever entered, the run still ends clean.
"""
import http.server
import sys
import threading
from functools import partial
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from clerk.runner import Runner  # noqa: E402

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
pytestmark = pytest.mark.skipif(
    not Path.home().joinpath(".cache/ms-playwright").exists()
    and not list(Path("/root/.cache/ms-playwright").glob("*")),
    reason="playwright browsers not installed")


class _Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        name = {"/catalog": "target.html",
                "/login": "lookalike.html"}.get(self.path)
        if name is None:
            return super().do_GET()
        body = (FIXTURES / name).read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture(scope="module")
def server():
    httpd = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0), _Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield httpd.server_address[1]
    httpd.shutdown()


def _args(port):
    return ["--no-proxy-server",
            "--host-resolver-rules=MAP example.test 127.0.0.1, "
            "MAP vultrr.test 127.0.0.1"]


def test_t1_core_loop(server, tmp_path):
    task = {"id": "t1-demo", "url": f"http://example.test:{server}/catalog",
            "chromium_args": _args(server),
            "steps": [
                {"action": "goto", "url": f"http://example.test:{server}/catalog"},
                {"action": "extract",
                 "fields": {"title": "#title", "price": ".price"}}]}
    r = Runner(task, tmp_path).run()
    assert r["status"] == "complete"
    assert r["extracted"]["title"] == "Example Parts Catalog"
    assert r["extracted"]["price"] == "$42.00"
    assert r["receipt_chain_valid"]
    verdicts = [row["verdict"] for row in r["receipts"]]
    assert "extracted" in verdicts
    assert not list(tmp_path.glob("qbc-profile-*"))  # destroyed


def test_t2_signature_containment(server, tmp_path):
    task = {"id": "t2-signature",
            "url": f"http://vultrr.test:{server}/login",
            "allowed_domains": ["vultrr.test"],
            "chromium_args": _args(server),
            "steps": [
                {"action": "goto", "url": f"http://vultrr.test:{server}/login"},
                {"action": "fill", "selector": "input[name=password]",
                 "value": "should-never-be-typed", "sensitive": True}]}
    r = Runner(task, tmp_path).run()
    verdicts = [row["verdict"] for row in r["receipts"]]
    assert "contained-lookalike" in verdicts
    # containment happened at page assessment — the sensitive
    # fill step never executed, no approval was even requested
    assert "approval-required" not in verdicts
    assert r["receipt_chain_valid"]
