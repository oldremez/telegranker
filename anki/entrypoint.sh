#!/bin/bash
set -e

export ANKI_BASE="${ANKI_BASE:-/home/anki/.local/share/Anki2}"
export ANKI_PROFILE="${ANKI_PROFILE:-User 1}"
export LANG="${LANG:-en_US.UTF-8}"
export LC_ALL="${LC_ALL:-en_US.UTF-8}"

mkdir -p "${ANKI_BASE}/${ANKI_PROFILE}"

# If a previous run left a prefs21.db that's missing the 'profiles' table
# (created by an old version of this setup script), remove it so Anki can
# recreate it with the correct schema.
PREFS="${ANKI_BASE}/prefs21.db"
if [ -f "$PREFS" ]; then
    HAS_PROFILES=$(python3 -c "
import sqlite3, sys
c = sqlite3.connect('${PREFS}')
n = c.execute(\"SELECT count() FROM sqlite_master WHERE name='profiles'\").fetchone()[0]
c.close()
print(n)
" 2>/dev/null || echo "0")
    if [ "$HAS_PROFILES" = "0" ]; then
        echo "Removing incomplete prefs21.db (missing profiles table) — Anki will recreate it."
        rm -f "$PREFS"
    fi
fi

python3 /home/anki/configure_sync.py

# Clean up any stale Xvfb lock from a previous (crashed) run
rm -f /tmp/.X99-lock /tmp/.X11-unix/X99

# Start virtual framebuffer
Xvfb :99 -screen 0 1280x800x24 -ac +extension GLX +render -noreset &
export DISPLAY=:99

# Give Xvfb a moment to initialise
sleep 2

echo "Starting Anki (profile: ${ANKI_PROFILE})..."
exec anki --base "${ANKI_BASE}" --profile "${ANKI_PROFILE}"
