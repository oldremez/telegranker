FROM debian:bookworm-slim

ARG ANKI_VERSION=23.12.1

RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb \
    xdg-utils \
    curl \
    wget \
    python3 \
    zstd \
    libgl1 \
    libegl1 \
    libxkbcommon-x11-0 \
    libdbus-1-3 \
    libxcb-icccm4 \
    libxcb-image0 \
    libxcb-keysyms1 \
    libxcb-randr0 \
    libxcb-render-util0 \
    libxcb-xinerama0 \
    libxcb-xfixes0 \
    libfontconfig1 \
    libfreetype6 \
    libglib2.0-0 \
    libnss3 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libdrm2 \
    libx11-xcb1 \
    libpulse0 \
    && rm -rf /var/lib/apt/lists/*

# Install Anki — split into separate steps so failures are attributed correctly
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && rm -rf /var/lib/apt/lists/*

RUN wget "https://github.com/ankitects/anki/releases/download/${ANKI_VERSION}/anki-${ANKI_VERSION}-linux-qt6.tar.zst" \
        -O /tmp/anki.tar.zst

RUN mkdir -p /tmp/anki \
    && tar --use-compress-program=zstd -xf /tmp/anki.tar.zst -C /tmp/anki --strip-components=1 \
    && rm /tmp/anki.tar.zst

RUN cd /tmp/anki && bash install.sh && rm -rf /tmp/anki

RUN useradd -m -s /bin/bash -u 1000 anki && mkdir -p /imports && chown anki:anki /imports

# Install AnkiConnect addon
RUN ADDON_DIR=/home/anki/.local/share/Anki2/addons21/AnkiConnect && \
    mkdir -p "$ADDON_DIR" && \
    wget -q "https://github.com/FooSoft/anki-connect/archive/refs/heads/master.tar.gz" -O /tmp/ac.tar.gz && \
    tar -xf /tmp/ac.tar.gz -C /tmp/ && \
    if [ -d /tmp/anki-connect-master/plugin ]; then \
        cp -r /tmp/anki-connect-master/plugin/. "$ADDON_DIR/"; \
    else \
        cp -r /tmp/anki-connect-master/. "$ADDON_DIR/"; \
    fi && \
    rm -rf /tmp/ac.tar.gz /tmp/anki-connect-master && \
    python3 -c "import json,os; p='$ADDON_DIR/config.json'; cfg=json.load(open(p)) if os.path.exists(p) else {}; cfg['webBindAddress']='0.0.0.0'; json.dump(cfg,open(p,'w'),indent=4)" && \
    chown -R anki:anki /home/anki/.local

COPY --chown=anki:anki entrypoint.sh /home/anki/entrypoint.sh
COPY --chown=anki:anki configure_sync.py /home/anki/configure_sync.py
RUN chmod +x /home/anki/entrypoint.sh

USER anki
WORKDIR /home/anki

EXPOSE 8765

ENTRYPOINT ["/home/anki/entrypoint.sh"]
