Place unpacked browser extensions here as directories:
  runtime/extensions/<ext_id>/manifest.json

Enable per profile via:
  python -m mozilla_manager.cli ext-set <profile_id> --ids ext_id1,ext_id2
or API POST /api/extensions/profiles/{id}
