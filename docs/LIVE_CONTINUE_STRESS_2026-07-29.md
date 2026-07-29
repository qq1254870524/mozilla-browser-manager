# Live Stress + All Features — 2026-07-29 (continue)

## Version
`1.10.2-v10.2`

## Results
| Suite | Result | Report |
|-------|--------|--------|
| e2e_all_features | **105/105** | `tmp/e2e_all_features.json` |
| e2e_stress_live | **43/43** | `tmp/e2e_stress_live.json` |
| recorder/tags/failover fix | **7/7** | `tmp/e2e_fix_recorder_tags.json` |
| compliance | **86/86** | |

## Fixes this round
1. **Recorder greenlet thread error** — `page.evaluate` on per-profile `BrowserWorker` (`rpa/recorder.py`); re-entrant safe `sync_bridge`
2. **RPA runner** — workflow steps on profile browser thread
3. **Failover switch empty body** — auto next same-country candidate
4. **Tags POST alias** — `POST /api/tags/profiles/{id}` (+ `/set`) besides PUT
5. **Live cookie storage_state** — browser thread when profile running

## Dual-engine stress
- Chromium + Camoufox concurrent
- Independent mihomo ports; stop one keeps the other
- Diagnose / rebind / lock / tags / batch / orphan cleanup
