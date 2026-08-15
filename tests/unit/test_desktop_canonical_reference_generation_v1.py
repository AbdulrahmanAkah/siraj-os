from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.application.desktop_canonical_reference_generation_v1 import (
    EPISODE_ID,
    CanonicalReferenceGenerationError,
    accept_reference_asset,
    prepare_reference_task,
    reject_reference_asset,
    required_checks,
)


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _seed_repo(tmp_path: Path) -> Path:
    repo = tmp_path
    reports = repo / "reports" / "pr01-production-readiness"
    assets = (
        repo
        / "projects"
        / EPISODE_ID
        / "orchestration"
        / "canonical-reference-v1"
        / "assets"
    )
    assets.mkdir(parents=True, exist_ok=True)

    _write(
        reports / "EP002_R27_CANONICAL_REFERENCE_PREPARATION_RESULT_V1.json",
        {
            "status": "PASS_CANONICAL_REFERENCE_PREPARATION",
            "reference_briefs_path": "reports/pr01-production-readiness/EP002_R27_CANONICAL_REFERENCE_BRIEFS_V1.json",
            "acceptance_checklist_path": "reports/pr01-production-readiness/EP002_R27_CANONICAL_REFERENCE_ACCEPTANCE_CHECKLIST_V1.json",
            "asset_intake_path": "reports/pr01-production-readiness/EP002_R27_CANONICAL_REFERENCE_ASSET_INTAKE_V1.json",
            "reference_asset_directory": f"projects/{EPISODE_ID}/orchestration/canonical-reference-v1/assets",
            "current_r27_counts": {"KEEP": 0, "REGENERATE": 0, "BLOCK": 27},
            "reclassification_performed": False,
            "regeneration_authorized": False,
        },
    )
    refs = []
    for ref_id in (
        "ADAM_GARDEN",
        "ADAM_EARTH",
        "ADAM_DEBATE",
        "HAWWA_GARDEN",
        "HAWWA_EARTH",
        "MUSA_DEBATE",
    ):
        refs.append(
            {
                "reference_id": ref_id,
                "brief": {
                    "purpose": "canonical identity",
                    "character": ref_id.split("_", 1)[0],
                    "narrative_state": ref_id.split("_", 1)[1],
                    "composition": ["full body", "rear or occluded face"],
                    "identity_lock": ["stable body identity"],
                    "wardrobe": ["simple time-neutral draped garment"],
                    "hard_forbidden": ["visible face", "modern clothing"],
                },
            }
        )
    _write(
        reports / "EP002_R27_CANONICAL_REFERENCE_BRIEFS_V1.json",
        {
            "reference_count": 6,
            "global_style_and_policy": {
                "visual_style": "cinematic, grounded",
                "historical_uncertainty_policy": "neutral non-assertive design",
            },
            "references": refs,
        },
    )
    common = [
        "FILE_EXISTS_AND_DECODES",
        "NO_VISIBLE_HUMAN_FACE",
        "SHA256_BINDING_REQUIRED",
    ]
    _write(
        reports / "EP002_R27_CANONICAL_REFERENCE_ACCEPTANCE_CHECKLIST_V1.json",
        {
            "human_review_required": True,
            "automatic_pass_allowed": False,
            "common_checks": common,
            "state_specific_checks": {
                ref_id: ["STATE_SPECIFIC_PASS"]
                for ref_id in (
                    "ADAM_GARDEN",
                    "ADAM_EARTH",
                    "ADAM_DEBATE",
                    "HAWWA_GARDEN",
                    "HAWWA_EARTH",
                    "MUSA_DEBATE",
                )
            },
        },
    )
    _write(
        reports / "EP002_R27_CANONICAL_REFERENCE_ASSET_INTAKE_V1.json",
        {
            "status": "AWAITING_6_ASSETS",
            "accepted_count": 0,
            "required_count": 6,
            "reclassification_allowed": False,
            "regeneration_allowed": False,
            "required_assets": [
                {
                    "reference_id": ref_id,
                    "filename": f"{ref_id}.png",
                    "status": "MISSING",
                    "sha256": None,
                    "human_review": "NOT_STARTED",
                    "accepted": False,
                }
                for ref_id in (
                    "ADAM_GARDEN",
                    "ADAM_EARTH",
                    "ADAM_DEBATE",
                    "HAWWA_GARDEN",
                    "HAWWA_EARTH",
                    "MUSA_DEBATE",
                )
            ],
        },
    )
    _write(
        repo / "projects/_series/siraj-media-pricing-registry-v2.json",
        {
            "registry_version": "test",
            "entries": [
                {
                    "provider": "RUNWARE",
                    "model": "google:4@3",
                    "media_kind": "RUNWARE_IMAGE",
                    "status": "PRICED",
                    "unit_price": 0.06895,
                    "currency": "USD",
                    "input_image_pricing": {
                        "additional_input_image_price": 0.00028
                    },
                }
            ],
        },
    )
    return repo


def _intake(repo: Path) -> dict:
    path = (
        repo
        / "reports"
        / "pr01-production-readiness"
        / "EP002_R27_CANONICAL_REFERENCE_ASSET_INTAKE_V1.json"
    )
    return json.loads(path.read_text(encoding="utf-8"))


