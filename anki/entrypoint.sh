#!/bin/bash
set -e

export ANKI_BASE="${ANKI_BASE:-/home/anki/.local/share/Anki2}"
export ANKI_PROFILE="${ANKI_PROFILE:-User 1}"

mkdir -p "${ANKI_BASE}/${ANKI_PROFILE}"

python3 /home/anki/configure_sync.py

echo "Starting Anki (profile: ${ANKI_PROFILE})..."
exec anki -b "${ANKI_BASE}" --profile "${ANKI_PROFILE}"
