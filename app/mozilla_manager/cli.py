from __future__ import annotations

# Windows cp936/gbk consoles blow up on emoji node names (🇺🇸…); force UTF-8 I/O.
try:
    import sys as _sys
    for _s in (_sys.stdout, _sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
except Exception:
    pass

import json
import sys
from pathlib import Path

import typer
from rich import print as rprint
from rich.table import Table

_APP_DIR = Path(__file__).resolve().parents[1]
if str(_APP_DIR) not in sys.path:
    sys.path.insert(0, str(_APP_DIR))

from mozilla_manager.doctor import run_doctor
from mozilla_manager.env_packs import binding_from_country, detect_egress_country, seed_packs
from mozilla_manager.engines import get_launcher
from mozilla_manager.launch_gate import preflight, write_check_page
from mozilla_manager.models import ChromiumPatch, EngineKind, EnvBinding, GeoLocation, ProxyConfig
from mozilla_manager.network.mihomo import allocate_port, start_mihomo, status_mihomo, stop_mihomo
from mozilla_manager.network.subscription import import_subscription, list_subscriptions
from mozilla_manager.paths import ROOT, ensure_layout
from mozilla_manager.runtime_manifest import read_manifest, write_manifest
from mozilla_manager.runtime_registry import list_running
from mozilla_manager.snapshots import export_profile_zip, snapshot_profile
from mozilla_manager.store import ProfileStore

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Mozilla Browser Manager — v1–v5 (ROOT=/home/baoge/Mozilla)",
)


# ----- system -----
@app.command("root")
def show_root() -> None:
    ensure_layout()
    seed_packs()
    rprint(f"[bold green]ROOT[/] {ROOT}")
    rprint(r"[dim]Windows:[/] \\wsl.localhost\Ubuntu\home\baoge\Mozilla")


@app.command("doctor")
def doctor_cmd() -> None:
    """P0: environment self-check + write runtime manifest."""
    report = run_doctor()
    for c in report["checks"]:
        flag = "OK" if c["ok"] else c["level"].upper()
        color = "green" if c["ok"] else ("yellow" if c["level"] == "warn" else "red")
        rprint(f"[{color}]{flag:5}[/] {c['name']}: {c['detail']}")
    rprint(f"\nmanifest -> runtime/manifests/current.json")
    rprint(f"doctor overall: {'[green]PASS[/]' if report['ok'] else '[red]FAIL[/]'}")
    raise typer.Exit(0 if report["ok"] else 1)


@app.command("engines")
def engines_info() -> None:
    rprint(
        """
[bold]Kernels[/]
  camoufox       https://github.com/daijro/camoufox
  pw_chromium    https://github.com/microsoft/playwright

[bold]Chromium patches (free combo)[/]
  patchright     https://github.com/Kaliiiiiiiiii-Vinyzu/patchright
  rebrowser      https://github.com/rebrowser/rebrowser-patches
  none
"""
    )


@app.command("manifest")
def manifest_cmd(refresh: bool = typer.Option(False, "--refresh")) -> None:
    data = write_manifest() if refresh or not read_manifest() else read_manifest()
    rprint(json.dumps(data, ensure_ascii=False, indent=2))


# ----- profiles CRUD -----
@app.command("list")
def list_profiles() -> None:
    rows = ProfileStore().list()
    table = Table(title="Profiles")
    for col in ("id", "name", "engine", "patch", "proxy", "tz", "locale"):
        table.add_column(col)
    for p in rows:
        proxy = p.proxy.mode
        if p.proxy.mihomo_port:
            proxy += f":{p.proxy.mihomo_port}"
        table.add_row(p.id, p.name, p.engine.value, p.chromium_patch.value, proxy, p.env.timezone_id, p.env.locale)
    rprint(table)


@app.command("create")
def create_profile(
    name: str = typer.Option(..., "--name", "-n"),
    engine: str = typer.Option("pw_chromium", "--engine", "-e"),
    patch: str = typer.Option("patchright", "--patch"),
    socks5: str = typer.Option("", "--socks5"),
    mihomo_port: int = typer.Option(0, "--mihomo-port"),
    sub: str = typer.Option("default", "--sub", help="subscription name for mihomo"),
    country: str = typer.Option("", "--country"),
    node_name: str = typer.Option("", "--node", help="subscription node title → auto country"),
    fingerprint_id: str = typer.Option("", "--fp", help="fingerprint template id"),
    timezone_id: str = typer.Option("", "--tz"),
    locale: str = typer.Option(""),
    lat: float = typer.Option(0.0, "--lat"),
    lon: float = typer.Option(0.0, "--lon"),
    auto_port: bool = typer.Option(False, "--auto-port", help="allocate mihomo port from profile id"),
) -> None:
    from mozilla_manager.modules.profiles import create_profile as _create
    from mozilla_manager.fingerprints import seed_fingerprints
    from mozilla_manager.env_packs import seed_packs

    seed_packs()
    seed_fingerprints()
    prof = _create(
        name=name,
        engine=engine,
        patch=patch,
        socks5=socks5,
        mihomo_port=mihomo_port,
        sub=sub,
        country=country,
        timezone_id=timezone_id,
        locale=locale,
        lat=lat,
        lon=lon,
        auto_port=auto_port,
        node_name=node_name,
        fingerprint_id=fingerprint_id,
    )
    rprint(f"[green]created[/] {prof['id']}")
    rprint(f"  dir    = {prof['user_data_dir']}")
    rprint(f"  engine = {prof['engine']} / {prof['chromium_patch']}")
    rprint(f"  proxy  = {prof['proxy']}")
    env = prof.get('env') or {}
    fp = (env.get('fingerprint') or {}).get('template_id')
    rprint(f"  env    = {env.get('timezone_id')} | {env.get('locale')} | fp={fp}")
    if prof.get('meta', {}).get('bound_node'):
        rprint(f"  node   = {prof['meta']['bound_node']} → {prof['meta'].get('expected_country')}")



@app.command("delete")
def delete_profile(profile_id: str, wipe: bool = typer.Option(True, "--wipe/--keep-files")) -> None:
    # stop if running
    try:
        get_launcher(ProfileStore().get(profile_id)).stop(profile_id)
    except Exception:
        pass
    ProfileStore().delete(profile_id, wipe_files=wipe)
    rprint(f"[yellow]deleted[/] {profile_id}")


@app.command("show")
def show_profile(profile_id: str) -> None:
    rprint(json.dumps(ProfileStore().get(profile_id).model_dump(mode="json"), ensure_ascii=False, indent=2))


