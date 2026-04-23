import os
from aqt import mw, gui_hooks


def _auto_login() -> None:
    email = os.environ.get("ANKIWEB_EMAIL", "").strip()
    password = os.environ.get("ANKIWEB_PASSWORD", "").strip()
    if not email or not password:
        return
    if mw.pm.profile.get("syncKey"):
        return  # already authenticated
    print(f"AnkiWeb: attempting auto-login for {email}...")
    try:
        try:
            auth = mw.col.sync_login(username=email, password=password)
        except AttributeError:
            auth = mw.col._backend.sync_login(username=email, password=password)
        mw.pm.profile["syncKey"] = auth.hkey
        mw.pm.profile["hostNum"] = auth.host_number
        mw.pm.save()
        print("AnkiWeb: auto-login succeeded.")
    except Exception as exc:
        print(f"AnkiWeb: auto-login failed: {exc}")


gui_hooks.profile_did_open.append(_auto_login)
