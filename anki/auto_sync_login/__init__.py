import os
from aqt import mw, gui_hooks


def _log(msg: str) -> None:
    print(msg, flush=True)
    with open("/tmp/anki-autologin.log", "a") as f:
        f.write(msg + "\n")


def _on_profile_loaded() -> None:
    if mw.pm.profile.get("syncKey"):
        _log("AnkiWeb: already authenticated.")
        return

    email = os.environ.get("ANKIWEB_EMAIL", "").strip()
    password = os.environ.get("ANKIWEB_PASSWORD", "").strip()
    if not email or not password:
        _log("AnkiWeb: no credentials set, skipping.")
        return

    _log(f"AnkiWeb: attempting auto-login for {email}...")
    endpoint = mw.pm.profile.get("syncEndpoint") or "https://sync.ankiweb.net/"
    try:
        try:
            auth = mw.col.sync_login(username=email, password=password, endpoint=endpoint)
        except AttributeError:
            auth = mw.col._backend.sync_login(username=email, password=password, endpoint=endpoint)
        mw.pm.profile["syncKey"] = auth.hkey
        if hasattr(auth, "host_number"):
            mw.pm.profile["hostNum"] = auth.host_number
        if hasattr(auth, "endpoint") and auth.endpoint:
            mw.pm.profile["syncEndpoint"] = auth.endpoint
        # Disable Anki's own auto-sync — it crashes headless when a full sync
        # is required (tries to show an Upload/Download dialog).
        mw.pm.profile["autoSync"] = False
        mw.pm.save()
        _log("AnkiWeb: auto-login succeeded.")
    except Exception as exc:
        _log(f"AnkiWeb: auto-login failed: {exc}")


gui_hooks.profile_did_open.append(_on_profile_loaded)