@app.command("set-proxy")
def set_proxy(
    profile_id: str,
    mode: str = typer.Option(..., "--mode", help="none|socks5|mihomo"),
    socks5: str = typer.Option("", "--socks5"),
    mihomo_port: int = typer.Option(0, "--mihomo-port"),
    node: str = typer.Option("", "--node"),
    auto_port: bool = typer.Option(False, "--auto-port"),
) -> None:
    port = mihomo_port
    if auto_port:
        port = allocate_port(profile_id)
    proxy = ProxyConfig(
        mode=mode,
        socks5=socks5 or None,
        mihomo_port=port or None,
        node_name=node or None,
    )
    prof = ProfileStore().update(profile_id, proxy=proxy)
    rprint(f"[green]proxy[/] {prof.id} -> {prof.proxy.model_dump()}")


@app.command("bind-country")
def bind_country(profile_id: str, country: str) -> None:
    env = binding_from_country(country)
    store = ProfileStore()
    meta = dict(store.get(profile_id).meta)
    meta["expected_country"] = country.upper()
    prof = store.update(profile_id, env=env, meta=meta)
    rprint(f"[green]bound[/] {prof.id} <- {country.upper()} ({prof.env.timezone_id})")


@app.command("bind-from-ip")
def bind_from_ip(profile_id: str, use_proxy: bool = typer.Option(True, "--use-proxy/--no-proxy")) -> None:
    store = ProfileStore()
    prof = store.get(profile_id)
    proxy_url = None
    if use_proxy:
        if prof.proxy.mode == "socks5" and prof.proxy.socks5:
            proxy_url = prof.proxy.socks5 if "://" in prof.proxy.socks5 else f"socks5://{prof.proxy.socks5}"
        elif prof.proxy.mode == "mihomo" and prof.proxy.mihomo_port:
            proxy_url = f"socks5://127.0.0.1:{prof.proxy.mihomo_port}"
    info = detect_egress_country(proxy_url)
    country = (info.get("country") or "").upper()
    rprint(f"egress ip={info.get('ip')} country={country} tz={info.get('timezone')}")
    if not country:
        raise typer.Exit(2)
    env = binding_from_country(country)
    if info.get("timezone"):
        env.timezone_id = str(info["timezone"])
    if info.get("latitude") and info.get("longitude"):
        env.geolocation = GeoLocation(latitude=float(info["latitude"]), longitude=float(info["longitude"]))
    meta = dict(prof.meta)
    meta["expected_country"] = country
    meta["last_egress"] = {k: info.get(k) for k in ("ip", "country", "city", "timezone")}
    store.update(profile_id, env=env, meta=meta)
    rprint(f"[green]bound from IP[/] {profile_id}")


# ----- nodes / mihomo -----
@app.command("sub-import")
def sub_import(url: str = typer.Option(..., "--url"), name: str = typer.Option("default", "--name")) -> None:
    meta = import_subscription(url, name=name)
    rprint(f"[green]imported[/] {json.dumps(meta, ensure_ascii=False, indent=2)}")


@app.command("sub-list")
def sub_list() -> None:
    rows = list_subscriptions()
    if not rows:
        rprint("[dim]no subscriptions — use sub-import --url ...[/]")
        return
    for r in rows:
        rprint(f"- {r.get('name')} host={r.get('url_host')} at={r.get('imported_at')} bytes={r.get('bytes')}")


@app.command("mihomo-start")
def mihomo_start_cmd(
    profile_id: str = typer.Option("", "--profile"),
    port: int = typer.Option(0, "--port"),
    sub: str = typer.Option("default", "--sub"),
    node: str = typer.Option("", "--node"),
) -> None:
    if profile_id:
        prof = ProfileStore().get(profile_id)
        port = port or prof.proxy.mihomo_port or allocate_port(profile_id)
        # persist port on profile
        ProfileStore().update(
            profile_id,
            proxy=ProxyConfig(mode="mihomo", mihomo_port=port, node_name=node or prof.proxy.node_name or sub),
        )
    if not port:
        rprint("[red]need --port or --profile[/]")
        raise typer.Exit(2)
    res = start_mihomo(port, subscription_name=sub, node_name=node or None)
    rprint(res)
    if not res.get("ok"):
        raise typer.Exit(1)


@app.command("mihomo-stop")
def mihomo_stop_cmd(port: int = typer.Option(..., "--port")) -> None:
    rprint(stop_mihomo(port))


@app.command("mihomo-status")
def mihomo_status_cmd() -> None:
    rprint(json.dumps(status_mihomo(), ensure_ascii=False, indent=2))


# ----- launch lifecycle -----
@app.command("check")
def check_cmd(
    profile_id: str,
    require_proxy: bool = typer.Option(False, "--require-proxy"),
) -> None:
    """Launch gate preflight (no browser)."""
    prof = ProfileStore().get(profile_id)
    report = preflight(prof, require_proxy=require_proxy)
    rprint(json.dumps(report, ensure_ascii=False, indent=2))
    if not report["ok"]:
        raise typer.Exit(1)


@app.command("launch")
def launch_profile(
    profile_id: str,
    headless: bool = typer.Option(False, "--headless"),
    skip_gate: bool = typer.Option(False, "--skip-gate"),
    require_proxy: bool = typer.Option(False, "--require-proxy"),
    no_check_page: bool = typer.Option(False, "--no-check-page"),
    start_mihomo_flag: bool = typer.Option(False, "--start-mihomo"),
) -> None:
    store = ProfileStore()
    prof = store.get(profile_id)

    if start_mihomo_flag or prof.proxy.mode == "mihomo":
        port = prof.proxy.mihomo_port or allocate_port(profile_id)
        if not prof.proxy.mihomo_port:
            prof = store.update(profile_id, proxy=ProxyConfig(mode="mihomo", mihomo_port=port, node_name=prof.proxy.node_name))
        sub = prof.proxy.node_name or "default"
        res = start_mihomo(port, subscription_name=sub if sub != "" else "default")
        if not res.get("ok"):
            rprint(f"[yellow]mihomo start[/] {res}")

    if not skip_gate:
        report = preflight(prof, require_proxy=require_proxy)
        if report["warnings"]:
            for w in report["warnings"]:
                rprint(f"[yellow]warn[/] {w}")
        if not report["ok"]:
            rprint(f"[red]launch gate blocked[/] {report['blocks']}")
            raise typer.Exit(2)
        rprint("[green]launch gate PASS[/]")

    launcher = get_launcher(prof)
    result = launcher.launch(prof, headless=headless, open_check=not no_check_page)
    if not result.ok:
        rprint(f"[red]FAIL[/] {result.message}")
        raise typer.Exit(1)
    rprint(f"[green]OK[/] {result.message}")
    rprint("Press Enter to stop...")
    try:
        input()
    finally:
        launcher.stop(profile_id)
        rprint("[yellow]stopped[/]")


