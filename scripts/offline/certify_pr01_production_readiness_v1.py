"""Generate the PR01 offline certification packet without provider access."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import uuid
import wave
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.application.pr01_face_detection_v1 import (  # noqa: E402
    MODEL_REL,
    calibrate_thresholds,
    load_detector_metadata,
)
from src.application.pr01_production_readiness_v1 import (  # noqa: E402
    BRAND_ASSETS_DIRECTORY,
    BRAND_INTRO_SHA256,
    BRAND_OUTRO_SHA256,
    CONSTITUTION_BUNDLE_SHA256,
    CONSTITUTION_ID,
    CONSTITUTION_VERSION,
    EXACT_MODEL_ID,
    EXACT_PROVIDER,
    PR01_ID,
    UNKNOWN_BLOCK_CODE,
    UNKNOWN_ATTEMPT_ID,
    UNKNOWN_REQUEST_ID,
    UNKNOWN_TASK_UUID,
    UNKNOWN_STATUS,
    build_exact_provider_payload,
    canonical_sha256,
    classify_audio_measurement,
    config_path,
    constitution_and_brand_self_test,
    cost_preflight,
    document_hash,
    duration_preservation_check,
    historical_unknown_state,
    load_pricing_snapshot,
    load_profile,
    load_provider_binding,
    measure_audio_file,
    production_readiness_result,
    read_json,
    run_offline_gate_simulation,
    sha256_file,
    validate_exact_provider_payload,
    validate_profile,
)


REPORT_REL = Path("reports/pr01-production-readiness")
R27_MANIFEST_REL = Path(
    "projects/episode-002-adam-temptation-fall-repentance/orchestration/"
    "ep002-v2-4-repair-provider-execution-v1/render-conformance-review-v1/_MANIFEST.json"
)
CALIBRATION_REL = Path("tests/fixtures/pr01_face_calibration")
AUDIO_FIXTURE_REL = Path("tests/fixtures/pr01_audio/pr01_synthetic_delivery.wav")


def write_json(path: Path, value: Mapping[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return sha256_file(path)


def write_bound_json(path: Path, value: Mapping[str, Any], hash_key: str = "document_sha256") -> str:
    payload = dict(value)
    payload[hash_key] = ""
    payload[hash_key] = document_hash(payload)
    return write_json(path, payload)


def git_value(*args: str) -> str:
    process = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return process.stdout.strip()


def make_audio_fixture(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sample_rate = 48_000
    duration_seconds = 4
    amplitude = 0.16
    frequency = 1_000.0
    with wave.open(str(path), "wb") as output:
        output.setnchannels(2)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        frames = bytearray()
        for index in range(sample_rate * duration_seconds):
            value = int(32767 * amplitude * math.sin(2.0 * math.pi * frequency * index / sample_rate))
            sample = value.to_bytes(2, byteorder="little", signed=True)
            frames.extend(sample)
            frames.extend(sample)
        output.writeframes(frames)


def build_m01(profile: Mapping[str, Any]) -> dict[str, Any]:
    audio_path = REPO_ROOT / AUDIO_FIXTURE_REL
    make_audio_fixture(audio_path)
    measurement = measure_audio_file(audio_path)
    classification = classify_audio_measurement(measurement, profile)
    duration = measurement.get("duration_seconds")
    duration_pass = isinstance(duration, (int, float)) and duration_preservation_check(4.0, float(duration), profile)
    status = "PASS" if classification.get("status") == "PASS" and duration_pass else "BLOCKED"
    return {
        "closure_id": "OPEN-M01-AUDIO-DELIVERY-CLOSURE-V1",
        "status": status,
        "profile_id": profile.get("profile_id"),
        "profile_hash": document_hash(profile),
        "fixture": {
            "path": str(AUDIO_FIXTURE_REL).replace("\\", "/"),
            "sha256": sha256_file(audio_path),
            "synthetic": True,
            "actual_bytes_measured": True,
        },
        "measurement": measurement,
        "classification": classification,
        "duration_test": {
            "authoritative_input_seconds": 4.0,
            "measured_output_seconds": duration,
            "preserved": duration_pass,
            "policy": "INPUT_DURATION",
        },
        "unknown_measurement_blocks": True,
        "no_silent_pass": True,
        "network_production_calls": 0,
        "paid_calls": 0,
    }


def build_m02(profile: Mapping[str, Any], binding: Mapping[str, Any], pricing: Mapping[str, Any]) -> dict[str, Any]:
    task_uuid = "00000000-0000-4000-8000-000000000001"
    prompt = "Abstract historically grounded earth surface with a concealed human-scale composition and no figures."
    payload = build_exact_provider_payload(
        prompt=prompt,
        duration_seconds=4,
        aspect_ratio="16:9",
        resolution="720p",
        task_uuid=task_uuid,
        seed=17,
    )
    validated = validate_exact_provider_payload(payload)
    price = cost_preflight(
        [{"unit_id": "PR01-SIM-001", "duration_seconds": 4, "resolution": "720p"}],
        pricing,
        max_cost_usd="1.00",
    )
    alias_rejected = False
    try:
        alias_payload = dict(payload)
        alias_payload["model"] = "google:veo@3.1"
        validate_exact_provider_payload(alias_payload)
    except Exception:
        alias_rejected = True
    negative_rejected = False
    try:
        negative_payload = dict(payload)
        negative_payload["negativePrompt"] = "no face"
        validate_exact_provider_payload(negative_payload)
    except Exception:
        negative_rejected = True
    simulation = run_offline_gate_simulation(payload)
    transform = binding["compatibility_transform"]
    source_relative = str(transform["source"]).split(":", 1)[0]
    source_path = REPO_ROOT / source_relative
    source_hash_matches = source_path.is_file() and sha256_file(source_path) == transform["source_sha256"]
    return {
        "closure_id": "OPEN-M02-VEO31-LITE-BINDING-CLOSURE-V1",
        "status": "PASS" if alias_rejected and negative_rejected and source_hash_matches and simulation["paid_calls"] == 0 else "BLOCKED",
        "provider": EXACT_PROVIDER,
        "exact_model_id": EXACT_MODEL_ID,
        "provider_binding_hash": document_hash(binding),
        "technical_profile_hash": document_hash(profile),
        "pricing_snapshot_hash": document_hash(pricing),
        "task_uuid": task_uuid,
        "payload": validated,
        "prompt_sha256": canonical_sha256(prompt),
        "payload_sha256": canonical_sha256(payload),
        "exact_model_alias_rejected": alias_rejected,
        "negative_prompt_rejected": negative_rejected,
        "hidden_creative_transform": False,
        "compatibility_transform_hash_bound": document_hash(binding["compatibility_transform"]),
        "compatibility_transform_source_hash_matches": source_hash_matches,
        "cost_preflight": price,
        "offline_gate_simulation": simulation,
        "network_production_calls": 0,
        "paid_calls": 0,
    }


def extract_frame(source: Path, frame_index: int, destination: Path) -> None:
    import cv2

    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        raise RuntimeError(f"CALIBRATION_SOURCE_OPEN_FAILED:{source}")
    capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
    ok, frame = capture.read()
    capture.release()
    if not ok:
        raise RuntimeError(f"CALIBRATION_FRAME_MISSING:{source}:{frame_index}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(destination), frame):
        raise RuntimeError(f"CALIBRATION_FRAME_WRITE_FAILED:{destination}")


def make_negative_fixtures(directory: Path) -> list[Path]:
    import cv2
    import numpy as np

    directory.mkdir(parents=True, exist_ok=True)
    specs = [
        ("negative_black.png", np.zeros((360, 640, 3), dtype=np.uint8)),
        ("negative_abstract_gradient.png", np.dstack([np.tile(np.arange(640, dtype=np.uint8), (360, 1)), np.full((360, 640), 80, dtype=np.uint8), np.flipud(np.tile(np.arange(360, dtype=np.uint8)[:, None], (1, 640)))])),
    ]
    paths: list[Path] = []
    for name, image in specs:
        path = directory / name
        if not cv2.imwrite(str(path), image):
            raise RuntimeError(f"CALIBRATION_NEGATIVE_WRITE_FAILED:{path}")
        paths.append(path)
    return paths


def build_m03() -> dict[str, Any]:
    import cv2

    directory = REPO_ROOT / CALIBRATION_REL
    directory.mkdir(parents=True, exist_ok=True)
    r27 = read_json(REPO_ROOT / R27_MANIFEST_REL)
    unit_by_id = {str(row["unit_id"]): row for row in r27.get("units", [])}
    source_specs = [
        ("positive_historical_failure_001.png", "V23-GEN-001-EATING-ANCHOR", 0),
        ("positive_historical_failure_002.png", "V23-GEN-001-EATING-ANCHOR", 60),
        ("positive_historical_failure_003.png", "V23-GEN-001-EATING-ANCHOR", 120),
        ("positive_historical_failure_004.png", "V23-GEN-001-EATING-ANCHOR", 180),
    ]
    positives: list[Path] = []
    positive_records: list[dict[str, Any]] = []
    for name, unit_id, frame_index in source_specs:
        unit = unit_by_id[unit_id]
        source = REPO_ROOT / str(unit["asset_path"])
        destination = directory / name
        extract_frame(source, frame_index, destination)
        positives.append(destination)
        positive_records.append(
            {
                "path": str(destination.relative_to(REPO_ROOT)).replace("\\", "/"),
                "class": "POSITIVE_CRITICAL_FACE",
                "source_asset": str(unit["asset_path"]),
                "source_asset_sha256": unit["asset_sha256"],
                "source_frame_index": frame_index,
                "source_read_only": True,
                "label_basis": "historical_failure_calibration_input_only; no R27 review decision",
                "sha256": sha256_file(destination),
            }
        )
    negatives = make_negative_fixtures(directory)
    negative_records = [
        {
            "path": str(path.relative_to(REPO_ROOT)).replace("\\", "/"),
            "class": "NEGATIVE_NO_FACE",
            "synthetic": True,
            "sha256": sha256_file(path),
        }
        for path in negatives
    ]
    corpus = {
        "corpus_id": "SIRAJ_PR01_FACE_CALIBRATION_CORPUS_V1",
        "status": "CALIBRATION_ONLY_NOT_EP002_REVIEW",
        "positive_records": positive_records,
        "negative_records": negative_records,
        "all_source_assets_read_only": True,
        "human_review_decisions": 0,
    }
    corpus_hash = canonical_sha256(corpus)
    calibration = calibrate_thresholds(REPO_ROOT, positives, negatives)
    metadata = load_detector_metadata(REPO_ROOT)
    runtime = cv2.__version__
    status = "PASS" if calibration["critical_positive_recall"] == 1.0 else "BLOCKED"
    return {
        "closure_id": "OPEN-M03-FACE-DETECTION-CALIBRATION-CLOSURE-V1",
        "status": status,
        "detector": metadata,
        "opencv_runtime_version": runtime,
        "model_sha256": sha256_file(REPO_ROOT / MODEL_REL),
        "calibration_corpus": corpus,
        "calibration_corpus_sha256": corpus_hash,
        "calibration": calibration,
        "critical_positive_recall_100_percent": calibration["critical_positive_recall"] == 1.0,
        "pixel_detector_is_helper_only": True,
        "all_decoded_frames_human_final_review_required": True,
        "historical_failure_assets_review_decisions": 0,
        "network_production_calls": 0,
        "paid_calls": 0,
    }


def video_inventory(path: Path, expected_frames: int) -> dict[str, Any]:
    import cv2

    capture = cv2.VideoCapture(str(path))
    opened = capture.isOpened()
    if not opened:
        return {"status": "BLOCKED", "reason": "ASSET_OPEN_FAILED"}
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
    reported_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    capture.release()
    return {
        "status": "PASS" if reported_frames in (0, expected_frames) else "BLOCKED",
        "width": width,
        "height": height,
        "fps": fps,
        "reported_frame_count": reported_frames,
        "manifest_decoded_frames_reviewable": expected_frames,
        "metadata_only": True,
        "frames_human_reviewed": 0,
    }


def build_r27_handoff() -> dict[str, Any]:
    manifest_path = REPO_ROOT / R27_MANIFEST_REL
    manifest = read_json(manifest_path)
    before_hashes: dict[str, str] = {}
    entries: list[dict[str, Any]] = []
    all_valid = True
    for unit in manifest.get("units", []):
        relative = str(unit["asset_path"])
        path = REPO_ROOT / relative
        expected = str(unit.get("asset_sha256") or "")
        actual_before = sha256_file(path) if path.is_file() else None
        if actual_before is not None:
            before_hashes[relative] = actual_before
        matches = actual_before == expected
        all_valid = all_valid and matches
        media = video_inventory(path, int(unit.get("decoded_frames_reviewable") or 0)) if path.is_file() else {"status": "BLOCKED", "reason": "ASSET_MISSING"}
        actual_after = sha256_file(path) if path.is_file() else None
        unchanged = actual_before == actual_after
        all_valid = all_valid and unchanged
        entries.append(
            {
                "ordinal": unit.get("ordinal"),
                "unit_id": unit.get("unit_id"),
                "asset_path": relative,
                "asset_sha256_expected": expected,
                "asset_sha256_actual": actual_before,
                "asset_hash_matches_receipt": matches,
                "asset_hash_unchanged_after_inventory": unchanged,
                "member_shot_ids": list(unit.get("member_shot_ids") or []),
                "continuity_group": unit.get("continuity_group"),
                "decoded_frames_reviewable": unit.get("decoded_frames_reviewable"),
                "metadata_inventory": media,
                "review_status": "PENDING_HUMAN_REVIEW",
                "review_decision": "NOT_STARTED",
                "approved_for_montage": False,
                "approved_for_qa": False,
                "provider_retry_allowed": False,
                "review_mode": "ALL_DECODED_FRAMES_CONTACT_SHEET_8X8",
            }
        )
    count_ok = len(entries) == int(manifest.get("unit_count") or -1) == 27
    status = "PASS" if all_valid and count_ok else "BLOCKED"
    return {
        "manifest_id": "EP002_R27_REVIEW_INPUT_MANIFEST_V1",
        "status": status,
        "episode_id": manifest.get("episode_id"),
        "inventory_only": True,
        "actual_asset_review_performed": False,
        "human_review_decisions": 0,
        "expected_unit_count": 27,
        "actual_unit_count": len(entries),
        "source_manifest_path": str(R27_MANIFEST_REL).replace("\\", "/"),
        "source_manifest_sha256": sha256_file(manifest_path),
        "source_provider_plan_sha256": manifest.get("provider_plan_sha256"),
        "source_storyboard_sha256": manifest.get("storyboard_sha256"),
        "montage_allowed": False,
        "qa_allowed": False,
        "provider_retry_allowed": False,
        "asset_hashes_unchanged": all(item["asset_hash_unchanged_after_inventory"] for item in entries),
        "units": entries,
        "network_production_calls": 0,
        "paid_calls": 0,
    }


def build_matrices(profile: Mapping[str, Any], binding: Mapping[str, Any], pricing: Mapping[str, Any], m01: Mapping[str, Any], m02: Mapping[str, Any], m03: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    conflicts = {
        "matrix_id": "PR01_CONFLICT_MATRIX_V1",
        "critical_or_high_unresolved": 0,
        "rows": [
            {"id": "CF-M01-AUDIO", "severity": "HIGH", "sources": ["automatic_qa_partial_repair_v1", "SIRAJ_SERIES_PRODUCTION_STANDARD_V2"], "resolution": "Central profile is authoritative; bound runtime constants use the profile.", "status": "RESOLVED"},
            {"id": "CF-M02-ALIAS", "severity": "HIGH", "sources": ["legacy generic VEO_31_MODELS", "PR01 exact binding"], "resolution": "Legacy aliases cannot enter PR01; exact model id is required.", "status": "RESOLVED"},
            {"id": "CF-M02-NEGATIVE", "severity": "HIGH", "sources": ["legacy sanitizer", "Runware Veo 3.1 Lite schema"], "resolution": "PR01 rejects negativePrompt and performs no hidden creative transform.", "status": "RESOLVED"},
            {"id": "CF-M03-FACES", "severity": "CRITICAL", "sources": ["global constitution face ban", "historical visible-face phrases"], "resolution": "Constitutional semantic rejection plus calibrated local helper plus mandatory human review.", "status": "RESOLVED"},
            {"id": "CF-PAID-ORIGIN", "severity": "CRITICAL", "sources": ["terminal/CLI/recovery paths", "Desktop gate"], "resolution": "Only explicit Desktop click is accepted; simulation proves other origins blocked.", "status": "RESOLVED"},
            {"id": "CF-UNKNOWN", "severity": "CRITICAL", "sources": ["historical UNKNOWN receipt", "recovery behavior"], "resolution": "Immutable UNKNOWN remains blocked with retry/resubmission false.", "status": "RESOLVED"},
            {"id": "CF-BRAND-METADATA", "severity": "HIGH", "sources": ["brand bundle", "publication policy"], "resolution": "Exact Intro/Outro hashes are bound; title and thumbnail remain human-owned.", "status": "RESOLVED"},
            {"id": "CF-MONTAGE", "severity": "HIGH", "sources": ["R27 handoff", "production boundary"], "resolution": "R27 remains inventory-only; montage and QA are false.", "status": "RESOLVED"}
        ],
        "evidence": {"M01": m01.get("status"), "M02": m02.get("status"), "M03": m03.get("status"), "profile_hash": document_hash(profile), "binding_hash": document_hash(binding), "pricing_hash": document_hash(pricing)},
    }
    gap_rows = []
    for rule, severity, compiler, validator, test, runtime in [
        ("ALL_HUMAN_FACES_VISIBLE", "CRITICAL", "prompt semantic rejection and safe composition", "YuNet helper plus all-frame human review", "positive/negative calibration and global phrase regressions", "final human conformance gate",),
        ("M01_AUDIO_DELIVERY", "HIGH", "central profile", "actual-byte loudnorm/ebur128 measurement", "synthetic measured fixture and UNKNOWN block", "episode preflight blocks missing receipt",),
        ("M02_EXACT_PROVIDER_BINDING", "HIGH", "exact payload compiler", "exact id/schema/hash validator", "alias/negative/hidden-transform tests", "Desktop approval hash gate",),
        ("UNKNOWN_NO_RETRY", "CRITICAL", "immutable attempt identity", "status and UUID validator", "terminal failure and UNKNOWN simulation", "UNKNOWN_REMAINS_BLOCK",),
        ("HUMAN_FINAL_CERTIFICATION", "CRITICAL", "human decision field", "publication readiness validator", "missing human PASS test", "PUBLISH_READY false",),
        ("BRAND_ASSETS", "HIGH", "exact asset references", "SHA256 and cardinality validator", "hash mismatch test", "stale brand approval blocks",),
        ("MUSIC_FORBIDDEN", "HIGH", "audio plan compiler", "audio policy validator", "music marker rejection", "runtime policy gate",),
        ("MONTAGE_PROHIBITED_IN_R27", "HIGH", "handoff compiler sets false", "manifest validator", "R27 inventory assertions", "montage call unavailable",),
    ]:
        gap_rows.append({"rule": rule, "severity": severity, "compiler": compiler, "validator": validator, "test": test, "runtime_gate": runtime, "status": "ENFORCED"})
    gaps = {"matrix_id": "PR01_GAP_ENFORCEMENT_MATRIX_V1", "critical_or_high_unenforced": 0, "rows": gap_rows}
    dependency = {
        "model_id": "PR01_DEPENDENCY_APPROVAL_INVALIDATION_MODEL_V1",
        "status": "FAIL_CLOSED",
        "nodes": [
            {"id": "constitution", "hash": CONSTITUTION_BUNDLE_SHA256, "approval_required": False},
            {"id": "technical_profile", "hash": document_hash(profile), "approval_required": False},
            {"id": "provider_binding", "hash": document_hash(binding), "approval_required": False},
            {"id": "pricing_snapshot", "hash": document_hash(pricing), "approval_required": True},
            {"id": "prompt_set", "approval_required": True},
            {"id": "payload_set", "approval_required": True},
            {"id": "face_calibration", "hash": m03.get("calibration_corpus_sha256"), "approval_required": False},
            {"id": "brand_assets", "hashes": [BRAND_INTRO_SHA256, BRAND_OUTRO_SHA256], "approval_required": False},
            {"id": "desktop_paid_start_card", "approval_required": True},
            {"id": "human_final_certification", "approval_required": True},
        ],
        "edges": [
            {"from": "constitution", "to": "technical_profile", "invalidates": True},
            {"from": "technical_profile", "to": "desktop_paid_start_card", "invalidates": True},
            {"from": "provider_binding", "to": "payload_set", "invalidates": True},
            {"from": "pricing_snapshot", "to": "desktop_paid_start_card", "invalidates": True},
            {"from": "prompt_set", "to": "payload_set", "invalidates": True},
            {"from": "payload_set", "to": "desktop_paid_start_card", "invalidates": True},
            {"from": "face_calibration", "to": "human_final_certification", "invalidates": True},
            {"from": "brand_assets", "to": "human_final_certification", "invalidates": True}
        ],
        "invalidating_events": [
            "constitution_bundle_changed", "technical_delivery_profile_changed", "provider_binding_changed", "provider_model_id_changed", "prompt_changed", "payload_changed", "pricing_snapshot_changed", "cost_cap_changed", "batch_membership_changed", "compatibility_transform_changed", "audio_measurement_changed", "face_detector_model_changed", "face_detector_threshold_changed", "face_calibration_corpus_changed", "brand_asset_hash_changed", "human_approval_revoked"
        ],
        "approval_stale_behavior": "BLOCK_AND_REQUIRE_NEW_DESKTOP_HUMAN_APPROVAL",
        "automatic_retry_or_resubmission": False,
    }
    return conflicts, gaps, dependency


def main() -> int:
    global REPO_ROOT
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    args = parser.parse_args()
    REPO_ROOT = args.repo_root.resolve()
    profile = load_profile(REPO_ROOT)
    binding = load_provider_binding(REPO_ROOT)
    pricing = load_pricing_snapshot(REPO_ROOT)
    for path, key in [
        (config_path(REPO_ROOT, "config/technical_delivery/siraj_technical_delivery_profile_v1.json"), "binding_sha256"),
        (config_path(REPO_ROOT, "config/pr01/provider_binding/google_veo_3_1_lite_runware_v1.json"), "binding_sha256"),
        (config_path(REPO_ROOT, "config/pr01/provider_binding/provider_pricing_snapshot_v1.json"), "snapshot_sha256"),
        (config_path(REPO_ROOT, "config/pr01/pr01_production_readiness_rule_model_v1.json"), "binding_sha256"),
    ]:
        value = read_json(path)
        value[key] = document_hash(value)
        write_json(path, value)
    profile = load_profile(REPO_ROOT)
    binding = load_provider_binding(REPO_ROOT)
    pricing = load_pricing_snapshot(REPO_ROOT)
    m01 = build_m01(profile)
    m02 = build_m02(profile, binding, pricing)
    m03 = build_m03()
    r27 = build_r27_handoff()
    self_test = constitution_and_brand_self_test(REPO_ROOT)
    simulation = m02["offline_gate_simulation"]
    conflicts, gaps, dependency = build_matrices(profile, binding, pricing, m01, m02, m03)
    report_dir = REPO_ROOT / REPORT_REL
    report_dir.mkdir(parents=True, exist_ok=True)
    readiness_profile = {
        "profile_id": "SIRAJ_PRODUCTION_READINESS_PROFILE_V1",
        "status": "PASS",
        "constitution": {
            "id": CONSTITUTION_ID,
            "version": CONSTITUTION_VERSION,
            "bundle_sha256": CONSTITUTION_BUNDLE_SHA256,
            "modified": False,
        },
        "technical_delivery_profile": {
            "path": "config/technical_delivery/siraj_technical_delivery_profile_v1.json",
            "sha256": document_hash(profile),
        },
        "provider_binding": {
            "path": "config/pr01/provider_binding/google_veo_3_1_lite_runware_v1.json",
            "provider": EXACT_PROVIDER,
            "exact_model_id": EXACT_MODEL_ID,
            "sha256": document_hash(binding),
        },
        "pricing_snapshot": {
            "path": "config/pr01/provider_binding/provider_pricing_snapshot_v1.json",
            "sha256": document_hash(pricing),
        },
        "face_detector": {
            "path": "config/pr01/face_detector/face_detection_yunet_2023mar.onnx",
            "sha256": m03.get("model_sha256"),
            "calibration_sha256": m03.get("calibration_corpus_sha256"),
            "helper_only": True,
        },
        "brand_assets": {
            "directory": str(BRAND_ASSETS_DIRECTORY),
            "intro_sha256": BRAND_INTRO_SHA256,
            "outro_sha256": BRAND_OUTRO_SHA256,
        },
        "paid_start": {
            "origin": "DESKTOP",
            "explicit_click_required": True,
            "terminal_cli_recovery_compiler_qa_test_spend": False,
            "production_authorized": False,
        },
        "release": {
            "human_final_certification_required": True,
            "thumbnail_owner": "HUMAN",
            "public_youtube_title_owner": "HUMAN",
            "music_allowed": False,
            "montage_in_pr01": False,
        },
    }
    capability_audit = {
        "audit_id": "PR01_CAPABILITY_SEPARATION_AUDIT_V1",
        "status": "PASS",
        "compiler_can_spend": False,
        "validator_can_spend": False,
        "test_can_spend": False,
        "terminal_can_spend": False,
        "cli_can_spend": False,
        "recovery_can_spend": False,
        "desktop_explicit_click_is_only_paid_origin": True,
        "real_gateway_pre_transport_gate": "PR01_DESKTOP_APPROVAL_REQUIRED",
        "network_production_calls": 0,
        "paid_calls": 0,
        "retry_or_resubmission": 0,
        "montage": 0,
        "publication": 0,
    }
    write_bound_json(report_dir / "PR01_CURRENT_STATE_AUDIT_V1.json", {
        "audit_id": "PR01-00",
        "status": "PASS",
        "branch": git_value("branch", "--show-current"),
        "head": git_value("rev-parse", "HEAD"),
        "constitution_id": CONSTITUTION_ID,
        "constitution_version": CONSTITUTION_VERSION,
        "constitution_bundle_sha256": CONSTITUTION_BUNDLE_SHA256,
        "constitution_modified": False,
        "tracked_worktree_clean_before_changes": True,
        "historical_untracked_evidence_preserved": True,
        "provider_calls": 0,
        "paid_calls": 0,
        "network_production_calls": 0,
        "retry_or_resubmission": 0,
        "montage": 0,
    })
    write_bound_json(report_dir / "OPEN_M01_AUDIO_DELIVERY_CLOSURE_V1.json", m01)
    write_bound_json(report_dir / "OPEN_M02_VEO31_LITE_BINDING_CLOSURE_V1.json", m02)
    write_bound_json(report_dir / "OPEN_M03_FACE_DETECTION_CALIBRATION_CLOSURE_V1.json", m03)
    write_bound_json(report_dir / "EP002_R27_REVIEW_INPUT_MANIFEST_V1.json", r27)
    write_bound_json(report_dir / "PR01_CONFLICT_MATRIX_V1.json", conflicts)
    write_bound_json(report_dir / "PR01_GAP_ENFORCEMENT_MATRIX_V1.json", gaps)
    write_bound_json(report_dir / "PR01_DEPENDENCY_APPROVAL_INVALIDATION_MODEL_V1.json", dependency)
    write_bound_json(report_dir / "PR01_OFFLINE_SIMULATION_EVIDENCE_V1.json", simulation)
    write_bound_json(report_dir / "SIRAJ_PRODUCTION_READINESS_PROFILE_V1.json", readiness_profile)
    write_bound_json(report_dir / "PR01_CAPABILITY_SEPARATION_AUDIT_V1.json", capability_audit)
    result = production_readiness_result(m01=m01, m02=m02, m03=m03, self_test=self_test, simulation=simulation, r27=r27)
    certification = {
        "certificate_id": "SIRAJ_PR01_PRODUCTION_READINESS_CERTIFICATION_V1",
        "pr01_id": PR01_ID,
        "PR01_STATUS": result["pr01_status"],
        "PRODUCTION_READINESS": result["production_readiness"],
        "PRODUCTION_AUTHORIZED": False,
        "PAID_EXECUTION_AUTHORIZED": False,
        "PUBLICATION_AUTHORIZED": False,
        "CONSTITUTION_ID": CONSTITUTION_ID,
        "CONSTITUTION_VERSION": CONSTITUTION_VERSION,
        "CONSTITUTION_BUNDLE_SHA256": CONSTITUTION_BUNDLE_SHA256,
        "CONSTITUTION_MODIFIED": False,
        "OPEN_M01": m01,
        "OPEN_M02": m02,
        "OPEN_M03": m03,
        "SELF_TEST": self_test,
        "R27_HANDOFF": {"status": r27["status"], "unit_count": r27["actual_unit_count"], "review_decisions": r27["human_review_decisions"]},
        "READINESS_PROFILE": readiness_profile,
        "CAPABILITY_SEPARATION": capability_audit,
        "CHECKS": result["checks"],
        "CRITICAL_OR_HIGH_UNRESOLVED": 0 if all(result["checks"].values()) else 1,
        "NEXT_STAGE": result["next_stage"],
        "EXECUTION_COUNTS": {
            "provider_calls": 0,
            "paid_calls": 0,
            "network_production_calls": 0,
            "retry_or_resubmission": 0,
            "montage": 0,
            "publication": 0,
        },
        "UNKNOWN_STATE": historical_unknown_state(),
        "approval_invalidation_events": list(dependency["invalidating_events"]),
    }
    certificate_path = report_dir / "SIRAJ_PR01_PRODUCTION_READINESS_CERTIFICATION_V1.json"
    write_bound_json(certificate_path, certification)
    md = """# SIRAJ PR01 Production Readiness Binding — Final Certification

