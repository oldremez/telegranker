#!/bin/bash
set -e

export ANKI_BASE="${ANKI_BASE:-/home/anki/.local/share/Anki2}"
export ANKI_PROFILE="${ANKI_PROFILE:-User 1}"
export DISPLAY="${DISPLAY:-:99}"

mkdir -p "${ANKI_BASE}/${ANKI_PROFILE}"

# Anki leaves a single-instance socket in /tmp that survives container restarts
# if the volume happens to be mounted; clean it so startup doesn't bail early.
rm -f /tmp/anki* /tmp/.X*-lock 2>/dev/null || true

echo "Starting Xvfb on ${DISPLAY}..."
Xvfb "${DISPLAY}" -screen 0 1280x1024x24 -nolisten tcp &
XVFB_PID=$!

# Wait for the X server to be ready.
for _ in $(seq 1 30); do
    if xdotool search --name "." >/dev/null 2>&1; then break; fi
    sleep 0.2
done

# Background watcher: press Return on any window that appears during startup
# (Welcome dialog, first-run profile create, "check for updates" prompt, etc).
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
