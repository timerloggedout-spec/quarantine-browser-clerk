# Quarantine Browser Clerk — staging tree

D2 (Vultr Agent Rush, C1·B) build, staged by the Swarm
execution seat ahead of the repo landing
(timerloggedout-spec/quarantine-browser-clerk, via the AppID
lane). On the repo ref's arrival this tree becomes the first
commit; the Vultr VM-per-task leg and the inference-driven
planner slot into the seams named below.

## What is proven in this tree (local harness, playwright)

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

## Seams for the live build

- **Vultr VM-per-task**: the runner's sandbox is the local
  disposable profile today (the spec's stated fallback);
  the VM leg provisions a throwaway vhp-2c-4gb-amd per task
  via the Vultr API and runs this same runner inside it,
  destroying the VM after — never stopping it.
- **Vultr Serverless Inference** (`clerk/inference.py`):
  OpenAI-compatible client for api.vultrinference.com/v1;
  key from `VULTR_API_KEY`, model from
  `VULTR_INFERENCE_MODEL`. The LLM planner proposes actions;
  every proposal still passes the route guard, the
  lookalike assessment, and the approval gate — the guard
  is not LLM-bypassable. Without a key the runner stays in
  deterministic steps mode and says so in the receipts.

## Run

    python -m pytest tests/ -q
    python -m clerk.cli run task.json [--approve-all]

Python 3.11+ · playwright · a Chromium build.
