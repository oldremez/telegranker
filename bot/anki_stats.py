"""Aggregate Anki deck statistics via AnkiConnect for /analyse.

Collects card composition, retention, answer-button distribution, interval
and ease distributions, review load, and study streaks into a compact dict
suitable for passing to an LLM. Every section degrades gracefully: if an
AnkiConnect action is missing or errors, that section is omitted and a note
is appended to ``unavailable`` rather than failing the whole command.
"""

import statistics
import time
from typing import Any, Awaitable, Callable

AnkiCall = Callable[..., Awaitable[dict]]

_DAY_MS = 24 * 60 * 60 * 1000
_FORECAST_DAYS = (1, 3, 7, 14, 30)
_INTERVAL_BUCKETS = (
    ("1d", 0, 1),
    ("2-7d", 2, 7),
    ("8-21d", 8, 21),
    ("22-60d", 22, 60),
    ("61-180d", 61, 180),
    ("180d+", 181, float("inf")),
)


def _round(value: float, digits: int = 1) -> float:
    return round(value, digits)


async def _multi(anki: AnkiCall, actions: list[dict]) -> list[dict]:
    """Run a batch of AnkiConnect actions via the `multi` action.

    Falls back to sequential calls if `multi` isn't available on this
    AnkiConnect build.
    """
    result = await anki("multi", actions=actions)
    if not result.get("error"):
        return result.get("result") or []
    results = []
    for action in actions:
        results.append(await anki(action["action"], **action.get("params", {})))
    return results


async def collect(anki: AnkiCall, deck: str) -> dict[str, Any]:
    stats: dict[str, Any] = {"deck": deck, "unavailable": []}

    counts = await _collect_counts(anki, deck, stats)
    if counts is None:
        stats["error"] = "Could not query card counts from Anki."
        return stats
    stats["card_counts"] = counts

    await _collect_forecast(anki, deck, stats)
    await _collect_intervals_and_ease(anki, deck, stats)
    await _collect_reviews(anki, deck, stats)
    await _collect_streak(anki, deck, stats)

    return stats


async def _collect_counts(anki: AnkiCall, deck: str, stats: dict) -> dict | None:
    d = deck.replace('"', '\\"')
    queries = {
        "new": f'deck:"{d}" is:new',
        "learning": f'deck:"{d}" is:learn',
        "young": f'deck:"{d}" is:review -is:learn prop:ivl<21',
        "mature": f'deck:"{d}" prop:ivl>=21',
        "suspended": f'deck:"{d}" is:suspended',
        "due_today": f'deck:"{d}" is:due',
        "total": f'deck:"{d}"',
    }
    actions = [{"action": "findCards", "params": {"query": q}} for q in queries.values()]
    results = await _multi(anki, actions)
    if len(results) != len(queries) or any(r.get("error") for r in results):
        return None
    return {key: len(r.get("result") or []) for key, r in zip(queries.keys(), results)}


async def _collect_forecast(anki: AnkiCall, deck: str, stats: dict) -> None:
    d = deck.replace('"', '\\"')
    try:
        actions = [
            {"action": "findCards", "params": {"query": f'deck:"{d}" prop:due<={n}'}}
            for n in _FORECAST_DAYS
        ]
        results = await _multi(anki, actions)
        if any(r.get("error") for r in results):
            raise ValueError(results)
        cumulative = [len(r.get("result") or []) for r in results]
        forecast = {}
        prev = 0
        for day, total in zip(_FORECAST_DAYS, cumulative):
            forecast[f"by_day_{day}"] = total
            prev = total
        stats["due_forecast_30d"] = forecast
    except Exception:
        stats["unavailable"].append("due_forecast")


async def _collect_intervals_and_ease(anki: AnkiCall, deck: str, stats: dict) -> None:
    d = deck.replace('"', '\\"')
    try:
        found = await anki("findCards", query=f'deck:"{d}" -is:new')
        if found.get("error"):
            raise ValueError(found["error"])
        card_ids = found.get("result") or []
        if not card_ids:
            stats["intervals"] = {"note": "no reviewed cards yet"}
            return

        info = await anki("cardsInfo", cards=card_ids)
        if info.get("error"):
            raise ValueError(info["error"])
        cards = info.get("result") or []

        intervals = [c["interval"] for c in cards if c.get("interval", 0) > 0]
        eases = [c["factor"] / 10 for c in cards if c.get("factor")]
        lapses = [c.get("lapses", 0) for c in cards]

        histogram = {label: 0 for label, _, _ in _INTERVAL_BUCKETS}
        for ivl in intervals:
            for label, lo, hi in _INTERVAL_BUCKETS:
                if lo <= ivl <= hi:
                    histogram[label] += 1
                    break

        stats["intervals"] = {
            "median_days": _round(statistics.median(intervals)) if intervals else 0,
            "mean_days": _round(statistics.mean(intervals)) if intervals else 0,
            "histogram": histogram,
        }
        stats["ease"] = {
            "median_percent": _round(statistics.median(eases)) if eases else 0,
            "low_ease_count": sum(1 for e in eases if e < 230),
            "low_ease_threshold_percent": 230,
        }
        stats["lapses"] = {
            "total": sum(lapses),
            "cards_with_3plus_lapses": sum(1 for l in lapses if l >= 3),
        }
    except Exception:
        stats["unavailable"].append("intervals_ease_lapses")


