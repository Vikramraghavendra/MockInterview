import json
import unittest
from unittest.mock import patch

from app.analytics import align_timeline, interaction_metrics
from app.contest import analyze_interview_cadence
from app.domains import DOMAINS, get_domain, inject_domain_context_to_llm
from app.evaluator import _fallback_evaluation, evaluate_timeline
from domain_knowledge import CODEGURU_EVALUATION_MATRIX, DOMAIN_KNOWLEDGE_BASE


class TimelineTests(unittest.TestCase):
    def test_interleaves_streams_in_timestamp_order(self):
        timeline = align_timeline(
            [{"session_timestamp_ms": 1200, "data": {"text_inserted": "x"}}],
            [{"session_timestamp_ms": 800, "word": "hello"}],
        )
        self.assertEqual([item["event_type"] for item in timeline], ["SPEECH_TOKEN", "CODE_MUTATION"])

    def test_flags_silence_and_preserves_code_context(self):
        timeline = align_timeline(
            [{"session_timestamp_ms": 12_001, "data": {"text_inserted": "const answer = 42;"}}],
            [],
        )
        self.assertTrue(timeline[0]["silence_warning"])
        self.assertEqual(timeline[0]["gap_duration_ms"], 12_001)
        self.assertIn("answer", timeline[0]["code_context"])

    def test_speech_resets_silence_window(self):
        timeline = align_timeline(
            [{"session_timestamp_ms": 13_000, "data": {"text_inserted": "x"}}],
            [{"session_timestamp_ms": 5_000, "word": "thinking"}],
        )
        self.assertFalse(timeline[1].get("silence_warning", False))

    def test_continuous_silence_produces_one_flag_with_gap_code(self):
        timeline = align_timeline(
            [
                {"session_timestamp_ms": 13_000, "data": {"text_inserted": "first"}},
                {"session_timestamp_ms": 17_000, "data": {"text_inserted": " second"}},
            ],
            [],
            20_000,
        )
        warnings = [event for event in timeline if event.get("silence_warning")]
        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0]["code_context"], "first")

    def test_trailing_silence_without_edits_is_represented(self):
        timeline = align_timeline([], [{"session_timestamp_ms": 1000, "word": "done"}], 15_000)
        silence = next(event for event in timeline if event["event_type"] == "SILENCE_GAP")
        self.assertEqual(silence["session_timestamp_ms"], 13_000)
        self.assertEqual(silence["gap_duration_ms"], 14_000)

    def test_final_code_snapshot_does_not_create_a_code_mutation(self):
        timeline = align_timeline(
            [{
                "event_type": "CODE_SNAPSHOT",
                "session_timestamp_ms": 20_000,
                "data": {"text_inserted": "", "final_code": "unchanged starter"},
            }],
            [],
            20_000,
        )
        self.assertEqual([event["event_type"] for event in timeline], ["SILENCE_GAP"])

    def test_hint_used_events_are_preserved_without_counting_as_code(self):
        hint = {"event_type": "HINT_USED", "session_timestamp_ms": 3000, "data": {"hint_id": "h1"}}
        timeline = align_timeline([hint], [], 4000)
        self.assertIn(hint, timeline)
        metrics = interaction_metrics([hint], [], 4000)
        self.assertEqual(metrics["characters_typed"], 0)

    def test_metrics_use_elapsed_duration_and_zero_safe_denominators(self):
        metrics = interaction_metrics(
            [{"data": {"text_inserted": "abc"}}],
            [{"word": "hello world"}],
            60_000,
        )
        self.assertEqual(metrics["spoken_words"], 2)
        self.assertEqual(metrics["characters_typed"], 3)
        self.assertEqual(metrics["talk_to_code_velocity_ratio"], 0.667)


class ContestTests(unittest.TestCase):
    def test_contest_clock_and_hint_penalty_are_reported(self):
        report = analyze_interview_cadence([], duration_ms=5 * 60_000, hints_used=2)
        self.assertEqual(report["round_type"], "DSA_INTERVIEW_SERIES")
        self.assertEqual(report["time_allowance_mins"], 90)
        self.assertEqual(report["time_remaining_ms"], 85 * 60_000)
        self.assertEqual(report["hint_penalty_points"], 10)

    def test_complexity_spike_without_explanation_is_flagged(self):
        timeline = [
            {"event_type": "SPEECH_TOKEN", "session_timestamp_ms": 1000, "word": "I will"},
            {"event_type": "CODE_MUTATION", "session_timestamp_ms": 2000, "data": {"text_inserted": "for item in items:"}},
        ]
        report = analyze_interview_cadence(timeline, duration_ms=5000)
        self.assertEqual(report["complexity_spikes"], 1)
        self.assertEqual(report["cadence_flags"][0]["code"], "UNEXPLAINED_COMPLEXITY_SPIKE")

    def test_nearby_complexity_explanation_prevents_cadence_flag(self):
        timeline = [
            {"event_type": "SPEECH_TOKEN", "session_timestamp_ms": 1000, "word": "Big O"},
            {"event_type": "CODE_MUTATION", "session_timestamp_ms": 2000, "data": {"text_inserted": "for item in items:"}},
        ]
        report = analyze_interview_cadence(timeline, duration_ms=5000)
        self.assertEqual(report["cadence_flags"], [])

    def test_complexity_spike_without_speech_is_flagged(self):
        report = analyze_interview_cadence(
            [{"event_type": "CODE_MUTATION", "session_timestamp_ms": 2000, "data": {"text_inserted": "while pending:"}}],
            duration_ms=5000,
        )
        self.assertEqual(report["cadence_flags"][0]["code"], "UNEXPLAINED_COMPLEXITY_SPIKE")


