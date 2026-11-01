import json
import os
from typing import Any

import httpx

from app.domains import get_domain, inject_domain_context_to_llm


def _evaluation_flags(profile, timeline: list[dict[str, Any]], rubric: list[dict[str, Any]], has_transcript: bool) -> list[dict[str, Any]]:
    flags = []
    code_events = [
        event
        for event in timeline
        if event.get("event_type") == "CODE_MUTATION"
        and (
            (event.get("data") or {}).get("text_inserted")
            or (event.get("data") or {}).get("text_deleted_length", 0) > 0
        )
    ]
    if code_events:
        first_code_ms = min(int(event.get("session_timestamp_ms", 0)) for event in code_events)
        if first_code_ms < profile.scope_window_ms:
            flags.append({
                "code": "STRUCTURAL_PREMATURE_IMPLEMENTATION",
                "title": "Implementation started before the scope window",
                "detail": "Code activity began before the five-minute scope and clarification window.",
                "timestamp_ms": first_code_ms,
            })

    if has_transcript:
        for index, item in enumerate(rubric):
            if item.get("met"):
                continue
            phase = profile.rubric_phases[min(index, len(profile.rubric_phases) - 1)]
            flags.append({
                "code": "RUBRIC_EXPECTATION_NOT_OBSERVED",
                "title": "Domain expectation not observed",
                "phase": phase.name,
                "detail": item["expectation"],
            })
    return flags


def _normalize_rubric(profile, candidate_rubric: Any, fallback_rubric: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(candidate_rubric, list):
        return fallback_rubric
    normalized = []
    for index, expectation in enumerate(profile.expectations):
        candidate = candidate_rubric[index] if index < len(candidate_rubric) else {}
        if not isinstance(candidate, dict):
            candidate = {}
        normalized.append({
            "expectation": expectation,
            "met": bool(candidate.get("met", fallback_rubric[index]["met"])),
            "evidence": str(candidate.get("evidence", fallback_rubric[index]["evidence"]))[:500],
        })
    return normalized


def _fallback_evaluation(domain_id: str, timeline: list[dict[str, Any]], metrics: dict[str, Any]) -> dict[str, Any]:
    profile = get_domain(domain_id)
    spoken_text = " ".join(
        str(event.get("word", ""))
        for event in timeline
        if event.get("event_type") == "SPEECH_TOKEN"
    ).lower()
    checks = [any(term in spoken_text for term in group) for group in profile.evidence_terms]
    if not spoken_text:
        checks = [False, False, False]
    score = round(sum(checks) / len(checks) * 100) if spoken_text else None
    syntax_terms = ("typing", "semicolon", "bracket", "variable name", "initializing")
    strategic_terms = ("because", "tradeoff", "constraint", "scale", "performance", "edge case")
    syntax_count = sum(spoken_text.count(term) for term in syntax_terms)
    strategic_count = sum(spoken_text.count(term) for term in strategic_terms)
    classification = (
        "STRATEGIC_THINKER" if strategic_count >= syntax_count else "SYNTAX_NARRATOR"
    ) if spoken_text else "NOT_ENOUGH_DATA"
    rubric = [
        {
            "expectation": expectation,
            "met": checks[index],
            "evidence": "Keyword evidence in transcript" if checks[index] else "No transcript evidence detected",
        }
        for index, expectation in enumerate(profile.expectations)
    ]
    return {
        "communication_score": score,
        "structural_classification": classification,
        "assumption_validation": checks[0],
        "rubric": rubric,
        "critique_summary": (
            "No transcript was available, so communication scoring was withheld."
            if not spoken_text
            else "Local heuristic evaluation; configure Ollama for contextual feedback."
        ),
        "interaction_metrics": metrics,
        "evaluation_flags": _evaluation_flags(profile, timeline, rubric, bool(spoken_text)),
        "evaluator": "heuristic_fallback",
    }


def evaluate_timeline(
    domain_id: str, timeline: list[dict[str, Any]], metrics: dict[str, Any]
) -> dict[str, Any]:
    profile = get_domain(domain_id)
    fallback = _fallback_evaluation(domain_id, timeline, metrics)
    transcript = " ".join(
        str(event.get("word", ""))
        for event in timeline
        if event.get("event_type") == "SPEECH_TOKEN"
    )
    if not transcript.strip():
        fallback["evaluator"] = "not_scored (no transcript available)"
        return fallback
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    model = os.getenv("OLLAMA_MODEL", "qwen3:8b")
    compact_events = [
        {
            "time_ms": event["session_timestamp_ms"],
            "type": event["event_type"],
            "word": event.get("word"),
            "code": (event.get("data") or {}).get("text_inserted", "")[:180],
            "silence_ms": event.get("gap_duration_ms"),
        }
        for event in timeline[-120:]
    ]
    system_prompt = " ".join((
        "You are a fair technical interview coach. Use only evidence in the transcript and timeline. Do not infer missing behavior.",
        "Return valid JSON with communication_score (0-100), structural_classification (STRATEGIC_THINKER or SYNTAX_NARRATOR), assumption_validation (boolean), rubric (one object per expectation with expectation, met, evidence), and critique_summary (string).",
        inject_domain_context_to_llm(domain_id),
    ))
    prompt = {
        "domain": profile.name,
        "subtrack": profile.subtrack,
        "knowledge_base": profile.knowledge_base,
        "expectations": profile.expectations,
        "rubric_phases": [
            {"name": phase.name, "window": phase.window, "checks": phase.checks}
            for phase in profile.rubric_phases
        ],
        "question_bank": profile.question_bank,
        "preparation_materials": profile.preparation_materials,
        "transcript": transcript[:12000],
        "timeline": compact_events,
        "interaction_metrics": metrics,
    }
    try:
        response = httpx.post(
            f"{base_url}/api/chat",
            json={
                "model": model,
                "stream": False,
                "format": "json",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": json.dumps(prompt)},
                ],
                "options": {"temperature": 0.1},
            },
            timeout=httpx.Timeout(72, connect=3),
        )
        response.raise_for_status()
        parsed = json.loads(response.json()["message"]["content"])
        classification = str(parsed.get("structural_classification", "")).upper()
        if classification not in {"STRATEGIC_THINKER", "SYNTAX_NARRATOR", "NOT_ENOUGH_DATA"}:
            classification = fallback["structural_classification"]
        response_score = parsed.get("communication_score", fallback["communication_score"])
        score = max(0, min(100, int(response_score))) if response_score is not None else None
        rubric = _normalize_rubric(profile, parsed.get("rubric"), fallback["rubric"])
        return {
            **fallback,
            "communication_score": score,
            "structural_classification": classification,
            "assumption_validation": bool(parsed.get("assumption_validation", fallback["assumption_validation"])),
            "rubric": rubric,
            "evaluation_flags": _evaluation_flags(profile, timeline, rubric, True),
            "critique_summary": str(parsed.get("critique_summary", fallback["critique_summary"]))[:1200],
            "evaluator": f"ollama:{model}",
        }
    except (httpx.HTTPError, KeyError, ValueError, TypeError):
        fallback["evaluator"] = f"heuristic_fallback (Ollama model '{model}' unavailable or invalid response)"
        return fallback