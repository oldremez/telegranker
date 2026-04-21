#!/bin/bash
set -e

export ANKI_BASE="${ANKI_BASE:-/home/anki/.local/share/Anki2}"
export ANKI_PROFILE="${ANKI_PROFILE:-User 1}"
export LANG="${LANG:-en_US.UTF-8}"
export LC_ALL="${LC_ALL:-en_US.UTF-8}"

mkdir -p "${ANKI_BASE}/${ANKI_PROFILE}"

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
