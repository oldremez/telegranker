#!/bin/bash
set -e

export ANKI_BASE="${ANKI_BASE:-/home/anki/.local/share/Anki2}"
export ANKI_PROFILE="${ANKI_PROFILE:-User 1}"
export DISPLAY="${DISPLAY:-:99}"
export QT_DEBUG_PLUGINS=1

mkdir -p "${ANKI_BASE}/${ANKI_PROFILE}"
mkdir -p /tmp/.X11-unix 2>/dev/null || true

rm -f /tmp/anki* /tmp/.X*-lock 2>/dev/null || true

# Self-heal a broken prefs21.db left over in the volume (needs BOTH
# `profiles` and `config` tables, or _loadMeta crashes).
PREFS="${ANKI_BASE}/prefs21.db"
if [[ -f "${PREFS}" ]]; then
    tables=$(sqlite3 "${PREFS}" "SELECT name FROM sqlite_master WHERE type='table';" 2>/dev/null || echo "")
    if ! grep -q '^profiles$' <<<"${tables}" || ! grep -q '^config$' <<<"${tables}"; then
        echo "prefs21.db is missing required tables (found: ${tables//$'\n'/,}); recreating."
        rm -f "${PREFS}" "${PREFS}-journal" "${PREFS}-wal" "${PREFS}-shm"
    fi
fi

echo "Starting Xvfb on ${DISPLAY}..."
Xvfb "${DISPLAY}" -screen 0 1280x1024x24 -ac -nolisten tcp &

for _ in $(seq 1 30); do
    if xdotool search --name "." >/dev/null 2>&1; then break; fi
    sleep 0.2
done
echo "Xvfb ready."

# Diagnostic watcher: every 3s for 2 minutes, list visible windows and
# press Return on each (dismisses Welcome / update prompts).
(
    for i in $(seq 1 40); do
        sleep 3
        wids=$(xdotool search --onlyvisible "" 2>/dev/null || true)
        if [[ -z "${wids}" ]]; then
            echo "[watcher t=${i}] no visible windows"
            continue
        fi
        for wid in ${wids}; do
            name=$(xdotool getwindowname "$wid" 2>/dev/null || echo "<no name>")
            echo "[watcher t=${i}] wid=$wid name='${name}' — sending Return"
            xdotool windowactivate "$wid" 2>/dev/null || true
            xdotool key --window "$wid" Return 2>/dev/null || true
        done
    done
) &

echo "Starting Anki (profile: ${ANKI_PROFILE})..."
exec anki -b "${ANKI_BASE}" --profile "${ANKI_PROFILE}"
