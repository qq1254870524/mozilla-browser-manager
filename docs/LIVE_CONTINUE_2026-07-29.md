# Live Continue Report — 2026-07-29

## Version
`1.10.2-v10.2`

## Fixes this round
1. **Orphan mihomo cleanup**
   - `network/mihomo.py`: `list_live_mihomo_processes` / `cleanup_orphan_mihomo` (multi-PID per port)
   - `POST /api/mihomo/cleanup-orphans`, `GET /api/mihomo/live`
   - `profiles.stop` always stops per-profile mihomo
   - `system.gc` includes mihomo orphan sweep + runtime reconcile
2. **Proxy node alias**
   - `SetProxyIn` accepts `node` **and** `node_name` (UI was silently dropping node)
3. **Cookie import alias**
   - `ImportIn` accepts `payload` **or** `cookies`
4. **Camoufox + Chromium concurrent launch**
   - Root cause: Playwright Sync API keeps an asyncio loop on the calling thread; shared ThreadPool reused that thread → Camoufox failed with *Sync API inside asyncio loop*
   - Fix: `engines/sync_bridge.py` per-profile long-lived `BrowserWorker` thread; launch/stop on same thread

## Live E2E
- File: `tmp/e2e_continue_live.json`
- **29/29 PASS** (14.45s)
- Chromium launch + JP rebind + diagnose + Camoufox after Chromium + cookie import + stop cleans mihomo

## Compliance
- 86/86 (`1.10.2-compliance`)
- OpenAPI paths: **151** (includes cleanup-orphans / live)

## Server
```bash
cd /home/baoge/Mozilla && source .venv/bin/activate
export PYTHONPATH=$PWD/app PLAYWRIGHT_BROWSERS_PATH=$PWD/runtime/browsers XDG_CACHE_HOME=$PWD/runtime/cache
setsid nohup .venv/bin/python -u -m uvicorn mozilla_manager.web:app --host 127.0.0.1 --port 17888 --log-level info >> logs/web.out 2>&1 < /dev/null &
echo $! > logs/web.pid
```
