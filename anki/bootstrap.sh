#!/bin/bash
set -e

# Install AnkiConnect on first run (idempotent).
ADDON_DIR=/data/addons21/2055492159
if [ ! -f "$ADDON_DIR/config.json" ]; then
    echo "Installing AnkiConnect..."
    mkdir -p "$ADDON_DIR"
    curl -sL -o /tmp/ac.zip \
        "https://ankiweb.net/shared/download/2055492159?v=2.1&p=250902"
    unzip -q /tmp/ac.zip -d "$ADDON_DIR/"
    rm /tmp/ac.zip
    sed -i 's/"webBindAddress"[[:space:]]*:[[:space:]]*"[^"]*"/"webBindAddress": "0.0.0.0"/' \
        "$ADDON_DIR/config.json"
    echo "AnkiConnect installed."
fi

# An unclean host reboot leaves X lock files from the previous run in this
# container's persistent /tmp; after PID reuse Xvfb thinks display :99 is still
# taken and exits silently, so Anki crash-loops with no display (hit 2026-08-17).
rm -f /tmp/.X99-lock /tmp/.X11-unix/X99

exec /startup.sh
