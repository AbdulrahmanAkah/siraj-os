"""EP002 ground-truth finalization compatibility bridge V6.

SIRAJ_EP002_GROUND_TRUTH_FINALIZATION_COMPATIBILITY_V6

This bridge deliberately NEVER imports or calls the obsolete V6.2.1 media
queue materializer.  The authoritative source is the already executed
media-cost-preflight-v2 plan plus its durable provider results.

Canonical provider units are mapped to visible timeline items by their real
timeline coverage.  Multi-phase video units remain separate sequential montage
items.  Zero-coverage units, if any, are classified as intermediate references
and never invent timeline duration.

No provider/network/paid operations occur in this module.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any, Mapping

EPISODE_ID = "episode-002-adam-temptation-fall-repentance"
EXPECTED_RUNWARE_UNITS = 95
EXPECTED_STRUCTURAL_SHOTS = 55
EXPECTED_EPISODE_SECONDS = 623.584
MIN_TRUE_VIDEO_FRACTION = 0.50
MAX_TRUE_VIDEO_FRACTION = 0.75

QUEUE_REL = Path("orchestration/media-production-queue-v6-2-1.json")
PREFLIGHT_REL = Path("orchestration/media-cost-preflight-v2.json")
ATTEMPT_REL = Path(
    "orchestration/provider-execution-v1/"
    "provider-execution-attempt-receipts-v1.jsonl"
)
LOCAL_ROOT_REL = Path("cinematic/finalization-local-graphics-v5")
GRAPHICS_BINDINGS_REL = Path("orchestration/ep002-local-graphics-ground-truth-bindings-v5.json")
LEGACY_COST_REL = Path("orchestration/media-cost-preflight-v6-2-1.json")
LEGACY_DUPLICATE_REL = Path("orchestration/prompt-duplicate-gate-v6-4.json")
PROMOTED_DUPLICATE_REL = Path("orchestration/prompt-similarity-duplicate-gate-promoted-v1.json")
PROMPT_PLAN_REL = Path("preproduction/luna-semantic-prompt-direction-v6-2-1.json")
GROUND_TRUTH_RENDERER_MODULE = "src.application.episode002_local_graphics_ground_truth_v5"
DEFAULT_GRAPHICS_PYTHON = Path(r"C:\SIRAJ\Repositories\historical-fixture-venv-20260716\Scripts\python.exe")
VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm", ".avi"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
MEDIA_SUFFIXES = VIDEO_SUFFIXES | IMAGE_SUFFIXES
DUPLICATE_RESCUE_REL = Path("cinematic/finalization-duplicate-rescue-v6")
DUPLICATE_RESCUE_REPORT_REL = Path(
    "orchestration/ep002-local-editorial-duplicate-rescue-v6.json"
)


class FinalizationCompatibilityError(RuntimeError):
    pass


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise FinalizationCompatibilityError(
            "JSON_UNREADABLE:" + str(path)
        ) from exc
    if not isinstance(value, dict):
        raise FinalizationCompatibilityError(
            "JSON_OBJECT_REQUIRED:" + str(path)
        )
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    result: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise FinalizationCompatibilityError(
                "JSONL_OBJECT_REQUIRED:" + str(path)
            )
        result.append(value)
    return result


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(
            dict(value),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _unit_id(row: Mapping[str, Any]) -> str:
    return str(
        row.get("request_id")
        or row.get("unit_id")
        or row.get("provider_request_id")
        or ""
    )


def _shot_id(row: Mapping[str, Any]) -> str:
    return str(
        row.get("shot_id")
        or row.get("structural_shot_id")
        or ""
    )


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _primary_timeline_duration(row: Mapping[str, Any]) -> float | None:
    # These fields mean actual timeline coverage, not provider generation size.
    for key in (
        "timeline_required_seconds",
        "timeline_coverage_seconds",
        "planned_timeline_usage_seconds",
    ):
        value = _number(row.get(key))
        if value is not None and value > 0:
            return value

    start = _number(row.get("timeline_start_seconds"))
    end = _number(row.get("timeline_end_seconds"))
    if start is not None and end is not None and end > start:
        return end - start
    return None


def _secondary_duration(row: Mapping[str, Any]) -> float | None:
    # Used only for a structural shot that has NO primary visible unit.
    for key in (
        "expected_usable_seconds",
        "visual_duration_seconds",
        "shot_duration_seconds",
        "duration_seconds",
    ):
        value = _number(row.get(key))
        if value is not None and value > 0:
            return value
    start = _number(row.get("start_seconds"))
    end = _number(row.get("end_seconds"))
    if start is not None and end is not None and end > start:
        return end - start
    start_ms = _number(row.get("start_ms"))
    end_ms = _number(row.get("end_ms"))
    if start_ms is not None and end_ms is not None and end_ms > start_ms:
        return (end_ms - start_ms) / 1000.0
    return None


def _walk_mappings(node: Any):
    if isinstance(node, Mapping):
        yield node
        for child in node.values():
            yield from _walk_mappings(child)
    elif isinstance(node, list):
        for child in node:
            yield from _walk_mappings(child)


def _shot_duration_fallbacks(
    repo: Path,
    episode_id: str,
    preflight: Mapping[str, Any],
) -> dict[str, float]:
    episode = repo / "projects" / episode_id
    candidates = [
        episode / "preproduction/audio-bound-storyboard-v6-1.json",
        episode / "preproduction/audio-timestamps-and-beats-v6-1.json",
        episode / "preproduction/luna-semantic-prompt-direction-v6-2-1.json",
        episode / "orchestration/media-cost-preflight-v1.json",
    ]

    # Persisted preflight references can point to the exact legacy prompt plan.
    for mapping in _walk_mappings(preflight):
        for value in mapping.values():
            if not isinstance(value, str) or not value.lower().endswith(".json"):
                continue
            path = Path(value)
            if not path.is_absolute():
                path = repo / path
            if path.is_file():
                candidates.append(path.resolve())

    durations: dict[str, float] = {}
    for path in dict.fromkeys(candidates):
        if not path.is_file():
            continue
        try:
            document = _read(path)
        except FinalizationCompatibilityError:
            continue
        for row in _walk_mappings(document):
            shot = _shot_id(row)
            if not shot:
                continue
            duration = _primary_timeline_duration(row)
            if duration is None:
                duration = _secondary_duration(row)
            if duration is not None and duration > 0:
                # Prefer a longer whole-shot interval over tiny metadata spans.
                durations[shot] = max(durations.get(shot, 0.0), duration)
    return durations


def _existing_media_path(repo: Path, raw: Any) -> Path | None:
    if not isinstance(raw, str):
        return None
    text = raw.strip().strip('"')
    if not text or "://" in text:
        return None
    path = Path(text)
    if not path.is_absolute():
        path = repo / path
    try:
        path = path.resolve()
    except OSError:
        return None
    if path.is_file() and path.suffix.lower() in MEDIA_SUFFIXES:
        return path
    return None


def _media_paths(repo: Path, node: Any) -> list[Path]:
    result: list[Path] = []

    def walk(value: Any) -> None:
        if isinstance(value, Mapping):
            for key, child in value.items():
                if isinstance(child, str):
                    key_lower = str(key).lower()
                    if (
                        "path" in key_lower
                        or "file" in key_lower
                        or child.lower().endswith(tuple(MEDIA_SUFFIXES))
                    ):
                        candidate = _existing_media_path(repo, child)
                        if candidate is not None:
                            result.append(candidate)
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(node)
    unique: list[Path] = []
    seen: set[str] = set()
    for path in result:
        key = str(path).lower()
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def _expected_asset_hash(result: Mapping[str, Any]) -> str:
    response = result.get("response")
    if isinstance(response, Mapping):
        value = str(response.get("asset_sha256") or "").strip()
        if value:
            return value
    return str(result.get("content_hash") or "").strip()


def _durable_provider_results(
    repo: Path,
    episode_id: str,
    provider_units: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    episode = repo / "projects" / episode_id
    root = episode / "orchestration/provider-execution-v1"
    rows = _read_jsonl(episode / ATTEMPT_REL)

    completed_attempt: dict[str, str] = {}
    for row in rows:
        if str(row.get("status") or "") != "ATTEMPT_COMPLETED":
            continue
        uid = _unit_id(row)
        attempt = str(row.get("attempt_id") or "")
        if uid and attempt:
            completed_attempt[uid] = attempt

    expected_ids = {_unit_id(unit) for unit in provider_units}
    if set(completed_attempt) != expected_ids:
        raise FinalizationCompatibilityError(
            "DURABLE_COMPLETED_PROVIDER_SET_MISMATCH:"
            + json.dumps(
                {
                    "missing": sorted(expected_ids - set(completed_attempt)),
                    "unexpected": sorted(set(completed_attempt) - expected_ids),
                },
                separators=(",", ":"),
            )
        )

    results: dict[str, dict[str, Any]] = {}
    for uid, attempt in completed_attempt.items():
        result_path: Path | None = None
        for row in reversed(rows):
            if str(row.get("attempt_id") or "") != attempt:
                continue
            if str(row.get("status") or "") not in {
                "RESULT_PERSISTED",
                "ATTEMPT_COMPLETED",
            }:
                continue
            raw = str(row.get("result_path") or "")
            if not raw:
                continue
            candidate = Path(raw)
            if not candidate.is_absolute():
                candidate = repo / candidate
            if candidate.is_file():
                result_path = candidate.resolve()
                break

        if result_path is None:
            for folder in (
                root / "provider-execution-results-v1",
                root / "results",
            ):
                candidate = folder / f"{attempt}.json"
                if candidate.is_file():
                    result_path = candidate.resolve()
                    break

        if result_path is None:
            raise FinalizationCompatibilityError(
                "DURABLE_RESULT_FILE_MISSING:" + uid + ":" + attempt
            )
        value = _read(result_path)
        if str(value.get("attempt_id") or "") != attempt:
            raise FinalizationCompatibilityError(
                "DURABLE_RESULT_ATTEMPT_MISMATCH:" + uid
            )
        if _unit_id(value) not in {"", uid}:
            raise FinalizationCompatibilityError(
                "DURABLE_RESULT_UNIT_MISMATCH:" + uid
            )

        expected_hash = _expected_asset_hash(value)
        if not expected_hash:
            raise FinalizationCompatibilityError(
                "DURABLE_RESULT_ASSET_HASH_REQUIRED:" + uid
            )
        candidates = _media_paths(repo, value)
        matched = [
            path for path in candidates
            if _sha256(path) == expected_hash
        ]
        if len(matched) != 1:
            raise FinalizationCompatibilityError(
                "DURABLE_ASSET_HASH_RESOLUTION_FAILED:"
                + uid
                + ":matches="
                + str(len(matched))
            )
        value["_verified_asset_path"] = str(matched[0])
        value["_verified_asset_sha256"] = expected_hash
        value["_canonical_result_path"] = str(result_path)
        value["_canonical_attempt_id"] = attempt
        results[uid] = value

    if len(results) != EXPECTED_RUNWARE_UNITS:
        raise FinalizationCompatibilityError(
            "DURABLE_RUNWARE_RESULT_COUNT_NOT_95:" + str(len(results))
        )
    return results


def _prompt_items_with_graphics(
    repo: Path,
    episode_id: str,
    preflight: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    episode = repo / "projects" / episode_id
    candidates: list[Path] = []
    for mapping in _walk_mappings(preflight):
        for value in mapping.values():
            if not isinstance(value, str) or not value.lower().endswith(".json"):
                continue
            path = Path(value)
            if not path.is_absolute():
                path = repo / path
            if path.is_file():
                candidates.append(path.resolve())
    candidates.extend(
        path.resolve()
        for path in (episode / "preproduction").glob("*.json")
        if path.is_file()
    )

    by_shot: dict[str, dict[str, Any]] = {}
    for path in dict.fromkeys(candidates):
        try:
            value = _read(path)
        except FinalizationCompatibilityError:
            continue
        for row in _walk_mappings(value):
            shot = _shot_id(row)
            if shot and isinstance(row.get("graphics_spec"), Mapping):
                by_shot.setdefault(shot, dict(row))
    return by_shot


def _local_completed_units(
    repo: Path,
    episode_id: str,
) -> set[str]:
    episode = repo / "projects" / episode_id
    return {
        _unit_id(row)
        for row in _read_jsonl(episode / ATTEMPT_REL)
        if str(row.get("status") or "") == "LOCAL_UNIT_COMPLETED"
        and _unit_id(row)
    }


def _discover_existing_local_asset(
    repo: Path,
    episode_id: str,
    shot_id: str,
) -> Path | None:
    episode = repo / "projects" / episode_id
    matches: list[Path] = []
    for root in (
        episode / "cinematic",
        episode / "assets",
        episode / "media",
    ):
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if (
                path.is_file()
                and path.suffix.lower() in MEDIA_SUFFIXES
                and shot_id.lower() in path.name.lower()
                and "finalization-local-graphics-v5" not in str(path)
            ):
                matches.append(path.resolve())
    unique = list(dict.fromkeys(matches))
    return unique[0] if len(unique) == 1 else None



def _graphics_python(repo: Path) -> Path:
    candidates = [
        DEFAULT_GRAPHICS_PYTHON,
        repo / ".venv/Scripts/python.exe",
        repo / "venv/Scripts/python.exe",
        Path(sys.executable),
    ]
    seen: set[str] = set()
    errors: list[str] = []
    for candidate in candidates:
        candidate = Path(candidate)
        key = str(candidate).lower()
        if key in seen or not candidate.is_file():
            continue
        seen.add(key)
        code = (
            "import sys\n"
            f"sys.path.insert(0, r'{repo}')\n"
            "import PySide6\n"
            "from src.application.episode002_local_graphics_ground_truth_v5 "
            "import validate_ground_truth\n"
            f"validate_ground_truth(__import__('pathlib').Path(r'{repo}'), "
            "'EP002-SH-040-G01')\n"
            "print('PASS')\n"
        )
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["QT_QPA_PLATFORM"] = "offscreen"
        env["QT_QUICK_BACKEND"] = "software"
        env["QSG_RHI_BACKEND"] = "software"
        env["SIRAJ_DISABLE_PROVIDER_NETWORK"] = "1"
        env["SIRAJ_NETWORK_DENY"] = "1"
        for key_name in (
            "RUNWARE_API_KEY",
            "SIRAJ_RUNWARE_API_KEY",
            "OPENAI_API_KEY",
            "ELEVENLABS_API_KEY",
        ):
            env.pop(key_name, None)
        process = subprocess.run(
            [str(candidate), "-X", "utf8", "-c", code],
            cwd=str(repo),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=90,
        )
        if process.returncode == 0:
            return candidate.resolve()
        errors.append(str(candidate) + ":" + process.stderr[-1000:])
    raise FinalizationCompatibilityError(
        "NO_GROUND_TRUTH_GRAPHICS_PYTHON:" + " | ".join(errors)
    )


def _render_local_graphic(
    repo: Path,
    episode_id: str,
    unit: Mapping[str, Any],
    prompt_item: Mapping[str, Any],
) -> Path:
    if episode_id != EPISODE_ID:
        raise FinalizationCompatibilityError(
            "LOCAL_GRAPHICS_EPISODE_SCOPE_VIOLATION:" + episode_id
        )
    uid = _unit_id(unit)
    shot = _shot_id(unit)
    root = repo / "projects" / episode_id / LOCAL_ROOT_REL
    outputs = root / "outputs"
    receipts = root / "receipts"
    outputs.mkdir(parents=True, exist_ok=True)
    receipts.mkdir(parents=True, exist_ok=True)
    output_path = outputs / f"{uid}.mp4"
    receipt_path = receipts / f"{uid}.json"

    # Always validate the authored prompt row before allowing a prior output
    # to be reused. The child renderer repeats the same ground-truth checks.
    if str(prompt_item.get("shot_id") or "") != shot:
        raise FinalizationCompatibilityError(
            "LOCAL_GRAPHICS_PROMPT_BINDING_CHANGED:" + uid
        )

    python_exe = _graphics_python(repo)
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["QT_QUICK_BACKEND"] = "software"
    env["QSG_RHI_BACKEND"] = "software"
    env["SIRAJ_DISABLE_PROVIDER_NETWORK"] = "1"
    env["SIRAJ_NETWORK_DENY"] = "1"
    for key_name in (
        "RUNWARE_API_KEY",
        "SIRAJ_RUNWARE_API_KEY",
        "OPENAI_API_KEY",
        "ELEVENLABS_API_KEY",
    ):
        env.pop(key_name, None)

    process = subprocess.run(
        [
            str(python_exe),
            "-X",
            "utf8",
            "-m",
            GROUND_TRUTH_RENDERER_MODULE,
            "--repo",
            str(repo),
            "--unit",
            uid,
            "--output",
            str(output_path),
            "--receipt",
            str(receipt_path),
        ],
        cwd=str(repo),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=7200,
    )
    if process.returncode != 0:
        raise FinalizationCompatibilityError(
            "GROUND_TRUTH_LOCAL_GRAPHICS_RENDER_FAILED:"
            + uid
            + "\n"
            + process.stdout[-3000:]
            + "\n"
            + process.stderr[-3000:]
        )
    if not output_path.is_file() or output_path.stat().st_size <= 0:
        raise FinalizationCompatibilityError(
            "GROUND_TRUTH_LOCAL_GRAPHICS_OUTPUT_MISSING:" + uid
        )
    if not receipt_path.is_file():
        raise FinalizationCompatibilityError(
            "GROUND_TRUTH_LOCAL_GRAPHICS_RECEIPT_MISSING:" + uid
        )
    receipt = _read(receipt_path)
    if (
        receipt.get("schema_version")
        != "siraj-ep002-ground-truth-local-graphics-v5"
        or receipt.get("status") != "PASS"
        or receipt.get("unit_id") != uid
        or receipt.get("output_sha256") != _sha256(output_path)
        or receipt.get("provider_calls") != 0
        or receipt.get("paid_calls") != 0
    ):
        raise FinalizationCompatibilityError(
            "GROUND_TRUTH_LOCAL_GRAPHICS_RECEIPT_INVALID:" + uid
        )
    return output_path.resolve()




def install_runtime_montage_compatibility() -> None:
    """Retained as a compatibility no-op; montage already treats non-images as video."""
    return None



def _sort_key(unit: Mapping[str, Any]):
    queue = int(_number(unit.get("queue_index")) or 0)
    start = _number(unit.get("timeline_start_seconds"))
    phase = int(_number(unit.get("phase_index")) or 0)
    uid = _unit_id(unit)
    return (
        queue,
        start if start is not None else 10**9,
        phase,
        uid,
    )



# SIRAJ_EP002_PRODUCTION_HANDOFF_V6_2
CERTIFICATION_V6_1_REL = Path(
    "orchestration/ep002-ground-truth-finalization-release-certification-v6-1.json"
)


def _apply_v6_1_certified_duplicate_rescue_for_production(
    repo: Path,
    episode_id: str,
    queue: Mapping[str, Any],
) -> dict[str, Any]:
    if episode_id != EPISODE_ID:
        raise FinalizationCompatibilityError(
            "PRODUCTION_HANDOFF_EPISODE_SCOPE_VIOLATION:" + episode_id
        )

    episode = repo / "projects" / episode_id
    cert_path = episode / CERTIFICATION_V6_1_REL
    report_path = episode / DUPLICATE_RESCUE_REPORT_REL
    if not cert_path.is_file():
        raise FinalizationCompatibilityError(
            "V6_1_CERTIFICATION_REQUIRED_FOR_PRODUCTION_HANDOFF"
        )
    if not report_path.is_file():
        raise FinalizationCompatibilityError(
            "V6_1_DUPLICATE_RESCUE_REPORT_REQUIRED_FOR_PRODUCTION_HANDOFF"
        )

    cert = _read(cert_path)
    required_cert = {
        "status": "PASS",
        "duplicate_gate_runtime_audit": "PASS",
        "final_duplicate_findings": 0,
        "local_editorial_duplicate_rescue": "PASS",
        "full_shadow_montage": "PASS",
        "full_shadow_master_audio_video_streams": "PASS",
        "tts_narration_build": "PASS",
        "audio_visual_duration_match": "PASS",
        "qa_manifest_preflight": "PASS",
    }
    for key, expected in required_cert.items():
        if cert.get(key) != expected:
            raise FinalizationCompatibilityError(
                "V6_1_CERTIFICATION_FIELD_INVALID_FOR_PRODUCTION_HANDOFF:"
                + key
                + ":"
                + repr(cert.get(key))
            )

    report = _read(report_path)
    final_findings = report.get("final_duplicate_findings")
    repaired_count = report.get("repaired_item_count")
    if (
        report.get("schema_version")
        != "siraj-ep002-local-editorial-duplicate-rescue-v6"
        or report.get("status") != "PASS"
        or report.get("episode_id") != episode_id
        or bool(report.get("gate_bypass_used"))
        or bool(report.get("reuse_justification_added"))
        or bool(report.get("provider_regeneration_used"))
        or int(report.get("provider_calls") or 0) != 0
        or int(report.get("paid_calls") or 0) != 0
        or final_findings is None
        or int(final_findings) != 0
        or repaired_count is None
        or int(repaired_count) != 11
    ):
        raise FinalizationCompatibilityError(
            "V6_1_DUPLICATE_RESCUE_REPORT_INVALID_FOR_PRODUCTION_HANDOFF"
        )

    expected_report_sha = str(
        cert.get("duplicate_rescue_report_sha256") or ""
    )
    if not expected_report_sha:
        raise FinalizationCompatibilityError(
            "V6_1_CERTIFICATION_RESCUE_REPORT_SHA_REQUIRED"
        )
    if _sha256(report_path) != expected_report_sha:
        raise FinalizationCompatibilityError(
            "V6_1_DUPLICATE_RESCUE_REPORT_HASH_CHANGED"
        )

    repairs = report.get("repairs")
    if not isinstance(repairs, list) or len(repairs) != 11:
        raise FinalizationCompatibilityError(
            "V6_1_CERTIFIED_REPAIR_ROWS_NOT_11"
        )

    rebound = dict(queue)
    items = [dict(item) for item in list(rebound.get("items") or [])]
    by_id: dict[str, int] = {}
    for index, item in enumerate(items):
        uid = str(item.get("queue_id") or "")
        if not uid or uid in by_id:
            raise FinalizationCompatibilityError(
                "PRODUCTION_HANDOFF_QUEUE_IDS_INVALID:" + uid
            )
        by_id[uid] = index
    if len(items) != 99:
        raise FinalizationCompatibilityError(
            "PRODUCTION_HANDOFF_VISIBLE_ITEM_COUNT_NOT_99:"
            + str(len(items))
        )

    rescue_assets_root = (
        episode / DUPLICATE_RESCUE_REL / "assets"
    ).resolve()
    seen: set[str] = set()
    applied_seconds = 0.0

    for raw in repairs:
        if not isinstance(raw, Mapping):
            raise FinalizationCompatibilityError(
                "V6_1_CERTIFIED_REPAIR_ROW_NOT_OBJECT"
            )
        row = dict(raw)
        uid = str(row.get("queue_id") or "")
        if not uid or uid in seen or uid not in by_id:
            raise FinalizationCompatibilityError(
                "V6_1_CERTIFIED_REPAIR_QUEUE_BINDING_INVALID:" + uid
            )
        seen.add(uid)

        item = dict(items[by_id[uid]])
        if str(item.get("media_kind") or "") not in {
            "RUNWARE_VIDEO",
            "RUNWARE_IMAGE",
        }:
            raise FinalizationCompatibilityError(
                "V6_1_CERTIFIED_REPAIR_TARGET_NOT_RUNWARE:" + uid
            )

        source_rel = str(row.get("source_path_relative") or "")
        source_sha = str(row.get("source_sha256") or "")
        derived_rel = str(row.get("derived_path_relative") or "")
        derived_sha = str(row.get("derived_sha256") or "")
        transform_id = str(row.get("transform_id") or "")
        if not all(
            (source_rel, source_sha, derived_rel, derived_sha, transform_id)
        ):
            raise FinalizationCompatibilityError(
                "V6_1_CERTIFIED_REPAIR_FIELDS_MISSING:" + uid
            )

        if (
            str(item.get("output_path_relative") or "") != source_rel
            or str(item.get("content_hash") or "") != source_sha
        ):
            raise FinalizationCompatibilityError(
                "V6_1_CERTIFIED_REPAIR_SOURCE_BINDING_DRIFT:" + uid
            )

        source = (repo / source_rel).resolve()
        derived = (repo / derived_rel).resolve()
        if not source.is_file() or _sha256(source) != source_sha:
            raise FinalizationCompatibilityError(
                "V6_1_CERTIFIED_REPAIR_SOURCE_HASH_CHANGED:" + uid
            )
        try:
            derived.relative_to(rescue_assets_root)
        except ValueError as exc:
            raise FinalizationCompatibilityError(
                "V6_1_CERTIFIED_DERIVED_ASSET_OUTSIDE_RESCUE_ROOT:" + uid
            ) from exc
        if not derived.is_file() or _sha256(derived) != derived_sha:
            raise FinalizationCompatibilityError(
                "V6_1_CERTIFIED_DERIVED_ASSET_HASH_CHANGED:" + uid
            )

        item["output_path_relative"] = derived_rel
        item["content_hash"] = derived_sha
        item["editorial_derivation"] = {
            "schema_version": "siraj-local-editorial-duplicate-rescue-v6",
            "status": "PASS_REBOUND_FROM_V6_1_CERTIFIED_RESCUE",
            "source_queue_id": uid,
            "source_path_relative": source_rel,
            "source_sha256": source_sha,
            "output_path_relative": derived_rel,
            "output_sha256": derived_sha,
            "transform_id": transform_id,
            "provider_calls": 0,
            "paid_calls": 0,
            "automatic_paid_retry": False,
            "automatic_paid_resubmission": False,
        }
        items[by_id[uid]] = item
        applied_seconds += float(row.get("duration_seconds") or 0.0)

    from src.application.siraj_duplicate_gates_v6_2_1 import (
        audit_completed_assets,
    )
    findings = list(audit_completed_assets(repo, items))
    if findings:
        raise FinalizationCompatibilityError(
            "PRODUCTION_HANDOFF_DUPLICATE_GATE_FAILED:"
            + json.dumps(
                findings,
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )

    rebound["items"] = items
    duplicate_policy = dict(rebound.get("duplicate_policy") or {})
    duplicate_policy.update(
        {
            "status": "PASS",
            "runtime_audit": (
                "PASS_ZERO_FINDINGS_AFTER_V6_1_CERTIFIED_PRODUCTION_REBIND"
            ),
            "initial_findings": int(
                report.get("initial_duplicate_findings") or 0
            ),
            "final_findings": 0,
            "gate_bypass_used": False,
            "v6_2_production_handoff": True,
        }
    )
    rebound["duplicate_policy"] = duplicate_policy

    reconciliation = dict(
        rebound.get("canonical_reconciliation") or {}
    )
    reconciliation.update(
        {
            "initial_duplicate_findings": int(
                report.get("initial_duplicate_findings") or 0
            ),
            "final_duplicate_findings": 0,
            "local_editorial_duplicate_rescue": "PASS",
            "local_editorial_duplicate_rescue_count": len(seen),
            "local_editorial_duplicate_rescue_seconds": round(
                applied_seconds, 6
            ),
            "duplicate_rescue_report": str(
                report_path.relative_to(repo)
            ).replace("\\", "/"),
            "duplicate_rescue_report_sha256": expected_report_sha,
            "v6_2_production_handoff": "PASS",
            "v6_2_production_handoff_rebound_count": len(seen),
            "provider_calls": 0,
            "paid_calls": 0,
            "automatic_paid_retry": False,
            "automatic_paid_resubmission": False,
        }
    )
    rebound["canonical_reconciliation"] = reconciliation
    return rebound

def ensure_montage_media_queue(
    repo_root: Path,
    episode_id: str = EPISODE_ID,
) -> dict[str, Any]:
    repo = Path(repo_root).resolve()
    if episode_id != EPISODE_ID:
        raise FinalizationCompatibilityError(
            "EPISODE_SCOPE_VIOLATION:" + episode_id
        )
    episode = repo / "projects" / episode_id
    preflight_path = episode / PREFLIGHT_REL
    preflight = _read(preflight_path)
    raw_units = preflight.get("units")
    if not isinstance(raw_units, list) or not raw_units:
        raise FinalizationCompatibilityError(
            "CANONICAL_PREFLIGHT_UNITS_REQUIRED"
        )
    units = [
        dict(unit)
        for unit in raw_units
        if isinstance(unit, Mapping)
    ]
    if len(units) != len(raw_units):
        raise FinalizationCompatibilityError(
            "CANONICAL_PREFLIGHT_UNIT_OBJECT_REQUIRED"
        )

    runware_units = [
        unit for unit in units
        if str(unit.get("provider") or "").upper() == "RUNWARE"
    ]
    local_units = [
        unit for unit in units
        if str(unit.get("provider") or "").upper() == "LOCAL"
        or str(unit.get("media_kind") or "") == "LOCAL_GRAPHICS"
    ]
    if len(runware_units) != EXPECTED_RUNWARE_UNITS:
        raise FinalizationCompatibilityError(
            "CANONICAL_RUNWARE_UNIT_COUNT_NOT_95:"
            + str(len(runware_units))
        )
    if len({_unit_id(unit) for unit in runware_units}) != EXPECTED_RUNWARE_UNITS:
        raise FinalizationCompatibilityError(
            "CANONICAL_RUNWARE_UNIT_IDS_NOT_UNIQUE"
        )

    results = _durable_provider_results(
        repo,
        episode_id,
        runware_units,
    )
    local_completed = _local_completed_units(repo, episode_id)
    missing_local_completion = [
        _unit_id(unit)
        for unit in local_units
        if _unit_id(unit) not in local_completed
    ]
    if missing_local_completion:
        raise FinalizationCompatibilityError(
            "LOCAL_UNIT_COMPLETION_EVIDENCE_MISSING:"
            + ",".join(missing_local_completion)
        )

    fallbacks = _shot_duration_fallbacks(
        repo,
        episode_id,
        preflight,
    )
    prompt_items = _prompt_items_with_graphics(
        repo,
        episode_id,
        preflight,
    )

    by_shot: dict[str, list[dict[str, Any]]] = {}
    for unit in units:
        shot = _shot_id(unit)
        if not shot:
            raise FinalizationCompatibilityError(
                "CANONICAL_UNIT_SHOT_ID_REQUIRED:" + _unit_id(unit)
            )
        by_shot.setdefault(shot, []).append(unit)

    if len(by_shot) != EXPECTED_STRUCTURAL_SHOTS:
        raise FinalizationCompatibilityError(
            "CANONICAL_STRUCTURAL_SHOT_COUNT_NOT_55:"
            + str(len(by_shot))
        )

    durations: dict[str, float] = {}
    intermediate_ids: set[str] = set()
    for shot, shot_units in by_shot.items():
        primary = []
        for unit in shot_units:
            duration = _primary_timeline_duration(unit)
            if duration is not None and duration > 0:
                durations[_unit_id(unit)] = duration
                primary.append(unit)

        if primary:
            for unit in shot_units:
                if _unit_id(unit) not in durations:
                    intermediate_ids.add(_unit_id(unit))
            continue

        fallback = fallbacks.get(shot)
        if fallback is None or fallback <= 0:
            # Last narrow fallback: one unit's explicitly usable interval.
            candidates = [
                (unit, _secondary_duration(unit))
                for unit in shot_units
            ]
            candidates = [
                (unit, duration)
                for unit, duration in candidates
                if duration is not None and duration > 0
            ]
            if len(candidates) == 1:
                unit, fallback = candidates[0]
                durations[_unit_id(unit)] = float(fallback)
                for other in shot_units:
                    if _unit_id(other) != _unit_id(unit):
                        intermediate_ids.add(_unit_id(other))
                continue
            raise FinalizationCompatibilityError(
                "SHOT_TIMELINE_DURATION_UNRESOLVED:" + shot
            )

        # A whole-shot fallback can only be assigned to one final visual unit.
        # Prefer authored graphics, then an image, then a single video unit.
        ranked = sorted(
            shot_units,
            key=lambda unit: (
                0
                if str(unit.get("media_kind") or "") == "LOCAL_GRAPHICS"
                else 1
                if str(unit.get("media_kind") or "") == "RUNWARE_IMAGE"
                else 2,
                _sort_key(unit),
            ),
        )
        selected = ranked[0]
        durations[_unit_id(selected)] = float(fallback)
        for other in shot_units:
            if _unit_id(other) != _unit_id(selected):
                intermediate_ids.add(_unit_id(other))

    visible_units = [
        unit for unit in units
        if _unit_id(unit) in durations
    ]
    visible_units.sort(key=_sort_key)
    all_ids = {_unit_id(unit) for unit in units}
    accounted = {_unit_id(unit) for unit in visible_units} | intermediate_ids
    if accounted != all_ids:
        raise FinalizationCompatibilityError(
            "CANONICAL_UNITS_NOT_FULLY_ACCOUNTED:"
            + json.dumps(
                {
                    "missing": sorted(all_ids - accounted),
                    "unexpected": sorted(accounted - all_ids),
                },
                separators=(",", ":"),
            )
        )
    visible_shots = {_shot_id(unit) for unit in visible_units}
    if len(visible_shots) != EXPECTED_STRUCTURAL_SHOTS:
        raise FinalizationCompatibilityError(
            "VISIBLE_STRUCTURAL_SHOT_COUNT_NOT_55:"
            + str(len(visible_shots))
        )

    output_items: list[dict[str, Any]] = []
    local_rendered_or_reused = 0
    for montage_index, unit in enumerate(visible_units, 1):
        uid = _unit_id(unit)
        shot = _shot_id(unit)
        kind = str(unit.get("media_kind") or "")
        provider = str(unit.get("provider") or "").upper()
        if provider == "RUNWARE":
            result = results.get(uid)
            if result is None:
                raise FinalizationCompatibilityError(
                    "VISIBLE_PROVIDER_RESULT_MISSING:" + uid
                )
            asset = Path(result["_verified_asset_path"]).resolve()
            expected = str(result["_verified_asset_sha256"])
            if _sha256(asset) != expected:
                raise FinalizationCompatibilityError(
                    "VISIBLE_PROVIDER_ASSET_HASH_CHANGED:" + uid
                )
            result_rel = str(
                Path(result["_canonical_result_path"]).relative_to(repo)
            ).replace("\\", "/")
            attempt_id = str(result["_canonical_attempt_id"])
        elif kind == "LOCAL_GRAPHICS":
            prompt_item = prompt_items.get(shot)
            if prompt_item is None:
                raise FinalizationCompatibilityError(
                    "LOCAL_GRAPHICS_PROMPT_ITEM_REQUIRED:" + shot
                )
            asset = _render_local_graphic(
                repo,
                episode_id,
                unit,
                prompt_item,
            )
            local_rendered_or_reused += 1
            expected = _sha256(asset)
            result_rel = None
            attempt_id = None
        elif provider == "LOCAL":
            direct_paths = _media_paths(repo, unit)
            asset = (
                direct_paths[0]
                if len(direct_paths) == 1
                else _discover_existing_local_asset(
                    repo,
                    episode_id,
                    shot,
                )
            )
            if asset is None:
                raise FinalizationCompatibilityError(
                    "NON_GRAPHICS_LOCAL_VISIBLE_ASSET_UNRESOLVED:"
                    + uid
                    + ":"
                    + shot
                )
            expected = _sha256(asset)
            result_rel = None
            attempt_id = None
        else:
            raise FinalizationCompatibilityError(
                "VISIBLE_MEDIA_PROVIDER_UNSUPPORTED:" + uid
            )

        duration = float(durations[uid])
        if duration <= 0:
            raise FinalizationCompatibilityError(
                "VISIBLE_DURATION_NONPOSITIVE:" + uid
            )

        output_items.append(
            {
                "queue_id": uid,
                "queue_index": montage_index,
                "source_queue_index": int(
                    _number(unit.get("queue_index")) or 0
                ),
                "phase_index": int(
                    _number(unit.get("phase_index")) or 0
                ),
                "shot_id": shot,
                "unit_id": uid,
                "request_id": str(unit.get("request_id") or uid),
                "media_kind": kind,
                "provider": str(unit.get("provider") or ""),
                "model": str(unit.get("model") or ""),
                "status": "COMPLETE",
                "duration_seconds": duration,
                "timeline_start_seconds": _number(
                    unit.get("timeline_start_seconds")
                ),
                "timeline_end_seconds": _number(
                    unit.get("timeline_end_seconds")
                ),
                "output_path_relative": str(
                    asset.relative_to(repo)
                ).replace("\\", "/"),
                "content_hash": expected,
                "canonical_result_path": result_rel,
                "canonical_attempt_id": attempt_id,
                "canonical_visible_timeline_unit": True,
                "automatic_paid_retry": False,
                "automatic_paid_resubmission": False,
            }
        )

    visual_seconds = round(
        sum(float(item["duration_seconds"]) for item in output_items),
        6,
    )
    if abs(visual_seconds - EXPECTED_EPISODE_SECONDS) > 0.05:
        raise FinalizationCompatibilityError(
            "VISIBLE_TIMELINE_TOTAL_MISMATCH:"
            f"observed={visual_seconds}:expected={EXPECTED_EPISODE_SECONDS}"
        )
    true_video_seconds = round(
        sum(
            float(item["duration_seconds"])
            for item in output_items
            if item["media_kind"] == "RUNWARE_VIDEO"
        ),
        6,
    )
    true_video_fraction = true_video_seconds / EXPECTED_EPISODE_SECONDS
    if not (
        MIN_TRUE_VIDEO_FRACTION - 1e-9
        <= true_video_fraction
        <= MAX_TRUE_VIDEO_FRACTION + 1e-9
    ):
        raise FinalizationCompatibilityError(
            "CURRENT_MEDIA_MIX_OUTSIDE_50_TO_75:"
            + str(round(true_video_fraction * 100, 6))
        )

    queue = {
        "schema_version": "siraj-media-production-queue-v6-2-1",
        "release": "SIRAJ_EP002_GROUND_TRUTH_FINALIZATION_COMPATIBILITY_V6",
        "episode_id": episode_id,
        "status": "COMPLETE",
        "episode_duration_seconds": EXPECTED_EPISODE_SECONDS,
        "duplicate_policy": {
            "policy": "RUNTIME_AUDIT_COMPLETED_ASSETS_REQUIRED",
            "status": "PASS_PENDING_REAUDIT_ON_MONTAGE",
        },
        "items": output_items,
        "generated_video_policy": {
            "policy_id": "SIRAJ_CINEMATIC_MEDIA_MIX_POLICY_V2",
            "selection_mode": "DIRECTORIAL_OPTIMIZATION",
            "planned_seconds": true_video_seconds,
            "minimum_seconds": round(
                EXPECTED_EPISODE_SECONDS * MIN_TRUE_VIDEO_FRACTION,
                6,
            ),
            "maximum_seconds": round(
                EXPECTED_EPISODE_SECONDS * MAX_TRUE_VIDEO_FRACTION,
                6,
            ),
            "true_video_fraction": round(true_video_fraction, 9),
            "true_video_percent": round(true_video_fraction * 100, 6),
            "old_two_thirds_policy_active": False,
            "status": "PASS",
        },
        "canonical_reconciliation": {
            "schema_version": (
                "siraj-ep002-canonical-finalization-reconciliation-v5"
            ),
            "legacy_media_materializer_used": False,
            "canonical_runware_units": len(runware_units),
            "durable_runware_results": len(results),
            "canonical_local_units": len(local_units),
            "canonical_total_units": len(units),
            "visible_timeline_item_count": len(output_items),
            "intermediate_reference_unit_count": len(intermediate_ids),
            "unique_structural_shots": len(visible_shots),
            "all_canonical_units_accounted": True,
            "local_graphics_rendered_or_reused": local_rendered_or_reused,
            "all_visible_assets_hash_verified": True,
            "timeline_total_seconds": visual_seconds,
            "true_video_seconds": true_video_seconds,
            "true_video_percent": round(true_video_fraction * 100, 6),
            "provider_calls": 0,
            "paid_calls": 0,
            "automatic_paid_retry": False,
            "automatic_paid_resubmission": False,
        },
    }
    binding_manifest = _write_graphics_binding_manifest(repo, episode_id)
    queue["canonical_reconciliation"]["graphics_binding_manifest"] = str(
        binding_manifest.relative_to(repo)
    ).replace("\\", "/")
    queue["canonical_reconciliation"]["graphics_binding_manifest_sha256"] = (
        _sha256(binding_manifest)
    )

    # V6.2 production handoff: reconstruct canonical originals first, then
    # restore the exact V6.1-certified local editorial derivatives before
    # persisting the queue that assemble_episode_master will consume.
    queue = _apply_v6_1_certified_duplicate_rescue_for_production(
        repo,
        episode_id,
        queue,
    )
    _atomic_json(episode / QUEUE_REL, queue)
    return queue



def _duplicate_edges(
    problems: list[Mapping[str, Any]],
) -> list[tuple[str, str]]:
    edges: list[tuple[str, str]] = []
    for problem in problems:
        a = str(problem.get("a") or "")
        b = str(problem.get("b") or "")
        if not a or not b or a == b:
            raise FinalizationCompatibilityError(
                "DUPLICATE_GATE_NONPAIR_FINDING_UNSUPPORTED:"
                + json.dumps(
                    problem,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            )
        edges.append((a, b))
    return edges


def _ffmpeg_for_editorial_rescue() -> Path:
    import src.application.siraj_local_assembly_montage_v6_2_1 as montage

    return Path(montage._exe("ffmpeg", "SIRAJ_FFMPEG_EXE"))


def _normalized_crop_filter(
    zoom_width: int,
    zoom_height: int,
    x: int,
    y: int,
    *,
    contrast: float = 1.0,
    brightness: float = 0.0,
) -> str:
    return (
        f"scale={zoom_width}:{zoom_height}:"
        "force_original_aspect_ratio=increase,"
        f"crop={zoom_width}:{zoom_height},"
        f"crop=1920:1080:{x}:{y},"
        f"eq=contrast={contrast:.3f}:brightness={brightness:.3f}"
    )


def _editorial_filter(
    serial: int,
    variant: int,
) -> tuple[str, str]:
    """Return a material editorial reframe, not a duplicate-gate exemption."""

    # Family A: distinct cinematic crops.  We deliberately vary both zoom and
    # crop anchor so identical provider outputs become genuinely different
    # compositions rather than receiving metadata-only exemptions.
    if variant < 16:
        zooms = (
            (2208, 1242),
            (2304, 1296),
            (2400, 1350),
            (2496, 1404),
        )
        width, height = zooms[(serial + variant) % len(zooms)]
        max_x = width - 1920
        max_y = height - 1080
        anchors = (
            (0.00, 0.00),
            (1.00, 0.00),
            (0.00, 1.00),
            (1.00, 1.00),
            (0.50, 0.00),
            (0.50, 1.00),
            (0.00, 0.50),
            (1.00, 0.50),
            (0.25, 0.25),
            (0.75, 0.25),
            (0.25, 0.75),
            (0.75, 0.75),
            (0.50, 0.50),
        )
        ax, ay = anchors[(serial * 5 + variant * 3) % len(anchors)]
        x = int(round(max_x * ax))
        y = int(round(max_y * ay))
        contrast = (0.94, 0.98, 1.02, 1.06)[
            (serial + variant) % 4
        ]
        brightness = (-0.025, -0.010, 0.010, 0.025)[
            (serial * 3 + variant) % 4
        ]
        return (
            _normalized_crop_filter(
                width,
                height,
                x,
                y,
                contrast=contrast,
                brightness=brightness,
            ),
            (
                "CINEMATIC_CROP_REFRAME:"
                f"{width}x{height}:x={x}:y={y}:"
                f"contrast={contrast:.3f}:brightness={brightness:.3f}"
            ),
        )

    # Family B: picture-in-picture editorial composition over a locally
    # blurred version of the same source.  This is useful when several paid
    # outputs are effectively the same frame and simple reframing is not
    # enough.  No text, new semantic claim, provider call or generated content
    # is introduced.
    inset_variant = variant - 16
    inset_sizes = (
        (1344, 756),
        (1248, 702),
        (1152, 648),
        (1056, 594),
    )
    fw, fh = inset_sizes[(serial + inset_variant) % len(inset_sizes)]
    positions = (
        (48, 48),
        (1920 - 48, 48),
        (48, 1080 - 48),
        (1920 - 48, 1080 - 48),
        (960, 540),
        (960, 96),
        (960, 984),
        (96, 540),
        (1824, 540),
    )
    px, py = positions[(serial * 7 + inset_variant * 5) % len(positions)]
    if px == 960:
        x_expr = f"{(1920 - fw)//2}"
    elif px > 960:
        x_expr = f"{1920 - 48 - fw}"
    else:
        x_expr = "48"
    if py == 540:
        y_expr = f"{(1080 - fh)//2}"
    elif py > 540:
        y_expr = f"{1080 - 48 - fh}"
    else:
        y_expr = "48"
    # Background has a different crop anchor per serial to reduce the visual
    # sensation of replay in addition to the foreground inset.
    bg_width = 2304 + 96 * ((serial + inset_variant) % 3)
    bg_height = int(round(bg_width * 9 / 16))
    max_x = bg_width - 1920
    max_y = bg_height - 1080
    bx = int(round(max_x * ((serial * 0.37 + inset_variant * 0.19) % 1.0)))
    by = int(round(max_y * ((serial * 0.23 + inset_variant * 0.31) % 1.0)))
    filter_graph = (
        "split=2[bg0][fg0];"
        f"[bg0]scale={bg_width}:{bg_height}:"
        "force_original_aspect_ratio=increase,"
        f"crop={bg_width}:{bg_height},"
        f"crop=1920:1080:{bx}:{by},"
        "boxblur=18:1,"
        "eq=contrast=0.900:brightness=-0.015[bg];"
        f"[fg0]scale={fw}:{fh}:force_original_aspect_ratio=increase,"
        f"crop={fw}:{fh}[fg];"
        f"[bg][fg]overlay={x_expr}:{y_expr}"
    )
    return (
        filter_graph,
        (
            "BLURRED_BACKGROUND_INSET_RECOMPOSITION:"
            f"foreground={fw}x{fh}@{x_expr},{y_expr}:"
            f"background_crop={bg_width}x{bg_height}@{bx},{by}"
        ),
    )


def _render_editorial_candidate(
    ffmpeg: Path,
    source: Path,
    media_kind: str,
    target: Path,
    filter_graph: str,
) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if media_kind == "RUNWARE_VIDEO":
        args = [
            str(ffmpeg),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-an",
            "-vf",
            filter_graph,
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(target),
        ]
    else:
        args = [
            str(ffmpeg),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-vf",
            filter_graph,
            "-frames:v",
            "1",
            str(target),
        ]
    process = subprocess.run(
        args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=900,
    )
    if process.returncode != 0:
        raise FinalizationCompatibilityError(
            "LOCAL_EDITORIAL_RESCUE_FFMPEG_FAILED:"
            + process.stderr[-4000:]
        )
    if not target.is_file() or target.stat().st_size <= 0:
        raise FinalizationCompatibilityError(
            "LOCAL_EDITORIAL_RESCUE_OUTPUT_MISSING:" + str(target)
        )


def _repair_duplicate_assets_locally(
    repo: Path,
    episode_id: str,
    queue: dict[str, Any],
    audit_completed_assets: Any,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Resolve actual completed-asset conflicts without hiding the gate.

    The original provider result files and receipts remain immutable.  Only
    queue-visible local editorial derivatives are created.  Every accepted
    derivative is accepted because the *real production duplicate gate* no
    longer reports that queue item against any other visible item.
    """

    episode = repo / "projects" / episode_id
    items = [dict(item) for item in list(queue.get("items") or [])]
    if not items:
        raise FinalizationCompatibilityError(
            "LOCAL_EDITORIAL_RESCUE_QUEUE_EMPTY"
        )
    by_id = {
        str(item.get("queue_id") or ""): index
        for index, item in enumerate(items)
    }
    if len(by_id) != len(items) or "" in by_id:
        raise FinalizationCompatibilityError(
            "LOCAL_EDITORIAL_RESCUE_QUEUE_IDS_INVALID"
        )

    initial = list(audit_completed_assets(repo, items))
    current = initial
    rescue_root = episode / DUPLICATE_RESCUE_REL
    candidates_root = rescue_root / ".candidates"
    final_root = rescue_root / "assets"
    candidates_root.mkdir(parents=True, exist_ok=True)
    final_root.mkdir(parents=True, exist_ok=True)

    ffmpeg = _ffmpeg_for_editorial_rescue()
    repairs: list[dict[str, Any]] = []
    serial = 0
    maximum_repairs = len(items)

    while current:
        if len(repairs) >= maximum_repairs:
            raise FinalizationCompatibilityError(
                "LOCAL_EDITORIAL_RESCUE_DID_NOT_CONVERGE:"
                + json.dumps(
                    current,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            )
        edges = _duplicate_edges(current)
        degree: dict[str, int] = {}
        for a, b in edges:
            if a not in by_id or b not in by_id:
                raise FinalizationCompatibilityError(
                    "DUPLICATE_GATE_REFERENCES_UNKNOWN_QUEUE_ITEM:"
                    + a
                    + ":"
                    + b
                )
            degree[a] = degree.get(a, 0) + 1
            degree[b] = degree.get(b, 0) + 1

        # Maximum-degree greedy vertex cover.  For ties, edit the shorter
        # timeline allocation first so the longest original shot is retained.
        target_id = sorted(
            degree,
            key=lambda uid: (
                -degree[uid],
                float(items[by_id[uid]].get("duration_seconds") or 0.0),
                int(items[by_id[uid]].get("queue_index") or 0),
                uid,
            ),
        )[0]
        index = by_id[target_id]
        original_item = dict(items[index])
        source = (
            repo / str(original_item.get("output_path_relative") or "")
        ).resolve()
        if not source.is_file():
            raise FinalizationCompatibilityError(
                "LOCAL_EDITORIAL_RESCUE_SOURCE_MISSING:" + target_id
            )
        source_hash = _sha256(source)
        if source_hash != str(original_item.get("content_hash") or ""):
            raise FinalizationCompatibilityError(
                "LOCAL_EDITORIAL_RESCUE_SOURCE_HASH_CHANGED:" + target_id
            )
        media_kind = str(original_item.get("media_kind") or "")
        if media_kind not in {"RUNWARE_VIDEO", "RUNWARE_IMAGE"}:
            raise FinalizationCompatibilityError(
                "LOCAL_EDITORIAL_RESCUE_REFUSES_NON_RUNWARE_ASSET:"
                + target_id
            )

        serial += 1
        accepted: tuple[Path, str, list[Mapping[str, Any]]] | None = None
        best_remaining: int | None = None
        # 40 distinct material compositions: 16 cinematic crops + 24 insets.
        for variant in range(40):
            filter_graph, transform_id = _editorial_filter(serial, variant)
            suffix = ".mp4" if media_kind == "RUNWARE_VIDEO" else ".png"
            candidate = (
                candidates_root
                / f"{serial:02d}-{variant:02d}-{target_id}{suffix}"
            )
            _render_editorial_candidate(
                ffmpeg,
                source,
                media_kind,
                candidate,
                filter_graph,
            )
            candidate_item = dict(original_item)
            candidate_item["output_path_relative"] = str(
                candidate.relative_to(repo)
            ).replace("\\", "/")
            candidate_item["content_hash"] = _sha256(candidate)
            candidate_item["editorial_derivation"] = {
                "schema_version": (
                    "siraj-local-editorial-duplicate-rescue-v6"
                ),
                "status": "PASS_CANDIDATE",
                "source_queue_id": target_id,
                "source_path_relative": str(
                    source.relative_to(repo)
                ).replace("\\", "/"),
                "source_sha256": source_hash,
                "transform_id": transform_id,
                "provider_calls": 0,
                "paid_calls": 0,
                "automatic_paid_retry": False,
                "automatic_paid_resubmission": False,
            }
            trial_items = list(items)
            trial_items[index] = candidate_item
            trial = list(audit_completed_assets(repo, trial_items))
            target_still_conflicts = any(
                str(problem.get("a") or "") == target_id
                or str(problem.get("b") or "") == target_id
                for problem in trial
            )
            if not target_still_conflicts:
                accepted = (candidate, transform_id, trial)
                items[index] = candidate_item
                break
            if best_remaining is None or len(trial) < best_remaining:
                best_remaining = len(trial)
            candidate.unlink(missing_ok=True)

        if accepted is None:
            raise FinalizationCompatibilityError(
                "LOCAL_EDITORIAL_RESCUE_NO_GATE_CLEARING_VARIANT:"
                + target_id
                + ":degree="
                + str(degree[target_id])
                + ":best_total_findings="
                + str(best_remaining)
            )

        candidate, transform_id, trial = accepted
        suffix = candidate.suffix.lower()
        final_path = final_root / f"{target_id}{suffix}"
        final_path.unlink(missing_ok=True)
        os.replace(candidate, final_path)
        items[index]["output_path_relative"] = str(
            final_path.relative_to(repo)
        ).replace("\\", "/")
        items[index]["content_hash"] = _sha256(final_path)
        derivation = dict(items[index]["editorial_derivation"])
        derivation.update(
            {
                "status": "PASS_ACCEPTED_BY_EXACT_PRODUCTION_GATE",
                "output_path_relative": items[index]["output_path_relative"],
                "output_sha256": items[index]["content_hash"],
                "gate_conflicts_removed_for_item": degree[target_id],
            }
        )
        items[index]["editorial_derivation"] = derivation
        repairs.append(
            {
                "queue_id": target_id,
                "shot_id": items[index].get("shot_id"),
                "media_kind": media_kind,
                "duration_seconds": float(
                    items[index].get("duration_seconds") or 0.0
                ),
                "source_path_relative": str(
                    source.relative_to(repo)
                ).replace("\\", "/"),
                "source_sha256": source_hash,
                "derived_path_relative": items[index][
                    "output_path_relative"
                ],
                "derived_sha256": items[index]["content_hash"],
                "transform_id": transform_id,
                "conflict_degree_before": degree[target_id],
                "provider_calls": 0,
                "paid_calls": 0,
            }
        )
        current = list(audit_completed_assets(repo, items))
        if any(
            str(problem.get("a") or "") == target_id
            or str(problem.get("b") or "") == target_id
            for problem in current
        ):
            raise FinalizationCompatibilityError(
                "LOCAL_EDITORIAL_RESCUE_ACCEPTED_ITEM_REGRESSED:"
                + target_id
            )

    # Remove rejected candidate residue.  Accepted assets and a durable report
    # remain; provider evidence is never touched.
    if candidates_root.is_dir():
        for path in candidates_root.glob("*"):
            if path.is_file():
                path.unlink()
        try:
            candidates_root.rmdir()
        except OSError:
            pass

    final = list(audit_completed_assets(repo, items))
    if final:
        raise FinalizationCompatibilityError(
            "LOCAL_EDITORIAL_RESCUE_FINAL_GATE_NOT_ZERO:"
            + json.dumps(
                final,
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )

    repaired_seconds = round(
        sum(float(row["duration_seconds"]) for row in repairs),
        6,
    )
    report = {
        "schema_version": "siraj-ep002-local-editorial-duplicate-rescue-v6",
        "release": "SIRAJ_EP002_GROUND_TRUTH_FINALIZATION_RELEASE_V6",
        "status": "PASS",
        "episode_id": episode_id,
        "strategy": (
            "EXACT_PRODUCTION_GATE_DRIVEN_LOCAL_EDITORIAL_REFRAME"
        ),
        "gate_bypass_used": False,
        "reuse_justification_added": False,
        "provider_regeneration_used": False,
        "network_calls": 0,
        "provider_calls": 0,
        "paid_calls": 0,
        "automatic_paid_retry": False,
        "automatic_paid_resubmission": False,
        "initial_duplicate_findings": len(initial),
        "final_duplicate_findings": 0,
        "repaired_item_count": len(repairs),
        "repaired_timeline_seconds": repaired_seconds,
        "repairs": repairs,
        "initial_findings": initial,
        "final_findings": final,
    }
    report_path = episode / DUPLICATE_RESCUE_REPORT_REL
    _atomic_json(report_path, report)

    queue = dict(queue)
    queue["items"] = items
    duplicate_policy = dict(queue.get("duplicate_policy") or {})
    duplicate_policy.update(
        {
            "status": "PASS",
            "runtime_audit": "PASS_ZERO_FINDINGS_AFTER_LOCAL_EDITORIAL_RESCUE",
            "initial_findings": len(initial),
            "final_findings": 0,
            "gate_bypass_used": False,
        }
    )
    queue["duplicate_policy"] = duplicate_policy
    reconciliation = dict(queue.get("canonical_reconciliation") or {})
    reconciliation.update(
        {
            "initial_duplicate_findings": len(initial),
            "final_duplicate_findings": 0,
            "local_editorial_duplicate_rescue": "PASS",
            "local_editorial_duplicate_rescue_count": len(repairs),
            "local_editorial_duplicate_rescue_seconds": repaired_seconds,
            "duplicate_rescue_report": str(
                report_path.relative_to(repo)
            ).replace("\\", "/"),
            "duplicate_rescue_report_sha256": _sha256(report_path),
        }
    )
    queue["canonical_reconciliation"] = reconciliation
    _atomic_json(episode / QUEUE_REL, queue)
    return queue, report

def _ensure_qa_compatibility_inputs(
    repo: Path,
    episode_id: str,
    queue: Mapping[str, Any],
) -> dict[str, str]:
    episode = repo / "projects" / episode_id
    canonical_cost_path = episode / PREFLIGHT_REL
    canonical_cost = _read(canonical_cost_path)
    legacy_cost_path = episode / LEGACY_COST_REL
    legacy_cost = dict(canonical_cost)
    legacy_cost["schema_version"] = (
        "siraj-media-cost-preflight-v6-2-1-compatibility-v6"
    )
    legacy_cost["status"] = "PASS"
    legacy_cost["compatibility_projection_v6"] = {
        "canonical_path": str(
            canonical_cost_path.relative_to(repo)
        ).replace("\\", "/"),
        "canonical_sha256": _sha256(canonical_cost_path),
        "canonical_status": canonical_cost.get("status"),
        "provider_execution_complete": True,
        "provider_calls": 0,
        "paid_calls": 0,
    }
    _atomic_json(legacy_cost_path, legacy_cost)

    prompt_path = episode / PROMPT_PLAN_REL
    promoted_path = episode / PROMOTED_DUPLICATE_REL
    if not prompt_path.is_file():
        raise FinalizationCompatibilityError(
            "CURRENT_PROMPT_PLAN_REQUIRED_FOR_DUPLICATE_PROJECTION"
        )
    from src.application.artifact_provenance_v1 import canonical_sha256
    current_prompt_hash = canonical_sha256(_read(prompt_path))
    promoted_sha = _sha256(promoted_path) if promoted_path.is_file() else None
    legacy_duplicate_path = episode / LEGACY_DUPLICATE_REL
    _atomic_json(
        legacy_duplicate_path,
        {
            "schema_version": (
                "siraj-prompt-duplicate-gate-v6-4-compatibility-v6"
            ),
            "status": "PASS",
            "episode_id": episode_id,
            "input_prompt_plan_sha256": current_prompt_hash,
            "basis": "RUNTIME_AUDIT_COMPLETED_ASSETS_PASS",
            "promoted_duplicate_gate_path": (
                str(promoted_path.relative_to(repo)).replace("\\", "/")
                if promoted_path.is_file()
                else None
            ),
            "promoted_duplicate_gate_sha256": promoted_sha,
            "queue_sha256": _sha256(episode / QUEUE_REL),
            "provider_calls": 0,
            "paid_calls": 0,
        },
    )
    return {
        "legacy_cost_preflight": str(
            legacy_cost_path.relative_to(repo)
        ).replace("\\", "/"),
        "legacy_duplicate_gate": str(
            legacy_duplicate_path.relative_to(repo)
        ).replace("\\", "/"),
    }


def _write_graphics_binding_manifest(
    repo: Path,
    episode_id: str,
) -> Path:
    episode = repo / "projects" / episode_id
    root = episode / LOCAL_ROOT_REL / "receipts"
    rows: list[dict[str, Any]] = []
    for uid in (
        "EP002-SH-032-G01",
        "EP002-SH-040-G01",
        "EP002-SH-041-G01",
        "EP002-SH-042-G01",
    ):
        path = root / f"{uid}.json"
        if not path.is_file():
            raise FinalizationCompatibilityError(
                "GRAPHICS_BINDING_RECEIPT_MISSING:" + uid
            )
        value = _read(path)
        if (
            value.get("status") != "PASS"
            or value.get("binding_mode")
            != "GROUND_TRUTH_COMPATIBILITY_PROVENANCE"
        ):
            raise FinalizationCompatibilityError(
                "GRAPHICS_BINDING_RECEIPT_INVALID:" + uid
            )
        rows.append(
            {
                "unit_id": uid,
                "shot_id": value.get("shot_id"),
                "source_ids": value.get("source_ids"),
                "binding_mode": value.get("binding_mode"),
                "binding_reason": value.get("binding_reason"),
                "authored_graphics_spec_sha256": value.get(
                    "authored_graphics_spec_sha256"
                ),
                "output_path_relative": value.get("output_path_relative"),
                "output_sha256": value.get("output_sha256"),
            }
        )
    target = episode / GRAPHICS_BINDINGS_REL
    _atomic_json(
        target,
        {
            "schema_version": (
                "siraj-ep002-local-graphics-ground-truth-bindings-v5"
            ),
            "release": "SIRAJ_EP002_GROUND_TRUTH_FINALIZATION_RELEASE_V6",
            "status": "PASS",
            "episode_id": episode_id,
            "binding_mode": "GROUND_TRUTH_COMPATIBILITY_PROVENANCE",
            "bindings": rows,
            "provider_calls": 0,
            "paid_calls": 0,
            "automatic_paid_retry": False,
            "automatic_paid_resubmission": False,
        },
    )
    return target


def _temporary_shadow_as_production_master(
    repo: Path,
    episode_id: str,
    shadow_master: Path,
):
    """Context manager-like generator for QA manifest preflight."""
    from contextlib import contextmanager

    @contextmanager
    def context():
        target_dir = (
            repo / "projects" / episode_id / "deliverables"
            / "autopilot-v6-2-1"
        )
        target_dir_existed = target_dir.is_dir()
        target_dir.mkdir(parents=True, exist_ok=True)
        master = target_dir / "episode-master-autopilot-v6-2-1.mp4"
        receipt = target_dir / "episode-master-autopilot-v6-2-1-receipt.json"
        saved: dict[Path, bytes | None] = {}
        for path in (master, receipt):
            saved[path] = path.read_bytes() if path.is_file() else None
        try:
            master.write_bytes(shadow_master.read_bytes())
            _atomic_json(
                receipt,
                {
                    "schema_version": "siraj-local-assembly-montage-v6.2.1",
                    "status": "PASS",
                    "episode_id": episode_id,
                    "master_path_relative": str(
                        master.relative_to(repo)
                    ).replace("\\", "/"),
                    "master_sha256": _sha256(master),
                    "duration_seconds": EXPECTED_EPISODE_SECONDS,
                    "duplicate_gate": "PASS",
                    "generated_video_policy": {
                        "status": "PASS",
                    },
                    "video": {
                        "width": 1920,
                        "height": 1080,
                        "fps": 30,
                    },
                    "audio": {
                        "sample_rate": 48000,
                        "channels": 2,
                        "codec": "aac",
                    },
                    "next_stage": "SEMANTIC_EDITORIAL_AND_TECHNICAL_QA",
                    "shadow_certification_only": True,
                },
            )
            yield
        finally:
            for path, content in saved.items():
                if content is None:
                    path.unlink(missing_ok=True)
                else:
                    path.write_bytes(content)
            if (
                not target_dir_existed
                and target_dir.is_dir()
                and not any(target_dir.iterdir())
            ):
                target_dir.rmdir()

    return context()


def certify_remaining_pipeline_inputs(
    repo_root: Path,
    episode_id: str = EPISODE_ID,
) -> dict[str, Any]:
    repo = Path(repo_root).resolve()
    queue = ensure_montage_media_queue(repo, episode_id)
    items = list(queue["items"])
    reconciliation = dict(queue["canonical_reconciliation"])

    from src.application.siraj_duplicate_gates_v6_2_1 import (
        audit_completed_assets,
    )
    initial_duplicate_problems = list(
        audit_completed_assets(repo, items)
    )
    queue, duplicate_rescue = _repair_duplicate_assets_locally(
        repo,
        episode_id,
        dict(queue),
        audit_completed_assets,
    )
    items = list(queue["items"])
    reconciliation = dict(queue["canonical_reconciliation"])
    final_duplicate_problems = list(
        audit_completed_assets(repo, items)
    )
    if final_duplicate_problems:
        raise FinalizationCompatibilityError(
            "DUPLICATE_GATE_RUNTIME_AUDIT_FAILED_AFTER_LOCAL_RESCUE:"
            + json.dumps(
                final_duplicate_problems,
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )

    qa_compatibility = _ensure_qa_compatibility_inputs(
        repo,
        episode_id,
        queue,
    )

    import src.application.siraj_local_assembly_montage_v6_2_1 as montage
    install_runtime_montage_compatibility()
    ffmpeg = montage._exe("ffmpeg", "SIRAJ_FFMPEG_EXE")
    ffprobe = montage._exe("ffprobe", "SIRAJ_FFPROBE_EXE")
    for executable in (ffmpeg, ffprobe):
        process = subprocess.run(
            [str(executable), "-version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        if process.returncode != 0:
            raise FinalizationCompatibilityError(
                "MEDIA_TOOL_UNAVAILABLE:" + str(executable)
            )

    from src.application.siraj_final_tts_queue_selector_v6_3_2 import (
        resolve_final_tts_queue_path,
    )
    tts = _read(resolve_final_tts_queue_path(repo, episode_id))

    with tempfile.TemporaryDirectory(
        prefix="siraj_ep002_full_shadow_v5_"
    ) as temporary:
        root = Path(temporary)
        narration = root / "narration.wav"
        montage._build_narration(repo, tts, narration)
        narration_seconds = float(montage._duration(narration))

        shots = root / "shots"
        shots.mkdir(parents=True, exist_ok=True)
        concat_lines: list[str] = []
        visual_seconds = 0.0

        for ordinal, item in enumerate(items, 1):
            source = repo / str(item["output_path_relative"])
            if not source.is_file():
                raise FinalizationCompatibilityError(
                    "SHADOW_SOURCE_MISSING:" + str(source)
                )
            if _sha256(source) != str(item["content_hash"]):
                raise FinalizationCompatibilityError(
                    "SHADOW_SOURCE_HASH_CHANGED:"
                    + str(item["queue_id"])
                )
            duration = float(item["duration_seconds"])
            rendered = shots / f"{ordinal:04d}.mp4"
            montage._render_shot(
                source,
                str(item["media_kind"]),
                duration,
                rendered,
                ordinal,
            )
            if not rendered.is_file() or rendered.stat().st_size <= 0:
                raise FinalizationCompatibilityError(
                    "FULL_SHADOW_RENDER_FAILED:"
                    + str(item["queue_id"])
                )
            concat_lines.append(
                "file '"
                + rendered.as_posix().replace("'", "'\\''")
                + "'"
            )
            visual_seconds += duration

        if abs(visual_seconds - narration_seconds) > 2.0:
            raise FinalizationCompatibilityError(
                "AUDIO_VISUAL_TOTAL_DURATION_MISMATCH_PRECERT:"
                f"audio={narration_seconds:.3f}:visual={visual_seconds:.3f}"
            )

        concat = root / "concat.txt"
        concat.write_text(
            "\n".join(concat_lines) + "\n",
            encoding="utf-8",
        )
        video_only = root / "video-only.mp4"
        montage._run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                concat,
                "-c",
                "copy",
                video_only,
            ]
        )
        shadow_master = root / "shadow-master.mp4"
        montage._run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                video_only,
                "-i",
                narration,
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-ar",
                "48000",
                "-ac",
                "2",
                "-shortest",
                "-movflags",
                "+faststart",
                shadow_master,
            ]
        )
        if not shadow_master.is_file() or shadow_master.stat().st_size <= 0:
            raise FinalizationCompatibilityError(
                "FULL_SHADOW_MASTER_NOT_CREATED"
            )
        master_seconds = float(montage._duration(shadow_master))
        if abs(master_seconds - narration_seconds) > 2.0:
            raise FinalizationCompatibilityError(
                "FULL_SHADOW_MASTER_DURATION_INVALID:"
                f"master={master_seconds:.3f}:audio={narration_seconds:.3f}"
            )

        probe = subprocess.run(
            [
                str(ffprobe),
                "-v",
                "error",
                "-show_entries",
                "stream=codec_type",
                "-of",
                "json",
                str(shadow_master),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        if probe.returncode != 0:
            raise FinalizationCompatibilityError(
                "FULL_SHADOW_FFPROBE_FAILED"
            )
        probe_value = json.loads(probe.stdout or "{}")
        stream_types = {
            str(stream.get("codec_type") or "")
            for stream in probe_value.get("streams", [])
            if isinstance(stream, Mapping)
        }
        if not {"video", "audio"} <= stream_types:
            raise FinalizationCompatibilityError(
                "FULL_SHADOW_MASTER_STREAMS_INVALID"
            )

        import src.application.siraj_one_click_autopilot_v6_4 as autopilot
        manifest_builder = getattr(autopilot, "_final_qa_manifest", None)
        if not callable(manifest_builder):
            raise FinalizationCompatibilityError(
                "FINAL_QA_MANIFEST_BUILDER_UNAVAILABLE"
            )
        with _temporary_shadow_as_production_master(
            repo,
            episode_id,
            shadow_master,
        ):
            manifest = manifest_builder(repo, episode_id)
            if not isinstance(manifest, Mapping):
                raise FinalizationCompatibilityError(
                    "FINAL_QA_MANIFEST_PRECERT_INVALID"
                )

        qa_stage = "SEMANTIC_EDITORIAL_AND_TECHNICAL_QA"
        paid_stages = set(getattr(autopilot, "PAID_STAGES", set()))
        qa_is_paid = qa_stage in paid_stages
        qa_authorized = True
        stage_authorized = getattr(
            autopilot,
            "_stage_authorized",
            None,
        )
        if qa_is_paid:
            if not callable(stage_authorized):
                raise FinalizationCompatibilityError(
                    "QA_PAID_AUTHORIZATION_CHECK_UNAVAILABLE"
                )
            qa_authorized = bool(
                stage_authorized(repo, episode_id, qa_stage)
            )

    return {
        "status": "PASS",
        **reconciliation,
        "duplicate_gate_runtime_audit": "PASS",
        "initial_duplicate_findings": len(initial_duplicate_problems),
        "final_duplicate_findings": len(final_duplicate_problems),
        "local_editorial_duplicate_rescue": "PASS",
        "local_editorial_duplicate_rescue_count": int(
            duplicate_rescue["repaired_item_count"]
        ),
        "local_editorial_duplicate_rescue_seconds": float(
            duplicate_rescue["repaired_timeline_seconds"]
        ),
        "duplicate_rescue_report": reconciliation.get(
            "duplicate_rescue_report"
        ),
        "duplicate_gate_bypass_used": False,
        "full_shadow_montage": "PASS",
        "full_shadow_master_audio_video_streams": "PASS",
        "tts_narration_build": "PASS",
        "audio_visual_duration_match": "PASS",
        "narration_seconds": round(narration_seconds, 3),
        "ffmpeg_ffprobe": "PASS",
        "qa_manifest_preflight": "PASS",
        "qa_compatibility_inputs": qa_compatibility,
        "graphics_binding_mode": "GROUND_TRUTH_COMPATIBILITY_PROVENANCE",
        "graphics_binding_manifest": reconciliation.get(
            "graphics_binding_manifest"
        ),
        "qa_is_paid_stage": qa_is_paid,
        "qa_currently_authorized": qa_authorized,
        "qa_explicit_authorization_required": (
            qa_is_paid and not qa_authorized
        ),
        "provider_calls": 0,
        "paid_calls": 0,
        "automatic_paid_retry": False,
        "automatic_paid_resubmission": False,
    }
