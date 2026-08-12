from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from src.application.visual_production_constitution_v2 import (
    load_visual_production_constitution_v2_1,
    validate_legacy_female_asset_record,
    validate_legacy_female_reuse_plan,
    validate_micro_shot_storyboard,
)


REPO = Path(__file__).resolve().parents[1]
EPISODE = REPO / "projects/episode-002-adam-temptation-fall-repentance"
STORYBOARD = EPISODE / "preproduction/EP002_SURGICAL_REPAIR_STORYBOARD_V2_1.json"
REAUDIT = EPISODE / "orchestration/ep002-legacy-female-reaudit-v2-1.json"
AUDIT = EPISODE / "orchestration/ep002-surgical-visual-asset-audit-v2-1.json"
REPORT = EPISODE / "orchestration/ep002-surgical-visual-repair-preproduction-v2-1.json"


def load_outputs() -> tuple[object, dict, list[dict], dict]:
    constitution = load_visual_production_constitution_v2_1(REPO)
    storyboard = json.loads(STORYBOARD.read_text(encoding="utf-8"))
    reaudit = json.loads(REAUDIT.read_text(encoding="utf-8"))
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    return constitution, storyboard, reaudit["REUSED_MICRO_SHOT_AUDIT"], audit


def test_v2_1_global_policy_is_active_and_fail_safe() -> None:
    constitution = load_visual_production_constitution_v2_1(REPO)
    policy = constitution.data["LEGACY_FEMALE_REUSE_POLICY"]
    assert constitution.version == "SIRAJ_VISUAL_PRODUCTION_CONSTITUTION_V2_1"
    assert constitution.data["CONSTITUTION_SCOPE"] == "ALL_FUTURE_EPISODES"
    assert constitution.data["FAIL_CLOSED"] is True
    assert policy["ZERO_LEGACY_FEMALE_REUSE_REQUIRED"] is True
    assert policy["UNCERTAIN_FEMALE_PRESENCE_REJECT"] is True
    assert policy["PRODUCTION_REUSE_ALLOWED_FOR_FEMALE_ASSET"] is False
    assert policy["FINAL_MONTAGE_ALLOWED_FOR_FEMALE_ASSET"] is False
    assert policy["FORENSIC_ASSET_PRESERVED"] is True


def test_confirmed_or_uncertain_legacy_female_asset_is_safety_excluded() -> None:
    base = {
        "FEMALE_PRESENT": "TRUE",
        "UNCERTAIN_FEMALE_PRESENCE": False,
        "REUSE_ALLOWED": False,
        "MONTAGE_ELIGIBLE": False,
        "FORENSIC_ASSET_PRESERVED": True,
        "DISPOSITION": "SAFETY_EXCLUDED",
        "NO_SALVAGE_TRANSFORM_USED": True,
    }
    assert validate_legacy_female_asset_record(base) == []

    uncertain = deepcopy(base)
    uncertain["FEMALE_PRESENT"] = "UNCERTAIN"
    uncertain["UNCERTAIN_FEMALE_PRESENCE"] = True
    assert validate_legacy_female_asset_record(uncertain) == []

    unsafe_reuse = deepcopy(base)
    unsafe_reuse["REUSE_ALLOWED"] = True
    assert "LEGACY_FEMALE_REUSE_ALLOWED_MUST_BE_FALSE" in validate_legacy_female_asset_record(unsafe_reuse)


def test_false_female_presence_is_the_only_legacy_reuse_state() -> None:
    record = {
        "FEMALE_PRESENT": "FALSE",
        "UNCERTAIN_FEMALE_PRESENCE": False,
        "REUSE_ALLOWED": True,
        "MONTAGE_ELIGIBLE": True,
        "FORENSIC_ASSET_PRESERVED": True,
        "DISPOSITION": "KEEP",
        "NO_SALVAGE_TRANSFORM_USED": True,
    }
    assert validate_legacy_female_asset_record(record) == []
    bad = deepcopy(record)
    bad["FEMALE_PRESENT"] = "UNCERTAIN"
    bad["UNCERTAIN_FEMALE_PRESENCE"] = True
    bad["REUSE_ALLOWED"] = False
    bad["MONTAGE_ELIGIBLE"] = False
    bad["DISPOSITION"] = "SAFETY_EXCLUDED"
    assert validate_legacy_female_reuse_plan([record]) == []
    assert validate_legacy_female_reuse_plan([bad])