async def _collect_reviews(anki: AnkiCall, deck: str, stats: dict) -> None:
    start_id = int(time.time() * 1000) - 30 * _DAY_MS
    try:
        result = await anki("cardReviews", deck=deck, startID=start_id)
        if result.get("error"):
            raise ValueError(result["error"])
        rows = result.get("result") or []
        if not rows:
            stats["reviews_30d"] = {"note": "no reviews in the last 30 days"}
            return
        _summarize_reviews(rows, stats)
    except Exception:
        stats["unavailable"].append("review_history")


def _summarize_reviews(rows: list, stats: dict) -> None:
    # row: [reviewTime, cardId, usn, buttonPressed, newInterval,
    #       previousInterval, newFactor, reviewDuration, reviewType]
    button_counts = {1: 0, 2: 0, 3: 0, 4: 0}
    young_pass = young_total = mature_pass = mature_total = 0
    per_day: dict[str, int] = {}
    total_duration_ms = 0

    for row in rows:
        review_time, _card_id, _usn, button, _new_ivl, prev_ivl, _new_factor, duration, review_type = row[:9]
        total_duration_ms += duration or 0

        day = time.strftime("%Y-%m-%d", time.localtime(review_time / 1000))
        per_day[day] = per_day.get(day, 0) + 1

        if review_type == 1 and button in button_counts:
            button_counts[button] += 1

        if review_type == 1 and prev_ivl > 0:
            passed = button != 1
            if prev_ivl < 21:
                young_total += 1
                young_pass += int(passed)
            else:
                mature_total += 1
                mature_pass += int(passed)

    total_buttons = sum(button_counts.values()) or 1
    stats["answer_distribution"] = {
        "again_pct": _round(100 * button_counts[1] / total_buttons),
        "hard_pct": _round(100 * button_counts[2] / total_buttons),
        "good_pct": _round(100 * button_counts[3] / total_buttons),
        "easy_pct": _round(100 * button_counts[4] / total_buttons),
    }
    stats["retention"] = {
        "young_pct": _round(100 * young_pass / young_total) if young_total else None,
        "mature_pct": _round(100 * mature_pass / mature_total) if mature_total else None,
    }

    counts = list(per_day.values())
    stats["reviews_per_day_30d"] = {
        "mean": _round(statistics.mean(counts)) if counts else 0,
        "max": max(counts) if counts else 0,
        "days_with_reviews": len(counts),
        "total_reviews": sum(counts),
    }
    stats["study_time"] = {
        "avg_minutes_per_active_day": _round(
            total_duration_ms / 1000 / 60 / len(counts)
        )
        if counts
        else 0,
        "avg_seconds_per_card": _round(total_duration_ms / 1000 / len(rows)) if rows else 0,
    }


async def _collect_streak(anki: AnkiCall, deck: str, stats: dict) -> None:
    try:
        result = await anki("getNumCardsReviewedByDay")
        if result.get("error"):
            raise ValueError(result["error"])
        rows = result.get("result") or []
        if not rows:
            stats["streak"] = {"current_days": 0, "longest_days": 0}
            return

        dates = sorted(row[0] for row in rows)
        date_set = set(dates)

        longest = current_run = 1
        for i in range(1, len(dates)):
            prev_day = time.mktime(time.strptime(dates[i - 1], "%Y-%m-%d"))
            this_day = time.mktime(time.strptime(dates[i], "%Y-%m-%d"))
            if this_day - prev_day == 86400:
                current_run += 1
            else:
                current_run = 1
            longest = max(longest, current_run)

        today = time.strftime("%Y-%m-%d")
        yesterday = time.strftime("%Y-%m-%d", time.localtime(time.time() - 86400))
        streak = 0
        cursor = today if today in date_set else (yesterday if yesterday in date_set else None)
        if cursor:
            while cursor in date_set:
                streak += 1
                cursor = time.strftime(
                    "%Y-%m-%d", time.localtime(time.mktime(time.strptime(cursor, "%Y-%m-%d")) - 86400)
                )

        recent_30 = sum(1 for d in dates if d >= time.strftime("%Y-%m-%d", time.localtime(time.time() - 30 * 86400)))
        stats["streak"] = {
            "current_days": streak,
            "longest_days": longest,
            "days_studied_last_30": recent_30,
        }
    except Exception:
        stats["unavailable"].append("streak")
