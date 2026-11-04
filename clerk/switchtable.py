"""The when-to-switch decision table — P3 fold-in (the L8
mechanism from arXiv:2610.18861, made a clerk policy).

The clerk runs DOM-first: cheap, auditable, deterministic.
Vision-verify is the escalation mode for the moments DOM
evidence stops being trustworthy. WHEN to switch is not a
vibe — it is this table, evaluated by the runner at named
checkpoints, and every switch is receipted with the trigger
that fired, the modes it moved between, and the adapter
loss it cost (a screenshot + a verify step).

Table rows (trigger -> escalation):
  consequential-action .... a step whose class is
      consequential (sensitive fill, download, or a step
      marked "consequential") never executes on DOM
      evidence alone.
  hidden-instruction-signal
      the last page assessment found lure signals aimed at
      the agent but below the containment threshold (no
      brand distance) — verify before any further action.
  state-mismatch ......... a step-declared expectation
      ("expect": {selector, contains}) no longer matches
      the live page — the page changed under the clerk
      (deceptive-interface shape) — verify before acting
      on it.

A task opts in with "switch_table": true and may set
"switch_budget" (default 3): switches are a bounded
resource per task, stamped here; exhausting the budget
halts the task at the approval seam rather than letting
verification become routine.

The verify itself binds the strongest available checker:
the Vultr inference client when configured (vision call),
else the human approval seam — receipted either way, never
silently substituted (same honesty rule as the VM leg).
"""
from __future__ import annotations

TRIGGERS = ("consequential-action", "hidden-instruction-signal",
            "state-mismatch")

CONSEQUENTIAL_ACTIONS = ("download",)


def triggers_for(step: dict, last_verdict: dict | None,
                 expect_state: str | None) -> list[str]:
    """Pure evaluation of the table for one checkpoint.

    step ......... the step about to execute
    last_verdict . the most recent page assessment (or None)
    expect_state . "match" | "mismatch" | None — the result
                   of probing the step's declared expectation
                   against the live page
    """
    fired: list[str] = []
    action = step.get("action")
    if step.get("sensitive") or step.get("consequential") \
            or action in CONSEQUENTIAL_ACTIONS:
        fired.append("consequential-action")
    if last_verdict and last_verdict.get("lures") \
            and not last_verdict.get("contained"):
        fired.append("hidden-instruction-signal")
    if expect_state == "mismatch":
        fired.append("state-mismatch")
    return fired


def probe_expect(page, step: dict) -> str | None:
    """Probe a step's declared expectation against the live
    page. Returns "match" / "mismatch" / None (no expect)."""
    expect = step.get("expect")
    if not expect:
        return None
    el = page.query_selector(expect.get("selector", ""))
    if el is None:
        return "mismatch"
    text = el.inner_text() if hasattr(el, "inner_text") else ""
    return "match" if expect.get("contains", "") in text \
        else "mismatch"
