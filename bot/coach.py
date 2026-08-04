"""Turn Anki deck stats into a coaching report via the Claude API."""

import json
import logging
import os
import re

import anthropic

log = logging.getLogger(__name__)

MODEL = "claude-opus-5"
_MAX_REPORT_CHARS = 4000  # Telegram's hard limit is 4096.

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()

_client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None

_SYSTEM_PROMPT = """\
You are an expert Anki coach specializing in language learning. Analyze the \
provided stats and give a concise, actionable report covering:
1. Overall health of the deck
2. Sustainability of the current pace
3. Retention quality
4. Specific things to change
5. One priority action this week

Be direct, specific to the numbers provided, and avoid generic advice. Cite \
the actual figures rather than restating the whole stats blob.

All active-deck metrics (card_counts, intervals, ease, lapses, due_forecast) \
exclude suspended cards, so they describe only the material actually in \
rotation. When a "suspended_detail" block is present it describes cards pulled \
out of rotation — typically leeches Anki auto-suspended at 8 lapses. Treat it \
as a separate backlog, not another bucket of the active deck: if its count is \
large relative to card_counts.mature, raise it under «⚠️ Проблемы» and suggest \
rewriting or deleting those cards. Note that retention percentages are computed \
from the raw review log and therefore still include reviews of cards that have \
since been suspended.

Write the entire report in Russian. The stats are given in English, but your \
response must be in natural, idiomatic Russian — use standard Anki terminology \
as Russian-speaking users know it («новые», «повторения», «интервал», \
«удержание», «лёгкость»). Do not translate the section headers below; use them \
exactly as written.

Format the report in exactly these five sections, in this order, using \
these emoji headers verbatim:

📊 Состояние колоды
⚠️ Проблемы
✅ Что работает хорошо
🎯 Приоритет на неделю
💡 Быстрые советы

Formatting rules (this is rendered in Telegram's legacy Markdown, not \
standard Markdown):
- Use single asterisks for bold (*like this*), never double asterisks.
- Use "•" for bullet points, never "-" or "#".
- No headers (#), no tables, no code fences.
- Keep the whole report under 2500 characters.
"""


class NotConfigured(Exception):
    """Raised when ANTHROPIC_API_KEY is unset."""


async def analyse(stats: dict, previous: dict | None, deck: str) -> str:
    if _client is None:
        raise NotConfigured("ANTHROPIC_API_KEY is not set.")

    parts = [f"Here are my Anki stats for my {deck} deck:", json.dumps(stats)]
    # Only compare snapshots that mean the same thing. A stored blob from an
    # older schema was computed differently, so diffing it would report a large
    # phantom change that is really just the measurement changing underneath.
    if previous and previous.get("schema") == stats.get("schema"):
        parts.append(
            "For comparison, here are my stats from the previous /analyse run "
            "— call out anything that changed:"
        )
        parts.append(json.dumps(previous))
    user_message = "\n\n".join(parts)

    response = await _client.messages.create(
        model=MODEL,
        max_tokens=8000,
        output_config={"effort": "medium"},
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    if response.stop_reason == "refusal":
        log.warning("Claude declined the /analyse request (stop_details=%s)", response.stop_details)
        return "Claude отказался анализировать эту статистику. Попробуйте позже."

    text = "".join(block.text for block in response.content if block.type == "text")
    return text.strip()


def to_telegram_markdown(text: str) -> str:
    """Sanitize Claude's output for Telegram's legacy Markdown parse mode."""
    text = re.sub(r"\*\*(.+?)\*\*", r"*\1*", text)
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^[-]\s+", "• ", text, flags=re.MULTILINE)
    return text.strip()


def split_for_telegram(text: str, limit: int = _MAX_REPORT_CHARS) -> list[str]:
    """Split a report into Telegram-sized chunks on paragraph boundaries."""
    if len(text) <= limit:
        return [text]

    chunks = []
    current = ""
    for paragraph in text.split("\n\n"):
        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) > limit and current:
            chunks.append(current)
            current = paragraph
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks
