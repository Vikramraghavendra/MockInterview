import re
from typing import Any


CONTEST_SIMULATION_METRICS = {
    "round_type": "DSA_INTERVIEW_SERIES",
    "time_allowance_mins": 90,
    "hint_penalty_score": 5,
}

COMPLEXITY_SIGNALS = re.compile(
    r"\b(for|while|sort|sorted|heap|recurs|binary.?search|graph|travers|dynamic.?program|memoiz)\b",
    re.IGNORECASE,
)
COMPLEXITY_EXPLANATIONS = (
    "big o", "complexity", "o(n", "o(log", "o(1", "space", "time bound", "quadratic", "linear time",
)


def analyze_interview_cadence(
    timeline_events: list[dict[str, Any]],
    duration_ms: int,
    hints_used: int | None = None,
) -> dict[str, Any]:
    code_events = [event for event in timeline_events if event.get("event_type") == "CODE_MUTATION"]
    speech_events = [event for event in timeline_events if event.get("event_type") == "SPEECH_TOKEN"]
    hint_events = [event for event in timeline_events if event.get("event_type") == "HINT_USED"]
    hints_used = max(len(hint_events), max(0, int(hints_used or 0)))

    explanations = [
        (int(event.get("session_timestamp_ms", 0)), str(event.get("word", "")).lower())
        for event in speech_events
    ]
    unexplained_spikes = []
    spike_count = 0
    for event in code_events:
        inserted = str((event.get("data") or {}).get("text_inserted", ""))
        if not COMPLEXITY_SIGNALS.search(inserted):
            continue
        spike_count += 1
        timestamp = int(event.get("session_timestamp_ms", 0))
        prior_words = [word for speech_ms, word in explanations if 0 <= timestamp - speech_ms <= 30_000]
        prior_context = " ".join(prior_words)
        if not any(term in prior_context for term in COMPLEXITY_EXPLANATIONS):
            unexplained_spikes.append({
                "code": "UNEXPLAINED_COMPLEXITY_SPIKE",
                "timestamp_ms": timestamp,
                "detail": "Algorithmic structure changed without a nearby time/space complexity explanation.",
            })

    elapsed_ms = max(0, int(duration_ms))
    words = sum(len(str(event.get("word", "")).split()) for event in speech_events)
    elapsed_minutes = max(elapsed_ms / 60_000, 1 / 60)
    penalty_points = max(0, int(hints_used)) * CONTEST_SIMULATION_METRICS["hint_penalty_score"]
    return {
        **CONTEST_SIMULATION_METRICS,
        "elapsed_ms": elapsed_ms,
        "time_remaining_ms": max(0, CONTEST_SIMULATION_METRICS["time_allowance_mins"] * 60_000 - elapsed_ms),
        "hints_used": max(0, int(hints_used)),
        "hint_penalty_points": penalty_points,
        "spoken_words_per_minute": round(words / elapsed_minutes, 1),
        "complexity_spikes": spike_count,
        "cadence_flags": unexplained_spikes,
    }