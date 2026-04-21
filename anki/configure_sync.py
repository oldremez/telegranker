#!/usr/bin/env python3
"""
Write baseline prefs to prefs21.db (locale, update checks off, etc.).

AnkiWeb sync credentials cannot be pre-configured via the public API in
Anki 23.x+ — the old /auth/ endpoint is gone.  Log in once through the
Anki UI (or via AnkiConnect's 'sync' action after you've logged in
interactively) and credentials will persist in the anki_data volume.
"""
import json
import os
import sqlite3

ANKI_BASE = os.environ.get("ANKI_BASE", "/home/anki/.local/share/Anki2")

os.makedirs(ANKI_BASE, exist_ok=True)

prefs_path = os.path.join(ANKI_BASE, "prefs21.db")
conn = sqlite3.connect(prefs_path)
conn.execute(
    "CREATE TABLE IF NOT EXISTS config "
    "(key TEXT NOT NULL PRIMARY KEY, usn INTEGER NOT NULL, val TEXT NOT NULL)"
)

defaults = {
    "checkForUpdates": False,
    "autoSyncMedia": True,
}
email = os.environ.get("ANKIWEB_EMAIL", "")
if email:
    defaults["syncUser"] = email

for key, val in defaults.items():
    conn.execute(
        "INSERT OR IGNORE INTO config VALUES (?, ?, ?)",
        (key, 0, json.dumps(val)),
    )

conn.commit()
conn.close()
print("Prefs initialised.")
