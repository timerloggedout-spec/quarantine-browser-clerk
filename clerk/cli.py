"""CLI: python -m clerk run task.json [--approve-all]

Prints the run result JSON (extracted data + receipt chain
state) on stdout; the full receipt log lands in
<workdir>/receipts.jsonl and downloads in
<workdir>/quarantine/.
"""
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from .runner import Runner


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="clerk")
    sub = ap.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run")
    run.add_argument("task")
    run.add_argument("--workdir", default=None)
    run.add_argument("--approve-all", action="store_true",
                     help="human operator approves consequential "
                          "actions (the vision-verify gate, CLI "
                          "form)")
    args = ap.parse_args(argv)
    task = json.loads(Path(args.task).read_text())
    workdir = Path(args.workdir) if args.workdir else Path(
        tempfile.mkdtemp(prefix="qbc-run-"))
    workdir.mkdir(parents=True, exist_ok=True)
    approve = (lambda desc: True) if args.approve_all else None
    result = Runner(task, workdir, approve=approve).run()
    result["workdir"] = str(workdir)
    print(json.dumps(result, indent=1))
    return 0 if result["status"] == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
