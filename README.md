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

## How this project uses Vultr

- **Vultr Cloud Compute — a disposable VM per task.**
  The production sandbox is a throwaway `vhp-2c-4gb-amd`
  instance ($0.033/h) provisioned per task through the
  Vultr API, used for exactly one task, then **destroyed —
  never stopped, never reused** (`clerk/vultr_vm.py`). A
  compromised or contaminated session has nowhere to
  persist: the machine it ran on ceases to exist. The leg
  is armed in code and activates the moment the account's
  API key is enabled; until then the identical runner
  executes against a disposable local Chromium profile
  (the design's stated fallback, and what CI exercises).
- **Vultr Serverless Inference — the planner.**
  `clerk/inference.py` is an OpenAI-compatible client for
  `api.vultrinference.com/v1` (`VULTR_API_KEY` /
  `VULTR_INFERENCE_MODEL`). The model proposes browsing
  actions; every proposal still passes the route guard,
  the lookalike assessment, and the human-approval gate —
  **the guard sits below the model and is not
  LLM-bypassable**. Without a key the runner stays in
  deterministic steps mode and says so in its receipts.
- **Why Vultr fits the design:** the containment model
  wants compute that is cheap enough to throw away per
  task and an inference endpoint the planner can call
  without leaving the same cloud's trust and billing
  surface. One account, one API key, two products: the
  sandbox and the brain, with the guard between them.

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

## Submission packet

`docs/SUBMISSION.md` (entry copy) · `docs/DEMO-SCRIPT.md`
(the demo walkthrough, incl. the containment moment) ·
`docs/SUBMISSION-PACKET.md` (artifact checklist + states).

## Run

    python -m pytest tests/ -q
    python -m clerk.cli run task.json [--approve-all]

Python 3.11+ · playwright · a Chromium build.
