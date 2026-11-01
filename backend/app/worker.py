import os
from pathlib import Path
from typing import Any

from app.analytics import align_timeline, interaction_metrics
from app.codeguru import check_codeguru_standards
from app.contest import analyze_interview_cadence
from app.evaluator import evaluate_timeline
from app.exporter import generate_social_share_card
from app.storage import MemoryStore, RedisStore, get_store


def transcribe_audio(manifest: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not manifest:
        return []
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return []

    model = WhisperModel(
        os.getenv("WHISPER_MODEL", "small"),
        device=os.getenv("WHISPER_DEVICE", "cpu"),
        compute_type=os.getenv("WHISPER_COMPUTE_TYPE", "int8"),
    )
    tokens = []
    for item in sorted(manifest, key=lambda value: value["timestamp_ms"]):
        path = Path(item["file_path"])
        if not path.is_file():
            continue
        segments, _ = model.transcribe(str(path), word_timestamps=True, vad_filter=True)
        for segment in segments:
            for word in segment.words or []:
                tokens.append(
                    {
                        "session_timestamp_ms": int(item["timestamp_ms"] + word.start * 1000),
                        "word": word.word.strip(),
                        "confidence": round(float(word.probability), 3),
                        "duration_ms": int((word.end - word.start) * 1000),
                    }
                )
    return tokens


def process_job(store: RedisStore | MemoryStore, job: dict[str, Any]) -> dict[str, Any]:
    session_id = job["session_id"]
    store.set_status(session_id, "PROCESSING")
    try:
        code_events = store.get_code(session_id)
        speech_tokens = transcribe_audio(store.get_audio(session_id))
        duration_ms = int(job.get("duration_ms", 0))
        timeline = align_timeline(code_events, speech_tokens, duration_ms)
        metrics = interaction_metrics(code_events, speech_tokens, duration_ms)
        report = evaluate_timeline(job["domain_id"], timeline, metrics)
        final_code = next(
            (
                str((event.get("data") or {}).get("final_code", ""))
                for event in reversed(code_events)
                if event.get("event_type") == "CODE_SNAPSHOT"
            ),
            "",
        )
        report["codeguru_review"] = check_codeguru_standards(
            timeline,
            final_code=final_code,
            language=job.get("language", "python"),
        )
        contest = analyze_interview_cadence(
            timeline,
            duration_ms,
            hints_used=job.get("hints_used"),
        )
        report["contest_simulation"] = contest
        report.setdefault("evaluation_flags", []).extend(contest["cadence_flags"])
        report["share_card_url"] = f"/api/session/{session_id}/download-card"
        card_path = generate_social_share_card(
            session_id, report, os.getenv("AUDIO_DIR", "/data/sessions")
        )
        result = {"report": report, "timeline": timeline, "share_card_path": card_path}
        store.save_result(session_id, result)
        store.set_status(session_id, "COMPLETED")
        return result
    except Exception:
        store.set_status(session_id, "FAILED")
        raise


def run_worker() -> None:
    store = get_store()
    print("[worker] waiting for interview jobs", flush=True)
    while True:
        job = store.next_job(timeout=5)
        if not job:
            continue
        try:
            process_job(store, job)
            print(f"[worker] completed session {job['session_id']}", flush=True)
        except Exception as error:
            print(f"[worker] failed session {job['session_id']}: {error}", flush=True)


if __name__ == "__main__":
    run_worker()