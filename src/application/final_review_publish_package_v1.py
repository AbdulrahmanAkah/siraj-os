from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.application.artifact_dependency_graph_v1 import canonical_sha256

RELEASE = "FINAL_REVIEW_AND_PUBLISH_PACKAGE_V1"

ORCHESTRATOR_STATE_REL = Path(
    "projects/_orchestrator/autonomous-episode-orchestrator-state-v1.json"
)
EPISODE_DEFINITION_REL = Path("contracts/episode-definition-v1.json")
STAGE_LEDGER_REL = Path("orchestration/stage-ledger-v1.json")
DEPENDENCY_GRAPH_REL = Path("orchestration/artifact-dependency-graph-v1.json")
QA_REPORT_REL = Path("qa/automatic-qa-report-v1.json")
FINAL_MASTER_REL = Path("deliverables/episode-master-v1.mp4")
FINAL_RECEIPT_REL = Path("deliverables/episode-master-v1-receipt.json")

PUBLISHING_DIR_REL = Path("publishing")
FINAL_REVIEW_REL = PUBLISHING_DIR_REL / "human-final-review-v1.json"
REPAIR_REQUEST_REL = PUBLISHING_DIR_REL / "final-review-repair-request-v1.json"
PUBLISH_PACKAGE_DIR_REL = PUBLISHING_DIR_REL / "publish-package-v1"
PUBLISH_MANIFEST_REL = PUBLISH_PACKAGE_DIR_REL / "publish-manifest-v1.json"
YOUTUBE_METADATA_REL = PUBLISH_PACKAGE_DIR_REL / "youtube-metadata-v1.json"
YOUTUBE_TITLE_REL = PUBLISH_PACKAGE_DIR_REL / "youtube-title.txt"
YOUTUBE_DESCRIPTION_REL = PUBLISH_PACKAGE_DIR_REL / "youtube-description.txt"
YOUTUBE_TAGS_REL = PUBLISH_PACKAGE_DIR_REL / "youtube-tags.txt"
UPLOAD_CHECKLIST_REL = PUBLISH_PACKAGE_DIR_REL / "manual-upload-checklist.md"
CHECKSUMS_REL = PUBLISH_PACKAGE_DIR_REL / "SHA256SUMS.txt"
METADATA_ARCHIVE_REL = PUBLISH_PACKAGE_DIR_REL / "publish-metadata-v1.zip"
RUN_STATE_REL = Path("orchestration/final-review-publish-package-state-v1.json")

REQUIRED_CHECKLIST_KEYS = (
    "watched_full_episode",
    "reviewed_audio_and_sync",
    "reviewed_visual_continuity",
    "reviewed_historical_semantic_accuracy",
    "confirmed_no_forbidden_music",
    "confirmed_no_private_or_sensitive_data",
    "approved_title_description_and_tags",
)

REVIEW_CATEGORIES = frozenset(
    {
        "VISUAL",
        "AUDIO",
        "CONTENT_ACCURACY",
        "METADATA",
        "OTHER",
    }
)

SAFE_TITLE_MAX_CHARS = 100
SAFE_DESCRIPTION_MAX_CHARS = 5_000
SAFE_TAGS_MAX_CHARS = 500


class FinalReviewError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class FinalReviewResult:
    episode_id: str
    status: str
    decision: str
    review_path: Path
    publish_manifest_path: Path | None
    repair_request_path: Path | None
    final_master_path: Path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FinalReviewError(f"CANNOT_READ_JSON:{path}:{exc}") from exc
    if not isinstance(value, dict):
        raise FinalReviewError(f"JSON_OBJECT_REQUIRED:{path}")
    return value


def _write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _relative(repo: Path, path: Path) -> str:
    return str(path.resolve().relative_to(repo.resolve())).replace("\\", "/")


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        return value
    return ()


def _active_episode(
    repo_root: Path,
) -> tuple[Path, str, Path, Path, dict[str, Any]]:
    repo = repo_root.resolve()
    state_path = repo / ORCHESTRATOR_STATE_REL
    state = _read(state_path)
    episode_id = state.get("current_episode_id")
    if not isinstance(episode_id, str) or not episode_id.strip():
        raise FinalReviewError("CURRENT_EPISODE_REQUIRED_FOR_FINAL_REVIEW")
    episode_id = episode_id.strip()
    episode_root = repo / "projects" / episode_id
    if not episode_root.is_dir():
        raise FinalReviewError("CURRENT_EPISODE_DIRECTORY_MISSING")
    return repo, episode_id, episode_root, state_path, state


def _clean_text(value: Any) -> str:
    return re.sub(r"[\t\r ]+", " ", str(value or "")).strip()


