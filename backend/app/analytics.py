from collections.abc import Iterable
from typing import Any


SILENCE_THRESHOLD_MS = 12_000


def align_timeline(
    code_events: Iterable[dict[str, Any]],
    speech_tokens: Iterable[dict[str, Any]],
    duration_ms: int | None = None,
) -> list[dict[str, Any]]:
    timeline = []
    for event in code_events:
        if event.get("event_type") == "CODE_SNAPSHOT":
            continue
        if event.get("event_type") == "HINT_USED":
            timeline.append({**event, "event_type": "HINT_USED"})
            continue
        timeline.append({**event, "event_type": "CODE_MUTATION"})
    for token in speech_tokens:
        timeline.append({**token, "event_type": "SPEECH_TOKEN"})
    timeline.sort(key=lambda event: (max(0, int(event.get("session_timestamp_ms", 0))), event["event_type"]))

    last_speech_ms = 0
    silent_code: list[str] = []
    silence_reported = False
    for event in timeline:
        event["session_timestamp_ms"] = max(0, int(event.get("session_timestamp_ms", 0)))
        if event["event_type"] == "SPEECH_TOKEN":
            gap_ms = event["session_timestamp_ms"] - last_speech_ms
            if gap_ms > SILENCE_THRESHOLD_MS and not silence_reported:
                event["silence_warning"] = True
                event["gap_duration_ms"] = gap_ms
                event["code_context"] = "".join(silent_code)[-500:]
            last_speech_ms = event["session_timestamp_ms"]
            silent_code = []
            silence_reported = False
            continue
        if event["event_type"] == "HINT_USED":
            continue

        data = event.get("data") or {}
        inserted = data.get("text_inserted", "")
        if inserted:
            silent_code.append(inserted)
        gap_ms = event["session_timestamp_ms"] - last_speech_ms
        if gap_ms > SILENCE_THRESHOLD_MS and not silence_reported:
            event["silence_warning"] = True
            event["gap_duration_ms"] = gap_ms
            event["code_context"] = "".join(silent_code)[-500:]
            silence_reported = True

    if duration_ms is not None:
        duration_ms = max(0, int(duration_ms))
        trailing_gap_ms = duration_ms - last_speech_ms
        if trailing_gap_ms > SILENCE_THRESHOLD_MS and not silence_reported:
            timeline.append({
                "event_type": "SILENCE_GAP",
                "session_timestamp_ms": last_speech_ms + SILENCE_THRESHOLD_MS,
                "silence_warning": True,
                "gap_duration_ms": trailing_gap_ms,
                "code_context": "".join(silent_code)[-500:],
            })
    timeline.sort(key=lambda event: (event["session_timestamp_ms"], event["event_type"]))
    return timeline


def interaction_metrics(
    code_events: Iterable[dict[str, Any]],
    speech_tokens: Iterable[dict[str, Any]],
    duration_ms: int,
) -> dict[str, Any]:
    code_events = list(code_events)
    speech_tokens = list(speech_tokens)
    minutes = max(duration_ms, 1) / 60_000
    words = sum(len(str(token.get("word", "")).split()) for token in speech_tokens)
    characters = sum(
        len(str((event.get("data") or {}).get("text_inserted", ""))) for event in code_events
    )
    words_per_minute = round(words / minutes, 1)
    characters_per_minute = round(characters / minutes, 1)
    return {
        "spoken_words": words,
        "characters_typed": characters,
        "words_per_minute": words_per_minute,
        "characters_per_minute": characters_per_minute,
        "talk_to_code_velocity_ratio": round(words_per_minute / max(characters_per_minute, 1), 3),
        "dead_air_flags": [
            {
                "timestamp_ms": event["session_timestamp_ms"],
                "duration_ms": event["gap_duration_ms"],
                "code_context": event.get("code_context", ""),
            }
            for event in align_timeline(code_events, speech_tokens, duration_ms)
            if event.get("silence_warning")
        ],
    }