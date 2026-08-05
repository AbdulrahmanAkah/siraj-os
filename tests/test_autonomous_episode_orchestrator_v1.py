from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from src.application.artifact_dependency_graph_v1 import (
    build_scope_dependency_graph,
    invalidate_nodes,
    rebuild_plan,
)
from src.application.autonomous_episode_orchestrator_v1 import (
    approve_scope,
    current_scope_proposal,
    generate_next_episode_scope,
    load_orchestrator_state,
)
from src.application.openai_luna_orchestrator_v1 import (
    LUNA_MODEL,
    LunaResult,
    build_scope_request,
)


def proposal() -> dict:
    events = []
    for index in range(1, 4):
        events.append(
            {
                "event_id": f"EV-{index:03d}",
                "title_ar": f"الحدث {index}",
                "description_ar": f"وصف الحدث التاريخي رقم {index}",
                "chronology_order": index,
                "evidence_posture": "QURAN_EXPLICIT",
                "confidence": "HIGH",
                "include_recommendation": True,
                "source_refs": [
                    {
                        "title": "مصدر",
                        "url": "https://example.com/source",
                        "source_type": "QURAN",
                        "supports": "يدعم الحدث",
                    }
                ],
                "uncertainty_ar": "",
            }
        )
    return {
        "proposal_version": 1,
        "slug_en": "next-episode",
        "topic_title_ar": "الحلقة التالية",
        "working_title_ar": "عنوان عمل",
        "central_question_ar": "ما الذي حدث بعد ذلك؟",
        "episode_summary_ar": "ملخص تفصيلي كافٍ للحلقة التالية المقترحة.",
        "rationale_ar": "استمرار زمني مباشر للسلسلة.",
        "estimated_duration_minutes": 20,
        "event_count": 3,
        "events": events,
        "excluded_candidates": [],
        "research_questions": ["ما الأدلة الأقوى؟"],
        "production_risk_notes": [],
    }


class AutonomousEpisodeOrchestratorV1Tests(unittest.TestCase):
    def test_luna_request_uses_responses_web_search_and_schema(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            request = build_scope_request(repo)
        self.assertEqual(request["model"], LUNA_MODEL)
        self.assertEqual(request["tools"], [{"type": "web_search"}])
        self.assertEqual(
            request["text"]["format"]["type"],
            "json_schema",
        )
        self.assertTrue(request["text"]["format"]["strict"])
        self.assertFalse(request["store"])

    def test_scope_generation_is_persisted_and_awaits_human_review(self):
        result = LunaResult(
            response_id="resp_test",
            payload=proposal(),
            raw_output_text=json.dumps(proposal(), ensure_ascii=False),
            input_tokens=1000,
            output_tokens=500,
            cached_input_tokens=100,
            estimated_text_cost_usd=0.00078,
        )
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            with patch(
                "src.application.autonomous_episode_orchestrator_v1."
                "request_scope_proposal",
                return_value=result,
            ):
                state = generate_next_episode_scope(repo, "test-key")
            self.assertEqual(
                state["status"],
                "AWAITING_HUMAN_SCOPE_REVIEW",
            )
            stored = current_scope_proposal(repo)
            self.assertIsNotNone(stored)
            self.assertEqual(stored["model"], "gpt-5.6-luna")
            self.assertFalse(stored["human_approval"])

    def test_approval_creates_new_episode_and_dependency_graph(self):
        result = LunaResult(
            response_id="resp_test",
            payload=proposal(),
            raw_output_text="{}",
            input_tokens=1,
            output_tokens=1,
            cached_input_tokens=0,
            estimated_text_cost_usd=0.0,
        )
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            existing = repo / "projects/episode-001-adam/contracts"
            existing.mkdir(parents=True)
            (existing / "episode-definition-v1.json").write_text(
                json.dumps({"episode_id": "episode-001-adam"}),
                encoding="utf-8",
            )
            with patch(
                "src.application.autonomous_episode_orchestrator_v1."
                "request_scope_proposal",
                return_value=result,
            ):
                generate_next_episode_scope(repo, "test-key")
            state = approve_scope(repo)
            self.assertEqual(
                state["status"],
                "SCOPE_APPROVED_AUTOMATIC_PIPELINE_QUEUED",
            )
            episode = repo / "projects/episode-002-next-episode"
            self.assertTrue(
                (episode / "contracts/episode-definition-v1.json").is_file()
            )
            graph = (
                episode
                / "orchestration/artifact-dependency-graph-v1.json"
            )
            self.assertTrue(graph.is_file())

    def test_partial_rebuild_invalidates_only_downstream(self):
        graph = build_scope_dependency_graph("episode-002-test", proposal())
        changed = "episode-002-test:SCRIPT:EV-002"
        invalidate_nodes(graph, [changed], "fix narration")
        plan = rebuild_plan(graph)
        invalidated = set(plan["invalidated_node_ids"])
        self.assertIn(changed, invalidated)
        self.assertIn("episode-002-test:TTS:EV-002", invalidated)
        self.assertIn("episode-002-test:FINAL_MASTER", invalidated)
        self.assertNotIn("episode-002-test:SCRIPT:EV-001", invalidated)
        self.assertFalse(plan["regenerate_entire_episode"])

    def test_idle_state_has_exact_two_human_gates(self):
        with tempfile.TemporaryDirectory() as temporary:
            state = load_orchestrator_state(Path(temporary))
        gates = state["autonomy_contract"]["human_gates"]
        self.assertEqual(
            gates,
            ["HUMAN_SCOPE_REVIEW", "HUMAN_FINAL_REVIEW"],
        )


if __name__ == "__main__":
    unittest.main()
