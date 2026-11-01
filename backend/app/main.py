import os
import uuid
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.domains import get_domain, public_domains
from app.schemas import CodeEventRequest, SessionStartRequest, SessionSubmitRequest
from app.storage import MemoryStore, RedisStore, get_store


app = FastAPI(title="InterviewRunway", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173").split(","),
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def _active_session(store: RedisStore | MemoryStore, session_id: str) -> dict[str, Any]:
    session = store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    if session.get("status") != "ACTIVE":
        raise HTTPException(status_code=409, detail="Session is not accepting new events.")
    return session


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/domains")
def domains() -> list[dict[str, object]]:
    return public_domains()


@app.post("/api/session/start")
def start_session(
    request: SessionStartRequest, store: RedisStore | MemoryStore = Depends(get_store)
) -> dict[str, str]:
    try:
        profile = get_domain(request.domain_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    session = store.create_session(profile.id)
    return {**session, "challenge": profile.challenge, "starter_code": profile.starter_code}


@app.post("/api/session/code/event")
def receive_code_event(
    request: CodeEventRequest, store: RedisStore | MemoryStore = Depends(get_store)
) -> dict[str, str]:
    _active_session(store, request.session_id)
    store.append_code(
        request.session_id,
        {
            "event_type": request.event_type,
            "session_timestamp_ms": request.session_timestamp_ms,
            "data": request.data,
        },
    )
    return {"status": "ACK"}


@app.post("/api/session/audio/chunk")
async def receive_audio_chunk(
    session_id: str = Form(...),
    timestamp_ms: int = Form(..., ge=0),
    chunk: UploadFile = File(...),
    store: RedisStore | MemoryStore = Depends(get_store),
) -> dict[str, str]:
    _active_session(store, session_id)
    payload = await chunk.read()
    if not payload:
        raise HTTPException(status_code=400, detail="Audio chunk is empty.")
    if len(payload) > 8 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Audio chunk exceeds the 8 MB limit.")
    chunk_id = str(uuid.uuid4())
    output_dir = Path(os.getenv("AUDIO_DIR", "/data/sessions")) / session_id / "audio"
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{timestamp_ms}_{chunk_id}.webm"
    path.write_bytes(payload)
    store.append_audio(
        session_id,
        {"timestamp_ms": timestamp_ms, "file_path": str(path), "content_type": chunk.content_type},
    )
    return {"status": "ACK"}


@app.post("/api/session/submit")
def submit_session(
    request: SessionSubmitRequest,
    background_tasks: BackgroundTasks,
    store: RedisStore | MemoryStore = Depends(get_store),
) -> dict[str, str]:
    session = _active_session(store, request.session_id)
    store.append_code(
        request.session_id,
        {
            "event_type": "CODE_SNAPSHOT",
            "session_timestamp_ms": request.duration_ms,
            "data": {"text_inserted": "", "final_code": request.final_code},
        },
    )
    job = {
        "job_id": str(uuid.uuid4()),
        "session_id": request.session_id,
        "domain_id": session["domain_id"],
        "language": get_domain(session["domain_id"]).language,
        "duration_ms": request.duration_ms,
        "hints_used": request.hints_used,
    }
    store.begin_processing(request.session_id, job)
    if isinstance(store, MemoryStore):
        from app.worker import process_job

        background_tasks.add_task(process_job, store, job)
    return {"status": "PROCESSING", "job_id": job["job_id"]}


@app.get("/api/session/{session_id}")
def session_status(
    session_id: str, store: RedisStore | MemoryStore = Depends(get_store)
) -> dict[str, Any]:
    session = store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    return session


@app.get("/api/session/{session_id}/download-card")
def download_card(
    session_id: str, store: RedisStore | MemoryStore = Depends(get_store)
) -> FileResponse:
    session = store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    card_path = Path(os.getenv("AUDIO_DIR", "/data/sessions")) / session_id / "share_card.png"
    if not card_path.is_file():
        raise HTTPException(status_code=404, detail="Share card is not ready.")
    return FileResponse(card_path, media_type="image/png", filename="interviewrunway-review.png")


@app.get("/api/session/{session_id}/timeline")
def session_timeline(
    session_id: str, store: RedisStore | MemoryStore = Depends(get_store)
) -> dict[str, Any]:
    session = store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    result = session.get("result")
    if not result:
        raise HTTPException(status_code=409, detail="Analysis is not ready.")
    return {"timeline": result["timeline"], "report": result["report"]}