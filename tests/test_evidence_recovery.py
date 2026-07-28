from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from src.application.storyboard_runtime.evidence_recovery import (
    AdamEvidenceKnowledgeRecovery,
    EvidenceRecoveryError,
    EVIDENCE_GATE_STATUS,
    RECOVERY_STATUS,
    validate_recovered_manifest,
    write_recovered_evidence_knowledge,
)


class AdamEvidenceKnowledgeRecoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name) / "repo"
        self._build_fixture(self.repo)

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def _build_fixture(repo: Path) -> None:
        (repo / ".git").mkdir(parents=True)
        episode = repo / "projects" / "episode-001-adam"
        contracts = episode / "contracts"
        editorial = episode / "editorial"
        normalized = (
            episode / "sources" / "secondary" / "assets" / "normalized"
        )
        review = episode / "sources" / "secondary" / "report-level-extraction"
        contracts.mkdir(parents=True)
        editorial.mkdir(parents=True)
        normalized.mkdir(parents=True)
        review.mkdir(parents=True)

        event_ids = [
            f"EV-ADAM-{number:03d}"
            for number in range(1, 38)
        ]
        event_map = [
            {"event_id": event_id, "verification_status": "pending"}
            for event_id in event_ids
        ]
        (editorial / "event-map.json").write_text(
            json.dumps(event_map),
            encoding="utf-8",
        )

        source_items = []
        for index in range(9):
            source_id = f"SRC-TEST-{index + 1:03d}"
            supported = event_ids[index::9]
            source_items.append(
                {
                    "source_id": source_id,
                    "source_type": "QURAN" if index == 0 else "TAFSIR",
                    "access_status": "PLANNED",
                    "allowed_for_extraction": False,
                    "allowed_for_quotation": False,
                    "checksum": "",
                    "path": "",
                    "notes": {"supports_event_ids": supported},
                }
            )
            source_root = normalized / source_id
            source_root.mkdir()
            (source_root / "manifest.json").write_text(
                json.dumps(
                    {
                        "schema_version": "fixture-normalized-v1",
                        "source_id": source_id,
                        "status": "NORMALIZED",
                    }
                ),
                encoding="utf-8",
            )
            (source_root / "pages.jsonl").write_text(
                "\n".join(
                    json.dumps(
                        {
                            "schema_version": "fixture-page-v1",
                            "source_id": source_id,
                            "page_id": f"{source_id}-P-{page}",
                        }
                    )
                    for page in range(2)
                )
                + "\n",
                encoding="utf-8",
            )
            (source_root / "toc.jsonl").write_text(
                json.dumps(
                    {
                        "schema_version": "fixture-toc-v1",
                        "source_id": source_id,
                        "status": "READY",
                    }
                )
                + "\n",
                encoding="utf-8",
            )

        package = {
            "schema_version": "siraj-episode-source-package-v1",
            "package_status": "DRAFT_ACQUISITION_PENDING",
            "source_items": source_items,
        }
        (contracts / "source-package-v1.draft.json").write_text(
            json.dumps(package),
            encoding="utf-8",
        )

        for index in range(46):
            source_id = f"SRC-TEST-{(index % 9) + 1:03d}"
            event_id = event_ids[index % len(event_ids)]
            (review / f"review-{index:03d}.json").write_text(
                json.dumps(
                    {
                        "schema_version": "fixture-review-v1",
                        "source_id": source_id,
                        "event_id": event_id,
                        "report_id": f"REPORT-TEST-{index:03d}",
                        "review_status": "PENDING_HUMAN_REVIEW",
                        "notes": "raw wording must not be copied",
                    }
                ),
                encoding="utf-8",
            )

    def test_builds_expected_inventory(self) -> None:
        recovered = AdamEvidenceKnowledgeRecovery().build(self.repo)
        self.assertEqual(recovered.normalized_source_count, 9)
        self.assertEqual(recovered.review_artifact_count, 46)
        self.assertEqual(recovered.recovery_status, RECOVERY_STATUS)
        self.assertEqual(recovered.evidence_gate_status, EVIDENCE_GATE_STATUS)

    def test_manifest_is_deterministic(self) -> None:
        first = AdamEvidenceKnowledgeRecovery().build(self.repo)
        second = AdamEvidenceKnowledgeRecovery().build(self.repo)
        self.assertEqual(first, second)
        self.assertEqual(first.to_json(), second.to_json())

    def test_raw_review_text_is_not_copied(self) -> None:
        recovered = AdamEvidenceKnowledgeRecovery().build(self.repo)
        self.assertNotIn("raw wording must not be copied", recovered.to_json())

    def test_gate_remains_withheld(self) -> None:
        payload = AdamEvidenceKnowledgeRecovery().build(self.repo).to_manifest()
        self.assertEqual(
            payload["evidence_gate_status"],
            "WITHHELD_PENDING_APPROVED_EVIDENCE_PACKAGE",
        )
        self.assertEqual(payload["automatic_evidence_approval"], "FORBIDDEN")
        self.assertEqual(payload["live_provider_execution"], "BLOCKED")

    def test_source_package_stays_draft(self) -> None:
        recovered = AdamEvidenceKnowledgeRecovery().build(self.repo)
        self.assertEqual(
            recovered.source_package_status,
            "DRAFT_ACQUISITION_PENDING",
        )
        self.assertIn("SOURCE_PACKAGE_NOT_HUMAN_APPROVED", recovered.gaps)

    def test_missing_source_count_is_rejected(self) -> None:
        source_root = (
            self.repo
            / "projects"
            / "episode-001-adam"
            / "sources"
            / "secondary"
            / "assets"
            / "normalized"
            / "SRC-TEST-009"
        )
        for child in source_root.iterdir():
            child.unlink()
        source_root.rmdir()
        with self.assertRaisesRegex(EvidenceRecoveryError, "at least nine"):
            AdamEvidenceKnowledgeRecovery().build(self.repo)

    def test_missing_review_count_is_rejected(self) -> None:
        review_root = (
            self.repo
            / "projects"
            / "episode-001-adam"
            / "sources"
            / "secondary"
            / "report-level-extraction"
        )
        for path in sorted(review_root.glob("review-*.json"))[:2]:
            path.unlink()
        with self.assertRaisesRegex(EvidenceRecoveryError, "at least 46"):
            AdamEvidenceKnowledgeRecovery().build(self.repo)

    def test_unknown_event_is_reported_not_approved(self) -> None:
        review_path = (
            self.repo
            / "projects"
            / "episode-001-adam"
            / "sources"
            / "secondary"
            / "report-level-extraction"
            / "review-000.json"
        )
        payload = json.loads(review_path.read_text(encoding="utf-8"))
        payload["event_id"] = "EV-ADAM-999"
        review_path.write_text(json.dumps(payload), encoding="utf-8")
        recovered = AdamEvidenceKnowledgeRecovery().build(self.repo)
        self.assertIn("EV-ADAM-999", recovered.unknown_event_ids)
        self.assertIn(
            "REVIEW_ARTIFACTS_REFERENCE_OUT_OF_SCOPE_EVENTS",
            recovered.gaps,
        )

    def test_secret_like_field_is_ignored(self) -> None:
        review_path = (
            self.repo
            / "projects"
            / "episode-001-adam"
            / "sources"
            / "secondary"
            / "report-level-extraction"
            / "review-000.json"
        )
        payload = json.loads(review_path.read_text(encoding="utf-8"))
        payload["api_key"] = "forbidden"
        review_path.write_text(json.dumps(payload), encoding="utf-8")
        recovered = AdamEvidenceKnowledgeRecovery().build(self.repo)
        self.assertNotIn("forbidden", recovered.to_json())
        self.assertNotIn("api_key", recovered.to_json())

    def test_absolute_paths_do_not_leak(self) -> None:
        review_path = (
            self.repo
            / "projects"
            / "episode-001-adam"
            / "sources"
            / "secondary"
            / "report-level-extraction"
            / "review-000.json"
        )
        payload = json.loads(review_path.read_text(encoding="utf-8"))
        payload["local_path"] = r"C:\private\source.txt"
        review_path.write_text(json.dumps(payload), encoding="utf-8")
        recovered = AdamEvidenceKnowledgeRecovery().build(self.repo)
        self.assertNotIn(r"C:\private\source.txt", recovered.to_json())

    def test_write_is_canonical_utf8_lf(self) -> None:
        recovered = AdamEvidenceKnowledgeRecovery().build(self.repo)
        output = self.repo / "out.json"
        write_recovered_evidence_knowledge(recovered, output)
        data = output.read_bytes()
        self.assertNotIn(b"\r\n", data)
        payload = json.loads(data.decode("utf-8"))
        validate_recovered_manifest(payload)

    def test_tampered_manifest_gate_is_rejected(self) -> None:
        payload = AdamEvidenceKnowledgeRecovery().build(self.repo).to_manifest()
        payload["evidence_gate_status"] = "OPEN"
        with self.assertRaisesRegex(EvidenceRecoveryError, "opened"):
            validate_recovered_manifest(payload)

    def test_unregistered_source_is_reported_not_approved(self) -> None:
        review_path = (
            self.repo
            / "projects"
            / "episode-001-adam"
            / "sources"
            / "secondary"
            / "report-level-extraction"
            / "review-000.json"
        )
        payload = json.loads(review_path.read_text(encoding="utf-8"))
        payload["source_id"] = "SRC-LOCAL-UNREGISTERED"
        review_path.write_text(json.dumps(payload), encoding="utf-8")
        recovered = AdamEvidenceKnowledgeRecovery().build(self.repo)
        self.assertIn("SRC-LOCAL-UNREGISTERED", recovered.unknown_source_ids)
        self.assertIn(
            "REVIEW_ARTIFACTS_REFERENCE_UNREGISTERED_SOURCES",
            recovered.gaps,
        )

    def test_cli_runs_from_arbitrary_cwd(self) -> None:
        script = (
            Path(__file__).resolve().parents[1]
            / "scripts"
            / "fast_track"
            / "recover_adam_evidence_knowledge_v1.py"
        )
        output = self.repo / "recovered.json"
        with tempfile.TemporaryDirectory() as cwd:
            result = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    str(script),
                    "--repo-root",
                    str(self.repo),
                    "--output",
                    str(output),
                ],
                cwd=cwd,
                text=True,
                encoding="utf-8",
                errors="replace",
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn(
            "STATUS=PASS_RECOVERED_EVIDENCE_KNOWLEDGE",
            result.stdout,
        )
        self.assertTrue(output.is_file())


if __name__ == "__main__":
    unittest.main()
