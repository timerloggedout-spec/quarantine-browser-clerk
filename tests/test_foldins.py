"""Fold-in proofs: P3's switch table + P4's availability
pre-flight, riding the production runner + receipt chain.

P3: a page that swaps its DOM mid-task (deceptive
interface) fires the state-mismatch row of the decision
table; the switch to vision-verify is receipted with its
trigger before the clerk acts on the changed page. The
switch budget is a hard bound: exhausted, the task halts.

P4: a three-step plan is scouted before execution and
issued one availability receipt per step — automatable
(catalog), gated (login wall), blocked (missing target) —
and the blocked step halts the run: the availability
report is the deliverable.
"""
import http.server
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from clerk.runner import Runner  # noqa: E402
from clerk.switchtable import triggers_for  # noqa: E402

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
                "/login": "lookalike.html",
                "/loginwall": "loginwall.html",
                "/swap": "swap.html"}.get(self.path)
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


def _args():
    return ["--no-proxy-server",
            "--host-resolver-rules=MAP example.test 127.0.0.1, "
            "MAP vultrr.test 127.0.0.1"]


def test_switch_table_pure_rows():
    assert triggers_for({"action": "fill", "sensitive": True},
                        None, None) == ["consequential-action"]
    assert triggers_for({"action": "extract"},
                        {"lures": ["ai agent"],
                         "contained": False},
                        None) == ["hidden-instruction-signal"]
    assert triggers_for({"action": "extract"}, None,
                        "mismatch") == ["state-mismatch"]
    assert triggers_for({"action": "extract"},
                        {"lures": [], "contained": False},
                        "match") == []


def test_switch_state_mismatch_fires_and_verifies(
        server, tmp_path):
    task = {"id": "p3-switch",
            "url": f"http://example.test:{server}/swap",
            "allowed_domains": ["example.test"],
            "chromium_args": _args(),
            "switch_table": True,
            "steps": [
                {"action": "goto",
                 "url": f"http://example.test:{server}/swap"},
                {"action": "wait", "ms": 1500},
                {"action": "extract",
                 "fields": {"price": "#price"},
                 "expect": {"selector": "#price",
                            "contains": "$42.00"}}]}
    r = Runner(task, tmp_path, approve=lambda desc: True).run()
    assert r["status"] == "complete"
    switched = [row for row in r["receipts"]
                if row["verdict"] == "mode-switched"]
    # the swap may land before or after the goto assessment
    # (timer vs load race) — either way a switch fires, and
    # the extract-time switch carries the mismatch trigger
    assert switched and any(
        "state-mismatch" in row["detail"] for row in switched)
    verdicts = [row["verdict"] for row in r["receipts"]]
    assert "vision-verified" in verdicts
    # the clerk acted on the verified CURRENT state, and the
    # receipt chain shows the whole sequence
    assert r["extracted"]["price"] == "$4,200.00"
    assert r["receipt_chain_valid"]


def test_switch_budget_exhausted_halts(server, tmp_path):
    task = {"id": "p3-budget",
            "url": f"http://example.test:{server}/loginwall",
            "allowed_domains": ["example.test"],
            "chromium_args": _args(),
            "switch_table": True, "switch_budget": 0,
            "steps": [
                {"action": "goto",
                 "url": f"http://example.test:{server}/loginwall"},
                {"action": "fill",
                 "selector": "input[name=password]",
                 "value": "x", "sensitive": True}]}
    r = Runner(task, tmp_path, approve=lambda desc: True).run()
    assert r["status"] == "approval-required"
    verdicts = [row["verdict"] for row in r["receipts"]]
    assert "switch-budget-exceeded" in verdicts
    assert r["receipt_chain_valid"]


def test_switch_off_keeps_legacy_gate(server, tmp_path):
    task = {"id": "p3-off",
            "url": f"http://example.test:{server}/loginwall",
            "allowed_domains": ["example.test"],
            "chromium_args": _args(),
            "steps": [
                {"action": "goto",
                 "url": f"http://example.test:{server}/loginwall"},
                {"action": "fill",
                 "selector": "input[name=password]",
                 "value": "x", "sensitive": True}]}
    r = Runner(task, tmp_path).run()  # default approve = deny
    verdicts = [row["verdict"] for row in r["receipts"]]
    assert "approval-required" in verdicts
    assert "mode-switched" not in verdicts


def test_preflight_three_verdicts(server, tmp_path):
    base = f"http://example.test:{server}"
    task = {"id": "p4-scout", "url": f"{base}/catalog",
            "allowed_domains": ["example.test"],
            "chromium_args": _args(),
            "preflight": True,
            "steps": [
                {"action": "goto", "url": f"{base}/catalog"},
                {"action": "goto", "url": f"{base}/loginwall"},
                {"action": "goto", "url": f"{base}/missing"}]}
    r = Runner(task, tmp_path).run()
    assert r["status"] == "preflight-blocked"
    verdicts = [row["verdict"] for row in r["receipts"]]
    assert "availability-automatable" in verdicts
    assert "availability-gated" in verdicts
    assert "availability-blocked" in verdicts
    assert r["preflight"]["blocked"] == 1
    assert r["receipt_chain_valid"]


def test_preflight_clear_plan_proceeds(server, tmp_path):
    base = f"http://example.test:{server}"
    task = {"id": "p4-clear", "url": f"{base}/catalog",
            "allowed_domains": ["example.test"],
            "chromium_args": _args(),
            "preflight": True,
            "steps": [
                {"action": "goto", "url": f"{base}/catalog"},
                {"action": "extract",
                 "fields": {"title": "#title",
                            "price": ".price"}}]}
    r = Runner(task, tmp_path).run()
    assert r["status"] == "complete"
    assert r["extracted"]["title"] == "Example Parts Catalog"
    assert r["preflight"]["blocked"] == 0
    assert r["receipt_chain_valid"]
