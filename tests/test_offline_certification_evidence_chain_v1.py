from __future__ import annotations

from pathlib import Path

import pytest

from scripts.offline.certify_unified_constitution_e0_e7_v1 import (
    _assert_case_insensitive_unique_keys,
)


REPO = Path(__file__).resolve().parents[1]


def test_e7_audit_evidence_is_raw_hash_bound_and_not_final_self_reference() -> None:
    source = (
        REPO / "scripts/offline/certify_unified_constitution_e0_e7_v1.py"
    ).read_text(encoding="utf-8-sig")
    assert 'RAW_EVIDENCE_FILENAME = "E7_RAW_ENFORCEMENT_EVIDENCE.json"' in source
    assert "audit_evidence=RAW_EVIDENCE_FILENAME" in source
    assert 'audit_evidence="FINAL_OFFLINE_ENFORCEMENT_CERTIFICATION.json"' not in source
    assert '"audit_evidence_hash_bound"' in source
    assert '"circular_self_reference": False' in source


def test_certification_json_rejects_case_insensitive_key_collisions() -> None:
    _assert_case_insensitive_unique_keys({"outer": {"unique": True}})
    with pytest.raises(ValueError, match="CASE_INSENSITIVE_JSON_KEY_COLLISION"):
        _assert_case_insensitive_unique_keys({"RULE_ID": "A", "rule_id": "B"})
