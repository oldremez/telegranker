import os
import sys
from aqt import mw, gui_hooks


def _log(msg: str) -> None:
    print(msg, flush=True)
    with open("/tmp/anki-autologin.log", "a") as f:
        f.write(msg + "\n")


def _make_auth():
    email = os.environ.get("ANKIWEB_EMAIL", "").strip()
    password = os.environ.get("ANKIWEB_PASSWORD", "").strip()
    if not email or not password:
        raise Exception("ANKIWEB_EMAIL / ANKIWEB_PASSWORD not set")
    endpoint = mw.pm.profile.get("syncEndpoint") or "https://sync.ankiweb.net/"
    try:
        return mw.col.sync_login(username=email, password=password, endpoint=endpoint)
    except AttributeError:
        return mw.col._backend.sync_login(username=email, password=password, endpoint=endpoint)


def _patch_ankiconnect() -> None:
    # Find the AnkiConnect module — its sys.modules key varies by Anki version.
    ac = None
    for key in list(sys.modules):
        mod = sys.modules[key]
        if hasattr(mod, "AnkiConnect") and hasattr(mod.AnkiConnect, "sync"):
            ac = mod
            _log(f"AnkiWeb: found AnkiConnect at sys.modules['{key}']")
            break
    if not ac:
        _log(f"AnkiWeb: AnkiConnect not found. addon-like keys: "
             f"{[k for k in sys.modules if k.isdigit() or 'anki' in k.lower()]}")
        return

    def fullSync(self):  # noqa: N802
        _log("AnkiWeb: fullSync action called.")
        auth = _make_auth()
        # Call full_upload_or_download directly — do NOT call sync_collection
        # first as that opens a server session that conflicts with the full sync.
        # Try progressively simpler signatures to handle API differences across
        # Anki versions.
        errs = []
        for kwargs in [
            {"auth": auth, "server_usn": 0, "upload": True},
            {"auth": auth, "upload": True},
        ]:
            try:
                mw.col.full_upload_or_download(**kwargs)
                _log(f"AnkiWeb: full upload complete (kwargs={list(kwargs)})")
                return
            except TypeError as e:
                errs.append(f"col: {e}")
            try:
                mw.col._backend.full_upload_or_download(**kwargs)
                _log(f"AnkiWeb: full upload complete via _backend (kwargs={list(kwargs)})")
                return
            except TypeError as e:
                errs.append(f"_backend: {e}")
        raise Exception(f"full_upload_or_download failed all signatures: {errs}")

    fullSync.api = True  # required by AnkiConnect's @util.api() dispatch
    ac.AnkiConnect.fullSync = fullSync
    _log("AnkiWeb: fullSync action registered.")


def _on_profile_loaded() -> None:
    # Always patch AnkiConnect so fullSync is available every boot.
    _patch_ankiconnect()

    if mw.pm.profile.get("syncKey"):
        _log("AnkiWeb: already authenticated.")
        return

    _log("AnkiWeb: attempting auto-login...")
    try:
        auth = _make_auth()
        mw.pm.profile["syncKey"] = auth.hkey
        if hasattr(auth, "host_number"):
            mw.pm.profile["hostNum"] = auth.host_number
        if hasattr(auth, "endpoint") and auth.endpoint:
            mw.pm.profile["syncEndpoint"] = auth.endpoint
        # Disable Anki's own auto-sync — it crashes headless when a full sync
        # is required (it tries to show an Upload/Download dialog).
        # All sync is done explicitly through the bot's /sync and /fullsync.
        mw.pm.profile["autoSync"] = False
        mw.pm.save()
        _log("AnkiWeb: auto-login succeeded, auto-sync disabled.")
    except Exception as exc:
        _log(f"AnkiWeb: auto-login failed: {exc}")


gui_hooks.profile_did_open.append(_on_profile_loaded)
