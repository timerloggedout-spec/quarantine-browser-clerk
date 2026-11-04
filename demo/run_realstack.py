#!/usr/bin/env python3
"""Real-stack demo — the T2 evidence run (GitHub Actions).

Five legs against the production runner machinery:
  A  LIVE positive: a task against a real allowlisted site
     (example.com) — extract + receipts + hash chain.
  B  SIGNATURE: the lookalike containment moment — the fake
     Vultr re-login (fixture host mapped to a local server,
     exactly as in the e2e suite) is contained at page
     assessment; the credential is never typed and no
     approval is requested.
  C  BRAND PIN (best-effort, non-gating): the REAL brand
     domain (vultr.com) must NOT be contained. Recorded with
     its outcome either way — third-party reachability from
     CI is not clerk behavior, so it never gates the job.
  D  SWITCH (P3 fold-in): a fixture page swaps its DOM
     mid-task and injects an agent-directed instruction;
     the decision table fires (state-mismatch), the switch
     to vision-verify is receipted with its trigger, and
     the clerk acts on the verified current state.
  E  PREFLIGHT (P4 fold-in): a three-step plan is scouted
     before execution — automatable / gated / blocked
     availability receipts — and the blocked step halts
     the run; the report is the deliverable.

Outputs land in out/: one workdir per leg (receipts.jsonl
each) + summary.json. Exit 0 iff legs A, B, D and E pass.
"""
from __future__ import annotations

import http.server
import json
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from clerk.runner import Runner  # noqa: E402

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
OUT = Path(__file__).resolve().parent.parent / "out"


class _Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        name = {"/login": "lookalike.html",
                "/catalog": "target.html",
                "/loginwall": "loginwall.html",
                "/swap": "swap.html"}.get(self.path)
        if name is None:
            self.send_response(404)
            self.end_headers()
            return
        body = (FIXTURES / name).read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def serve() -> int:
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0),
                                            _Handler)
    threading.Thread(target=httpd.serve_forever,
                     daemon=True).start()
    return httpd.server_address[1]


def _wd(name: str) -> Path:
    d = OUT / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def leg_a() -> dict:
    task = {"id": "realstack-a-live",
            "url": "https://example.com/",
            "allowed_domains": ["example.com"],
            "chromium_args": ["--no-proxy-server"],
            "steps": [
                {"action": "goto", "url": "https://example.com/"},
                {"action": "extract",
                 "fields": {"title": "title", "lead": "p"}}]}
    try:
        r = Runner(task, _wd("a-live")).run()
    except Exception as e:
        # recorded, not swallowed: the leg still gates the
        # job (ok=False) but legs B/C run so one dispatch
        # yields the full evidence set
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    # the live example.com page carries no <h1> at all (probe,
    # run 41805942661: 200 · title "Example Domain" · has_h1
    # false in both proxy modes) — the original h1 target was
    # the defect, not the clerk; title + lead paragraph are
    # the page's real extraction surface
    ok = (r["status"] == "complete" and r["receipt_chain_valid"]
          and bool(r["extracted"].get("title"))
          and bool(r["extracted"].get("lead")))
    return {"ok": ok, "status": r["status"],
            "extracted": r["extracted"],
            "chain_valid": r["receipt_chain_valid"],
            "probe": _probe_example()}


def _probe_example() -> dict:
    """Diagnostic (non-clerk): what does this environment
    actually serve for example.com, with and without the
    proxy bypass — separates clerk behavior from serving."""
    from playwright.sync_api import sync_playwright
    out = {}
    for label, args in (("no_proxy", ["--no-proxy-server"]),
                        ("default_proxy", [])):
        try:
            with sync_playwright() as pw:
                kw = {}
                from clerk.runner import _chromium_executable
                exe = _chromium_executable()
                if exe:
                    kw["executable_path"] = exe
                b = pw.chromium.launch(headless=True, args=args,
                                       **kw)
                page = b.new_page()
                resp = page.goto("https://example.com/",
                                 wait_until="domcontentloaded",
                                 timeout=30000)
                page.wait_for_timeout(1500)
                html = page.content()
                out[label] = {
                    "status": resp.status if resp else None,
                    "url": page.url, "title": page.title(),
                    "has_h1": "<h1" in html,
                    "html_head": html[:160]}
                b.close()
        except Exception as e:
            out[label] = {"error": f"{type(e).__name__}: {e}"}
    return out


