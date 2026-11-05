# Quarantine Browser Clerk — submission copy (DRAFT, T3)

Status: draft for the Nov 7 landing; final pass at packet
assembly. Claims below are limited to what the repo's CI
evidence shows; the VM leg is stated as armed, not live.

## Title

Quarantine Browser Clerk

## Tagline

A browser agent that works in a throwaway room — every
page assessed before it's touched, every act receipted,
and the room destroyed when the task ends.

## The problem

Browser agents are one convincing page away from typing
your password into the wrong site. Prompt-level caution
doesn't fix that: the page is adversarial input, and the
agent reads it with the same eyes it acts with. Safety
has to live **below** the model — in the machinery the
model cannot talk its way past.

## What it does

Give the clerk a task ("pull the headline and lead from
this page"). It:

1. Opens a disposable browser profile (in production: a
   fresh Vultr Cloud Compute instance, destroyed after).
2. Routes every request through a per-task domain
   allowlist — deny by default, every abort receipted.
3. Assesses each page for lookalike/lure signals **before
   any interaction**: a page impersonating a known brand
   from a lookalike domain, waving a credential form and
   "session expired" language, is contained on sight —
   no credential typed, no download run, no approval even
   requested.
4. Downloads only into a per-task quarantine directory;
   nothing is executed, nothing leaves.
5. Halts consequential actions at a human-approval gate.
6. Emits a hash-chained receipt log
   (`quarantine-clerk/receipt/v1`) — the task's whole
   life, tamper-evident, replayable.
7. Destroys the profile (production: the VM) and ends.

## The signature moment

A fixture page impersonates a Vultr re-login from a
lookalike domain and tries to walk the agent through
entering its password and downloading a "verifier". The
clerk contains it at page assessment: verdict sequence
`task-start → allowed → contained-lookalike →
task-complete`. The real vultr.com, by contrast, is
pinned as a brand domain and is **not** contained —
containment needs both domain distance from an imitated
brand AND a lure signal, so the guard doesn't cry wolf
at the genuine site.

## Production execution status

The current repository now includes a controlled FastAPI web UI/API and a
per-task Docker sandbox with an allowlist-only HTTPS proxy (PR #11). GitHub
Actions still proves the browser mechanisms on its hosted runner. The web
app and Docker sandbox have **not** yet been deployed or validated on a Vultr
host, and no public App URL is claimed.

- The Docker sandbox is intended to run on a Vultr Cloud Compute host; the
  low-level `clerk/vultr_vm.py` helpers are not used by this host/container
  architecture.
- `clerk/inference.py` is an OpenAI-compatible client used for optional
  P3 vision verification; it is not yet an action planner.
- No public Vultr-hosted App URL or key-bearing cloud run is recorded.
- The D2 implementation and deployment blockers are tracked in
  [issue #9](https://github.com/timerloggedout-spec/quarantine-browser-clerk/issues/9).


## Evidence

- CI `demo-realstack` run **41807278198** — SUCCESS:
  live extraction from a real allowlisted site · the
  signature containment · the brand pin, three receipt
  chains valid, shipped as the run artifact.
- Unit + e2e suite: 8/8 (local harness + CI `ci.yml`).
- Fold-ins (T3): the switch table + availability
  pre-flight — `tests/test_foldins.py` (6 tests) and
  demo legs D (switch) + E (preflight) in
  `demo/run_realstack.py`; evidence = the fold-in PR's
  green `ci` + `demo-realstack` runs.
- Repo is public; every claim above maps to a file,
  a test, or a run named in `docs/SUBMISSION-PACKET.md`.

## Why it matters

Agents will browse on our behalf whether the machinery
is safe or not. The clerk is the shape of the safe
version: containment as architecture, not as a system
prompt — disposable compute, deny-by-default routing,
assessment before interaction, and a receipt for
everything, so a human can replay exactly what the
agent saw and did.
