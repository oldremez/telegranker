# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
cp .env.example .env          # then set TELEGRAM_BOT_TOKEN
docker compose up -d --build  # rebuild after any bot/ change
docker compose logs -f bot    # bot logs (INFO level, stdout unbuffered)
docker compose logs -f anki   # Anki/AnkiConnect startup, addon install
docker compose down -v        # wipe volumes, start fresh
```

There is **no test suite, linter, or CI** in this repo. The practical verification loop is:

```bash
# 1. Syntax check (the bot's own deps aren't installed on the host)
cd bot && python3 -m py_compile *.py

# 2. anki_stats.py / state.py / coach.py import standalone (no `telegram` dep)
#    — they can be unit-tested against fake AnkiConnect callables without Docker
python3 -c "import anki_stats, state, coach"

# 3. Probe what this AnkiConnect build actually supports before relying on an action
curl -s localhost:8765 -d '{"action":"apiReflect","version":6,"params":{"scopes":["actions"]}}'
```

Step 3 matters: `getDeckStats` was used in commit `97a1623` and replaced with `findCards` queries in
`489470a` because it misbehaved on this image. Do not assume an action exists — probe it, and give
every new AnkiConnect call a fallback.

## Architecture

```
Telegram ──> bot container ──JSON-RPC──> AnkiConnect :8765 ──> headless Anki (Xvfb + x11vnc :5900)
                                                                        ↕
                                                                    AnkiWeb sync
```

Two compose services. `bot` waits on `anki`'s healthcheck (90s start period — AnkiConnect installs
itself on first boot via `anki/bootstrap.sh`). **The bot has no access to the Anki collection except
through AnkiConnect HTTP** — no genanki, no `.apkg` generation, no sqlite. `anki/auto_sync_login/`
is an Anki add-on (runs *inside* the anki container, imports `aqt`) that logs into AnkiWeb headlessly
on profile open and force-disables Anki's own autoSync, which crashes headless when a full sync is
required.

### `bot/` module split

| File | Role |
|---|---|
| `bot.py` | Handlers, command registry, `_anki()` transport, `main()` |
| `anki_stats.py` | `collect(anki, deck)` → stats dict for `/analyse` |
| `coach.py` | Claude API call + Telegram-markdown helpers |
| `state.py` | Rate limit + trend snapshot (stored *in Anki*, see below) |

The three non-`bot.py` modules take `_anki` as an injected callable rather than importing `bot.py`
— that avoids a circular import and lets them be tested against fakes.

### Everything goes through `_anki()`

`_anki(action, **params)` ([bot.py](bot/bot.py)) is the only outbound path to Anki. It posts
AnkiConnect API **version 6** and returns the raw envelope:

```python
{"result": <payload>, "error": None}   # or {"result": None, "error": "..."}
```

**Errors arrive in the payload, not as exceptions** — always check `result.get("error")` before
reading `result["result"]`. Connection failures are caught and returned in that same shape, so
callers never see an `aiohttp` exception. Each call opens its own `ClientSession`, so batch
multiple queries into one `multi` action rather than looping (see `anki_stats._multi`, which falls
back to sequential calls if `multi` is unavailable).

### Adding a command

Append one `Command(name, description, handler)` to the `COMMANDS` list in `bot.py`. Help text
(`cmd_help`) and BotFather registration (`_post_init`) are both derived from that list — no other
registration step. Handlers are `async def h(update, ctx) -> None` and start with
`if not _allowed(update): return`.

Use `_Responder(update)` for anything that sends more than one message: its first `send()` replies
to the triggering message, subsequent ones are plain chat sends.

### The bot container is deliberately stateless

`/analyse`'s rate limit and previous-run snapshot are stored **inside the Anki collection** as a
media file `_telegranker.json` (`storeMediaFile`/`retrieveMediaFile`), not in a Docker volume. The
leading underscore is Anki's documented convention for add-on/template-owned media, so "Check Media"
never flags it as unused, and it syncs to AnkiWeb with everything else. Do not introduce a state
volume or local file without a specific reason — `state.py` is the intended place for anything
that must outlive a request, and a missing or corrupt state file must degrade to `{}`, never break
a command.

## Gotchas

**Quote deck names in search queries.** `deck:"{deck}"` — an unquoted `deck:{d}` silently breaks on
any deck whose name contains a space. Deck search includes subdecks.

**Telegram uses legacy Markdown parse mode**, not CommonMark. `**bold**`, `#` headers, tables, and
code fences all raise `BadRequest`. Use `*bold*` / `_italic_` / `•` bullets. For LLM-generated text,
run it through `coach.to_telegram_markdown()` and send via a try/`except BadRequest` that resends
with `parse_mode=None`. Message limit is 4096 chars (`coach.split_for_telegram` splits at 4000).

**`addNotes` reports duplicates as `None`** in its returned id list rather than erroring — zip the
returned ids against the notes you sent to tell added from skipped (see `handle_text`).

**`sync` returning `"Sync status 2"`** means a full sync is required; this cannot be resolved
headlessly and needs the VNC flow (port 5900, no password). `cmd_sync` special-cases this message.

**Claude API**: the model is `claude-opus-5`. `temperature`, `top_p`, `top_k`, and
`thinking.budget_tokens` all return 400 on it — use `output_config={"effort": ...}` instead.
Thinking is on by default and shares the `max_tokens` budget with the response text, so keep
`max_tokens` generous. Check `stop_reason == "refusal"` before reading `response.content`.
`/analyse` degrades to a clear message when `ANTHROPIC_API_KEY` is unset rather than failing.

## Environment

Set in `.env` (gitignored), injected via `docker-compose.yml`. Note `DEFAULT_DECK` defaults to
`Imported` in `bot.py` but compose overrides it to `Greek`.

| Variable | Purpose |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Required — the bot exits without it |
| `ALLOWED_USER_IDS` | Comma-separated numeric IDs; **empty means everyone is allowed** |
| `ANKIWEB_EMAIL` / `ANKIWEB_PASSWORD` | Optional headless sync login |
| `ANTHROPIC_API_KEY` | Optional; gates `/analyse` |
| `DEFAULT_DECK` | Target deck for all imports and stats |