def test_v2_1_reaudits_all_reused_microshots_and_has_zero_legacy_female_reuse() -> None:
    constitution, storyboard, reuse_records, audit = load_outputs()
    reused = [
        shot
        for shot in storyboard["MICRO_SHOTS"]
        if shot["SOURCE"] in {"EXISTING", "REASSIGNED_EXISTING"}
    ]
    assert len(reused) == 96
    assert len(reuse_records) == 96
    assert len({record["ASSET_ID"] for record in reuse_records}) == 40
    assert all(record["FEMALE_PRESENT"] == "FALSE" for record in reuse_records)
    assert all(record["UNCERTAIN_FEMALE_PRESENCE"] is False for record in reuse_records)
    assert all(record["REUSE_ALLOWED"] is True for record in reuse_records)
    assert all(record["MONTAGE_ELIGIBLE"] is True for record in reuse_records)
    assert all(record["FORENSIC_ASSET_PRESERVED"] is True for record in reuse_records)
    assert validate_legacy_female_reuse_plan(reuse_records) == []
    assert all(item["V2_1_REUSE_ELIGIBLE"] is True for item in audit["asset_audit"] if item["ASSET_ID"] in {r["ASSET_ID"] for r in reuse_records})
    result = validate_micro_shot_storyboard(
        storyboard,
        constitution,
        dossiers=json.loads(
            (EPISODE / "preproduction/EP002_CHARACTER_EVIDENCE_DOSSIERS_V2.json").read_text(encoding="utf-8")
        )["CHARACTERS"],
        temporal_audits={
            item["ASSET_ID"]: item
            for item in audit["asset_audit"]
            if item.get("V2_1_REUSE_ELIGIBLE") is True
        },
    )
    assert result["status"] == "PASS"


def test_v2_1_reuse_validator_rejects_true_or_uncertain_shot() -> None:
    constitution, storyboard, _, audit = load_outputs()
    candidate = deepcopy(storyboard)
    reused = next(
        shot
        for shot in candidate["MICRO_SHOTS"]
        if shot["SOURCE"] in {"EXISTING", "REASSIGNED_EXISTING"}
    )
    reused["FEMALE_PRESENT"] = "UNCERTAIN"
    reused["UNCERTAIN_FEMALE_PRESENCE"] = True
    reused["REUSE_ALLOWED"] = False
    reused["MONTAGE_ELIGIBLE"] = False
    reused["DISPOSITION"] = "SAFETY_EXCLUDED"
    result = validate_micro_shot_storyboard(
        candidate,
        constitution,
        dossiers=json.loads(
            (EPISODE / "preproduction/EP002_CHARACTER_EVIDENCE_DOSSIERS_V2.json").read_text(encoding="utf-8")
        )["CHARACTERS"],
        temporal_audits={
            item["ASSET_ID"]: item
            for item in audit["asset_audit"]
            if item.get("V2_1_REUSE_ELIGIBLE") is True
        },
    )
    assert result["status"] == "FAIL"
    assert any("FEMALE_PRESENT_MUST_BE_FALSE" in error for error in result["errors"])


def test_v2_1_report_has_required_zero_counts_and_preserves_forensics() -> None:
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    reaudit = json.loads(REAUDIT.read_text(encoding="utf-8"))
    assert report["STATUS"] == "PASS_EP002_SURGICAL_VISUAL_REPAIR_PREPRODUCTION_V2_1"
    assert report["REUSED_LEGACY_MICRO_SHOT_COUNT"] == 96
    assert report["LEGACY_FEMALE_REUSE_COUNT"] == 0
    assert report["BLURRED_FEMALE_REUSE_COUNT"] == 0
    assert report["MASKED_FEMALE_REUSE_COUNT"] == 0
    assert report["CROPPED_FEMALE_REUSE_COUNT"] == 0
    assert report["FORENSIC_ASSET_PRESERVED"] is True
    assert report["PRODUCTION_REUSE_ALLOWED_FOR_EXCLUDED"] is False
    assert report["FINAL_MONTAGE_ALLOWED_FOR_EXCLUDED"] is False
    assert report["NETWORK_CALLS"] == 0
    assert report["PROVIDER_CALLS"] == 0
    assert report["PAID_CALLS"] == 0
    assert report["VISUAL_GENERATION_ALLOWED"] is False
    assert report["APPROVED_STORYBOARD_SHA256"] is None
    assert reaudit["LEGACY_FEMALE_REUSE_COUNT"] == 0
    assert reaudit["NO_SALVAGE_TRANSFORMS_USED"] is True