class DomainTests(unittest.TestCase):
    def test_profiles_include_expectations_and_challenges(self):
        self.assertEqual(len(DOMAINS), 4)
        self.assertEqual(
            set(DOMAINS),
            {"backend_systems", "backend_data_infra", "frontend_architecture", "ml_platform"},
        )
        for profile in DOMAINS.values():
            self.assertTrue(profile.knowledge_base)
            self.assertTrue(profile.expectations)
            self.assertTrue(profile.challenge)
            self.assertTrue(profile.rubric_phases)
            self.assertTrue(profile.question_bank)
            self.assertTrue(profile.preparation_materials)

    def test_requested_knowledge_base_export_contains_all_tracks(self):
        self.assertIn("frontend_architecture", DOMAIN_KNOWLEDGE_BASE)
        self.assertIn("Strategic Communicator Blueprint", DOMAIN_KNOWLEDGE_BASE["ml_platform"]["materials"])
        self.assertEqual(
            DOMAIN_KNOWLEDGE_BASE["ml_platform"]["code_quality_standards"]["evaluation_standard"],
            CODEGURU_EVALUATION_MATRIX["evaluation_standard"],
        )

    def test_domain_aliases_preserve_existing_ids(self):
        self.assertEqual(get_domain("frontend_ui").id, "frontend_architecture")
        self.assertEqual(get_domain("data_engineering").id, "backend_data_infra")

    def test_llm_context_is_selected_by_track(self):
        context = inject_domain_context_to_llm("frontend_architecture")
        self.assertIn("500,000", context)
        self.assertIn("STRUCTURAL_PREMATURE_IMPLEMENTATION", context)

    def test_evaluator_flags_coding_before_five_minute_scope(self):
        timeline = [
            {"event_type": "SPEECH_TOKEN", "session_timestamp_ms": 1000, "word": "scale"},
            {
                "event_type": "CODE_MUTATION",
                "session_timestamp_ms": 12_000,
                "data": {"text_inserted": "allow()"},
            },
        ]
        report = _fallback_evaluation("backend_systems", timeline, {})
        self.assertEqual(report["evaluation_flags"][0]["code"], "STRUCTURAL_PREMATURE_IMPLEMENTATION")

    def test_evaluator_does_not_flag_code_after_scope_window(self):
        report = _fallback_evaluation(
            "backend_systems",
            [{"event_type": "CODE_MUTATION", "session_timestamp_ms": 301_000, "data": {}}],
            {},
        )
        self.assertFalse(any(flag["code"] == "STRUCTURAL_PREMATURE_IMPLEMENTATION" for flag in report["evaluation_flags"]))

    def test_final_snapshot_without_edits_is_not_implementation(self):
        report = _fallback_evaluation(
            "backend_systems",
            [{
                "event_type": "CODE_MUTATION",
                "session_timestamp_ms": 1000,
                "data": {"text_inserted": "", "final_code": "starter template"},
            }],
            {},
        )
        self.assertFalse(any(flag["code"] == "STRUCTURAL_PREMATURE_IMPLEMENTATION" for flag in report["evaluation_flags"]))

    def test_selected_domain_context_is_sent_as_llm_system_message(self):
        response_body = {
            "message": {
                "content": json.dumps({
                    "communication_score": 75,
                    "structural_classification": "STRATEGIC_THINKER",
                    "assumption_validation": True,
                    "rubric": [{"met": True, "evidence": "Discussed the latency budget."}] * 3,
                    "critique_summary": "Clear latency breakdown.",
                })
            }
        }
        timeline = [{"event_type": "SPEECH_TOKEN", "session_timestamp_ms": 1000, "word": "latency"}]
        with patch("app.evaluator.httpx.post") as post, patch.dict(
            "os.environ", {"OLLAMA_BASE_URL": "http://ollama.test"}
        ):
            post.return_value.json.return_value = response_body
            report = evaluate_timeline("ml_platform", timeline, {})
        messages = post.call_args.kwargs["json"]["messages"]
        self.assertEqual(messages[0]["role"], "system")
        self.assertIn("50 ms", messages[0]["content"])
        self.assertEqual(report["evaluator"], "ollama:qwen3:8b")

    def test_unknown_domain_is_rejected(self):
        with self.assertRaises(ValueError):
            get_domain("not-a-domain")


if __name__ == "__main__":
    unittest.main()