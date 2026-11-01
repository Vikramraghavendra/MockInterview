import json
import os
import uuid
from collections import defaultdict, deque
from typing import Any

import redis


class RedisStore:
    def __init__(self, url: str):
        self.client = redis.Redis.from_url(url, decode_responses=True)

    def create_session(self, domain_id: str) -> dict[str, str]:
        session_id = str(uuid.uuid4())
        session = {"session_id": session_id, "domain_id": domain_id, "status": "ACTIVE"}
        self.client.hset(f"session:{session_id}", mapping=session)
        return session

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        session = self.client.hgetall(f"session:{session_id}")
        if not session:
            return None
        result = self.client.get(f"session:{session_id}:result")
        if result:
            session["result"] = json.loads(result)
        return session

    def append_code(self, session_id: str, event: dict[str, Any]) -> None:
        self.client.rpush(f"session:{session_id}:code", json.dumps(event))

    def get_code(self, session_id: str) -> list[dict[str, Any]]:
        return [json.loads(item) for item in self.client.lrange(f"session:{session_id}:code", 0, -1)]

    def append_audio(self, session_id: str, item: dict[str, Any]) -> None:
        self.client.rpush(f"session:{session_id}:audio_manifest", json.dumps(item))

    def get_audio(self, session_id: str) -> list[dict[str, Any]]:
        return [json.loads(item) for item in self.client.lrange(f"session:{session_id}:audio_manifest", 0, -1)]

    def begin_processing(self, session_id: str, job: dict[str, Any]) -> None:
        with self.client.pipeline(transaction=True) as pipe:
            pipe.hset(f"session:{session_id}", "status", "PROCESSING")
            pipe.rpush("queue:processing_jobs", json.dumps(job))
            pipe.execute()

    def set_status(self, session_id: str, status: str) -> None:
        self.client.hset(f"session:{session_id}", "status", status)

    def save_result(self, session_id: str, result: dict[str, Any]) -> None:
        self.client.set(f"session:{session_id}:result", json.dumps(result))

    def next_job(self, timeout: int = 5) -> dict[str, Any] | None:
        queued = self.client.blpop("queue:processing_jobs", timeout=timeout)
        return json.loads(queued[1]) if queued else None


class MemoryStore:
    """Small in-process store for API tests and local demos without Redis."""

    def __init__(self):
        self.sessions: dict[str, dict[str, Any]] = {}
        self.code: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.audio: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.jobs: deque[dict[str, Any]] = deque()

    def create_session(self, domain_id: str) -> dict[str, str]:
        session_id = str(uuid.uuid4())
        session = {"session_id": session_id, "domain_id": domain_id, "status": "ACTIVE"}
        self.sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        session = self.sessions.get(session_id)
        return dict(session) if session else None

    def append_code(self, session_id: str, event: dict[str, Any]) -> None:
        self.code[session_id].append(event)

    def get_code(self, session_id: str) -> list[dict[str, Any]]:
        return list(self.code[session_id])

    def append_audio(self, session_id: str, item: dict[str, Any]) -> None:
        self.audio[session_id].append(item)

    def get_audio(self, session_id: str) -> list[dict[str, Any]]:
        return list(self.audio[session_id])

    def begin_processing(self, session_id: str, job: dict[str, Any]) -> None:
        self.sessions[session_id]["status"] = "PROCESSING"
        self.jobs.append(job)

    def set_status(self, session_id: str, status: str) -> None:
        self.sessions[session_id]["status"] = status

    def save_result(self, session_id: str, result: dict[str, Any]) -> None:
        self.sessions[session_id]["result"] = result

    def next_job(self, timeout: int = 5) -> dict[str, Any] | None:
        return self.jobs.popleft() if self.jobs else None


_store: RedisStore | MemoryStore | None = None


def get_store() -> RedisStore | MemoryStore:
    global _store
    if _store is None:
        if os.getenv("STORAGE_BACKEND", "redis") == "memory":
            _store = MemoryStore()
        else:
            _store = RedisStore(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    return _store


def reset_store() -> None:
    global _store
    _store = None