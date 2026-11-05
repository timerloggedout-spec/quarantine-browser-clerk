# Quarantine Browser Clerk

D2 (Vultr Agent Rush) — an agent browser clerk whose every
act is contained, receipted, and disposable by construction.
Repo: timerloggedout-spec/quarantine-browser-clerk.

## What is proven (CI, Actions evidence)

- **T1 core loop** (`tests/test_e2e.py::test_t1_core_loop`):
  task in → sandboxed browse → extracted data + hash-chained
  receipt log out; disposable profile destroyed after.
- **T2 signature mechanism**
  (`test_t2_signature_containment` + `fixtures/lookalike.html`):
  a lookalike-domain page socially-engineering the agent
  (fake Vultr re-login + verifier download) is CONTAINED at
  page assessment — receipt sequence task-start → allowed →
  **contained-lookalike** → task-complete → profile
  destroyed; no credential is ever typed, no approval is
  even requested.
- **T2 on the real stack** (`.github/workflows/demo.yml`,
  run **41807278198** SUCCESS): leg A — live extraction from
  a real allowlisted site (example.com: title + lead pulled,
  chain valid); leg B — the signature containment fires
  against the lookalike fixture host; leg C — the real
  brand domain (vultr.com) is **not** contained (the brand
  pin holds). Receipts for all three legs ship as the run's
  `realstack-receipts` artifact.

## Intended production stack — current activation status

The competition target is a web-facing clerk backed by isolated execution on
Vultr. The repository's current evidence is narrower than that target:

- **Vultr Cloud Compute:** `clerk/vultr_vm.py` currently contains low-level
  `provision()` and `destroy()` API helpers. No runner/CLI path yet invokes
  them, transfers a task to a remote VM, waits for readiness, collects remote
  output, or guarantees VM destruction. A Vultr VM-per-task deployment is
  **not yet implemented or evidenced**.
- **Vultr Serverless Inference:** `clerk/inference.py` is an
  OpenAI-compatible client for `api.vultrinference.com/v1`. The current
  runner uses it only for optional P3 vision verification when configured;
  it does **not** generate the browsing plan. Task steps are currently
  supplied as deterministic JSON.
- **Current proven execution:** the CLI runner uses a disposable local
  Chromium profile. GitHub Actions proves the T1/T2/T3 mechanisms on its
  hosted runner; this is not a Vultr-hosted execution claim.
- **Activation:** no Vultr API/inference key or model configuration is
  recorded in this repository. Keep credentials in runtime secret custody;
  never commit them.

The production integration gap is tracked in
[issue #9](https://github.com/timerloggedout-spec/quarantine-browser-clerk/issues/9).

## Containment model (enforced below the agent)

- Disposable Chromium profile per task (deleted after);
  full-Chromium preferred (the headless shell ignores
  host-resolver rules — see `clerk/runner.py`).
- Route guard: every request passes the task's domain
  allowlist (deny-by-default); aborts are receipted.
- Downloads land only in a per-task quarantine directory;
  never executed, never moved out.
- Lookalike/lure assessment before any interaction
  (`clerk/lookalike.py`): containment needs BOTH domain
  distance from an imitated brand AND a lure signal
  (credential form, session-expired / verifier language,
  agent-directed phrasing) — explainable, test-pinned.
- Consequential actions (sensitive fills) halt at the
  human-approval seam (vision-verify gate); default deny.
- Receipts: `quarantine-clerk/receipt/v1`, hash-chained,
  tamper-evident (`ReceiptLog.verify`).

## Folded-in mechanisms (T3, additive — opt-in per task)

- **The switch table** (`clerk/switchtable.py`): the clerk
  runs DOM-first; WHEN it escalates to vision-verify is a
  decision table, not a judgment call — consequential
  action class · sub-threshold hidden-instruction signals ·
  a step's declared expectation no longer matching the
  live page (state-mismatch: the page changed under the
  clerk). Every switch is receipted with its trigger and
  bounded by a per-task switch budget. Verification binds
  the inference client when keyed, else the human seam —
  receipted either way. Opt in: `"switch_table": true`.
- **Availability pre-flight** (`clerk/preflight.py`): with
  `"preflight": true`, the plan is scouted before it is
  executed — one availability receipt per step
  (automatable · gated · blocked, the exact wall named).
  A blocked step halts the run; the report is the
  deliverable — an honest "no" with evidence, before a
  workflow is built on a step that cannot run.

## Submission packet

`docs/SUBMISSION.md` (entry copy) · `docs/DEMO-SCRIPT.md`
(the demo walkthrough, incl. the containment moment) ·
`docs/SUBMISSION-PACKET.md` (artifact checklist + states).

## Run

    python -m pytest tests/ -q
    python -m clerk.cli run task.json [--approve-all]

Python 3.11+ · playwright · a Chromium build.