def test_initial_reference_routes_to_character_consistency(tmp_path: Path):
    repo = _seed_repo(tmp_path)
    prepared = prepare_reference_task(
        repo_root=repo,
        reference_id="ADAM_GARDEN",
    )
    assert prepared["route"]["model"] == "google:4@3"
    assert prepared["route"]["role"] == "CHARACTER_CONSISTENCY"
    assert prepared["payload"]["taskType"] == "imageInference"
    assert "No visible human face" in prepared["prompt"]


def test_dependent_reference_requires_accepted_base(tmp_path: Path):
    repo = _seed_repo(tmp_path)
    with pytest.raises(
        CanonicalReferenceGenerationError,
        match="DEPENDENCY_REFERENCE_NOT_ACCEPTED:ADAM_GARDEN",
    ):
        prepare_reference_task(repo_root=repo, reference_id="ADAM_EARTH")


def test_dependent_reference_uses_data_uri_after_acceptance(tmp_path: Path):
    repo = _seed_repo(tmp_path)
    intake_path = (
        repo
        / "reports"
        / "pr01-production-readiness"
        / "EP002_R27_CANONICAL_REFERENCE_ASSET_INTAKE_V1.json"
    )
    intake = _intake(repo)
    row = next(x for x in intake["required_assets"] if x["reference_id"] == "ADAM_GARDEN")
    final = (
        repo
        / "projects"
        / EPISODE_ID
        / "orchestration"
        / "canonical-reference-v1"
        / "assets"
        / "ADAM_GARDEN.png"
    )
    final.write_bytes(b"fake-png")
    import hashlib
    row["accepted"] = True
    row["sha256"] = hashlib.sha256(b"fake-png").hexdigest()
    row["status"] = "ACCEPTED_SHA256_BOUND"
    row["human_review"] = "PASS"
    _write(intake_path, intake)

    prepared = prepare_reference_task(repo_root=repo, reference_id="ADAM_EARTH")
    refs = prepared["payload"]["inputs"]["referenceImages"]
    assert len(refs) == 1
    assert refs[0].startswith("data:image/png;base64,")
    assert prepared["route"]["role"] == "REFERENCE_EDIT"


def test_accept_requires_complete_human_checklist(tmp_path: Path):
    repo = _seed_repo(tmp_path)
    intake_path = (
        repo
        / "reports"
        / "pr01-production-readiness"
        / "EP002_R27_CANONICAL_REFERENCE_ASSET_INTAKE_V1.json"
    )
    candidate = (
        repo
        / "projects"
        / EPISODE_ID
        / "orchestration"
        / "canonical-reference-v1"
        / "candidates"
        / "ADAM_GARDEN"
        / "candidate.png"
    )
    candidate.parent.mkdir(parents=True, exist_ok=True)
    candidate.write_bytes(b"candidate")
    import hashlib
    intake = _intake(repo)
    row = next(x for x in intake["required_assets"] if x["reference_id"] == "ADAM_GARDEN")
    row["candidate_path"] = str(candidate.relative_to(repo)).replace("\\", "/")
    row["candidate_sha256"] = hashlib.sha256(b"candidate").hexdigest()
    row["status"] = "CANDIDATE_PENDING_HUMAN_REVIEW"
    _write(intake_path, intake)

    with pytest.raises(
        CanonicalReferenceGenerationError,
        match="HUMAN_REFERENCE_CHECKLIST_INCOMPLETE",
    ):
        accept_reference_asset(repo, "ADAM_GARDEN", confirmed_checks=[])

    checks = required_checks(repo, "ADAM_GARDEN")
    updated = accept_reference_asset(
        repo,
        "ADAM_GARDEN",
        confirmed_checks=checks,
    )
    accepted = next(
        x for x in updated["required_assets"] if x["reference_id"] == "ADAM_GARDEN"
    )
    assert accepted["accepted"] is True
    assert accepted["human_review"] == "PASS"
    assert updated["reclassification_allowed"] is False
    assert updated["regeneration_allowed"] is False


def test_reject_preserves_candidate_and_requires_reason(tmp_path: Path):
    repo = _seed_repo(tmp_path)
    intake_path = (
        repo
        / "reports"
        / "pr01-production-readiness"
        / "EP002_R27_CANONICAL_REFERENCE_ASSET_INTAKE_V1.json"
    )
    candidate = (
        repo
        / "projects"
        / EPISODE_ID
        / "orchestration"
        / "canonical-reference-v1"
        / "candidates"
        / "MUSA_DEBATE"
        / "candidate.png"
    )
    candidate.parent.mkdir(parents=True, exist_ok=True)
    candidate.write_bytes(b"candidate")
    import hashlib
    intake = _intake(repo)
    row = next(x for x in intake["required_assets"] if x["reference_id"] == "MUSA_DEBATE")
    row["candidate_path"] = str(candidate.relative_to(repo)).replace("\\", "/")
    row["candidate_sha256"] = hashlib.sha256(b"candidate").hexdigest()
    row["status"] = "CANDIDATE_PENDING_HUMAN_REVIEW"
    _write(intake_path, intake)

    with pytest.raises(
        CanonicalReferenceGenerationError,
        match="REFERENCE_REJECTION_REASON_REQUIRED",
    ):
        reject_reference_asset(repo, "MUSA_DEBATE", reason="")

    updated = reject_reference_asset(
        repo,
        "MUSA_DEBATE",
        reason="face visible",
    )
    rejected = next(
        x for x in updated["required_assets"] if x["reference_id"] == "MUSA_DEBATE"
    )
    assert rejected["accepted"] is False
    assert rejected["human_review"] == "REJECTED"
    assert candidate.is_file()
