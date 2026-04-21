#!/bin/bash
set -e

export ANKI_BASE="${ANKI_BASE:-/home/anki/.local/share/Anki2}"
export ANKI_PROFILE="${ANKI_PROFILE:-User 1}"

mkdir -p "${ANKI_BASE}/${ANKI_PROFILE}"

# Try to configure AnkiWeb sync if credentials were provided
if [ -n "${ANKIWEB_EMAIL}" ] && [ -n "${ANKIWEB_PASSWORD}" ]; then
    python3 /home/anki/configure_sync.py || echo "Sync pre-configuration failed — log in manually via 'docker exec' if needed"
fi

# Start virtual framebuffer
Xvfb :99 -screen 0 1280x800x24 -ac +extension GLX +render -noreset &
export DISPLAY=:99

# Give Xvfb a moment to initialise
sleep 2

echo "Starting Anki (profile: ${ANKI_PROFILE})..."
exec anki --base "${ANKI_BASE}" --profile "${ANKI_PROFILE}"