@app.command("stop")
def stop_profile(profile_id: str) -> None:
    prof = ProfileStore().get(profile_id)
    get_launcher(prof).stop(profile_id)
    rprint(f"[yellow]stopped[/] {profile_id}")


@app.command("ps")
def ps_cmd() -> None:
    rprint(json.dumps(list_running(), ensure_ascii=False, indent=2))


# ----- backup -----
@app.command("snapshot")
def snapshot_cmd(profile_id: str, note: str = typer.Option("", "--note")) -> None:
    path = snapshot_profile(profile_id, note=note)
    rprint(f"[green]snapshot[/] {path}")


@app.command("export")
def export_cmd(profile_id: str) -> None:
    path = export_profile_zip(profile_id)
    rprint(f"[green]export zip[/] {path}")


@app.command("write-check-page")
def write_check_page_cmd(profile_id: str) -> None:
    uri = write_check_page(ProfileStore().get(profile_id))
    rprint(uri)


@app.command("serve")
def serve_cmd(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(17888, "--port"),
) -> None:
    """Start local AdsPower-style Web UI (ROOT-locked)."""
    ensure_layout()
    seed_packs()
    import uvicorn
    rprint(f"[bold green]Web UI[/] http://{host}:{port}/  ROOT={ROOT}")
    uvicorn.run("mozilla_manager.web:app", host=host, port=port, reload=False)



# ----- v2 templates / sessions -----
@app.command("packs")
def packs_cmd() -> None:
    from mozilla_manager.env_packs import list_packs, seed_packs
    seed_packs()
    rprint(json.dumps(list_packs(), ensure_ascii=False, indent=2))


@app.command("fingerprints")
def fingerprints_cmd() -> None:
    from mozilla_manager.fingerprints import list_fingerprints, seed_fingerprints
    seed_fingerprints()
    rprint(json.dumps(list_fingerprints(), ensure_ascii=False, indent=2))


@app.command("recommend-node")
def recommend_node_cmd(
    node: str = typer.Argument(..., help="subscription node title"),
    jitter: bool = typer.Option(True, "--jitter/--no-jitter"),
) -> None:
    from mozilla_manager.env_packs import recommend_from_node
    rprint(json.dumps(recommend_from_node(node, jitter=jitter), ensure_ascii=False, indent=2))


@app.command("bind-node")
def bind_node_cmd(
    profile_id: str,
    node: str = typer.Option(..., "--node", "-N"),
    sub: str = typer.Option("default", "--sub"),
    auto_port: bool = typer.Option(True, "--auto-port/--no-auto-port"),
    fingerprint: str = typer.Option("", "--fp"),
) -> None:
    from mozilla_manager.modules.templates import bind_node_to_profile
    res = bind_node_to_profile(
        profile_id,
        node_name=node,
        sub=sub,
        auto_port=auto_port,
        fingerprint_id=fingerprint,
    )
    rprint(json.dumps(res, ensure_ascii=False, indent=2))


@app.command("set-fingerprint")
def set_fp_cmd(profile_id: str, template: str = typer.Option(..., "--template", "-t")) -> None:
    from mozilla_manager.modules.templates import set_fingerprint
    rprint(json.dumps(set_fingerprint(profile_id, template), ensure_ascii=False, indent=2))


@app.command("session-backup")
def session_backup_cmd(
    profile_id: str,
    label: str = typer.Option("", "--label"),
    full: bool = typer.Option(False, "--full", help="include full user_data copy"),
) -> None:
    from mozilla_manager.modules.sessions import backup_session
    res = backup_session(profile_id, label=label, include_user_data=full)
    rprint(json.dumps(res, ensure_ascii=False, indent=2))


@app.command("session-restore")
def session_restore_cmd(
    profile_id: str,
    ts: str = typer.Option(..., "--ts"),
    no_user_data: bool = typer.Option(False, "--no-user-data"),
) -> None:
    from mozilla_manager.modules.sessions import restore_session
    res = restore_session(profile_id, ts, restore_user_data=not no_user_data)
    rprint(json.dumps(res, ensure_ascii=False, indent=2))


@app.command("session-list")
def session_list_cmd(profile_id: str = typer.Argument("")) -> None:
    from mozilla_manager.modules.sessions import list_sessions
    rprint(json.dumps(list_sessions(profile_id or None), ensure_ascii=False, indent=2))




# ----- v3: db / consistency / nodes / health / extensions / matrix -----
@app.command("consistency")
def consistency_cmd(repair: bool = typer.Option(False, "--repair")) -> None:
    from mozilla_manager.consistency import check_consistency
    rprint(json.dumps(check_consistency(repair=repair), ensure_ascii=False, indent=2))


@app.command("db-init")
def db_init_cmd() -> None:
    from mozilla_manager import db
    from mozilla_manager.store import ProfileStore
    path = db.init_db()
    n = 0
    for prof in ProfileStore().list():
        db.upsert_profile_row(prof)
        n += 1
    rprint(f"[green]db[/] {path} synced profiles={n}")


@app.command("audit")
def audit_cmd(limit: int = typer.Option(50, "--limit"), profile_id: str = typer.Option("", "--profile")) -> None:
    from mozilla_manager import db
    rows = db.list_audit(limit=limit, profile_id=profile_id or None)
    rprint(json.dumps(rows, ensure_ascii=False, indent=2))


@app.command("gc")
def gc_cmd(hours: float = typer.Option(24.0, "--hours"), dry: bool = typer.Option(False, "--dry-run")) -> None:
    from mozilla_manager.tmp_gc import gc_tmp
    rprint(json.dumps(gc_tmp(max_age_hours=hours, dry_run=dry), ensure_ascii=False, indent=2))


@app.command("matrix")
def matrix_cmd() -> None:
    from mozilla_manager.engines.matrix import list_matrix
    rprint(json.dumps(list_matrix(), ensure_ascii=False, indent=2))


@app.command("nodes")
def nodes_cmd(sub: str = typer.Option("default", "--sub")) -> None:
    from mozilla_manager.modules.nodes_svc import list_nodes_enriched
    rprint(json.dumps(list_nodes_enriched(sub), ensure_ascii=False, indent=2))


@app.command("nodes-groups")
def nodes_groups_cmd(sub: str = typer.Option("default", "--sub")) -> None:
    from mozilla_manager.modules.nodes_svc import group_by_country
    rprint(json.dumps(group_by_country(sub), ensure_ascii=False, indent=2))


@app.command("fav-add")
def fav_add_cmd(node: str = typer.Option(..., "--node"), sub: str = typer.Option("default", "--sub")) -> None:
    from mozilla_manager.modules.nodes_svc import favorite_add
    rprint(favorite_add(sub, node))


@app.command("fav-list")
def fav_list_cmd(sub: str = typer.Option("", "--sub")) -> None:
    from mozilla_manager.modules.nodes_svc import favorites
    rprint(json.dumps(favorites(sub or None), ensure_ascii=False, indent=2))


