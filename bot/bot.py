import asyncio
import logging
import os
from pathlib import Path

import aiohttp
from telegram import Update
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

def _parse_cards(text: str) -> list[dict]:
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
            translation, _, comment = back.partition(" | ")
            back = f"{translation.strip()}<br><br><i>{comment.strip()}</i>"
        notes.append({
            "deckName": DEFAULT_DECK,
            "modelName": "Basic",
            "fields": {"Front": front, "Back": back},
            "tags": ["telegram"],
        })
    return notes


# ── Handlers ─────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _allowed(update):
        return
    await update.message.reply_text(
        "*Anki Import Bot*\n\n"
        "Send me:\n"
        "• `.apkg` file — imports an Anki package\n"
        "• `.txt` / `.csv` file — tab-separated `Front<TAB>Back` per line; "
        "optional ` | comment` after Back becomes a styled note\n"
        "• Plain text `Question::Answer` — adds a single card\n\n"
        f"Default deck: *{DEFAULT_DECK}*\n\n"
        "Commands:\n"
        "/sync — trigger AnkiWeb sync\n"
        "/decks — list available decks",
        parse_mode="Markdown",
    )


async def cmd_sync(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _allowed(update):
        return
    await update.message.reply_text("Syncing with AnkiWeb…")
    result = await _anki("sync")
    if result.get("error"):
        await update.message.reply_text(f"Sync error: {result['error']}")
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
        raw = await tg_file.download_as_bytearray()
        text = raw.decode("utf-8", errors="replace")
        notes = _parse_cards(text)

        if not notes:
            await update.message.reply_text("No valid `Front::Back` lines found in file.")
            return

        result = await _anki("addNotes", notes=notes)
        if result.get("error"):
            await update.message.reply_text(f"Error: {result['error']}")
            return

        added = sum(1 for n in (result.get("result") or []) if n is not None)
        await update.message.reply_text(
            f"Added *{added}/{len(notes)}* cards to *{DEFAULT_DECK}*.",
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
        "modelName": "Basic",
        "fields": {"Front": front.strip(), "Back": back.strip()},
        "tags": ["telegram"],
    }

    result = await _anki("addNote", note=note)
    if result.get("error"):
        await update.message.reply_text(f"Failed: {result['error']}")
        return

    await update.message.reply_text(
        f"Card added to *{DEFAULT_DECK}*.", parse_mode="Markdown"
    )
    await _sync_quietly()


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    IMPORTS_DIR.mkdir(parents=True, exist_ok=True)

    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler(["start", "help"], cmd_start))
    app.add_handler(CommandHandler("sync", cmd_sync))
    app.add_handler(CommandHandler("decks", cmd_decks))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    log.info("Bot polling…  allowed_users=%s  deck=%s", ALLOWED_USER_IDS or "all", DEFAULT_DECK)
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
