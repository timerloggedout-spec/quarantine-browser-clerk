"""Availability pre-flight — P4 fold-in.

Coherence is not availability: a task plan can be perfectly
well-formed while its steps are not executable — a login
wall, a re-auth, a target that no longer resolves. Before
the clerk accepts a task it may scout it: every step is
probed in the same disposable profile, under the same
allowlist route guard, and issued an AVAILABILITY RECEIPT:

  availability-automatable . the step executes as planned
  availability-gated ....... the step exists but sits
      behind a human gate (credential form / login wall /
      consequential action class)
  availability-blocked ...... the step cannot execute: the
      navigation fails, the host is off-allowlist, the
      page is contained as a lookalike, or an extraction
      target is absent. The receipt names the exact wall.

The scout's deliverable is the receipt set itself — an
honest "no", with evidence, before any build is committed
to a doomed workflow. Blocked steps halt the run (status
"preflight-blocked") unless the task sets
"proceed_anyway": true; gated steps are reported and the
run proceeds — the runner's own gates still apply at
execution time.
"""
from __future__ import annotations

from .lookalike import assess, KNOWN_BRANDS


def _classify_goto(page, step, task) -> tuple[str, str]:
    url = step["url"]
    try:
        resp = page.goto(url, wait_until="domcontentloaded",
                         timeout=step.get("timeout_ms", 15000))
    except Exception as e:
        return "availability-blocked", \
            f"navigation failed: {type(e).__name__}: {e}"
    status = resp.status if resp is not None else 0
    if status >= 400:
        return "availability-blocked", f"HTTP {status} at {url}"
    verdict = assess(page.url, page.content(),
                     tuple(task["brands"])
                     if task.get("brands") else KNOWN_BRANDS)
    if verdict["contained"]:
        return "availability-blocked", \
            f"contained-lookalike: {verdict['reason']}"
    if 'type="password"' in page.content().lower():
        return "availability-gated", \
            "credential form present — login wall; a human " \
            "session gate stands before this step"
    return "availability-automatable", f"HTTP {status}; page " \
        "reachable, no gate detected"


def run_preflight(page, task: dict, log) -> dict:
    """Probe every step; emit one receipt per step into the
    run's chain. Returns the availability report."""
    steps = task.get("steps") or [
        {"action": "goto", "url": task["url"]}]
    report = {"steps": [], "automatable": 0, "gated": 0,
              "blocked": 0}
    for i, step in enumerate(steps):
        action = step.get("action")
        url = step.get("url", page.url)
        if action == "goto":
            verdict, wall = _classify_goto(page, step, task)
        elif action == "extract":
            missing = [name for name, sel in
                       (step.get("fields") or {}).items()
                       if page.query_selector(sel) is None]
            if missing:
                verdict, wall = "availability-blocked", \
                    f"extraction targets absent: {missing}"
            else:
                verdict, wall = "availability-automatable", \
                    "all extraction targets resolve"
        elif step.get("sensitive") or step.get("consequential"):
            verdict, wall = "availability-gated", \
                "consequential step — human approval gate"
        else:
            verdict, wall = "availability-automatable", \
                f"{action} step carries no gate"
        key = verdict.rsplit("-", 1)[1]
        report[key] += 1
        entry = {"step": i, "action": action, "verdict": verdict,
                 "wall": wall}
        report["steps"].append(entry)
        log.emit("preflight", verdict, url,
                 f"step {i} ({action}): {wall}")
    return report