@app.command("speedtest")
def speedtest_cmd(
    sub: str = typer.Option("default", "--sub"),
    limit: int = typer.Option(0, "--limit"),
    workers: int = typer.Option(16, "--workers"),
) -> None:
    from mozilla_manager.modules.nodes_svc import speedtest
    rprint(json.dumps(speedtest(sub, limit=limit, workers=workers), ensure_ascii=False, indent=2))


@app.command("sub-refresh")
def sub_refresh_cmd(name: str = typer.Option("default", "--name"), due: bool = typer.Option(False, "--due"), force: bool = typer.Option(False, "--force")) -> None:
    from mozilla_manager.modules import subscriptions as s
    if due:
        rprint(json.dumps(s.refresh_due(force=force), ensure_ascii=False, indent=2))
    else:
        rprint(json.dumps(s.refresh_sub(name), ensure_ascii=False, indent=2))


@app.command("health-egress")
def health_egress_cmd(profile_id: str) -> None:
    from mozilla_manager.modules.health import check_egress
    rprint(json.dumps(check_egress(profile_id), ensure_ascii=False, indent=2))


@app.command("health-rebind")
def health_rebind_cmd(profile_id: str, force: bool = typer.Option(False, "--force")) -> None:
    from mozilla_manager.modules.health import rebind_from_egress
    rprint(json.dumps(rebind_from_egress(profile_id, only_if_mismatch=not force), ensure_ascii=False, indent=2))


@app.command("recommend-ip")
def recommend_ip_cmd(proxy: str = typer.Option("", "--proxy")) -> None:
    from mozilla_manager.modules.health import recommend_from_ip
    rprint(json.dumps(recommend_from_ip(proxy or None), ensure_ascii=False, indent=2))


@app.command("extensions")
def extensions_cmd() -> None:
    from mozilla_manager.modules.extensions import list_extensions
    rprint(json.dumps(list_extensions(), ensure_ascii=False, indent=2))


@app.command("ext-set")
def ext_set_cmd(profile_id: str, exts: str = typer.Option("", "--ids", help="comma-separated extension ids")) -> None:
    from mozilla_manager.modules.extensions import set_profile_extensions
    ids = [x.strip() for x in exts.split(",") if x.strip()]
    rprint(json.dumps(set_profile_extensions(profile_id, ids), ensure_ascii=False, indent=2))


@app.command("restore-last-session")
def restore_last_cmd(headless: bool = typer.Option(False, "--headless")) -> None:
    from mozilla_manager.modules.profiles import restore_last_session
    rprint(json.dumps(restore_last_session(headless=headless), ensure_ascii=False, indent=2))




# ----- v4 cookies / login / timetravel / failover / privacy -----
@app.command("cookie-import")
def cookie_import_cmd(
    profile_id: str,
    file: str = typer.Option("", "--file", help="JSON file path under ROOT or absolute under ROOT"),
    data: str = typer.Option("", "--data", help="raw JSON or Base64"),
    merge: bool = typer.Option(True, "--merge/--replace"),
) -> None:
    from mozilla_manager.modules import cookies as c
    from mozilla_manager.paths import safe_resolve
    payload: object
    if file:
        payload = safe_resolve(file).read_text(encoding="utf-8")
    elif data:
        payload = data
    else:
        rprint("[red]need --file or --data[/]")
        raise typer.Exit(2)
    rprint(json.dumps(c.import_cookies(profile_id, payload, merge=merge), ensure_ascii=False, indent=2))


@app.command("cookie-export")
def cookie_export_cmd(
    profile_id: str,
    fmt: str = typer.Option("json", "--fmt"),
) -> None:
    from mozilla_manager.modules import cookies as c
    rprint(json.dumps(c.export_cookies(profile_id, fmt=fmt), ensure_ascii=False, indent=2))


@app.command("login-watch")
def login_watch_cmd(
    profile_id: str,
    urls: str = typer.Option(..., "--urls", help="comma-separated URLs"),
    hours: float = typer.Option(24.0, "--hours"),
) -> None:
    from mozilla_manager.modules.login_health import set_watch_targets
    ul = [u.strip() for u in urls.split(",") if u.strip()]
    rprint(json.dumps(set_watch_targets(profile_id, ul, interval_hours=hours), ensure_ascii=False, indent=2))


@app.command("login-check")
def login_check_cmd(profile_id: str) -> None:
    from mozilla_manager.modules.login_health import check_login
    rprint(json.dumps(check_login(profile_id), ensure_ascii=False, indent=2))


@app.command("tt-create")
def tt_create_cmd(profile_id: str, label: str = typer.Option("", "--label"), full: bool = typer.Option(False, "--full")) -> None:
    from mozilla_manager.modules.timetravel import create_restore_point
    rprint(json.dumps(create_restore_point(profile_id, label=label, include_user_data=full), ensure_ascii=False, indent=2))


@app.command("tt-list")
def tt_list_cmd(profile_id: str) -> None:
    from mozilla_manager.modules.timetravel import list_points
    rprint(json.dumps(list_points(profile_id), ensure_ascii=False, indent=2))


@app.command("tt-rollback")
def tt_rollback_cmd(profile_id: str, ts: str = typer.Option(..., "--ts")) -> None:
    from mozilla_manager.modules.timetravel import rollback
    rprint(json.dumps(rollback(profile_id, ts), ensure_ascii=False, indent=2))


@app.command("node-switch")
def node_switch_cmd(profile_id: str, node: str = typer.Option(..., "--node"), rebind: bool = typer.Option(True, "--rebind/--no-rebind")) -> None:
    from mozilla_manager.modules.failover import switch_node_live
    rprint(json.dumps(switch_node_live(profile_id, node, rebind_env=rebind), ensure_ascii=False, indent=2))


@app.command("failover")
def failover_cmd(profile_id: str, no_check: bool = typer.Option(False, "--no-check")) -> None:
    from mozilla_manager.modules.failover import auto_failover
    rprint(json.dumps(auto_failover(profile_id, check_ip=not no_check), ensure_ascii=False, indent=2))


@app.command("privacy-set")
def privacy_set_cmd(
    profile_id: str,
    webrtc: str = typer.Option("disable", "--webrtc"),
    doh: str = typer.Option("secure", "--doh"),
    doh_url: str = typer.Option("https://cloudflare-dns.com/dns-query", "--doh-url"),
) -> None:
    from mozilla_manager.store import ProfileStore
    store = ProfileStore()
    prof = store.get(profile_id)
    meta = dict(prof.meta)
    meta["webrtc_mode"] = webrtc
    meta["doh_mode"] = doh
    meta["doh_template"] = doh_url
    store.update(profile_id, meta=meta)
    rprint(f"[green]privacy[/] webrtc={webrtc} doh={doh}")