def _clean_multiline(value: Any) -> str:
    lines = [re.sub(r"[\t\r ]+", " ", line).strip() for line in str(value or "").splitlines()]
    return "\n".join(line for line in lines if line).strip()


def _normalize_tags(tags: Sequence[str] | str) -> list[str]:
    if isinstance(tags, str):
        values = re.split(r"[,،\n]+", tags)
    else:
        values = [str(value) for value in tags]
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = _clean_text(value).lstrip("#")
        key = cleaned.casefold()
        if cleaned and key not in seen:
            seen.add(key)
            result.append(cleaned)
    return result


def _validate_metadata(
    title: str,
    description: str,
    tags: Sequence[str] | str,
) -> tuple[str, str, list[str]]:
    cleaned_title = _clean_text(title)
    cleaned_description = _clean_multiline(description)
    cleaned_tags = _normalize_tags(tags)
    if not cleaned_title:
        raise FinalReviewError("PUBLISH_TITLE_REQUIRED")
    if len(cleaned_title) > SAFE_TITLE_MAX_CHARS:
        raise FinalReviewError("PUBLISH_TITLE_TOO_LONG")
    if len(cleaned_description) > SAFE_DESCRIPTION_MAX_CHARS:
        raise FinalReviewError("PUBLISH_DESCRIPTION_TOO_LONG")
    tag_text = ", ".join(cleaned_tags)
    if len(tag_text) > SAFE_TAGS_MAX_CHARS:
        raise FinalReviewError("PUBLISH_TAGS_TOO_LONG")
    return cleaned_title, cleaned_description, cleaned_tags


def _validate_checklist(checklist: Mapping[str, Any]) -> dict[str, bool]:
    normalized = {
        key: bool(checklist.get(key))
        for key in REQUIRED_CHECKLIST_KEYS
    }
    missing = [key for key, checked in normalized.items() if not checked]
    if missing:
        raise FinalReviewError(
            "FINAL_REVIEW_CHECKLIST_INCOMPLETE:" + ",".join(missing)
        )
    return normalized


def _verify_qa_and_final_integrity(
    repo: Path,
    episode_root: Path,
    state: Mapping[str, Any],
) -> dict[str, Any]:
    qa_path = episode_root / QA_REPORT_REL
    final_path = episode_root / FINAL_MASTER_REL
    final_receipt_path = episode_root / FINAL_RECEIPT_REL
    for path, code in (
        (qa_path, "AUTOMATIC_QA_REPORT_REQUIRED"),
        (final_path, "FINAL_MASTER_REQUIRED"),
        (final_receipt_path, "FINAL_RENDER_RECEIPT_REQUIRED"),
    ):
        if not path.is_file():
            raise FinalReviewError(code)

    qa = _read(qa_path)
    if qa.get("status") != "PASS":
        raise FinalReviewError("AUTOMATIC_QA_MUST_PASS_BEFORE_FINAL_APPROVAL")
    qa_sha = _sha256(qa_path)
    expected_qa_sha = state.get("automatic_qa_report_sha256")
    if isinstance(expected_qa_sha, str) and expected_qa_sha and expected_qa_sha != qa_sha:
        raise FinalReviewError("AUTOMATIC_QA_REPORT_HASH_MISMATCH")

    receipt = _read(final_receipt_path)
    final_sha = _sha256(final_path)
    if receipt.get("final_master_sha256") != final_sha:
        raise FinalReviewError("FINAL_MASTER_HASH_MISMATCH")
    if receipt.get("status") != "COMPLETE_READY_FOR_AUTOMATIC_QA":
        raise FinalReviewError("FINAL_RENDER_RECEIPT_STATUS_INVALID")

    return {
        "qa_report_path": qa_path,
        "qa_report_sha256": qa_sha,
        "final_master_path": final_path,
        "final_master_sha256": final_sha,
        "final_master_bytes": final_path.stat().st_size,
        "final_receipt_path": final_receipt_path,
        "final_receipt_sha256": _sha256(final_receipt_path),
        "qa_report": qa,
        "final_receipt": receipt,
    }


def _latest_repair_request(episode_root: Path) -> dict[str, Any] | None:
    path = episode_root / REPAIR_REQUEST_REL
    if not path.is_file():
        return None
    return _read(path)


