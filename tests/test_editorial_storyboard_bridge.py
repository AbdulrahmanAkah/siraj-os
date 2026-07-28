from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from src.application.storyboard_runtime import (
    EVIDENCE_GATE_WITHHELD,
    EDITORIAL_STORYBOARD_BRIDGE_SCHEMA_VERSION,
    EditorialStoryboardBridge,
    EditorialStoryboardProfile,
    EvidenceMode,
    NarrativeFunction,
    RUNWARE_EXECUTION_STATUS,
    canonical_text_sha256,
    write_blueprint,
)


PROFILE_PATH = (
    Path(__file__).resolve().parents[1]
    / "projects/episode-001-adam/cinematic/storyboard-profile-v1.json"
)


class EditorialStoryboardBridgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile_payload = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        self.profile = EditorialStoryboardProfile.from_mapping(self.profile_payload)
        self.required_event_ids = [
            event_id
            for frame in self.profile.frames
            for event_id in frame.event_ids
        ]
        self.central_question = self.profile.series_contract.central_question

    def _episode_definition(self, approval: str = "NOT_REQUESTED") -> dict[str, object]:
        return {
            "schema_version": "siraj-episode-definition-v1",
            "episode_id": "episode-001-adam",
            "central_question": self.central_question,
            "minimum_duration_minutes": 18,
            "target_duration_minutes": 22,
            "maximum_duration_minutes": 25,
            "historical_scope": {"required_event_ids": self.required_event_ids},
            "source_package": {"approval_status": approval},
            "verification": {"status": "deferred"},
        }

    @staticmethod
    def _integration_validation() -> dict[str, object]:
        return {
            "status": "PASS",
            "counts": {
                "events": 37,
                "human_decisions": 16,
                "research_questions": 32,
                "source_records": 30,
            },
        }

    @staticmethod
    def _source_package() -> dict[str, object]:
        return {
            "source_items": [{"id": index} for index in range(30)],
            "research_questions": [{"id": index} for index in range(32)],
        }

    def _events(self) -> list[dict[str, object]]:
        events = []
        for index, event_id in enumerate(self.required_event_ids):
            events.append(
                {
                    "event_id": event_id,
                    "order": (index + 1) * 10,
                    "title": f"Event {event_id}",
                    "section": f"Section {index // 4}",
                    "question_ids": [f"RQ-{index:03d}"],
                    "verification_status": (
                        "quran_explicit" if index % 3 == 0 else "pending"
                    ),
                    "chronology_type": (
                        "explicit" if index % 2 == 0 else "pending_verification"
                    ),
                    "duration_weight": "normal",
                    "importance": "core",
                }
            )
        return events

    @staticmethod
    def _decisions() -> list[dict[str, object]]:
        required = [
            "HD-GLOBAL-007",
            "HD-GLOBAL-009",
            "HD-GLOBAL-010",
            "HD-ADAM-001",
            "HD-ADAM-002",
        ]
        ids = required + [f"HD-EXTRA-{index:03d}" for index in range(11)]
        return [
            {"decision_id": decision_id, "status": "approved"}
            for decision_id in ids
        ]

    def _build(self, *, approval: str = "NOT_REQUESTED"):
        return EditorialStoryboardBridge().build_from_data(
            episode_definition=self._episode_definition(approval),
            integration_validation=self._integration_validation(),
            source_package=self._source_package(),
            event_map=self._events(),
            human_decisions=self._decisions(),
            profile=self.profile,
            input_fingerprints={"fixture": "abc"},
        )

    def test_builds_fourteen_frame_adam_blueprint(self) -> None:
        blueprint = self._build()
        self.assertEqual(
            blueprint.schema_version,
            EDITORIAL_STORYBOARD_BRIDGE_SCHEMA_VERSION,
        )
        self.assertEqual(blueprint.storyboard.frame_count, 14)
        self.assertEqual(list(blueprint.frame_event_coverage), self.required_event_ids)
        self.assertEqual(
            sum(
                item.planned_seconds
                for item in blueprint.compiled_episode.plan.directives
            ),
            1320,
        )

    def test_climax_is_iblis_refusal_frame(self) -> None:
        blueprint = self._build()
        directives = blueprint.compiled_episode.plan.directives
        self.assertEqual(directives[9].narrative_function, NarrativeFunction.CLIMAX)
        self.assertEqual(
            blueprint.storyboard.frames[9].trace_metadata["event_ids"],
            ["EV-ADAM-052", "EV-ADAM-053", "EV-ADAM-054", "EV-ADAM-055"],
        )

    def test_no_event_is_bound_as_evidence_before_approval(self) -> None:
        blueprint = self._build()
        self.assertEqual(blueprint.evidence_gate_status, EVIDENCE_GATE_WITHHELD)
        self.assertTrue(
            all(
                not frame.referenced_evidence_ids
                for frame in blueprint.storyboard.frames
            )
        )
        self.assertTrue(
            all(
                directive.evidence_mode
                in {
                    EvidenceMode.SYMBOLIC_VISUALIZATION,
                    EvidenceMode.ATMOSPHERIC_TRANSITION,
                }
                for directive in blueprint.compiled_episode.plan.directives
            )
        )

    def test_live_execution_and_video_preallocation_remain_blocked(self) -> None:
        blueprint = self._build()
        self.assertEqual(
            blueprint.compiled_episode.plan.runware_execution_status,
            RUNWARE_EXECUTION_STATUS,
        )
        self.assertEqual(
            blueprint.compiled_episode.plan.generated_video_seconds,
            0,
        )
        self.assertFalse(blueprint.compiled_episode.live_execution_allowed)

    def test_profile_covers_all_thirty_seven_events_once(self) -> None:
        self.assertEqual(len(self.required_event_ids), 37)
        self.assertEqual(len(set(self.required_event_ids)), 37)

    def test_missing_event_is_rejected(self) -> None:
        events = self._events()[:-1]
        with self.assertRaisesRegex(ValueError, "Event map"):
            EditorialStoryboardBridge().build_from_data(
                episode_definition=self._episode_definition(),
                integration_validation=self._integration_validation(),
                source_package=self._source_package(),
                event_map=events,
                human_decisions=self._decisions(),
                profile=self.profile,
            )

    def test_duplicate_profile_event_is_rejected(self) -> None:
        payload = json.loads(json.dumps(self.profile_payload))
        payload["frames"][3]["event_ids"].append("EV-ADAM-010")
        with self.assertRaisesRegex(ValueError, "repeats an event id"):
            EditorialStoryboardProfile.from_mapping(payload)

    def test_approved_source_without_bindings_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "event-to-evidence binding"):
            self._build(approval="APPROVED")

    def test_canonical_hash_ignores_windows_line_endings(self) -> None:
        self.assertEqual(
            canonical_text_sha256(b"a\nb\n"),
            canonical_text_sha256(b"a\r\nb\r\n"),
        )

    def test_manifest_is_deterministic(self) -> None:
        first = self._build()
        second = self._build()
        self.assertEqual(first.bridge_id, second.bridge_id)
        self.assertEqual(first.to_json(), second.to_json())

    def test_writes_utf8_lf_blueprint(self) -> None:
        blueprint = self._build()
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "blueprint.json"
            write_blueprint(output, blueprint)
            data = output.read_bytes()
            self.assertIn("آدم".encode("utf-8"), data)
            self.assertNotIn(b"\r\n", data)
            parsed = json.loads(data.decode("utf-8"))
            self.assertEqual(parsed["storyboard"]["frame_count"], 14)

    def test_cli_bootstraps_repository_root_from_arbitrary_cwd(self) -> None:
        script = (
            Path(__file__).resolve().parents[1]
            / "scripts/fast_track/build_adam_cinematic_blueprint_v1.py"
        )
        environment = dict(os.environ)
        environment.pop("PYTHONPATH", None)
        with tempfile.TemporaryDirectory() as temporary:
            result = subprocess.run(
                [sys.executable, "-I", str(script), "--help"],
                cwd=temporary,
                env=environment,
                text=True,
                encoding="utf-8",
                errors="replace",
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("Build Adam episode editorial cinematic blueprint", result.stdout)

    def test_last_frame_is_next_episode_promise(self) -> None:
        blueprint = self._build()
        self.assertEqual(
            blueprint.compiled_episode.plan.directives[-1].narrative_function,
            NarrativeFunction.NEXT_EPISODE_PROMISE,
        )
        self.assertEqual(
            blueprint.storyboard.frames[-1].trace_metadata["event_ids"],
            ["EV-ADAM-099"],
        )


if __name__ == "__main__":
    unittest.main()
