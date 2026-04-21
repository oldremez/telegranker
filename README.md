# telegranker

Telegram bot that imports flashcard files into a headless Anki desktop instance running in Docker, with automatic AnkiWeb sync.

## Architecture

```
Telegram  →  bot container  →  AnkiConnect (port 8765)  →  Anki (headless, Xvfb)
                                                               ↕
                                                           AnkiWeb sync
```

- **anki** service: Anki 23.12.1 (Qt6) running under Xvfb with the AnkiConnect addon
- **bot** service: Python Telegram bot that proxies files/text to AnkiConnect

## Quick start

```bash
cp .env.example .env
# Edit .env — set TELEGRAM_BOT_TOKEN and (optionally) ANKIWEB_* credentials
docker compose up -d --build
```

## Supported inputs

| Input | Action |
|-------|--------|
| `.apkg` file | Import Anki package directly |
| `.txt` / `.csv` file | Import cards — one `Front::Back` per line |
| Text message `Question::Answer` | Add a single Basic card |

### Bot commands
- `/start` / `/help` — usage info
- `/decks` — list all decks
- `/sync` — trigger AnkiWeb sync manually

## AnkiWeb sync

On startup the container tries to authenticate with AnkiWeb automatically using `ANKIWEB_EMAIL` / `ANKIWEB_PASSWORD` and writes the session token into the Anki prefs database.

If auto-configuration fails (e.g. due to AnkiWeb API changes), log in once manually:

```bash
# Open an interactive shell inside the running anki container
docker exec -it telegranker-anki-1 bash

# Re-run the sync configuration script
python3 /home/anki/configure_sync.py
```

Anki data (profile, collection, media) is persisted in the `anki_data` Docker volume, so credentials survive container restarts.

## Security

Set `ALLOWED_USER_IDS` in `.env` to a comma-separated list of Telegram numeric user IDs to restrict access. Leave it empty to allow anyone who can find the bot.

## Volumes

| Volume | Purpose |
|--------|---------|
| `anki_data` | Anki profile, collection, media |
| `imports` | Shared directory for `.apkg` file hand-off between bot and Anki |