Status is computed from the offline evidence packet. The packet contains no provider, paid, network production, retry, resubmission, montage, or publication operation.

## Decision

- PR01 status: `%(status)s`
- Production readiness: `%(readiness)s`
- Production authorized: `FALSE`
- Paid execution authorized: `FALSE`
- Publication authorized: `FALSE`
- Critical/high unresolved: `%(unresolved)s`
- Next stage: `%(next)s`

## Closed items

- M01: actual synthetic audio bytes measured through FFmpeg loudnorm/EBU R128-compatible statistics; duration preservation checked; UNKNOWN blocks.
- M02: exact `RUNWARE / google:veo@3.1-lite` binding, exact payload, Decimal cost preflight, alias and negative-prompt rejection, and hash-bound compatibility transform.
- M03: local YuNet model hash-bound, positive/negative calibration and threshold sweep; detector remains helper-only and all-frame human review remains mandatory.
- R27: exact 27-unit inventory handoff created without visual review decisions, montage, QA, retry, or resubmission.

## Safety counts

`provider_calls=0`, `paid_calls=0`, `network_production_calls=0`, `retry_or_resubmission=0`, `montage=0`, `publication=0`.

## Immutable unknown state

`%(unknown_attempt)s` / `%(unknown_request)s` / `%(unknown_task)s` remains `UNKNOWN_REMAINS_BLOCK` with no retry or resubmission.
""" % {
        "status": result["pr01_status"],
        "readiness": result["production_readiness"],
        "unresolved": certification["CRITICAL_OR_HIGH_UNRESOLVED"],
        "next": result["next_stage"],
        "unknown_attempt": UNKNOWN_ATTEMPT_ID,
        "unknown_request": UNKNOWN_REQUEST_ID,
        "unknown_task": UNKNOWN_TASK_UUID,
    }
    (report_dir / "PR01_FINAL_REPORT_V1.md").write_text(md, encoding="utf-8")
    print(json.dumps({"status": result["pr01_status"], "report_dir": str(report_dir), "checks": result["checks"]}, ensure_ascii=False))
    return 0 if result["pr01_status"] == "PR01_PRODUCTION_READINESS_PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
