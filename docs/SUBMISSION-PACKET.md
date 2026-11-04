# Submission packet — Quarantine Browser Clerk (D2)

Landing target: Sat Nov 7 · wall Sun Nov 8 15:00 PT.
States as of T3 assembly (2026-11-04); an item reads
NOT_ESTABLISHED until its evidence exists.

| # | Artifact | State |
|---|---|---|
| 1 | Repo public, main green | ✅ timerloggedout-spec/quarantine-browser-clerk · PR #3 merged `2fd10df305` |
| 2 | README w/ Vultr-use section (submission requirement) | ✅ this packet's PR |
| 3 | Submission copy | ✅ DRAFT `docs/SUBMISSION.md` — final pass at landing |
| 4 | Demo script w/ ≥1 containment moment | ✅ `docs/DEMO-SCRIPT.md` (Beat 3) |
| 5 | T1 core loop proof | ✅ e2e test + CI |
| 6 | T2 signature proof (real stack) | ✅ run 41807278198 SUCCESS · artifact `realstack-receipts` |
| 7 | Vultr VM-per-task leg | ⏳ ARMED — `clerk/vultr_vm.py` raises NotProvisioned without `VULTR_API_KEY`; fires on key enablement (owner Console step) |
| 8 | Vultr Serverless Inference planner | ⏳ WIRED keyless — `clerk/inference.py`; deterministic mode receipted until the key lands |
| 9 | Demo recording | NOT_ESTABLISHED — records at landing prep (script = item 4; CI artifact = fallback footage) |
| 10 | Landing/submission form filing | NOT_ESTABLISHED — Nov 7, manager's hand w/ this packet |
| 11 | Fold-ins: switch table (P3) + availability pre-flight (P4) | ⏳ BUILT on the fold-in PR — `clerk/switchtable.py` · `clerk/preflight.py` · tests/test_foldins.py (6 tests) · demo legs D+E; lands on merge + green realstack run |

## Honesty rails for the landing

- The VM + inference legs are described as armed/wired,
  never live, until a key-bearing run exists.
- Every performance/safety claim in the copy maps to
  run 41807278198, the e2e suite, or a named file.
- Kill-criterion record: T2 was due Nov 5 EOD; the
  criterion was MET Nov 4 (run 41807278198).
