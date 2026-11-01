import os
import tempfile
import unittest
from unittest.mock import patch

from app.storage import MemoryStore
from app.worker import process_job


class WorkerTests(unittest.TestCase):
    def test_job_persists_report_timeline_and_share_card(self):
        store = MemoryStore()
        session = store.create_session("backend_systems")
        store.append_code(
            session["session_id"],
            {"session_timestamp_ms": 1000, "data": {"text_inserted": "def allow(key):"}},
        )
        store.append_code(
            session["session_id"],
            {"event_type": "CODE_SNAPSHOT", "session_timestamp_ms": 20_000, "data": {"final_code": "def allow(key):\n    return True"}},
        )
        with tempfile.TemporaryDirectory() as output_dir, patch.dict(
            os.environ,
            {"AUDIO_DIR": output_dir, "OLLAMA_BASE_URL": "http://127.0.0.1:1"},
        ):
            result = process_job(
                store,
                {
                    "session_id": session["session_id"],
                    "domain_id": "backend_systems",
                    "language": "python",
                    "duration_ms": 20_000,
                    "hints_used": 1,
                },
            )
            self.assertTrue(os.path.isfile(result["share_card_path"]))
            self.assertEqual(store.get_session(session["session_id"])["status"], "COMPLETED")
            self.assertIn("interaction_metrics", result["report"])
            self.assertIsNone(result["report"]["communication_score"])
            self.assertEqual(result["report"]["structural_classification"], "NOT_ENOUGH_DATA")
            self.assertEqual(result["report"]["evaluator"], "not_scored (no transcript available)")
            self.assertIn("timeline", result)
            self.assertEqual(result["report"]["codeguru_review"]["evaluation_standard"], "CODEGURU_COMMUNITY_BEST_PRACTICES")
            self.assertEqual(result["report"]["contest_simulation"]["hint_penalty_points"], 5)


if __name__ == "__main__":
    unittest.main()