"""Fetch-by-fetch action receipts in the fleet evidence
envelope: one JSON object per action, hash-chained (each
receipt carries the previous receipt's hash — the same
prove-it discipline as the fleet's other ledgers). A run's
receipt log is the demo's evidence artifact: every allowed,
blocked, contained, quarantined, and approval-gated action
is in it, in order.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

VERDICTS = ("allowed", "blocked-allowlist", "contained-lookalike",
            "download-quarantined", "extracted", "approval-required",
            "task-start", "task-complete", "task-failed")


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ReceiptLog:
    def __init__(self, task_id: str, path: Path | None = None):
        self.task_id = task_id
        self.path = Path(path) if path else None
        self.seq = 0
        self.prev_hash = "GENESIS"
        self.rows: list[dict] = []

    def emit(self, action: str, verdict: str, url: str = "",
             detail: str = "") -> dict:
        assert verdict in VERDICTS, verdict
        self.seq += 1
        row = {
            "schema": "quarantine-clerk/receipt/v1",
            "receipt_id": f"qr-{self.seq:04d}",
            "task_id": self.task_id,
            "seq": self.seq,
            "at": _iso_now(),
            "action": action,
            "url": url,
            "verdict": verdict,
            "detail": detail,
            "prev_hash": self.prev_hash,
        }
        payload = json.dumps({k: row[k] for k in sorted(row)
                              if k != "prev_hash"},
                             sort_keys=True).encode()
        row["hash"] = hashlib.sha256(
            self.prev_hash.encode() + payload).hexdigest()[:24]
        self.prev_hash = row["hash"]
        self.rows.append(row)
        if self.path:
            with self.path.open("a") as fh:
                fh.write(json.dumps(row, sort_keys=True) + "\n")
        return row

    def verify(self) -> bool:
        prev = "GENESIS"
        for row in self.rows:
            if row["prev_hash"] != prev:
                return False
            payload = json.dumps(
                {k: row[k] for k in sorted(row)
                 if k not in ("prev_hash", "hash")},
                sort_keys=True).encode()
            expect = hashlib.sha256(
                prev.encode() + payload).hexdigest()[:24]
            if row["hash"] != expect:
                return False
            prev = row["hash"]
        return True
