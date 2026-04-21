FROM debian:bookworm-slim

ARG ANKI_VERSION=23.12.1
ARG ANKICONNECT_VERSION=24.6.17.0

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    wget \
    jq \
    zstd \
    locales \
    libxcb-xinerama0 \
    libxcb-cursor0 \
    libnss3 \
    libxcomposite-dev \
    libxdamage-dev \
    libxtst-dev \
    libxkbcommon-dev \
    libxkbfile-dev \
    libglib2.0-0 \
    libdbus-1-3 \
    libfontconfig1 \
    libfreetype6 \
    && sed -i 's/# en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' /etc/locale.gen \
    && dpkg-reconfigure --frontend=noninteractive locales \
    && update-locale LANG=en_US.UTF-8 \
    && rm -rf /var/lib/apt/lists/*

ENV LANG=en_US.UTF-8
ENV LANGUAGE=en_US
ENV LC_ALL=en_US.UTF-8
# Use Qt's built-in VNC platform plugin — no X server or Xvfb needed
ENV QT_QPA_PLATFORM=vnc
ENV QT_XKB_CONFIG_ROOT=/usr/share/X11/xkb
ENV FONTCONFIG_PATH=/etc/fonts
ENV QMLSCENE_DEVICE=softwarecontext
ENV DISABLE_QT5_COMPAT=1

RUN useradd -m -s /bin/bash -u 1000 anki \
    && mkdir -p /imports && chown anki:anki /imports

# Install Anki
RUN wget -q "https://github.com/ankitects/anki/releases/download/${ANKI_VERSION}/anki-${ANKI_VERSION}-linux-qt6.tar.zst" \
        -O /tmp/anki.tar.zst \
    && zstd -d /tmp/anki.tar.zst -o /tmp/anki.tar \
    && mkdir -p /tmp/anki \
    && tar -xf /tmp/anki.tar -C /tmp/anki --strip-components=1 \
    && cd /tmp/anki \
    && cat install.sh | sed 's/xdg-mime/#xdg-mime/g; s/xdg-icon-resource/#xdg-icon-resource/g; s/xdg-desktop-menu/#xdg-desktop-menu/g' | sh - \
    && rm -rf /tmp/anki /tmp/anki.tar

# Install AnkiConnect
RUN ADDON_DIR=/home/anki/.local/share/Anki2/addons21/AnkiConnect \
    && mkdir -p "$ADDON_DIR" \
    && curl -sL "https://git.sr.ht/~foosoft/anki-connect/archive/${ANKICONNECT_VERSION}.tar.gz" \
       | tar -xz -C /tmp/ \
    && cp -r /tmp/anki-connect-${ANKICONNECT_VERSION}/plugin/. "$ADDON_DIR/" \
    && rm -rf /tmp/anki-connect-${ANKICONNECT_VERSION} \
    && jq '.webBindAddress = "0.0.0.0"' "$ADDON_DIR/config.json" > /tmp/cfg.json \
    && mv /tmp/cfg.json "$ADDON_DIR/config.json" \
    && chown -R anki:anki /home/anki/.local

COPY --chown=anki:anki entrypoint.sh /home/anki/entrypoint.sh
RUN chmod +x /home/anki/entrypoint.sh

USER anki
WORKDIR /home/anki

EXPOSE 8765

ENTRYPOINT ["/home/anki/entrypoint.sh"]
