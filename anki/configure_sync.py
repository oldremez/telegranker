#!/usr/bin/env python3
"""
One-time setup that runs before Anki starts.

prefs21.db is intentionally NOT touched here — Anki 23.x requires both a
'profiles' table (with a pickled ProfileMeta blob) and a 'config' table,
and creating only one of them makes _loadMeta crash.  Anki creates the file
correctly on its own first run.  Post-startup sync config (if ever needed)
should go through AnkiConnect or the Anki UI.
"""
import os

anki_base = os.environ.get("ANKI_BASE", "/home/anki/.local/share/Anki2")
profile = os.environ.get("ANKI_PROFILE", "User 1")

os.makedirs(os.path.join(anki_base, profile), exist_ok=True)
print("Prefs initialised.")
