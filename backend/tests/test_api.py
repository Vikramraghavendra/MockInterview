import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.storage import MemoryStore, get_store


class ApiWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore()
        self.output_dir = tempfile.TemporaryDirectory()
        self.env_patch = patch.dict(
            os.environ,
            {"AUDIO_DIR": self.output_dir.name, "OLLAMA_BASE_URL": "http://127.0.0.1:1"},
        )
        self.env_patch.start()
        app.dependency_overrides[get_store] = lambda: self.store
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.env_patch.stop()
        self.output_dir.cleanup()

    def test_complete_session_ingestion_and_report_flow(self):
        started = self.client.post("/api/session/start", json={"domain_id": "backend_systems"})
        self.assertEqual(started.status_code, 200)
        session_id = started.json()["session_id"]
        self.assertIn("100,000", started.json()["challenge"])

        event = self.client.post(
            "/api/session/code/event",
            json={
                "session_id": session_id,
                "session_timestamp_ms": 1200,
                "event_type": "CODE_MUTATION",
                "data": {"text_inserted": "def allow(key):"},
            },
        )
        self.assertEqual(event.json()["status"], "ACK")

        hint = self.client.post(
            "/api/session/code/event",
            json={
                "session_id": session_id,
                "session_timestamp_ms": 1400,
                "event_type": "HINT_USED",
                "data": {"hint_id": "backend_systems-1", "hint_index": 1, "penalty_points": 5},
            },
        )
        self.assertEqual(hint.json()["status"], "ACK")

        audio = self.client.post(
            "/api/session/audio/chunk",
            data={"session_id": session_id, "timestamp_ms": "1000"},
            files={"chunk": ("chunk.webm", b"audio bytes", "audio/webm")},
        )
        self.assertEqual(audio.status_code, 200)

        submitted = self.client.post(
            "/api/session/submit",
            json={"session_id": session_id, "duration_ms": 20_000, "final_code": "def allow(key):"},
        )
        self.assertEqual(submitted.status_code, 200)
        status = self.client.get(f"/api/session/{session_id}").json()
        self.assertEqual(status["status"], "COMPLETED")
        self.assertIn("interaction_metrics", status["result"]["report"])
        self.assertTrue(any(
            flag["code"] == "STRUCTURAL_PREMATURE_IMPLEMENTATION"
            for flag in status["result"]["report"]["evaluation_flags"]
        ))
        self.assertTrue(os.path.isfile(status["result"]["share_card_path"]))
        self.assertEqual(status["result"]["report"]["contest_simulation"]["hint_penalty_points"], 5)
        self.assertIn("codeguru_review", status["result"]["report"])
        self.assertEqual(status["result"]["report"]["contest_simulation"]["hints_used"], 1)
        self.assertTrue(any(event["event_type"] == "HINT_USED" for event in status["result"]["timeline"]))
        self.assertEqual(self.client.get(f"/api/session/{session_id}/timeline").status_code, 200)
        self.assertEqual(self.client.get(f"/api/session/{session_id}/download-card").status_code, 200)

    def test_unknown_domain_missing_and_inactive_sessions_are_rejected(self):
        invalid = self.client.post("/api/session/start", json={"domain_id": "unknown"})
        self.assertEqual(invalid.status_code, 422)
        missing = self.client.post(
            "/api/session/code/event",
            json={"session_id": "missing", "session_timestamp_ms": 0, "data": {}},
        )
        self.assertEqual(missing.status_code, 404)
        started = self.client.post("/api/session/start", json={"domain_id": "backend_systems"})
        session_id = started.json()["session_id"]
        self.client.post(
            "/api/session/submit",
            json={"session_id": session_id, "duration_ms": 0, "final_code": ""},
        )
        inactive = self.client.post(
            "/api/session/code/event",
            json={"session_id": session_id, "session_timestamp_ms": 1, "data": {}},
        )
        self.assertEqual(inactive.status_code, 409)

    def test_domain_endpoint_exposes_question_bank_and_preparation(self):
        response = self.client.get("/api/domains")
        self.assertEqual(response.status_code, 200)
        profiles = {profile["id"]: profile for profile in response.json()}
        self.assertEqual(len(profiles), 4)
        frontend = profiles["frontend_architecture"]
        self.assertTrue(frontend["question_bank"])
        self.assertTrue(frontend["hints"])
        self.assertIn("Google-style", frontend["company_round"])
        self.assertEqual(frontend["contest_simulation"]["hint_penalty_score"], 5)
        self.assertTrue(frontend["preparation_masterclass"])
        self.assertIn("60 FPS", " ".join(frontend["expectations"]))


if __name__ == "__main__":
    unittest.main()