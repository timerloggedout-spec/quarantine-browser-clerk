# Submission packet — Quarantine Browser Clerk (D2)

Landing target: Sat Nov 7 · wall Sun Nov 8 15:00 PT.
States refreshed 2026-11-05 from the public entry repo and D2 challenge record.
An item remains NOT_ESTABLISHED until its named evidence exists.

| # | Artifact / gate | State | Evidence / remaining work |
|---|---|---|---|
| 1 | Public repo, main green | ✅ | `timerloggedout-spec/quarantine-browser-clerk`; current main `457cad7213eb`; CI run [41822618113](https://github.com/timerloggedout-spec/quarantine-browser-clerk/actions/runs/41822618113) SUCCESS; post-fix CI [42129363148](https://github.com/timerloggedout-spec/quarantine-browser-clerk/actions/runs/42129363148) SUCCESS |
| 2 | README with Vultr-use / architecture section | ✅ | Updated to distinguish the intended production stack from what is actually wired |
| 3 | Submission copy | 🟡 DRAFT | `docs/SUBMISSION.md`; must be finalized after cloud deployment and URL evidence |
| 4 | Demo script with containment moment | ✅ | `docs/DEMO-SCRIPT.md`, Beat 3 |
| 5 | T1 core loop proof | ✅ | `tests/test_e2e.py::test_t1_core_loop` and CI |
| 6 | T2 signature proof | ✅ | [run 41807278198](https://github.com/timerloggedout-spec/quarantine-browser-clerk/actions/runs/41807278198) SUCCESS; real-stack receipt artifact |
| 7 | Isolated task sandbox | 🟡 IMPLEMENTED IN PR #11; NOT DEPLOYED | Per-task Docker container + internal network + allowlist-only HTTPS proxy are implemented. Vultr host provisioning, host-firewall validation, real cloud execution, and teardown evidence remain outstanding. |
| 8 | Vultr Serverless Inference planner | 🟡 PARTIAL | `clerk/inference.py` exists and is used for optional P3 vision verification; it does not generate the browsing plan. No configured inference key/model evidence. |
| 9 | Public demo recording | ✅ PUBLISHED per D2 promo record | [YouTube demo](https://www.youtube.com/watch?v=z-hkwnUFOqM), recorded as Public, 143s on 2026-11-04. The repo's CI receipt artifact remains the technical fallback evidence. |
| 10 | Public app URL + lablab submission | 🔴 NOT SUBMITTED | Web UI/API is implemented in PR #11 but not deployed. Lablab draft saved at 76%; Demo platform and App URL fields remain outstanding. |
| 11 | P3 switch table + P4 availability pre-flight | ✅ MERGED / CI GREEN | PR [#6](https://github.com/timerloggedout-spec/quarantine-browser-clerk/pull/6) merged as `d3f0ffbf03f6`; [CI 41822618113](https://github.com/timerloggedout-spec/quarantine-browser-clerk/actions/runs/41822618113) and [demo-realstack 41822618119](https://github.com/timerloggedout-spec/quarantine-browser-clerk/actions/runs/41822618119) SUCCESS |
| 12 | GitHub App identity (AppID) | 🟡 PACKAGE PREPARED; NOT PROVISIONED | Moniker `Proctor · QuarantineBrowserClerk` issued. Non-secret manifest package merged to termux-monorepo master in [PR #5022](https://github.com/timerloggedout-spec/termux-monorepo/pull/5022). Still requires owner-session Create confirmation, installation consent for this repo only, AppID-lane conversion, 0600 custody, and API verification. |
| 13 | Provider-dispatch provenance | 🟡 NO EXTERNAL BUILD DISPATCH CLAIMED | D2's recorded route was command-dispatch. The current chat has no linked Agent Swarm; no provider session is claimed for this maintenance. PR #8 records this direct repository change explicitly. |

## Honesty rails for the landing

- Do not describe the VM helpers as a live Vultr sandbox until a real
  key-bearing run proves provision → execution → result collection → destroy.
- Do not describe the inference client as an action planner until it emits
  bounded structured plans and the runner validates every action.
- The current local/Actions browser profile is not a Vultr-hosted sandbox.
- Keep D2 submission status separate from AMD AI League match artifacts.
- Keep API keys, private keys, client secrets, and installation tokens out of
  Git, chat, comments, screenshots, and public demo artifacts.
- D2 lablab submission remains unfiled until the App URL and Demo platform
  fields are populated and the owner confirms the final submission.