def _approval_allowed(
    state: Mapping[str, Any],
    episode_root: Path,
) -> None:
    status = str(state.get("status", ""))
    if status == "AWAITING_HUMAN_FINAL_REVIEW":
        return
    if status == "HUMAN_FINAL_REVIEW_CHANGES_REQUESTED":
        request = _latest_repair_request(episode_root)
        if request is None:
            raise FinalReviewError("FINAL_REVIEW_REPAIR_REQUEST_MISSING")
        if bool(request.get("requires_qa_rerun")):
            raise FinalReviewError("AUTOMATIC_QA_RERUN_REQUIRED_AFTER_CHANGES")
        return
    if status == "READY_TO_PUBLISH":
        return
    raise FinalReviewError(f"FINAL_REVIEW_APPROVAL_NOT_ALLOWED:{status}")


def suggest_publish_metadata(repo_root: Path) -> dict[str, Any]:
    repo, episode_id, episode_root, _, _ = _active_episode(repo_root)
    del repo
    definition_path = episode_root / EPISODE_DEFINITION_REL
    definition = _read(definition_path) if definition_path.is_file() else {}
    title = _clean_text(
        definition.get("working_title_ar")
        or definition.get("title_ar")
        or episode_id
    )
    central_question = _clean_text(definition.get("central_question_ar"))
    description_lines = []
    if central_question:
        description_lines.append(central_question)
    description_lines.extend(
        [
            "",
            "حلقة وثائقية من مشروع سراج.",
            "تتم المراجعة البشرية النهائية قبل النشر اليدوي.",
        ]
    )
    return {
        "title": title[:SAFE_TITLE_MAX_CHARS],
        "description": "\n".join(description_lines).strip(),
        "tags": ["سراج", "وثائقي", "تاريخ"],
        "visibility_preference": "PRIVATE",
    }


def _upsert_graph_node(
    nodes: list[dict[str, Any]],
    payload: Mapping[str, Any],
) -> None:
    node_id = payload.get("node_id")
    existing = next(
        (
            node
            for node in nodes
            if isinstance(node, dict) and node.get("node_id") == node_id
        ),
        None,
    )
    if existing is None:
        nodes.append(dict(payload))
    else:
        existing.update(payload)


def _add_edge(edges: list[dict[str, str]], source: str, target: str) -> None:
    edge = {"from": source, "to": target}
    if edge not in edges:
        edges.append(edge)


def _update_dependency_graph(
    repo: Path,
    episode_id: str,
    episode_root: Path,
    *,
    review_path: Path,
    decision: str,
    publish_manifest_path: Path | None,
) -> None:
    path = episode_root / DEPENDENCY_GRAPH_REL
    if not path.is_file():
        return
    graph = _read(path)
    nodes = graph.get("nodes")
    edges = graph.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise FinalReviewError("DEPENDENCY_GRAPH_STRUCTURE_INVALID")

    review_node = f"{episode_id}:HUMAN_FINAL_REVIEW"
    _upsert_graph_node(
        nodes,
        {
            "node_id": review_node,
            "kind": "HUMAN_FINAL_REVIEW_RECEIPT",
            "source_id": episode_id,
            "status": "COMPLETE" if decision == "APPROVE" else "BLOCKED",
            "version": 1,
            "artifact_path_relative": _relative(repo, review_path),
            "artifact_sha256": _sha256(review_path),
            "invalidated_at_utc": None,
            "invalidation_reason": None,
        },
    )
    _add_edge(edges, f"{episode_id}:FINAL_RENDER", review_node)
    _add_edge(edges, f"{episode_id}:AUTOMATIC_QA_REPORT", review_node)

    if publish_manifest_path is not None:
        package_node = f"{episode_id}:PUBLISH_PACKAGE"
        _upsert_graph_node(
            nodes,
            {
                "node_id": package_node,
                "kind": "MANUAL_PUBLISH_PACKAGE",
                "source_id": episode_id,
                "status": "COMPLETE",
                "version": 1,
                "artifact_path_relative": _relative(repo, publish_manifest_path),
                "artifact_sha256": _sha256(publish_manifest_path),
                "invalidated_at_utc": None,
                "invalidation_reason": None,
            },
        )
        _add_edge(edges, review_node, package_node)

    graph["status"] = (
        "READY_TO_PUBLISH"
        if decision == "APPROVE"
        else "HUMAN_FINAL_REVIEW_CHANGES_REQUESTED"
    )
    graph["updated_at_utc"] = _now()
    graph.pop("graph_sha256", None)
    graph["graph_sha256"] = canonical_sha256(graph)
    _write(path, graph)


