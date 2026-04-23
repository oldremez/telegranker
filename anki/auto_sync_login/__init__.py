import os
from aqt import mw, gui_hooks


def _log(msg: str) -> None:
    print(msg, flush=True)
    with open("/tmp/anki-autologin.log", "a") as f:
        f.write(msg + "\n")


def _auto_login() -> None:
    _log("AnkiWeb: auto_sync_login hook fired.")
    email = os.environ.get("ANKIWEB_EMAIL", "").strip()
    password = os.environ.get("ANKIWEB_PASSWORD", "").strip()
    if not email or not password:
        _log("AnkiWeb: no credentials set, skipping.")
        return
    if mw.pm.profile.get("syncKey"):
        _log("AnkiWeb: already authenticated, skipping.")
        return
    _log(f"AnkiWeb: attempting auto-login for {email}...")
    endpoint = mw.pm.profile.get("syncEndpoint") or "https://sync.ankiweb.net/"
    try:
        try:
            auth = mw.col.sync_login(username=email, password=password, endpoint=endpoint)
        except AttributeError:
            auth = mw.col._backend.sync_login(username=email, password=password, endpoint=endpoint)
        _log(f"AnkiWeb: auth fields: {[f for f in dir(auth) if not f.startswith('_')]}")
        mw.pm.profile["syncKey"] = auth.hkey
        if hasattr(auth, "host_number"):
            mw.pm.profile["hostNum"] = auth.host_number
        if hasattr(auth, "endpoint") and auth.endpoint:
            mw.pm.profile["syncEndpoint"] = auth.endpoint
        mw.pm.save()
        _log("AnkiWeb: auto-login succeeded.")
    except Exception as exc:
        _log(f"AnkiWeb: auto-login failed: {exc}")


gui_hooks.profile_did_open.append(_auto_login)
