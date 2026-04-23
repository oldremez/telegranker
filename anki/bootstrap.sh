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

exec /startup.sh