def _update_stage_ledger(
    repo: Path,
    episode_root: Path,
    *,
    decision: str,
    review_path: Path,
    publish_manifest_path: Path | None,
    repair_target_stage: str | None,
) -> None:
    path = episode_root / STAGE_LEDGER_REL
    if not path.is_file():
        return
    ledger = _read(path)
    stages = ledger.get("stages")
    if not isinstance(stages, list):
        raise FinalReviewError("STAGE_LEDGER_STAGES_REQUIRED")
    for stage in stages:
        if not isinstance(stage, dict):
            continue
        stage_name = stage.get("stage")
        if stage_name == "HUMAN_FINAL_REVIEW":
            stage["status"] = "COMPLETE" if decision == "APPROVE" else "CHANGES_REQUESTED"
            stage["artifact_path_relative"] = _relative(repo, review_path)
            stage["updated_at_utc"] = _now()
        elif stage_name == "READY_TO_PUBLISH":
            if decision == "APPROVE" and publish_manifest_path is not None:
                stage["status"] = "COMPLETE"
                stage["artifact_path_relative"] = _relative(repo, publish_manifest_path)
            else:
                stage["status"] = "QUEUED"
            stage["updated_at_utc"] = _now()
    ledger["status"] = (
        "READY_TO_PUBLISH"
        if decision == "APPROVE"
        else "HUMAN_FINAL_REVIEW_CHANGES_REQUESTED"
    )
    ledger["resume_from"] = (
        "MANUAL_YOUTUBE_UPLOAD"
        if decision == "APPROVE"
        else str(repair_target_stage or "HUMAN_FINAL_REVIEW")
    )
    ledger["updated_at_utc"] = _now()
    _write(path, ledger)


def _write_manual_upload_checklist(
    path: Path,
    *,
    episode_id: str,
    final_master_relative: str,
    final_master_sha256: str,
    visibility_preference: str,
) -> None:
    text = f"""# Manual Publishing Checklist\n\nEpisode: `{episode_id}`\n\n## Upload source\n\n- Video: `{final_master_relative}`\n- SHA-256: `{final_master_sha256}`\n- Preferred initial visibility: `{visibility_preference}`\n\n## Required manual steps\n\n- [ ] Open the final video and verify the first and final frames.\n- [ ] Upload the exact file referenced above.\n- [ ] Paste the title, description and tags from this package.\n- [ ] Set audience, visibility, language, category and thumbnail manually.\n- [ ] Recheck the uploaded processing result before making it public.\n- [ ] Record the platform URL outside SIRAJ after publication.\n\nSIRAJ does not upload automatically and stores no YouTube credentials.\n"""
    _write_text(path, text)


def _metadata_archive(
    package_root: Path,
    archive_path: Path,
    files: Sequence[Path],
) -> None:
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = archive_path.with_suffix(archive_path.suffix + ".tmp")
    temporary.unlink(missing_ok=True)
    with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in files:
            bundle.write(path, path.relative_to(package_root))
    os.replace(temporary, archive_path)


