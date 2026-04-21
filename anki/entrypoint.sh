#!/bin/bash
set -e

export ANKI_BASE="${ANKI_BASE:-/home/anki/.local/share/Anki2}"
export ANKI_PROFILE="${ANKI_PROFILE:-User 1}"
export DISPLAY="${DISPLAY:-:99}"

mkdir -p "${ANKI_BASE}/${ANKI_PROFILE}"
mkdir -p /tmp/.X11-unix 2>/dev/null || true

# Clean up stale single-instance / X sockets that survive container restarts.
rm -f /tmp/anki* /tmp/.X*-lock 2>/dev/null || true

# Self-heal a broken prefs21.db.  Anki 23.x requires both `profiles` and
# `config` tables — an incomplete DB (e.g. left behind by an earlier botched
# run) crashes _loadMeta before the Qt event loop even starts.  If either
# table is missing, wipe the file so Anki recreates it cleanly.
PREFS="${ANKI_BASE}/prefs21.db"
if [[ -f "${PREFS}" ]]; then
    tables=$(sqlite3 "${PREFS}" "SELECT name FROM sqlite_master WHERE type='table';" 2>/dev/null || echo "")
    if ! grep -q '^profiles$' <<<"${tables}" || ! grep -q '^config$' <<<"${tables}"; then
        echo "prefs21.db is missing required tables (found: ${tables//$'\n'/,}); recreating."
        rm -f "${PREFS}" "${PREFS}-journal" "${PREFS}-wal" "${PREFS}-shm"
    fi
fi

echo "Starting Xvfb on ${DISPLAY}..."
Xvfb "${DISPLAY}" -screen 0 1280x1024x24 -nolisten tcp &

for _ in $(seq 1 30); do
    if xdotool search --name "." >/dev/null 2>&1; then break; fi
    sleep 0.2
done

# Press Return on any window that appears during the first minute — dismisses
# the Welcome / first-run profile / update-check dialogs that otherwise block
# profileLoaded (and therefore AnkiConnect's HTTP server).
(
    for _ in $(seq 1 60); do
        for wid in $(xdotool search --onlyvisible "" 2>/dev/null); do
            xdotool windowactivate "$wid" 2>/dev/null || true
            xdotool key --window "$wid" Return 2>/dev/null || true
        done
        sleep 1
    done
) &

echo "Starting Anki (profile: ${ANKI_PROFILE})..."
exec anki -b "${ANKI_BASE}" --profile "${ANKI_PROFILE}"
