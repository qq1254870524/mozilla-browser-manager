"""Compatibility facade — re-exports domain modules for CLI / legacy imports."""
from __future__ import annotations

from mozilla_manager.modules import (
    doctor_svc,
    extensions,
    groups,
    health,
    mihomo_svc,
    nodes_svc,
    profiles,
    proxies,
    sessions,
    subscriptions,
    system,
    templates,
)

boot = system.boot
doctor = doctor_svc.run

profiles_list = profiles.list_profiles
profile_get = profiles.get_profile
profile_create = profiles.create_profile
profile_update = profiles.update_profile
profile_delete = profiles.delete_profile
profile_set_proxy = profiles.set_proxy
profile_bind_country = profiles.bind_country
profile_launch = profiles.launch
profile_stop = profiles.stop
profile_check = profiles.check
profile_export = profiles.export_zip
profile_snapshot = profiles.snapshot
list_running = profiles.running
restore_last_session = profiles.restore_last_session

session_backup = profiles.session_backup
session_restore = profiles.session_restore
session_list = profiles.session_list

packs_list = templates.packs
fingerprints_list = templates.fingerprints
recommend_node = templates.recommend_node
bind_node = templates.bind_node_to_profile
set_fingerprint = templates.set_fingerprint

groups_list = groups.list_groups
proxies_from_profiles = proxies.list_proxies

sub_import = subscriptions.import_sub
subs_list = subscriptions.list_subs
nodes_list = subscriptions.list_sub_nodes
sub_refresh = subscriptions.refresh_sub

mihomo_start = mihomo_svc.start
mihomo_stop = mihomo_svc.stop
mihomo_status = mihomo_svc.status

nodes_enriched = nodes_svc.list_nodes_enriched
nodes_speedtest = nodes_svc.speedtest
health_egress = health.check_egress
health_rebind = health.rebind_from_egress
extensions_list = extensions.list_extensions