@app.command("export-incr")
def export_incr_cmd(profile_id: str) -> None:
    from mozilla_manager.snapshots import export_profile_zip_incremental
    path = export_profile_zip_incremental(profile_id)
    rprint(f"[green]incremental export[/] {path}")


@app.command("nodes-preferred")
def nodes_preferred_cmd(sub: str = typer.Option("default", "--sub"), country: str = typer.Option("", "--country")) -> None:
    from mozilla_manager.modules.nodes_svc import preferred_by_country
    rprint(json.dumps(preferred_by_country(sub, country=country or None), ensure_ascii=False, indent=2))


@app.command("migrate-tab")
def migrate_tab_cmd(
    url: str = typer.Option(..., "--url"),
    target: str = typer.Option(..., "--target"),
    open_now: bool = typer.Option(False, "--open"),
) -> None:
    from mozilla_manager.api.routes.migrate import migrate, MigrateIn
    # call logic directly
    from mozilla_manager.store import ProfileStore
    from mozilla_manager import db
    store = ProfileStore()
    t = store.get(target)
    meta = dict(t.meta)
    tabs = list(meta.get("tabs") or [])
    if url not in tabs:
        tabs.append(url)
    meta["tabs"] = tabs
    store.update(target, meta=meta)
    db.audit("tab_migrate", target, {"url": url})
    rprint(json.dumps({"ok": True, "target": target, "tabs": tabs}, ensure_ascii=False, indent=2))




# ----- v5 runtime/nodes + turnstile -----
@app.command("sub-switch")
def sub_switch_cmd(name: str = typer.Argument(...), update_profiles: bool = typer.Option(False, "--update-profiles")) -> None:
    from mozilla_manager.modules.subscriptions import switch_sub
    rprint(json.dumps(switch_sub(name, update_profiles=update_profiles), ensure_ascii=False, indent=2))


@app.command("sub-active")
def sub_active_cmd() -> None:
    from mozilla_manager.modules.subscriptions import get_active, runtime_status
    rprint(json.dumps(runtime_status(), ensure_ascii=False, indent=2))


@app.command("sub-export")
def sub_export_cmd(
    name: str = typer.Option("", "--name"),
    fmt: str = typer.Option("zip", "--fmt", help="zip|json|yaml|jsonl"),
) -> None:
    from mozilla_manager.modules.subscriptions import export_sub
    rprint(json.dumps(export_sub(name or None, fmt=fmt), ensure_ascii=False, indent=2))


@app.command("sub-import-file")
def sub_import_file_cmd(
    path: str = typer.Option(..., "--path"),
    name: str = typer.Option("imported", "--name"),
) -> None:
    from mozilla_manager.modules.subscriptions import import_nodes_file
    rprint(json.dumps(import_nodes_file(path, name=name), ensure_ascii=False, indent=2))


@app.command("nodes-migrate")
def nodes_migrate_cmd() -> None:
    from mozilla_manager.network.node_store import migrate_legacy_to_runtime
    rprint(json.dumps(migrate_legacy_to_runtime(), ensure_ascii=False, indent=2))


@app.command("turnstile-vendor")
def turnstile_vendor_cmd() -> None:
    from mozilla_manager.modules.turnstile import ensure_vendor
    rprint(json.dumps(ensure_vendor(), ensure_ascii=False, indent=2))


@app.command("turnstile-solve")
def turnstile_solve_cmd(
    profile_id: str,
    url: str = typer.Option(..., "--url"),
    headless: bool = typer.Option(False, "--headless"),
    timeout: float = typer.Option(60.0, "--timeout"),
) -> None:
    from mozilla_manager.modules.turnstile import solve_in_profile
    rprint(json.dumps(solve_in_profile(profile_id, url, headless=headless, timeout=timeout), ensure_ascii=False, indent=2))



# ----- v6 stealth / TLS / net-quality -----
@app.command("stealth-show")
def stealth_show_cmd(profile_id: str, full: bool = typer.Option(False, "--full")) -> None:
    from mozilla_manager.modules import stealth_svc
    r = stealth_svc.get_bundle(profile_id, ensure=True)
    if not full:
        r.pop("bundle", None)
    rprint(json.dumps(r, ensure_ascii=False, indent=2))


@app.command("stealth-regen")
def stealth_regen_cmd(
    profile_id: str,
    tls: str = typer.Option("", "--tls"),
) -> None:
    from mozilla_manager.modules import stealth_svc
    rprint(json.dumps(stealth_svc.regenerate(profile_id, tls_profile=tls or None), ensure_ascii=False, indent=2))


@app.command("stealth-tls")
def stealth_tls_cmd(profile_id: str, tls_profile: str = typer.Argument(...)) -> None:
    from mozilla_manager.modules import stealth_svc
    rprint(json.dumps(stealth_svc.set_tls(profile_id, tls_profile), ensure_ascii=False, indent=2))


@app.command("stealth-doh")
def stealth_doh_cmd(
    profile_id: str,
    mode: str = typer.Option("secure", "--mode"),
    template: str = typer.Option("https://cloudflare-dns.com/dns-query", "--template"),
    servers: str = typer.Option("", "--servers", help="space-separated DoH URLs"),
    force: bool = typer.Option(True, "--force/--no-force"),
) -> None:
    from mozilla_manager.modules import stealth_svc
    srv = [x for x in servers.split() if x] or None
    rprint(json.dumps(stealth_svc.set_doh(profile_id, mode=mode, template=template, servers=srv, force=force), ensure_ascii=False, indent=2))


@app.command("stealth-entropy")
def stealth_entropy_cmd(profile_id: str = typer.Argument("")) -> None:
    from mozilla_manager.modules import stealth_svc
    rprint(json.dumps(stealth_svc.entropy_report(profile_id or None), ensure_ascii=False, indent=2))


@app.command("stealth-collision")
def stealth_collision_cmd(limit: int = typer.Option(30, "--limit")) -> None:
    from mozilla_manager.modules import stealth_svc
    rprint(json.dumps(stealth_svc.collision_report(limit=limit), ensure_ascii=False, indent=2))


@app.command("tls-profiles")
def tls_profiles_cmd() -> None:
    from mozilla_manager.modules import stealth_svc
    rprint(json.dumps(stealth_svc.tls_profiles(), ensure_ascii=False, indent=2))


@app.command("net-quality")
def net_quality_cmd(profile_id: str, samples: int = typer.Option(5, "--samples")) -> None:
    from mozilla_manager.modules import stealth_svc
    rprint(json.dumps(stealth_svc.net_quality_for_profile(profile_id, samples=samples), ensure_ascii=False, indent=2))


