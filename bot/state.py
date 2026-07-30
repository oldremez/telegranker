"""Stateless-bot storage: rate limit + trend snapshot live inside Anki.

Persisted as a media file (`_telegranker.json`) in the Anki collection,
read/written via AnkiConnect's storeMediaFile/retrieveMediaFile actions. The
leading underscore is Anki's documented Check Media exemption, so the file
is never flagged as unused media. This keeps the bot container itself fully
stateless — no volumes, no local files.
"""

import base64
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

AnkiCall = Callable[..., Awaitable[dict]]

log = logging.getLogger(__name__)

_FILENAME = "_telegranker.json"
_MIN_INTERVAL = timedelta(hours=24)

State = dict[str, dict[str, Any]]


async def load(anki: AnkiCall) -> State:
    try:
        result = await anki("retrieveMediaFile", filename=_FILENAME)
        data = result.get("result")
        if not data:
            return {}
        raw = base64.b64decode(data)
        return json.loads(raw)
    except Exception:
        log.warning("Could not load %s from Anki media; starting fresh.", _FILENAME)
        return {}


async def save(anki: AnkiCall, state: State) -> None:
    try:
        payload = base64.b64encode(json.dumps(state).encode("utf-8")).decode("ascii")
        result = await anki(
            "storeMediaFile", filename=_FILENAME, data=payload, deleteExisting=True
        )
        stored_name = result.get("result")
        if result.get("error") or (stored_name and stored_name != _FILENAME):
            log.warning("Unexpected storeMediaFile result for %s: %s", _FILENAME, result)
    except Exception:
        log.warning("Could not save %s to Anki media.", _FILENAME, exc_info=True)


def can_run(state: State, user_id: int) -> tuple[bool, timedelta]:
    entry = state.get(str(user_id))
    if not entry or "last_run" not in entry:
        return True, timedelta(0)
    last_run = datetime.fromisoformat(entry["last_run"])
    elapsed = datetime.now(timezone.utc) - last_run
    if elapsed >= _MIN_INTERVAL:
        return True, timedelta(0)
    return False, _MIN_INTERVAL - elapsed


def previous_stats(state: State, user_id: int) -> dict | None:
    entry = state.get(str(user_id))
    return entry.get("last_stats") if entry else None


async def record(anki: AnkiCall, state: State, user_id: int, stats: dict) -> None:
    state[str(user_id)] = {
        "last_run": datetime.now(timezone.utc).isoformat(),
        "last_stats": stats,
    }
    await save(anki, state)
