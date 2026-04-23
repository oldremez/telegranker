import logging
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable, Awaitable

import aiohttp
from telegram import Update, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
ANKICONNECT_URL = os.environ.get("ANKI_CONNECT_URL", "http://anki:8765")
IMPORTS_DIR = Path(os.environ.get("IMPORTS_DIR", "/imports"))
DEFAULT_DECK = os.environ.get("DEFAULT_DECK", "Imported")

_raw_ids = os.environ.get("ALLOWED_USER_IDS", "").strip()
ALLOWED_USER_IDS: set[int] = set(int(x) for x in _raw_ids.split(",") if x.strip()) if _raw_ids else set()

Handler = Callable[[Update, ContextTypes.DEFAULT_TYPE], Awaitable[None]]


@dataclass
class Command:
    name: str
    description: str
    handler: Handler


def _allowed(update: Update) -> bool:
    if not ALLOWED_USER_IDS:
        return True
    return update.effective_user.id in ALLOWED_USER_IDS


async def _anki(action: str, **params) -> dict:
    payload = {"action": action, "version": 6, "params": params}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(ANKICONNECT_URL, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                return await resp.json()
    except (aiohttp.ClientConnectorError, aiohttp.ServerConnectionError, TimeoutError, OSError):
        return {"result": None, "error": "Cannot connect to Anki — the container may be down or restarting."}


async def _sync_quietly() -> None:
    try:
        await _anki("sync")
    except Exception as exc:
        log.warning("Sync failed: %s", exc)


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _next_deck_name() -> str:
    base = date.today().isoformat()
    result = await _anki("deckNames")
    existing = set(result.get("result") or [])
    if base not in existing:
        return base
    i = 2
    while f"{base} #{i}" in existing:
        i += 1
    return f"{base} #{i}"


def _parse_cards(text: str, deck_name: str) -> list[dict]:
    notes = []
    for line in text.splitlines():
        line = line.rstrip()
        if not line or line.lstrip().startswith("#") or "\t" not in line:
            continue
        front, _, back = line.partition("\t")
        front = front.strip()
        back = back.strip()
        if not front or not back:
            continue
        if " | " in back:
            back, _, _ = back.partition(" | ")
            back = back.strip()
        notes.append({
            "deckName": deck_name,
            "modelName": "Basic (and reversed card)",
            "fields": {"Front": front, "Back": back},
            "tags": ["telegram"],
            "options": {"allowDuplicate": True},
        })
    return notes


# ── Command handlers ──────────────────────────────────────────────────────────

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _allowed(update):
        return
    lines = [
        "*Anki Import Bot*\n",
        "Send me:",
        "• `.apkg` file — imports an Anki package",
        "• `.txt` / `.csv` file — tab-separated `Front⇥Back` per line; "
        "optional ` | comment` after Back becomes a styled note",
        "• Plain text `Question::Answer` — adds a single card\n",
        f"Default deck: *{DEFAULT_DECK}*\n",
        "*Commands:*",
    ]
    for cmd in COMMANDS:
        lines.append(f"/{cmd.name} — {cmd.description}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_sync(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _allowed(update):
        return
    await update.message.reply_text("Syncing with AnkiWeb…")
    result = await _anki("sync")
    error = result.get("error") or ""
    if "Sync status 2" in error:
        await update.message.reply_text(
            "Full sync required — connect to VNC on port 5900 and click Sync in Anki "
            "to choose Upload or Download. Only needed once after a fresh install."
        )
    elif error:
        await update.message.reply_text(f"Sync error: {error}")
    else:
        await update.message.reply_text("Sync complete.")


async def cmd_decks(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _allowed(update):
        return
    result = await _anki("deckNames")
    if result.get("error"):
        await update.message.reply_text(f"Error: {result['error']}")
        return
    decks = "\n".join(f"• {d}" for d in sorted(result.get("result") or []))
    await update.message.reply_text(f"*Decks:*\n{decks}", parse_mode="Markdown")


# ── Command registry ─────────────────────────────────────────────────────────
# Add new commands here; help text and BotFather registration are automatic.

COMMANDS: list[Command] = [
    Command("help",  "Show this help message",  cmd_help),
    Command("sync",  "Trigger AnkiWeb sync",     cmd_sync),
    Command("decks", "List available decks",     cmd_decks),
]


# ── Message handlers ──────────────────────────────────────────────────────────

async def handle_document(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _allowed(update):
        await update.message.reply_text("Not authorised.")
        return

    doc = update.message.document
    name = doc.file_name or "file"
    ext = Path(name).suffix.lower()

    if ext not in (".apkg", ".txt", ".csv"):
        await update.message.reply_text("Unsupported file type. Send `.apkg`, `.txt`, or `.csv`.")
        return

    await update.message.reply_text(f"Processing *{name}*…", parse_mode="Markdown")
    tg_file = await ctx.bot.get_file(doc.file_id)

    if ext == ".apkg":
        dest = IMPORTS_DIR / name
        await tg_file.download_to_drive(str(dest))
        result = await _anki("importPackage", path=str(dest))
        try:
            dest.unlink(missing_ok=True)
        except OSError:
            pass
        if result.get("error"):
            await update.message.reply_text(f"Import failed: {result['error']}")
            return
        await update.message.reply_text(f"Imported *{name}* successfully.", parse_mode="Markdown")
        await _sync_quietly()

    else:
        deck_name = await _next_deck_name()
        await _anki("createDeck", deck=deck_name)
        raw = await tg_file.download_as_bytearray()
        notes = _parse_cards(raw.decode("utf-8", errors="replace"), deck_name)
        if not notes:
            await update.message.reply_text("No valid `Front⇥Back` lines found in file.")
            return
        result = await _anki("addNotes", notes=notes)
        if result.get("error"):
            await update.message.reply_text(f"Error: {result['error']}")
            return
        added = sum(1 for n in (result.get("result") or []) if n is not None)
        await update.message.reply_text(
            f"Added *{added}/{len(notes)}* cards to *{deck_name}*.",
            parse_mode="Markdown",
        )
        await _sync_quietly()


async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _allowed(update):
        return
    text = (update.message.text or "").strip()
    if "::" not in text:
        await update.message.reply_text("Use `Question::Answer` to add a card.", parse_mode="Markdown")
        return
    front, _, back = text.partition("::")
    note = {
        "deckName": DEFAULT_DECK,
        "modelName": "Basic (and reversed card)",
        "fields": {"Front": front.strip(), "Back": back.strip()},
        "tags": [],
    }
    result = await _anki("addNote", note=note)
    if result.get("error"):
        await update.message.reply_text(f"Failed: {result['error']}")
        return
    await update.message.reply_text(f"Card added to *{DEFAULT_DECK}*.", parse_mode="Markdown")
    await _sync_quietly()


# ── Main ─────────────────────────────────────────────────────────────────────

_CARD_CSS = """html, body { height: 100%; margin: 0; }

.card {
    font-family: Arial, sans-serif;
    font-size: 20px;
    text-align: center;
    color: black;
    background-color: white;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100%;
    padding: 16px;
    box-sizing: border-box;
}"""


async def _post_init(app: Application) -> None:
    await app.bot.set_my_commands([BotCommand(c.name, c.description) for c in COMMANDS])
    log.info("Registered %d commands with BotFather.", len(COMMANDS))
    for model in ("Basic", "Basic (and reversed card)"):
        result = await _anki("updateModelStyling", model={"name": model, "css": _CARD_CSS})
    if result.get("error"):
        log.warning("Could not update card styling: %s", result["error"])
    else:
        log.info("Card styling updated.")


def main() -> None:
    IMPORTS_DIR.mkdir(parents=True, exist_ok=True)

    app = (
        Application.builder()
        .token(TELEGRAM_TOKEN)
        .post_init(_post_init)
        .build()
    )

    for cmd in COMMANDS:
        app.add_handler(CommandHandler(cmd.name, cmd.handler))
    app.add_handler(CommandHandler("start", cmd_help))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    log.info("Bot polling…  allowed_users=%s  deck=%s", ALLOWED_USER_IDS or "all", DEFAULT_DECK)
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