def _build_publish_package(
    repo: Path,
    episode_id: str,
    episode_root: Path,
    integrity: Mapping[str, Any],
    *,
    review_path: Path,
    title: str,
    description: str,
    tags: Sequence[str],
    visibility_preference: str,
) -> Path:
    package_root = episode_root / PUBLISH_PACKAGE_DIR_REL
    package_root.mkdir(parents=True, exist_ok=True)
    title_path = episode_root / YOUTUBE_TITLE_REL
    description_path = episode_root / YOUTUBE_DESCRIPTION_REL
    tags_path = episode_root / YOUTUBE_TAGS_REL
    metadata_path = episode_root / YOUTUBE_METADATA_REL
    checklist_path = episode_root / UPLOAD_CHECKLIST_REL
    checksums_path = episode_root / CHECKSUMS_REL
    archive_path = episode_root / METADATA_ARCHIVE_REL
    manifest_path = episode_root / PUBLISH_MANIFEST_REL

    _write_text(title_path, title + "\n")
    _write_text(description_path, description + ("\n" if description else ""))
    _write_text(tags_path, ", ".join(tags) + ("\n" if tags else ""))

    metadata = {
        "schema_version": "siraj-youtube-metadata-v1",
        "release": RELEASE,
        "episode_id": episode_id,
        "title": title,
        "description": description,
        "tags": list(tags),
        "visibility_preference": visibility_preference,
        "audience_setting": "REVIEW_MANUALLY_DURING_UPLOAD",
        "language_setting": "REVIEW_MANUALLY_DURING_UPLOAD",
        "thumbnail": "OPTIONAL_MANUAL_SELECTION",
        "manual_upload_only": True,
        "youtube_api_requests": 0,
        "created_at_utc": _now(),
    }
    metadata["metadata_sha256"] = canonical_sha256(metadata)
    _write(metadata_path, metadata)

    _write_manual_upload_checklist(
        checklist_path,
        episode_id=episode_id,
        final_master_relative=_relative(repo, integrity["final_master_path"]),
        final_master_sha256=str(integrity["final_master_sha256"]),
        visibility_preference=visibility_preference,
    )

    archive_members = [
        title_path,
        description_path,
        tags_path,
        metadata_path,
        checklist_path,
    ]
    _metadata_archive(package_root, archive_path, archive_members)

    checksum_entries = [
        (integrity["final_master_path"], integrity["final_master_sha256"]),
        (integrity["qa_report_path"], integrity["qa_report_sha256"]),
        (integrity["final_receipt_path"], integrity["final_receipt_sha256"]),
        (review_path, _sha256(review_path)),
        *[(path, _sha256(path)) for path in archive_members],
        (archive_path, _sha256(archive_path)),
    ]
    _write_text(
        checksums_path,
        "".join(
            f"{digest}  {_relative(repo, path)}\n"
            for path, digest in checksum_entries
        ),
    )

    manifest = {
        "schema_version": "siraj-manual-publish-package-v1",
        "release": RELEASE,
        "episode_id": episode_id,
        "status": "READY_TO_PUBLISH",
        "manual_youtube_upload": True,
        "automatic_upload": "FORBIDDEN",
        "youtube_api_requests": 0,
        "provider_requests": 0,
        "local_api_cost_usd": 0.0,
        "music": "FORBIDDEN",
        "final_master": {
            "path_relative": _relative(repo, integrity["final_master_path"]),
            "sha256": integrity["final_master_sha256"],
            "bytes": integrity["final_master_bytes"],
        },
        "automatic_qa_report": {
            "path_relative": _relative(repo, integrity["qa_report_path"]),
            "sha256": integrity["qa_report_sha256"],
            "status": "PASS",
        },
        "human_final_review": {
            "path_relative": _relative(repo, review_path),
            "sha256": _sha256(review_path),
            "decision": "APPROVE",
        },
        "metadata": {
            "json_relative": _relative(repo, metadata_path),
            "title_relative": _relative(repo, title_path),
            "description_relative": _relative(repo, description_path),
            "tags_relative": _relative(repo, tags_path),
            "archive_relative": _relative(repo, archive_path),
            "archive_sha256": _sha256(archive_path),
        },
        "checksums_relative": _relative(repo, checksums_path),
        "manual_upload_checklist_relative": _relative(repo, checklist_path),
        "created_at_utc": _now(),
    }
    manifest["manifest_sha256"] = canonical_sha256(manifest)
    _write(manifest_path, manifest)
    return manifest_path


def approve_final_review_and_build_publish_package(
    repo_root: Path,
    *,
    reviewer: str,
    checklist: Mapping[str, Any],
    title: str,
    description: str = "",
    tags: Sequence[str] | str = (),
    notes: str = "",
    visibility_preference: str = "PRIVATE",
) -> FinalReviewResult:
    repo, episode_id, episode_root, state_path, state = _active_episode(repo_root)
    _approval_allowed(state, episode_root)
    reviewer_name = _clean_text(reviewer)
    if not reviewer_name:
        raise FinalReviewError("FINAL_REVIEWER_REQUIRED")
    normalized_checklist = _validate_checklist(checklist)
    clean_title, clean_description, clean_tags = _validate_metadata(
        title,
        description,
        tags,
    )
    visibility = _clean_text(visibility_preference).upper() or "PRIVATE"
    if visibility not in {"PRIVATE", "UNLISTED", "PUBLIC"}:
        raise FinalReviewError("VISIBILITY_PREFERENCE_INVALID")
    integrity = _verify_qa_and_final_integrity(repo, episode_root, state)

    review_path = episode_root / FINAL_REVIEW_REL
    review = {
        "schema_version": "siraj-human-final-review-v1",
        "release": RELEASE,
        "episode_id": episode_id,
        "status": "APPROVED",
        "decision": "APPROVE",
        "reviewer": reviewer_name,
        "checklist": normalized_checklist,
        "notes": _clean_multiline(notes),
        "automatic_qa_report_relative": _relative(repo, integrity["qa_report_path"]),
        "automatic_qa_report_sha256": integrity["qa_report_sha256"],
        "final_master_relative": _relative(repo, integrity["final_master_path"]),
        "final_master_sha256": integrity["final_master_sha256"],
        "manual_youtube_upload": True,
        "automatic_upload": "FORBIDDEN",
        "youtube_api_requests": 0,
        "provider_requests": 0,
        "local_api_cost_usd": 0.0,
        "reviewed_at_utc": _now(),
    }
    review["review_sha256"] = canonical_sha256(review)
    _write(review_path, review)

    manifest_path = _build_publish_package(
        repo,
        episode_id,
        episode_root,
        integrity,
        review_path=review_path,
        title=clean_title,
        description=clean_description,
        tags=clean_tags,
        visibility_preference=visibility,
    )

    state.update(
        {
            "status": "READY_TO_PUBLISH",
            "stage": "READY_TO_PUBLISH",
            "next_stage": "MANUAL_YOUTUBE_UPLOAD",
            "human_final_review_path_relative": _relative(repo, review_path),
            "human_final_review_sha256": _sha256(review_path),
            "publish_package_manifest_path_relative": _relative(repo, manifest_path),
            "publish_package_manifest_sha256": _sha256(manifest_path),
            "manual_youtube_upload": True,
            "automatic_upload": "FORBIDDEN",
            "last_error": None,
            "updated_at_utc": _now(),
        }
    )
    _write(state_path, state)
    _update_stage_ledger(
        repo,
        episode_root,
        decision="APPROVE",
        review_path=review_path,
        publish_manifest_path=manifest_path,
        repair_target_stage=None,
    )
    _update_dependency_graph(
        repo,
        episode_id,
        episode_root,
        review_path=review_path,
        decision="APPROVE",
        publish_manifest_path=manifest_path,
    )
    _write(
        episode_root / RUN_STATE_REL,
        {
            "schema_version": "siraj-final-review-publish-package-state-v1",
            "release": RELEASE,
            "episode_id": episode_id,
            "status": "READY_TO_PUBLISH",
            "decision": "APPROVE",
            "review_path_relative": _relative(repo, review_path),
            "publish_manifest_path_relative": _relative(repo, manifest_path),
            "manual_youtube_upload": True,
            "youtube_api_requests": 0,
            "provider_requests": 0,
            "local_api_cost_usd": 0.0,
            "updated_at_utc": _now(),
        },
    )
    return FinalReviewResult(
        episode_id=episode_id,
        status="READY_TO_PUBLISH",
        decision="APPROVE",
        review_path=review_path,
        publish_manifest_path=manifest_path,
        repair_request_path=None,
        final_master_path=integrity["final_master_path"],
    )


