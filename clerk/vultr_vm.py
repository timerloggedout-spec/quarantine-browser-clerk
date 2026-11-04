"""Vultr VM-per-task leg (spec: throwaway VM per task via
API where feasible; destroyed after, never stopped).

Inert until VULTR_API_KEY is provisioned (owner item, on
record): every entry point raises a named NotProvisioned
error rather than failing obscurely, and the runner's local
disposable-profile mode remains the working fallback the
spec prescribes. When the key lands, provision() creates a
vhp-2c-4gb-amd instance (the packet's sizing), the caller
runs the same Runner inside it, and destroy() tears it down
in a finally — a leaked sandbox VM is a defect by design
here, so destroy is not optional-path code.
"""
from __future__ import annotations

import json
import os
import urllib.request

API = "https://api.vultr.com/v2"
PLAN = "vhp-2c-4gb-amd"  # packet sizing (tool-rate verified)


class NotProvisioned(RuntimeError):
    pass


def _key() -> str:
    key = os.environ.get("VULTR_API_KEY", "")
    if not key:
        raise NotProvisioned(
            "VULTR_API_KEY not provisioned (owner item)")
    return key


def _call(method: str, path: str, body: dict | None = None,
          timeout=60):
    req = urllib.request.Request(
        API + path, method=method,
        data=json.dumps(body).encode() if body else None,
        headers={"Authorization": f"Bearer {_key()}",
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        return json.loads(raw) if raw else {}


def provision(label: str, region: str, os_id: int) -> dict:
    """Create the throwaway sandbox VM. Returns the instance
    record (id + main_ip once running)."""
    out = _call("POST", "/instances", {
        "region": region, "plan": PLAN, "os_id": os_id,
        "label": label, "tags": ["quarantine-clerk", "throwaway"],
        "hostname": label})
    return out.get("instance", out)


def destroy(instance_id: str) -> None:
    _call("DELETE", f"/instances/{instance_id}")
