from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from src.application.storyboard_runtime import (
    CinematicCompilationPolicy,
    CinematicSeriesCompiler,
    EpisodeSeriesContract,
    Storyboard,
    StoryboardFrame,
)
from src.application.storyboard_runtime.evidence_binding import (
    APPROVED_EVIDENCE_PACKAGE_SCHEMA_VERSION,
    EVENT_EVIDENCE_ADJUDICATION_SCHEMA_VERSION,
    EVIDENCE_GATE_OPEN,
    EVIDENCE_GATE_WITHHELD,
    ApprovedEventEvidenceAdjudication,
    ApprovedEvidenceBinder,
    ApprovedEvidencePackage,
    CinematicSeriesError,
    canonical_json_sha256,
    event_evidence_adjudication_template,
    approved_evidence_package_template,
    validate_non_executable_templates,
    write_evidence_bound_blueprint,
)


class ApprovedEvidenceBindingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = build_fixture()

    def bind(self, fixture=None):
        data = fixture or self.fixture
        package = ApprovedEvidencePackage.from_mapping(data["evidence_package"])
        adjudication = ApprovedEventEvidenceAdjudication.from_mapping(
            data["adjudication"]
        )
        return ApprovedEvidenceBinder().bind_from_data(
            episode_definition=data["episode_definition"],
            event_map=data["event_map"],
            editorial_blueprint=data["editorial_blueprint"],
            approved_source_package=data["source_package"],
            evidence_package=package,
            adjudication=adjudication,
            evidence_package_fingerprint=canonical_json_sha256(
                data["evidence_package"]
            ),
            adjudication_fingerprint=canonical_json_sha256(
                data["adjudication"]
            ),
        )

    def test_binds_complete_human_approved_evidence(self):
        result = self.bind()
        manifest = result.to_manifest()
        self.assertEqual(manifest["evidence_gate_status"], EVIDENCE_GATE_OPEN)
        self.assertEqual(manifest["live_execution_status"], "BLOCKED")
        self.assertEqual(
            manifest["runware_execution_status"],
            "BLOCKED_PENDING_MANUAL_PROVIDER_TEST",
        )
        refs = [
            item["referenced_evidence_ids"]
            for item in manifest["storyboard"]["frames"]
        ]
        self.assertIn("EVID-001", refs[1])
        self.assertIn("EVID-002", refs[2])
        self.assertEqual(refs[-1], [])

    def test_quran_explicit_event_cannot_be_omitted(self):
        data = copy.deepcopy(self.fixture)
        data["adjudication"]["decisions"][0] = {
            "event_id": "EV-001",
            "disposition": "omit_unverified",
            "evidence_ids": [],
            "qualification_label": None,
            "rationale": "bad",
        }
        with self.assertRaisesRegex(CinematicSeriesError, "Quran-explicit"):
            self.bind(data)

    def test_quran_explicit_event_requires_quran_evidence(self):
        data = copy.deepcopy(self.fixture)
        data["evidence_package"]["evidence_items"][0][
            "claim_classification"
        ] = "accepted_athar"
        data["episode_definition"]["evidence_package"][
            "input_fingerprint"
        ] = canonical_json_sha256(data["evidence_package"])
        with self.assertRaisesRegex(CinematicSeriesError, "Quran-explicit evidence"):
            self.bind(data)

    def test_source_package_must_be_approved(self):
        data = copy.deepcopy(self.fixture)
        data["source_package"]["package_status"] = "DRAFT_ACQUISITION_PENDING"
        with self.assertRaisesRegex(CinematicSeriesError, "payload must be APPROVED"):
            self.bind(data)

    def test_episode_definition_must_record_human_source_approval(self):
        data = copy.deepcopy(self.fixture)
        data["episode_definition"]["source_package"][
            "approval_status"
        ] = "NOT_REQUESTED"
        with self.assertRaisesRegex(CinematicSeriesError, "explicitly APPROVED"):
            self.bind(data)

    def test_evidence_package_fingerprint_must_match_episode_contract(self):
        data = copy.deepcopy(self.fixture)
        data["episode_definition"]["evidence_package"][
            "input_fingerprint"
        ] = "0" * 64
        with self.assertRaisesRegex(CinematicSeriesError, "fingerprint"):
            self.bind(data)

    def test_source_must_support_bound_event(self):
        data = copy.deepcopy(self.fixture)
        data["source_package"]["source_items"][1]["notes"][
            "supports_event_ids"
        ] = ["EV-001"]
        with self.assertRaisesRegex(CinematicSeriesError, "does not support"):
            self.bind(data)

    def test_planned_source_is_rejected(self):
        data = copy.deepcopy(self.fixture)
        data["source_package"]["source_items"][1]["access_status"] = "PLANNED"
        with self.assertRaisesRegex(CinematicSeriesError, "merely planned"):
            self.bind(data)

    def test_source_checksum_must_match(self):
        data = copy.deepcopy(self.fixture)
        data["evidence_package"]["evidence_items"][1][
            "source_checksum_sha256"
        ] = "c" * 64
        data["episode_definition"]["evidence_package"][
            "input_fingerprint"
        ] = canonical_json_sha256(data["evidence_package"])
        with self.assertRaisesRegex(CinematicSeriesError, "checksum differs"):
            self.bind(data)

    def test_automated_approval_identity_is_rejected(self):
        data = copy.deepcopy(self.fixture)
        data["evidence_package"]["approval"]["approved_by"] = "SYSTEM"
        data["episode_definition"]["evidence_package"][
            "input_fingerprint"
        ] = canonical_json_sha256(data["evidence_package"])
        with self.assertRaisesRegex(CinematicSeriesError, "automated identity"):
            self.bind(data)

    def test_qualified_inclusion_requires_label(self):
        data = copy.deepcopy(self.fixture)
        data["adjudication"]["decisions"][1]["qualification_label"] = None
        with self.assertRaisesRegex(CinematicSeriesError, "audience-facing label"):
            self.bind(data)

    def test_assertive_inclusion_rejects_interpretation(self):
        data = copy.deepcopy(self.fixture)
        data["adjudication"]["decisions"][1][
            "disposition"
        ] = "include_assertive"
        data["adjudication"]["decisions"][1]["qualification_label"] = None
        data["evidence_package"]["evidence_items"][1][
            "claim_classification"
        ] = "scholarly_interpretation"
        data["episode_definition"]["evidence_package"][
            "input_fingerprint"
        ] = canonical_json_sha256(data["evidence_package"])
        with self.assertRaisesRegex(CinematicSeriesError, "assertive evidence classes"):
            self.bind(data)

    def test_editorial_event_requires_editorial_only(self):
        data = copy.deepcopy(self.fixture)
        data["adjudication"]["decisions"][2] = {
            "event_id": "EV-003",
            "disposition": "omit_unverified",
            "evidence_ids": [],
            "qualification_label": None,
            "rationale": "wrong",
        }
        with self.assertRaisesRegex(CinematicSeriesError, "Editorial events"):
            self.bind(data)

    def test_orphan_evidence_is_rejected(self):
        data = copy.deepcopy(self.fixture)
        orphan = copy.deepcopy(data["evidence_package"]["evidence_items"][1])
        orphan["evidence_id"] = "EVID-ORPHAN"
        data["evidence_package"]["evidence_items"].append(orphan)
        data["episode_definition"]["evidence_package"][
            "input_fingerprint"
        ] = canonical_json_sha256(data["evidence_package"])
        with self.assertRaisesRegex(CinematicSeriesError, "orphans"):
            self.bind(data)

    def test_event_decisions_must_preserve_order(self):
        data = copy.deepcopy(self.fixture)
        decisions = data["adjudication"]["decisions"]
        decisions[0], decisions[1] = decisions[1], decisions[0]
        with self.assertRaisesRegex(CinematicSeriesError, "approved order"):
            self.bind(data)

    def test_binding_is_deterministic(self):
        first = self.bind().to_json()
        second = self.bind().to_json()
        self.assertEqual(first, second)

    def test_cinematic_structure_and_zero_video_are_preserved(self):
        original = self.fixture["editorial_blueprint"]["cinematic_compilation"]
        bound = self.bind().to_manifest()["cinematic_compilation"]
        self.assertEqual(
            [item["narrative_function"] for item in original["frames"]],
            [item["narrative_function"] for item in bound["frames"]],
        )
        self.assertEqual(
            [item["planned_seconds"] for item in original["frames"]],
            [item["planned_seconds"] for item in bound["frames"]],
        )
        self.assertEqual(bound["duration"]["generated_video_planned_seconds"], 0)

    def test_templates_are_non_executable_and_secret_free(self):
        evidence = approved_evidence_package_template("episode-001-adam")
        adjudication = event_evidence_adjudication_template("episode-001-adam")
        self.assertTrue(validate_non_executable_templates(evidence, adjudication))
        with self.assertRaises(CinematicSeriesError):
            ApprovedEvidencePackage.from_mapping(evidence)
        with self.assertRaises(CinematicSeriesError):
            ApprovedEventEvidenceAdjudication.from_mapping(adjudication)


    def test_cli_template_check_bootstraps_from_arbitrary_cwd(self):
        repo_root = Path(__file__).resolve().parents[1]
        script = repo_root / "scripts/fast_track/bind_adam_approved_evidence_v1.py"
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [sys.executable, "-I", str(script), "--template-check"],
                cwd=directory,
                text=True,
                encoding="utf-8",
                errors="replace",
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("STATUS=PASS_EVIDENCE_TEMPLATES_NON_EXECUTABLE", result.stdout)

    def test_writes_canonical_utf8_lf(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bound.json"
            write_evidence_bound_blueprint(path, self.bind())
            data = path.read_bytes()
            self.assertNotIn(b"\r\n", data)
            self.assertEqual(json.loads(data.decode("utf-8"))["evidence_gate_status"], EVIDENCE_GATE_OPEN)


def build_fixture():
    contract = EpisodeSeriesContract(
        series_title="Series",
        season_title="Season",
        episode_id="episode-001-adam",
        season_question="Season question?",
        central_question="Central question?",
        emotional_promise="Emotional promise",
        knowledge_promise="Knowledge promise",
        next_episode_question="Next question?",
    )
    frames = [
        StoryboardFrame(
            frame_id=f"FRAME-{index}",
            scene_id=f"SCENE-{index}",
            frame_purpose=f"Purpose {index}",
            position=index,
            trace_metadata={
                "event_ids": (
                    ["EV-001"]
                    if index == 1
                    else ["EV-002"]
                    if index == 2
                    else ["EV-003"]
                    if index == 6
                    else []
                )
            },
        )
        for index in range(7)
    ]
    storyboard = Storyboard(
        storyboard_id="STORYBOARD-BASE",
        scene_plan_id="SCENE-PLAN-BASE",
        frames=frames,
        frame_count=7,
        trace_metadata={
            "evidence_gate_statuses": [EVIDENCE_GATE_WITHHELD],
            "episode_ids": ["episode-001-adam"],
        },
    )
    compiled = CinematicSeriesCompiler().compile(
        storyboard,
        contract,
        policy=CinematicCompilationPolicy(target_episode_seconds=1320),
    )
    editorial_blueprint = {
        "schema_version": "siraj-editorial-storyboard-bridge-v1",
        "bridge_id": "BRIDGE-BASE",
        "episode_id": "episode-001-adam",
        "source_approval_status": "NOT_REQUESTED",
        "evidence_gate_status": EVIDENCE_GATE_WITHHELD,
        "verification_status": "deferred",
        "live_execution_status": "BLOCKED",
        "runware_execution_status": "BLOCKED_PENDING_MANUAL_PROVIDER_TEST",
        "storyboard": {
            "storyboard_id": storyboard.storyboard_id,
            "scene_plan_id": storyboard.scene_plan_id,
            "frame_count": storyboard.frame_count,
            "validation_state": storyboard.validation_state,
            "frames": [
                {
                    "frame_id": item.frame_id,
                    "scene_id": item.scene_id,
                    "frame_purpose": item.frame_purpose,
                    "referenced_evidence_ids": [],
                    "position": item.position,
                    "trace_metadata": item.trace_metadata,
                }
                for item in storyboard.frames
            ],
        },
        "cinematic_compilation": compiled.to_manifest(),
    }
    event_map = [
        {
            "event_id": "EV-001",
            "order": 10,
            "title": "Quran event",
            "verification_status": "quran_explicit",
        },
        {
            "event_id": "EV-002",
            "order": 20,
            "title": "Qualified event",
            "verification_status": "pending",
        },
        {
            "event_id": "EV-003",
            "order": 30,
            "title": "Editorial promise",
            "verification_status": "editorial",
        },
    ]
    source_package = {
        "schema_version": "siraj-episode-source-package-v1",
        "episode_id": "episode-001-adam",
        "package_status": "APPROVED",
        "input_fingerprint": "source-package-fingerprint-v1",
        "source_items": [
            {
                "source_id": "SRC-QURAN-001",
                "source_type": "QURAN",
                "access_status": "APPROVED",
                "allowed_for_extraction": True,
                "allowed_for_quotation": True,
                "checksum": "a" * 64,
                "notes": {"supports_event_ids": ["EV-001"]},
            },
            {
                "source_id": "SRC-ATHAR-001",
                "source_type": "ATHAR",
                "access_status": "VERIFIED",
                "allowed_for_extraction": True,
                "allowed_for_quotation": False,
                "checksum": "b" * 64,
                "notes": {"supports_event_ids": ["EV-002"]},
            },
        ],
    }
    approval = {
        "approval_id": "APPROVAL-001",
        "approved_by": "Human Reviewer",
        "approved_at": "2026-07-28T00:00:00Z",
        "approval_status": "APPROVED",
        "human_approval": True,
        "notes": "Reviewed manually.",
    }
    evidence_package = {
        "schema_version": APPROVED_EVIDENCE_PACKAGE_SCHEMA_VERSION,
        "package_id": "EVIDENCE-PACKAGE-001",
        "episode_id": "episode-001-adam",
        "source_package_fingerprint": source_package["input_fingerprint"],
        "approval": approval,
        "evidence_items": [
            {
                "evidence_id": "EVID-001",
                "event_id": "EV-001",
                "source_id": "SRC-QURAN-001",
                "claim_classification": "quran_explicit",
                "claim_summary": "Explicit Quran evidence.",
                "locator": "Surah 1:1",
                "source_checksum_sha256": "a" * 64,
                "excerpt_sha256": "1" * 64,
                "quotation_allowed": True,
                "visual_reconstruction_allowed": False,
                "usage_restrictions": ["NO_PROPHET_DEPICTION"],
            },
            {
                "evidence_id": "EVID-002",
                "event_id": "EV-002",
                "source_id": "SRC-ATHAR-001",
                "claim_classification": "accepted_athar",
                "claim_summary": "Approved qualified report.",
                "locator": "Book 1, section 2",
                "source_checksum_sha256": "b" * 64,
                "excerpt_sha256": "2" * 64,
                "quotation_allowed": False,
                "visual_reconstruction_allowed": False,
                "usage_restrictions": ["QUALIFIED_LANGUAGE_REQUIRED"],
            },
        ],
    }
    adjudication = {
        "schema_version": EVENT_EVIDENCE_ADJUDICATION_SCHEMA_VERSION,
        "adjudication_id": "ADJUDICATION-001",
        "episode_id": "episode-001-adam",
        "evidence_package_id": evidence_package["package_id"],
        "approval": {
            **approval,
            "approval_id": "APPROVAL-002",
        },
        "decisions": [
            {
                "event_id": "EV-001",
                "disposition": "include_assertive",
                "evidence_ids": ["EVID-001"],
                "qualification_label": None,
                "rationale": "Explicit Quran evidence.",
            },
            {
                "event_id": "EV-002",
                "disposition": "include_qualified",
                "evidence_ids": ["EVID-002"],
                "qualification_label": "ورد بأثر مقبول وفق الاعتماد البشري",
                "rationale": "Qualified language is required.",
            },
            {
                "event_id": "EV-003",
                "disposition": "editorial_only",
                "evidence_ids": [],
                "qualification_label": None,
                "rationale": "Episode transition only.",
            },
        ],
    }
    episode_definition = {
        "schema_version": "siraj-episode-definition-v1",
        "episode_id": "episode-001-adam",
        "historical_scope": {
            "required_event_ids": ["EV-001", "EV-002", "EV-003"]
        },
        "source_package": {
            "approval_status": "APPROVED",
            "path": "contracts/source-package-v1.approved.json",
        },
        "evidence_package": {
            "path": "evidence/approved-evidence-package-v1.json",
            "input_fingerprint": canonical_json_sha256(evidence_package),
        },
    }
    return {
        "episode_definition": episode_definition,
        "event_map": event_map,
        "editorial_blueprint": editorial_blueprint,
        "source_package": source_package,
        "evidence_package": evidence_package,
        "adjudication": adjudication,
    }


if __name__ == "__main__":
    unittest.main()