def _repair_target(categories: Sequence[str]) -> tuple[str, bool]:
    selected = set(categories)
    if "AUDIO" in selected:
        return "SFX_DESIGN", True
    if "VISUAL" in selected:
        return "DESKTOP_MEDIA_EXECUTION", True
    if "CONTENT_ACCURACY" in selected:
        return "SCRIPT_WRITING", True
    if selected == {"METADATA"}:
        return "HUMAN_FINAL_REVIEW", False
    return "HUMAN_FINAL_REVIEW", True


def request_final_review_changes(
    repo_root: Path,
    *,
    reviewer: str,
    categories: Sequence[str],
    notes: str,
    shot_ids: Sequence[str] = (),
) -> FinalReviewResult:
    repo, episode_id, episode_root, state_path, state = _active_episode(repo_root)
    status = str(state.get("status", ""))
    if status not in {
        "AWAITING_HUMAN_FINAL_REVIEW",
        "HUMAN_FINAL_REVIEW_CHANGES_REQUESTED",
        "READY_TO_PUBLISH",
    }:
        raise FinalReviewError(f"FINAL_REVIEW_CHANGES_NOT_ALLOWED:{status}")
    reviewer_name = _clean_text(reviewer)
    if not reviewer_name:
        raise FinalReviewError("FINAL_REVIEWER_REQUIRED")
    clean_notes = _clean_multiline(notes)
    if not clean_notes:
        raise FinalReviewError("FINAL_REVIEW_CHANGE_NOTES_REQUIRED")
    normalized_categories = sorted(
        {
            _clean_text(category).upper()
            for category in categories
            if _clean_text(category)
        }
    )
    if not normalized_categories:
        raise FinalReviewError("FINAL_REVIEW_CHANGE_CATEGORY_REQUIRED")
    unknown = sorted(set(normalized_categories) - REVIEW_CATEGORIES)
    if unknown:
        raise FinalReviewError("FINAL_REVIEW_CHANGE_CATEGORY_INVALID:" + ",".join(unknown))
    normalized_shots = sorted(
        {
            _clean_text(shot_id)
            for shot_id in shot_ids
            if _clean_text(shot_id)
        }
    )
    repair_target_stage, requires_qa_rerun = _repair_target(normalized_categories)

    integrity = _verify_qa_and_final_integrity(repo, episode_root, state)
    review_path = episode_root / FINAL_REVIEW_REL
    repair_path = episode_root / REPAIR_REQUEST_REL
    reviewed_at = _now()
    review = {
        "schema_version": "siraj-human-final-review-v1",
        "release": RELEASE,
        "episode_id": episode_id,
        "status": "CHANGES_REQUESTED",
        "decision": "REQUEST_CHANGES",
        "reviewer": reviewer_name,
        "categories": normalized_categories,
        "shot_ids": normalized_shots,
        "notes": clean_notes,
        "automatic_qa_report_relative": _relative(repo, integrity["qa_report_path"]),
        "automatic_qa_report_sha256": integrity["qa_report_sha256"],
        "final_master_relative": _relative(repo, integrity["final_master_path"]),
        "final_master_sha256": integrity["final_master_sha256"],
        "automatic_paid_regeneration": "FORBIDDEN",
        "provider_requests": 0,
        "reviewed_at_utc": reviewed_at,
    }
    review["review_sha256"] = canonical_sha256(review)
    _write(review_path, review)

    repair_request = {
        "schema_version": "siraj-final-review-repair-request-v1",
        "release": RELEASE,
        "episode_id": episode_id,
        "status": "OPEN",
        "categories": normalized_categories,
        "shot_ids": normalized_shots,
        "notes": clean_notes,
        "repair_target_stage": repair_target_stage,
        "requires_qa_rerun": requires_qa_rerun,
        "full_regeneration_for_local_defect": "FORBIDDEN",
        "automatic_paid_regeneration": "FORBIDDEN",
        "provider_requests": 0,
        "created_at_utc": reviewed_at,
    }
    repair_request["repair_request_sha256"] = canonical_sha256(repair_request)
    _write(repair_path, repair_request)

    package_root = episode_root / PUBLISH_PACKAGE_DIR_REL
    if package_root.is_dir():
        shutil.rmtree(package_root)

    state.update(
        {
            "status": "HUMAN_FINAL_REVIEW_CHANGES_REQUESTED",
            "stage": "HUMAN_FINAL_REVIEW",
            "next_stage": repair_target_stage,
            "human_final_review_path_relative": _relative(repo, review_path),
            "human_final_review_sha256": _sha256(review_path),
            "final_review_repair_request_path_relative": _relative(repo, repair_path),
            "final_review_repair_request_sha256": _sha256(repair_path),
            "last_error": "HUMAN_FINAL_REVIEW_CHANGES_REQUESTED",
            "updated_at_utc": _now(),
        }
    )
    state.pop("publish_package_manifest_path_relative", None)
    state.pop("publish_package_manifest_sha256", None)
    _write(state_path, state)
    _update_stage_ledger(
        repo,
        episode_root,
        decision="REQUEST_CHANGES",
        review_path=review_path,
        publish_manifest_path=None,
        repair_target_stage=repair_target_stage,
    )
    _update_dependency_graph(
        repo,
        episode_id,
        episode_root,
        review_path=review_path,
        decision="REQUEST_CHANGES",
        publish_manifest_path=None,
    )
    _write(
        episode_root / RUN_STATE_REL,
        {
            "schema_version": "siraj-final-review-publish-package-state-v1",
            "release": RELEASE,
            "episode_id": episode_id,
            "status": "CHANGES_REQUESTED",
            "decision": "REQUEST_CHANGES",
            "repair_target_stage": repair_target_stage,
            "requires_qa_rerun": requires_qa_rerun,
            "review_path_relative": _relative(repo, review_path),
            "repair_request_path_relative": _relative(repo, repair_path),
            "automatic_paid_regeneration": "FORBIDDEN",
            "provider_requests": 0,
            "local_api_cost_usd": 0.0,
            "updated_at_utc": _now(),
        },
    )
    return FinalReviewResult(
        episode_id=episode_id,
        status="HUMAN_FINAL_REVIEW_CHANGES_REQUESTED",
        decision="REQUEST_CHANGES",
        review_path=review_path,
        publish_manifest_path=None,
        repair_request_path=repair_path,
        final_master_path=integrity["final_master_path"],
    )


