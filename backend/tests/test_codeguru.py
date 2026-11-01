import unittest

from app.codeguru import CODEGURU_EVALUATION_MATRIX, check_codeguru_standards


class CodeGuruReviewTests(unittest.TestCase):
    def test_python_ast_and_language_signals_cover_all_focus_areas(self):
        code = """class Cache:
    def __init__(self):
        self.values = dict()

    def get(self, key):
        try:
            with self.lock:
                return self.values.get(key)
        finally:
            self.release()
"""
        report = check_codeguru_standards([], code, "python")
        self.assertEqual(report["evaluation_standard"], CODEGURU_EVALUATION_MATRIX["evaluation_standard"])
        self.assertEqual(report["parser"]["status"], "parsed")
        self.assertEqual([area["status"] for area in report["areas"]], ["observed"] * 3)

    def test_cpp_idioms_are_checked_for_cpp_code(self):
        report = check_codeguru_standards([], "class Cache { std::vector<int> values; };", "c++")
        self.assertEqual(report["language"], "cpp")
        self.assertEqual(report["parser"]["name"], "language_pattern_scan")
        self.assertEqual(report["areas"][0]["status"], "observed")
        self.assertEqual(report["areas"][1]["status"], "observed")
        self.assertEqual(report["areas"][2]["status"], "observed")

    def test_javascript_lifecycle_cleanup_is_detected(self):
        code = "class SearchView { cleanup() { controller.abort(); clearTimeout(timer); } }"
        report = check_codeguru_standards([], code, "javascript")
        self.assertEqual(report["areas"][1]["status"], "observed")
        self.assertEqual(report["areas"][2]["status"], "not_observed")

    def test_multiword_design_discussion_before_primary_class_is_evidence(self):
        timeline = [
            {"event_type": "SPEECH_TOKEN", "session_timestamp_ms": 1000, "word": "We"},
            {"event_type": "SPEECH_TOKEN", "session_timestamp_ms": 1200, "word": "need"},
            {"event_type": "SPEECH_TOKEN", "session_timestamp_ms": 1400, "word": "clean"},
            {"event_type": "SPEECH_TOKEN", "session_timestamp_ms": 1600, "word": "abstractions"},
            {"event_type": "CODE_MUTATION", "session_timestamp_ms": 2000, "data": {"text_inserted": "class Cache:"}},
        ]
        report = check_codeguru_standards(timeline, "class Cache:\n    pass", "python")
        self.assertIn("before a primary declaration", report["areas"][0]["evidence"][0])

    def test_missing_code_is_reported_as_insufficient_not_failure(self):
        report = check_codeguru_standards([], "", "python")
        self.assertEqual([area["status"] for area in report["areas"]], ["insufficient_code"] * 3)
        self.assertIn("not proof", report["note"])


if __name__ == "__main__":
    unittest.main()