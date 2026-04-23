import os
import sys
from aqt import mw, gui_hooks
from aqt.qt import QTimer


def _log(msg: str) -> None:
    print(msg, flush=True)
    with open("/tmp/anki-autologin.log", "a") as f:
        f.write(msg + "\n")


def _make_auth():
    """Build a fresh SyncAuth by re-logging in with env credentials."""
    email = os.environ.get("ANKIWEB_EMAIL", "").strip()
    password = os.environ.get("ANKIWEB_PASSWORD", "").strip()
    if not email or not password:
        raise Exception("ANKIWEB_EMAIL / ANKIWEB_PASSWORD not set")
    endpoint = mw.pm.profile.get("syncEndpoint") or "https://sync.ankiweb.net/"
    try:
        return mw.col.sync_login(username=email, password=password, endpoint=endpoint)
    except AttributeError:
        return mw.col._backend.sync_login(username=email, password=password, endpoint=endpoint)


def _full_upload(auth) -> None:
    try:
        mw.col.full_upload_or_download(auth=auth, server_usn=0, upload=True)
    except TypeError:
        mw.col._backend.full_upload_or_download(auth=auth, server_usn=0, upload=True)


def _patch_ankiconnect() -> None:
    """Add a fullSync action to AnkiConnect so the bot can trigger a full upload."""
    ac = sys.modules.get("2055492159")
    if not ac:
        _log("AnkiWeb: AnkiConnect module not found, skipping patch.")
        return

    def fullSync(self):  # noqa: N802
        _log("AnkiWeb: fullSync action called.")
        auth = _make_auth()
        _full_upload(auth)
        _log("AnkiWeb: full upload complete.")

    ac.AnkiConnect.fullSync = fullSync
    _log("AnkiWeb: fullSync action registered on AnkiConnect.")


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
    try:
        auth = _make_auth()
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

    # Patch AnkiConnect after the event loop starts (all addons are loaded by then).
    QTimer.singleShot(2000, _patch_ankiconnect)


gui_hooks.profile_did_open.append(_auto_login)
