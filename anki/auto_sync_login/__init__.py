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
        try:
            mw.col.full_upload_or_download(auth=auth, server_usn=0, upload=True)
        except TypeError:
            mw.col._backend.full_upload_or_download(auth=auth, server_usn=0, upload=True)
        _log("AnkiWeb: full upload complete.")

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
        mw.pm.save()
        _log("AnkiWeb: auto-login succeeded.")
    except Exception as exc:
        _log(f"AnkiWeb: auto-login failed: {exc}")


gui_hooks.profile_did_open.append(_on_profile_loaded)
