# telegranker

Telegram bot that imports flashcard files into a headless Anki instance running in Docker.

## Architecture

```
Telegram  →  bot container  →  AnkiConnect (8765)  →  headless Anki (Xvfb + x11vnc)
                                                              ↕
                                                          AnkiWeb sync
```

- **anki** service: [ankimcp/headless-anki](https://github.com/ankimcp/headless-anki) `x11-vnc-v1.2.0` image; compose bootstraps the [AnkiConnect](https://ankiweb.net/shared/info/2055492159) addon on first start.
- **bot** service: Python Telegram bot that proxies files/text to AnkiConnect.

## Quick start

```bash
cp .env.example .env
# Edit .env — set TELEGRAM_BOT_TOKEN
docker compose up -d
```

First boot downloads AnkiConnect into the `anki_data` volume and patches it to bind `0.0.0.0` so the bot container can reach it. The healthcheck turns green once port 8765 answers.

## Supported inputs

| Input | Action |
|-------|--------|
| `.apkg` file | Import Anki package directly |
| `.txt` / `.csv` file | Tab-separated `Front<TAB>Back` per line; optional ` \| comment` after Back is rendered as an italic note below the answer |
| Text message `Question::Answer` | Add a single Basic card |

### Bot commands
- `/start` / `/help` — usage info
- `/decks` — list all decks
- `/sync` — trigger AnkiWeb sync

## AnkiWeb sync

Set `ANKIWEB_EMAIL` and `ANKIWEB_PASSWORD` in `.env`. On first start, a small addon calls Anki's sync-login backend API and stores the session key in the profile — no GUI interaction needed. Subsequent restarts skip login if the key is already present.

If auto-login fails (wrong credentials, AnkiWeb API change, etc.), fall back to the one-time VNC flow:

```bash
# Connect to localhost:5900 with any VNC client (no password).
# Tools → Preferences → Syncing → log in with your AnkiWeb account.
```

## Security

Set `ALLOWED_USER_IDS` in `.env` to a comma-separated list of Telegram numeric user IDs to restrict access. Leave it empty to allow anyone who can find the bot.

The VNC port (5900) is exposed without a password — do not publish it on an untrusted network. Bind it to `127.0.0.1:5900` in `docker-compose.yml` if the host is public.

## Volumes

| Volume | Purpose |
|--------|---------|
| `anki_data` | Anki profile, collection, media, AnkiConnect addon |
| `imports` | Shared directory for `.apkg` file hand-off between bot and Anki |

Wipe both with `docker compose down -v` to start fresh.