@app.command("geo-strict")
def geo_strict_cmd(profile_id: str, enable: bool = typer.Option(True, "--enable/--disable")) -> None:
    from mozilla_manager.store import ProfileStore
    store = ProfileStore()
    prof = store.get(profile_id)
    meta = dict(prof.meta)
    meta["geo_match_strict"] = enable
    store.update(profile_id, meta=meta)
    rprint(json.dumps({"ok": True, "profile_id": profile_id, "geo_match_strict": enable}, ensure_ascii=False, indent=2))



# ----- v7 RPA / 2FA / batch / diagnose / migrate / media / global -----
@app.command("batch-create")
def batch_create_cmd(
    country: str = typer.Option(..., "--country", "-c"),
    count: int = typer.Option(5, "--count", "-n"),
    prefix: str = typer.Option("", "--prefix"),
    group: str = typer.Option("", "--group"),
    engine: str = typer.Option("pw_chromium", "--engine"),
    patch: str = typer.Option("patchright", "--patch"),
    sub: str = typer.Option("default", "--sub"),
) -> None:
    from mozilla_manager.modules import batch_svc
    rprint(json.dumps(batch_svc.batch_create(country=country, count=count, name_prefix=prefix, group=group, engine=engine, patch=patch, sub=sub), ensure_ascii=False, indent=2))


@app.command("rpa-list")
def rpa_list_cmd() -> None:
    from mozilla_manager.rpa.store import list_workflows
    rprint(json.dumps(list_workflows(), ensure_ascii=False, indent=2))


@app.command("rpa-save")
def rpa_save_cmd(
    name: str = typer.Option(..., "--name"),
    profile_id: str = typer.Option("", "--profile"),
    steps_json: str = typer.Option(..., "--steps", help="JSON array of steps"),
    wf_id: str = typer.Option("", "--id"),
) -> None:
    from mozilla_manager.rpa.store import save_workflow
    steps = json.loads(steps_json)
    doc = save_workflow({"id": wf_id or name, "name": name, "profile_id": profile_id or None, "steps": steps})
    rprint(json.dumps(doc, ensure_ascii=False, indent=2))