def leg_b(port: int) -> dict:
    args = ["--no-proxy-server",
            "--host-resolver-rules=MAP vultrr.test 127.0.0.1"]
    task = {"id": "realstack-b-signature",
            "url": f"http://vultrr.test:{port}/login",
            "allowed_domains": ["vultrr.test"],
            "chromium_args": args,
            "steps": [
                {"action": "goto",
                 "url": f"http://vultrr.test:{port}/login"},
                {"action": "fill",
                 "selector": "input[name=password]",
                 "value": "should-never-be-typed",
                 "sensitive": True}]}
    r = Runner(task, _wd("b-signature")).run()
    verdicts = [row["verdict"] for row in r["receipts"]]
    ok = ("contained-lookalike" in verdicts
          and "approval-required" not in verdicts
          and r["receipt_chain_valid"])
    return {"ok": ok, "verdicts": verdicts,
            "chain_valid": r["receipt_chain_valid"]}


def leg_c() -> dict:
    task = {"id": "realstack-c-brandpin",
            "url": "https://www.vultr.com/",
            "allowed_domains": ["vultr.com", "www.vultr.com"],
            "chromium_args": ["--no-proxy-server"],
            "steps": [{"action": "goto",
                       "url": "https://www.vultr.com/"}]}
    try:
        r = Runner(task, _wd("c-brandpin")).run()
        verdicts = [row["verdict"] for row in r["receipts"]]
        return {"ok": "contained-lookalike" not in verdicts,
                "verdicts": verdicts,
                "chain_valid": r["receipt_chain_valid"]}
    except Exception as e:  # reachability is not the clerk
        return {"ok": None, "error": f"{type(e).__name__}: {e}"}


def _fixture_args() -> list:
    return ["--no-proxy-server",
            "--host-resolver-rules=MAP example.test 127.0.0.1"]


def leg_d(port: int) -> dict:
    base = f"http://example.test:{port}"
    task = {"id": "realstack-d-switch",
            "url": f"{base}/swap",
            "allowed_domains": ["example.test"],
            "chromium_args": _fixture_args(),
            "switch_table": True,
            "steps": [
                {"action": "goto", "url": f"{base}/swap"},
                {"action": "wait", "ms": 1500},
                {"action": "extract",
                 "fields": {"price": "#price"},
                 "expect": {"selector": "#price",
                            "contains": "$42.00"}}]}
    r = Runner(task, _wd("d-switch"),
               approve=lambda desc: True).run()
    switched = [row for row in r["receipts"]
                if row["verdict"] == "mode-switched"]
    verdicts = [row["verdict"] for row in r["receipts"]]
    ok = (any("state-mismatch" in row["detail"]
              for row in switched)
          and "vision-verified" in verdicts
          and r["extracted"].get("price") == "$4,200.00"
          and r["receipt_chain_valid"])
    return {"ok": ok, "verdicts": verdicts,
            "extracted": r["extracted"],
            "chain_valid": r["receipt_chain_valid"]}


def leg_e(port: int) -> dict:
    base = f"http://example.test:{port}"
    task = {"id": "realstack-e-preflight",
            "url": f"{base}/catalog",
            "allowed_domains": ["example.test"],
            "chromium_args": _fixture_args(),
            "preflight": True,
            "steps": [
                {"action": "goto", "url": f"{base}/catalog"},
                {"action": "goto", "url": f"{base}/loginwall"},
                {"action": "goto", "url": f"{base}/missing"}]}
    r = Runner(task, _wd("e-preflight")).run()
    verdicts = [row["verdict"] for row in r["receipts"]]
    ok = (r["status"] == "preflight-blocked"
          and "availability-automatable" in verdicts
          and "availability-gated" in verdicts
          and "availability-blocked" in verdicts
          and r["receipt_chain_valid"])
    return {"ok": ok, "status": r["status"],
            "verdicts": verdicts,
            "chain_valid": r["receipt_chain_valid"]}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    port = serve()
    summary = {"a_live": leg_a(), "b_signature": leg_b(port),
               "c_brandpin": leg_c(), "d_switch": leg_d(port),
               "e_preflight": leg_e(port)}
    (OUT / "summary.json").write_text(
        json.dumps(summary, indent=1) + "\n")
    print(json.dumps(summary, indent=1))
    return 0 if (summary["a_live"]["ok"]
                 and summary["b_signature"]["ok"]
                 and summary["d_switch"]["ok"]
                 and summary["e_preflight"]["ok"]) else 2


if __name__ == "__main__":
    raise SystemExit(main())
