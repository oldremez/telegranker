#!/usr/bin/env python3
"""Pre-configure AnkiWeb sync credentials in prefs21.db before Anki starts."""
import json
import os
import sqlite3
import urllib.parse
import urllib.request

ANKIWEB_EMAIL = os.environ.get("ANKIWEB_EMAIL", "")
ANKIWEB_PASSWORD = os.environ.get("ANKIWEB_PASSWORD", "")
ANKI_BASE = os.environ.get("ANKI_BASE", "/home/anki/.local/share/Anki2")

if not ANKIWEB_EMAIL or not ANKIWEB_PASSWORD:
    print("No AnkiWeb credentials — skipping sync setup.")
    raise SystemExit(0)

os.makedirs(ANKI_BASE, exist_ok=True)


def _auth_json(email: str, password: str) -> str | None:
    """Newer AnkiWeb auth (JSON body)."""
    body = json.dumps({"username": email, "password": password}).encode()
    req = urllib.request.Request(
        "https://sync.ankiweb.net/auth/",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
        return data.get("key") or None


def _auth_form(email: str, password: str) -> str | None:
    """Older AnkiWeb auth (form-encoded body)."""
    body = urllib.parse.urlencode({"u": email, "p": password}).encode()
    req = urllib.request.Request(
        "https://sync.ankiweb.net/auth/",
        data=body,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        key = resp.read().decode().strip()
        return key if key and key != "null" else None


host_key = None
for attempt in (_auth_json, _auth_form):
    try:
        host_key = attempt(ANKIWEB_EMAIL, ANKIWEB_PASSWORD)
        if host_key:
            break
    except Exception as exc:
        print(f"Auth attempt failed: {exc}")

prefs_path = os.path.join(ANKI_BASE, "prefs21.db")
conn = sqlite3.connect(prefs_path)
conn.execute(
    "CREATE TABLE IF NOT EXISTS config "
    "(key TEXT NOT NULL PRIMARY KEY, usn INTEGER NOT NULL, val TEXT NOT NULL)"
)

# Sensible defaults regardless of auth success
for key, val in [
    ("checkForUpdates", False),
    ("autoSyncMedia", True),
]:
    conn.execute(
        "INSERT OR IGNORE INTO config VALUES (?, ?, ?)",
        (key, 0, json.dumps(val)),
    )

if host_key:
    for key, val in [
        ("syncUser", ANKIWEB_EMAIL),
        ("hostKey", host_key),
        ("autoSync", True),
    ]:
        conn.execute(
            "INSERT OR REPLACE INTO config VALUES (?, ?, ?)",
            (key, 0, json.dumps(val)),
        )
    print(f"AnkiWeb sync configured for {ANKIWEB_EMAIL}")
else:
    # Store the email so Anki knows who to sync as — user will be prompted for password on first UI login
    conn.execute(
        "INSERT OR IGNORE INTO config VALUES (?, ?, ?)",
        ("syncUser", 0, json.dumps(ANKIWEB_EMAIL)),
    )
    print(
        "Could not obtain AnkiWeb auth token automatically.\n"
        "Run: docker exec -it <anki-container> python3 /home/anki/configure_sync.py\n"
        "after the container starts, or log in via the Anki UI."
    )
    raise SystemExit(1)

conn.commit()
conn.close()