@app.command("rpa-run")
def rpa_run_cmd(
    wf_id: str,
    profile_id: str = typer.Option("", "--profile"),
    headless: bool = typer.Option(True, "--headless/--headed"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    from mozilla_manager.rpa.runner import run_workflow
    rprint(json.dumps(run_workflow(wf_id, profile_id=profile_id or None, headless=headless, dry_run=dry_run), ensure_ascii=False, indent=2))


@app.command("rpa-schedule")
def rpa_schedule_cmd(
    schedule_id: str = typer.Option(..., "--id"),
    workflow_id: str = typer.Option(..., "--wf"),
    profile_id: str = typer.Option(..., "--profile"),
    every: int = typer.Option(0, "--every", help="minutes"),
    daily_at: str = typer.Option("", "--daily", help="HH:MM"),
) -> None:
    from mozilla_manager.rpa.scheduler import upsert_schedule, start_scheduler
    row = upsert_schedule(schedule_id=schedule_id, workflow_id=workflow_id, profile_id=profile_id, every_minutes=every or None, daily_at=daily_at or None)
    start_scheduler()
    rprint(json.dumps(row, ensure_ascii=False, indent=2))


@app.command("totp-add")
def totp_add_cmd(
    name: str = typer.Option(..., "--name"),
    secret: str = typer.Option("", "--secret"),
    otpauth: str = typer.Option("", "--otpauth"),
    issuer: str = typer.Option("", "--issuer"),
    profile_id: str = typer.Option("", "--profile"),
) -> None:
    from mozilla_manager.modules import totp_svc
    rprint(json.dumps(totp_svc.add_account(name=name, secret=secret, otpauth=otpauth, issuer=issuer, profile_id=profile_id), ensure_ascii=False, indent=2))


@app.command("totp-list")
def totp_list_cmd(profile_id: str = typer.Option("", "--profile")) -> None:
    from mozilla_manager.modules import totp_svc
    rprint(json.dumps(totp_svc.list_accounts(profile_id=profile_id or None), ensure_ascii=False, indent=2))


@app.command("totp-code")
def totp_code_cmd(account_id: str) -> None:
    from mozilla_manager.modules import totp_svc
    rprint(json.dumps(totp_svc.code_for(account_id), ensure_ascii=False, indent=2))


@app.command("diagnose")
def diagnose_cmd(profile_id: str, samples: int = typer.Option(4, "--samples")) -> None:
    from mozilla_manager.network.diagnose import diagnose_profile
    rprint(json.dumps(diagnose_profile(profile_id, samples=samples), ensure_ascii=False, indent=2))


@app.command("migrate-export")
def migrate_export_cmd(profile_id: str) -> None:
    from mozilla_manager.modules import transfer_svc
    rprint(json.dumps(transfer_svc.export_migrate_pack(profile_id), ensure_ascii=False, indent=2))


@app.command("migrate-import")
def migrate_import_cmd(path: str = typer.Option(..., "--path"), name: str = typer.Option("", "--name")) -> None:
    from mozilla_manager.modules import transfer_svc
    rprint(json.dumps(transfer_svc.import_migrate_pack(path, new_name=name), ensure_ascii=False, indent=2))


@app.command("virtual-media")
def virtual_media_cmd(
    profile_id: str,
    enable: bool = typer.Option(True, "--enable/--disable"),
    camera: bool = typer.Option(True, "--cam/--no-cam"),
    mic: bool = typer.Option(True, "--mic/--no-mic"),
) -> None:
    from mozilla_manager.modules import media_fake
    rprint(json.dumps(media_fake.set_virtual_media(profile_id, enable=enable, camera=camera, mic=mic), ensure_ascii=False, indent=2))


@app.command("countries")
def countries_cmd() -> None:
    from mozilla_manager.env_packs import seed_packs, list_packs
    seed_packs()
    packs = list_packs()
    rprint(json.dumps({"count": len(packs), "countries": packs}, ensure_ascii=False, indent=2))

# ---- v8: recorder / tags / jobs / ops ----
@app.command("record-start")
def record_start_cmd(profile_id: str) -> None:
    from mozilla_manager.rpa import recorder
    rprint(json.dumps(recorder.start_recording(profile_id), ensure_ascii=False, indent=2))


@app.command("record-poll")
def record_poll_cmd(profile_id: str) -> None:
    from mozilla_manager.rpa import recorder
    rprint(json.dumps(recorder.poll_events(profile_id), ensure_ascii=False, indent=2))


@app.command("record-stop")
def record_stop_cmd(
    profile_id: str,
    name: str = typer.Option("", "--name"),
    no_save: bool = typer.Option(False, "--no-save"),
) -> None:
    from mozilla_manager.rpa import recorder
    rprint(json.dumps(recorder.stop_recording(profile_id, save_workflow=not no_save, name=name), ensure_ascii=False, indent=2))


@app.command("record-status")
def record_status_cmd(profile_id: str) -> None:
    from mozilla_manager.rpa import recorder
    rprint(json.dumps(recorder.status(profile_id), ensure_ascii=False, indent=2))


@app.command("tag-add")
def tag_add_cmd(profile_id: str, tags: str = typer.Option(..., "--tags", help="comma-separated")) -> None:
    from mozilla_manager.modules import tags_svc
    arr = [x.strip() for x in tags.split(",") if x.strip()]
    rprint(json.dumps(tags_svc.add_tags(profile_id, arr), ensure_ascii=False, indent=2))


@app.command("tag-list")
def tag_list_cmd(profile_id: str = typer.Option("", "--profile")) -> None:
    from mozilla_manager.modules import tags_svc
    if profile_id:
        rprint(json.dumps({"profile_id": profile_id, "tags": tags_svc.get_tags(profile_id)}, ensure_ascii=False, indent=2))
    else:
        rprint(json.dumps(tags_svc.list_all_tags(), ensure_ascii=False, indent=2))


@app.command("tag-remove")
def tag_remove_cmd(profile_id: str, tags: str = typer.Option(..., "--tags")) -> None:
    from mozilla_manager.modules import tags_svc
    arr = [x.strip() for x in tags.split(",") if x.strip()]
    rprint(json.dumps(tags_svc.remove_tags(profile_id, arr), ensure_ascii=False, indent=2))


@app.command("dashboard")
def dashboard_cmd() -> None:
    from mozilla_manager.modules import ops_svc
    rprint(json.dumps(ops_svc.dashboard(), ensure_ascii=False, indent=2))


@app.command("history")
def history_cmd(limit: int = typer.Option(20, "--limit")) -> None:
    from mozilla_manager.modules import ops_svc
    rprint(json.dumps(ops_svc.history(limit=limit), ensure_ascii=False, indent=2))


@app.command("summary")
def summary_cmd(profile_id: str) -> None:
    from mozilla_manager.modules import ops_svc
    rprint(json.dumps(ops_svc.profile_summary(profile_id), ensure_ascii=False, indent=2))


@app.command("bulk-diagnose")
def bulk_diagnose_cmd(
    ids: str = typer.Option("", "--ids", help="comma profile ids; empty=all"),
    samples: int = typer.Option(2, "--samples"),
    background: bool = typer.Option(False, "--bg", help="async job (only meaningful under serve process)"),
) -> None:
    from mozilla_manager.modules import ops_svc
    arr = [x.strip() for x in ids.split(",") if x.strip()] or None
    # CLI defaults to sync so process exit does not kill daemon worker mid-flight
    rprint(json.dumps(ops_svc.bulk_diagnose(arr, samples=samples, async_job=background), ensure_ascii=False, indent=2))


@app.command("jobs")
def jobs_cmd(limit: int = typer.Option(20, "--limit")) -> None:
    from mozilla_manager.modules import jobs_svc
    rprint(json.dumps(jobs_svc.list_jobs(limit=limit), ensure_ascii=False, indent=2))


@app.command("job-get")
def job_get_cmd(job_id: str) -> None:
    from mozilla_manager.modules import jobs_svc
    rprint(json.dumps(jobs_svc.get_job(job_id), ensure_ascii=False, indent=2))



# ---- v9: notify / locks / watchdogs / audit / timeline ----
@app.command("notify-list")
def notify_list_cmd(limit: int = typer.Option(20, "--limit"), unread: bool = typer.Option(False, "--unread")) -> None:
    from mozilla_manager.modules import notify_svc
    rprint(json.dumps(notify_svc.list_notices(limit=limit, unread_only=unread), ensure_ascii=False, indent=2))


@app.command("notify-read")
def notify_read_cmd(all_read: bool = typer.Option(False, "--all")) -> None:
    from mozilla_manager.modules import notify_svc
    rprint(json.dumps(notify_svc.mark_read(all_=all_read or True), ensure_ascii=False, indent=2))


@app.command("notify-push")
def notify_push_cmd(title: str, kind: str = typer.Option("custom", "--kind"), level: str = typer.Option("info", "--level")) -> None:
    from mozilla_manager.modules import notify_svc
    rprint(json.dumps(notify_svc.push(kind, title, level=level), ensure_ascii=False, indent=2))


@app.command("lock")
def lock_cmd(profile_id: str, reason: str = typer.Option("manual", "--reason"), ttl: int = typer.Option(3600, "--ttl")) -> None:
    from mozilla_manager.modules import lock_svc
    rprint(json.dumps(lock_svc.lock(profile_id, reason=reason, ttl_sec=ttl), ensure_ascii=False, indent=2))


@app.command("unlock")
def unlock_cmd(profile_id: str) -> None:
    from mozilla_manager.modules import lock_svc
    rprint(json.dumps(lock_svc.unlock(profile_id), ensure_ascii=False, indent=2))


@app.command("locks")
def locks_cmd() -> None:
    from mozilla_manager.modules import lock_svc
    rprint(json.dumps(lock_svc.list_locked(), ensure_ascii=False, indent=2))


@app.command("watchdog-add")
def watchdog_add_cmd(
    profile_id: str,
    kind: str = typer.Option("login_check", "--kind"),
    every: int = typer.Option(60, "--every"),
    daily: str = typer.Option("", "--daily"),
    auto_failover: bool = typer.Option(False, "--auto-failover"),
    wid: str = typer.Option("", "--id"),
) -> None:
    from mozilla_manager.modules import watchdog_svc
    params = {"auto_failover": auto_failover} if kind == "diagnose" else {}
    rprint(json.dumps(watchdog_svc.upsert(
        watchdog_id=wid or None, kind=kind, profile_id=profile_id,
        every_minutes=every or None, daily_at=daily or None, params=params,
    ), ensure_ascii=False, indent=2))


@app.command("watchdog-list")
def watchdog_list_cmd() -> None:
    from mozilla_manager.modules import watchdog_svc
    rprint(json.dumps(watchdog_svc.list_watchdogs(), ensure_ascii=False, indent=2))


@app.command("watchdog-tick")
def watchdog_tick_cmd() -> None:
    from mozilla_manager.modules import watchdog_svc
    rprint(json.dumps({"ok": True, "ran": watchdog_svc.tick_once()}, ensure_ascii=False, indent=2))


@app.command("watchdog-status")
def watchdog_status_cmd() -> None:
    from mozilla_manager.modules import watchdog_svc
    rprint(json.dumps(watchdog_svc.status(), ensure_ascii=False, indent=2))


@app.command("audit")
def audit_cmd(limit: int = typer.Option(30, "--limit"), profile_id: str = typer.Option("", "--profile")) -> None:
    from mozilla_manager import db
    rprint(json.dumps(db.list_audit(limit=limit, profile_id=profile_id or None), ensure_ascii=False, indent=2))


@app.command("record-timeline")
def record_timeline_cmd(profile_id: str) -> None:
    from mozilla_manager.rpa import recorder
    rprint(json.dumps(recorder.timeline(profile_id), ensure_ascii=False, indent=2))



# ---- v10: fleet / vault / reports / backup / machine ----
@app.command("machine")
def machine_cmd(name: str = typer.Option("", "--name")) -> None:
    from mozilla_manager.modules import machine_svc
    if name:
        rprint(json.dumps(machine_svc.set_name(name), ensure_ascii=False, indent=2))
    else:
        rprint(json.dumps(machine_svc.get_machine(), ensure_ascii=False, indent=2))


@app.command("fleet-export")
def fleet_export_cmd(
    ids: str = typer.Option("", "--ids", help="comma profile ids to include full data"),
    all_data: bool = typer.Option(False, "--all-data"),
    name: str = typer.Option("", "--name"),
) -> None:
    from mozilla_manager.modules import fleet_svc
    arr = [x.strip() for x in ids.split(",") if x.strip()]
    rprint(json.dumps(fleet_svc.export_fleet_pack(
        include_profiles=arr or None,
        include_profile_data=all_data or bool(arr),
        name=name,
    ), ensure_ascii=False, indent=2))


@app.command("fleet-import")
def fleet_import_cmd(path: str = typer.Option(..., "--path"), totp: bool = typer.Option(False, "--totp")) -> None:
    from mozilla_manager.modules import fleet_svc
    rprint(json.dumps(fleet_svc.import_fleet_pack(path, import_totp=totp), ensure_ascii=False, indent=2))


@app.command("fleet-list")
def fleet_list_cmd() -> None:
    from mozilla_manager.modules import fleet_svc
    rprint(json.dumps(fleet_svc.list_fleet_packs(), ensure_ascii=False, indent=2))


@app.command("vault-put")
def vault_put_cmd(name: str, value: str = typer.Option(..., "--value"), note: str = typer.Option("", "--note")) -> None:
    from mozilla_manager.modules import vault_svc
    rprint(json.dumps(vault_svc.put(name, value, meta={"note": note} if note else {}), ensure_ascii=False, indent=2))


@app.command("vault-get")
def vault_get_cmd(name: str, reveal: bool = typer.Option(False, "--reveal")) -> None:
    from mozilla_manager.modules import vault_svc
    rprint(json.dumps(vault_svc.get(name, reveal=reveal), ensure_ascii=False, indent=2))


@app.command("vault-list")
def vault_list_cmd() -> None:
    from mozilla_manager.modules import vault_svc
    rprint(json.dumps(vault_svc.list_secrets(), ensure_ascii=False, indent=2))


@app.command("vault-del")
def vault_del_cmd(name: str) -> None:
    from mozilla_manager.modules import vault_svc
    rprint(json.dumps(vault_svc.delete(name), ensure_ascii=False, indent=2))


@app.command("report-ops")
def report_ops_cmd() -> None:
    from mozilla_manager.modules import report_svc
    rprint(json.dumps(report_svc.export_ops_report(), ensure_ascii=False, indent=2))


@app.command("backup")
def backup_cmd(label: str = typer.Option("", "--label")) -> None:
    from mozilla_manager.modules import backup_svc
    rprint(json.dumps(backup_svc.create_backup(label=label), ensure_ascii=False, indent=2))


@app.command("backup-list")
def backup_list_cmd() -> None:
    from mozilla_manager.modules import backup_svc
    rprint(json.dumps(backup_svc.list_backups(), ensure_ascii=False, indent=2))


@app.command("backup-schedule")
def backup_schedule_cmd(
    every: float = typer.Option(24.0, "--every"),
    enable: bool = typer.Option(True, "--enable/--disable"),
    keep: int = typer.Option(10, "--keep"),
) -> None:
    from mozilla_manager.modules import backup_svc
    rprint(json.dumps(backup_svc.configure_schedule(every_hours=every, enabled=enable, keep=keep), ensure_ascii=False, indent=2))



@app.command("client")
def client_cmd(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(17888, "--port"),
    no_window: bool = typer.Option(False, "--no-window"),
    allow_browser: bool = typer.Option(False, "--allow-browser"),
    tk: bool = typer.Option(False, "--tk"),
) -> None:
    """启动桌面客户端程序（原生窗口 + 内置模块化后端），不是打开网页。"""
    from mozilla_manager.client.app import run_client
    argv = ["--host", host, "--port", str(port)]
    if no_window:
        argv.append("--no-window")
    if allow_browser:
        argv.append("--allow-browser")
    if tk:
        argv.append("--tk")
    raise SystemExit(run_client(argv))



@app.command("auto-rebind")
def auto_rebind_cmd(
    profile_id: str,
    enable: bool = typer.Option(True, "--enable/--disable"),
) -> None:
    """开关：每次 launch 是否按出口 IP 自动重绑 tz/locale/geo（默认开启）。"""
    from mozilla_manager.modules import health as health_mod
    rprint(json.dumps(health_mod.set_auto_rebind(profile_id, enabled=enable), ensure_ascii=False, indent=2))


@app.command("rebind-now")
def rebind_now_cmd(profile_id: str) -> None:
    """立即按当前出口 IP 重绑 tz/locale/geo（不启动浏览器）。"""
    from mozilla_manager.modules import health as health_mod
    rprint(json.dumps(health_mod.rebind_tz_locale_geo(profile_id, only_if_mismatch=False), ensure_ascii=False, indent=2))

@app.command("compliance")
def compliance_cmd(
    failed_only: bool = typer.Option(False, "--failed-only"),
) -> None:
    """核对 v1–v10 需求是否都已落地（代码+布局+API）。"""
    from mozilla_manager.modules.compliance import audit
    rep = audit()
    if failed_only:
        rprint(json.dumps({"ok": rep["ok"], "failed": rep["failed"], "failures": rep["failures"]}, ensure_ascii=False, indent=2))
    else:
        rprint(json.dumps({k: rep[k] for k in ("ok", "version", "total", "passed", "failed", "contracts", "failures")}, ensure_ascii=False, indent=2))
    if not rep.get("ok"):
        raise typer.Exit(code=1)


@app.command("backfill-meta")
def backfill_meta_cmd() -> None:
    """给旧 Profile 补齐 webrtc/doh/auto_rebind 等默认 meta。"""
    from mozilla_manager.modules.profiles import backfill_all_meta_defaults
    rprint(json.dumps(backfill_all_meta_defaults(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    app()