def load_final_review_status(repo_root: Path) -> dict[str, Any]:
    try:
        repo, episode_id, episode_root, _, state = _active_episode(repo_root)
    except FinalReviewError as exc:
        return {"status": "NOT_READY", "ready": False, "last_error": str(exc)}
    review_path = episode_root / FINAL_REVIEW_REL
    repair_path = episode_root / REPAIR_REQUEST_REL
    manifest_path = episode_root / PUBLISH_MANIFEST_REL
    final_path = episode_root / FINAL_MASTER_REL
    qa_path = episode_root / QA_REPORT_REL
    status = str(state.get("status", "UNKNOWN"))
    repair_request = _latest_repair_request(episode_root)
    can_approve = status == "AWAITING_HUMAN_FINAL_REVIEW" or (
        status == "HUMAN_FINAL_REVIEW_CHANGES_REQUESTED"
        and isinstance(repair_request, Mapping)
        and not bool(repair_request.get("requires_qa_rerun"))
    )
    return {
        "episode_id": episode_id,
        "status": status,
        "stage": str(state.get("stage", "")),
        "next_stage": str(state.get("next_stage", "")),
        "last_error": state.get("last_error"),
        "ready": status in {
            "AWAITING_HUMAN_FINAL_REVIEW",
            "HUMAN_FINAL_REVIEW_CHANGES_REQUESTED",
            "READY_TO_PUBLISH",
        },
        "can_approve": can_approve,
        "ready_to_publish": status == "READY_TO_PUBLISH" and manifest_path.is_file(),
        "review_path": str(review_path),
        "repair_request_path": str(repair_path),
        "publish_manifest_path": str(manifest_path),
        "publish_package_dir": str(episode_root / PUBLISH_PACKAGE_DIR_REL),
        "final_master_path": str(final_path),
        "qa_report_path": str(qa_path),
        "manual_youtube_upload": True,
        "automatic_upload": "FORBIDDEN",
        "youtube_api_requests": 0,
        "provider_requests": 0,
        "repo_root": str(repo),
    }


def run_final_review_smoke_test(
    output_root: Path,
) -> dict[str, Any]:
    root = output_root.resolve() / "final-review-smoke-repo"
    episode_id = "episode-999-smoke"
    episode_root = root / "projects" / episode_id
    (root / ORCHESTRATOR_STATE_REL).parent.mkdir(parents=True, exist_ok=True)
    (episode_root / FINAL_MASTER_REL).parent.mkdir(parents=True, exist_ok=True)
    (episode_root / QA_REPORT_REL).parent.mkdir(parents=True, exist_ok=True)
    (episode_root / STAGE_LEDGER_REL).parent.mkdir(parents=True, exist_ok=True)
    (episode_root / EPISODE_DEFINITION_REL).parent.mkdir(parents=True, exist_ok=True)
    final_path = episode_root / FINAL_MASTER_REL
    final_path.write_bytes(b"siraj-final-review-smoke-video")
    final_sha = _sha256(final_path)
    _write(
        episode_root / FINAL_RECEIPT_REL,
        {
            "status": "COMPLETE_READY_FOR_AUTOMATIC_QA",
            "final_master_sha256": final_sha,
        },
    )
    qa_path = episode_root / QA_REPORT_REL
    _write(
        qa_path,
        {
            "schema_version": "siraj-automatic-qa-report-v1",
            "status": "PASS",
            "paid_provider_requests": 0,
        },
    )
    _write(
        root / ORCHESTRATOR_STATE_REL,
        {
            "current_episode_id": episode_id,
            "status": "AWAITING_HUMAN_FINAL_REVIEW",
            "stage": "HUMAN_FINAL_REVIEW",
            "automatic_qa_report_sha256": _sha256(qa_path),
        },
    )
    _write(
        episode_root / STAGE_LEDGER_REL,
        {
            "stages": [
                {"stage": "HUMAN_FINAL_REVIEW", "status": "AWAITING_HUMAN"},
                {"stage": "READY_TO_PUBLISH", "status": "QUEUED"},
            ]
        },
    )
    _write(
        episode_root / DEPENDENCY_GRAPH_REL,
        {
            "nodes": [
                {"node_id": f"{episode_id}:FINAL_RENDER"},
                {"node_id": f"{episode_id}:AUTOMATIC_QA_REPORT"},
            ],
            "edges": [],
        },
    )
    _write(
        episode_root / EPISODE_DEFINITION_REL,
        {
            "episode_id": episode_id,
            "working_title_ar": "حلقة اختبار سراج",
        },
    )
    checklist = {key: True for key in REQUIRED_CHECKLIST_KEYS}
    result = approve_final_review_and_build_publish_package(
        root,
        reviewer="SMOKE_REVIEWER",
        checklist=checklist,
        title="حلقة اختبار سراج",
        description="اختبار محلي لحزمة النشر.",
        tags=["سراج", "اختبار"],
    )
    manifest = _read(result.publish_manifest_path) if result.publish_manifest_path else {}
    return {
        "status": "PASS" if result.status == "READY_TO_PUBLISH" else "FAIL",
        "decision": result.decision,
        "manifest_status": manifest.get("status"),
        "manual_youtube_upload": manifest.get("manual_youtube_upload"),
        "youtube_api_requests": manifest.get("youtube_api_requests"),
        "provider_requests": manifest.get("provider_requests"),
        "publish_manifest_sha256": (
            _sha256(result.publish_manifest_path)
            if result.publish_manifest_path is not None
            else None
        ),
    }
