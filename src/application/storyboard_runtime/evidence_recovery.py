"""Recover existing local evidence work into a deterministic, non-approving contract.

This module inventories normalized source assets and review artifacts already present
under an episode project. It records only metadata, identifiers, counts, and hashes.
It never copies source text, never approves evidence, and never opens the evidence gate.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, asdict
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any, Iterable, Mapping


RECOVERED_EVIDENCE_KNOWLEDGE_SCHEMA_VERSION = (
    "siraj-recovered-evidence-knowledge-v1"
)
RECOVERY_STATUS = "RECOVERED_REVIEW_PENDING"
EVIDENCE_GATE_STATUS = "WITHHELD_PENDING_APPROVED_EVIDENCE_PACKAGE"
AUTOMATIC_APPROVAL_STATUS = "FORBIDDEN"
LIVE_EXECUTION_STATUS = "BLOCKED"

SOURCE_ID_RE = re.compile(r"^SRC-[A-Z0-9][A-Z0-9-]*$")
EVENT_ID_RE = re.compile(r"^EV-[A-Z0-9][A-Z0-9-]*$")
REPORT_ID_RE = re.compile(r"^(?:RP|REPORT|REP)-[A-Z0-9][A-Z0-9-]*$")
SECRET_KEY_RE = re.compile(
    r"(?:api[_-]?key|token|secret|password|credential|authorization)",
    re.IGNORECASE,
)
ABSOLUTE_WINDOWS_RE = re.compile(r"^[A-Za-z]:[\\/]")
CONTENT_FIELD_NAMES = frozenset(
    {
        "text",
        "content",
        "body",
        "raw_text",
        "page_text",
        "normalized_text",
        "quoted_text",
        "transcript",
    }
)
MAX_STRUCTURED_FILE_BYTES = 16 * 1024 * 1024


class EvidenceRecoveryError(ValueError):
    """Raised when local evidence recovery cannot be completed safely."""


@dataclass(frozen=True, slots=True)
class StructuredFileSummary:
    relative_path: str
    sha256: str
    size_bytes: int
    format: str
    record_count: int
    schema_versions: tuple[str, ...]
    source_ids: tuple[str, ...]
    event_ids: tuple[str, ...]
    report_ids: tuple[str, ...]
    statuses: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RecoveredSourceSummary:
    source_id: str
    manifest: StructuredFileSummary | None
    pages: StructuredFileSummary | None
    toc: StructuredFileSummary | None
    total_records: int
    candidate_event_ids: tuple[str, ...]
    recovery_state: str


@dataclass(frozen=True, slots=True)
class ReviewArtifactSummary:
    artifact: StructuredFileSummary
    review_stage: str


@dataclass(frozen=True, slots=True)
class RecoveredEvidenceKnowledge:
    recovery_id: str
    episode_id: str
    source_package_status: str
    normalized_sources: tuple[RecoveredSourceSummary, ...]
    review_artifacts: tuple[ReviewArtifactSummary, ...]
    normalized_source_count: int
    review_artifact_count: int
    candidate_event_links: tuple[tuple[str, tuple[str, ...]], ...]
    uncovered_event_ids: tuple[str, ...]
    unknown_event_ids: tuple[str, ...]
    unknown_source_ids: tuple[str, ...]
    gaps: tuple[str, ...]
    input_fingerprints: tuple[tuple[str, str], ...]
    schema_version: str = RECOVERED_EVIDENCE_KNOWLEDGE_SCHEMA_VERSION
    recovery_status: str = RECOVERY_STATUS
    evidence_gate_status: str = EVIDENCE_GATE_STATUS
    automatic_evidence_approval: str = AUTOMATIC_APPROVAL_STATUS
    live_provider_execution: str = LIVE_EXECUTION_STATUS

    def to_manifest(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "recovery_id": self.recovery_id,
            "episode_id": self.episode_id,
            "recovery_status": self.recovery_status,
            "source_package_status": self.source_package_status,
            "evidence_gate_status": self.evidence_gate_status,
            "automatic_evidence_approval": self.automatic_evidence_approval,
            "live_provider_execution": self.live_provider_execution,
            "normalized_source_count": self.normalized_source_count,
            "review_artifact_count": self.review_artifact_count,
            "normalized_sources": [
                {
                    "source_id": item.source_id,
                    "manifest": _summary_or_none(item.manifest),
                    "pages": _summary_or_none(item.pages),
                    "toc": _summary_or_none(item.toc),
                    "total_records": item.total_records,
                    "candidate_event_ids": list(item.candidate_event_ids),
                    "recovery_state": item.recovery_state,
                }
                for item in self.normalized_sources
            ],
            "review_artifacts": [
                {
                    "review_stage": item.review_stage,
                    "artifact": asdict(item.artifact),
                }
                for item in self.review_artifacts
            ],
            "candidate_event_links": {
                source_id: list(event_ids)
                for source_id, event_ids in self.candidate_event_links
            },
            "uncovered_event_ids": list(self.uncovered_event_ids),
            "unknown_event_ids": list(self.unknown_event_ids),
            "unknown_source_ids": list(self.unknown_source_ids),
            "gaps": list(self.gaps),
            "input_fingerprints": dict(self.input_fingerprints),
        }

    def to_json(self, *, pretty: bool = True) -> str:
        return json.dumps(
            self.to_manifest(),
            ensure_ascii=False,
            sort_keys=True,
            indent=2 if pretty else None,
            separators=None if pretty else (",", ":"),
        ) + ("\n" if pretty else "")


class AdamEvidenceKnowledgeRecovery:
    """Recover existing local Adam evidence metadata without approving it."""

    REVIEW_ROOT_NAMES = (
        "bounded-review-windows",
        "final-window-review",
        "human-window-review",
        "report-boundary-isnad-review",
        "report-level-extraction",
        "report-resegmentation-chain-normalization",
        "topic-prefilter",
        "gemini-semantic-analysis-draft",
        "diagnostics",
    )

    def build(self, repo_root: Path) -> RecoveredEvidenceKnowledge:
        repo_root = Path(repo_root).resolve()
        if not (repo_root / ".git").exists():
            raise EvidenceRecoveryError(f"Missing Git repository: {repo_root}")

        episode_root = repo_root / "projects" / "episode-001-adam"
        source_package_path = (
            episode_root / "contracts" / "source-package-v1.draft.json"
        )
        event_map_path = episode_root / "editorial" / "event-map.json"
        normalized_root = (
            episode_root / "sources" / "secondary" / "assets" / "normalized"
        )
        secondary_root = episode_root / "sources" / "secondary"
        repair_root = repo_root / "working" / "adam-truncated-window-repair-v1"

        source_package = _load_json_object(source_package_path)
        event_map = _load_json_array(event_map_path)
        source_package_status = str(
            source_package.get("package_status", "UNKNOWN")
        )
        required_event_ids = tuple(
            str(item.get("event_id"))
            for item in event_map
            if isinstance(item, Mapping) and isinstance(item.get("event_id"), str)
        )
        if not required_event_ids:
            raise EvidenceRecoveryError("Event map contains no event ids.")
        if len(set(required_event_ids)) != len(required_event_ids):
            raise EvidenceRecoveryError("Event map contains duplicate event ids.")

        candidate_links = _source_package_candidate_links(source_package)
        normalized_sources = self._recover_normalized_sources(
            repo_root,
            normalized_root,
            candidate_links,
        )
        review_artifacts = self._recover_review_artifacts(
            repo_root,
            secondary_root,
            repair_root,
        )

        discovered_source_ids = {
            item.source_id for item in normalized_sources
        }
        for item in review_artifacts:
            discovered_source_ids.update(item.artifact.source_ids)

        package_source_ids = set(candidate_links)
        unknown_source_ids = tuple(sorted(discovered_source_ids - package_source_ids))

        merged_links: dict[str, set[str]] = {
            source_id: set(event_ids)
            for source_id, event_ids in candidate_links.items()
        }
        for source in normalized_sources:
            merged_links.setdefault(source.source_id, set()).update(
                source.candidate_event_ids
            )
        for review in review_artifacts:
            for source_id in review.artifact.source_ids:
                merged_links.setdefault(source_id, set()).update(
                    review.artifact.event_ids
                )

        known_events = set(required_event_ids)
        unknown_event_ids = tuple(
            sorted(
                {
                    event_id
                    for event_ids in merged_links.values()
                    for event_id in event_ids
                    if event_id not in known_events
                }
            )
        )
        covered_events = {
            event_id
            for event_ids in merged_links.values()
            for event_id in event_ids
            if event_id in known_events
        }
        uncovered_event_ids = tuple(
            event_id
            for event_id in required_event_ids
            if event_id not in covered_events
        )

        gaps = self._build_gaps(
            source_package,
            normalized_sources,
            review_artifacts,
            uncovered_event_ids,
            unknown_event_ids,
            unknown_source_ids,
        )

        fingerprints = (
            (
                _relative_to_repo(source_package_path, repo_root),
                _sha256_file(source_package_path),
            ),
            (
                _relative_to_repo(event_map_path, repo_root),
                _sha256_file(event_map_path),
            ),
        )
        normalized_source_count = len(normalized_sources)
        review_artifact_count = len(review_artifacts)
        if normalized_source_count < 9:
            raise EvidenceRecoveryError(
                "Expected at least nine normalized source directories from the "
                f"inspected local state; found {normalized_source_count}."
            )
        if review_artifact_count < 46:
            raise EvidenceRecoveryError(
                "Expected at least 46 review artifacts from the inspected local "
                f"state; found {review_artifact_count}."
            )

        canonical_links = tuple(
            (source_id, tuple(sorted(event_ids)))
            for source_id, event_ids in sorted(merged_links.items())
        )
        recovery_id = _deterministic_id(
            "recovered_evidence_knowledge",
            [
                "episode-001-adam",
                source_package_status,
                [asdict(item) for item in normalized_sources],
                [
                    {
                        "review_stage": item.review_stage,
                        "artifact": asdict(item.artifact),
                    }
                    for item in review_artifacts
                ],
                canonical_links,
                uncovered_event_ids,
                unknown_event_ids,
                unknown_source_ids,
                gaps,
                fingerprints,
            ],
        )

        recovered = RecoveredEvidenceKnowledge(
            recovery_id=recovery_id,
            episode_id="episode-001-adam",
            source_package_status=source_package_status,
            normalized_sources=normalized_sources,
            review_artifacts=review_artifacts,
            normalized_source_count=normalized_source_count,
            review_artifact_count=review_artifact_count,
            candidate_event_links=canonical_links,
            uncovered_event_ids=uncovered_event_ids,
            unknown_event_ids=unknown_event_ids,
            unknown_source_ids=unknown_source_ids,
            gaps=gaps,
            input_fingerprints=tuple(sorted(fingerprints)),
        )
        _validate_manifest_safety(recovered.to_manifest())
        return recovered

    def _recover_normalized_sources(
        self,
        repo_root: Path,
        normalized_root: Path,
        candidate_links: Mapping[str, tuple[str, ...]],
    ) -> tuple[RecoveredSourceSummary, ...]:
        if not normalized_root.is_dir():
            raise EvidenceRecoveryError(
                f"Normalized source root is missing: {normalized_root}"
            )

        recovered: list[RecoveredSourceSummary] = []
        for directory in sorted(normalized_root.iterdir(), key=lambda item: item.name):
            if directory.is_symlink():
                raise EvidenceRecoveryError(
                    f"Symlinked source directory is forbidden: {directory}"
                )
            if not directory.is_dir() or not SOURCE_ID_RE.fullmatch(directory.name):
                continue
            source_id = directory.name
            manifest = _summarize_optional_structured_file(
                directory / "manifest.json",
                repo_root,
            )
            pages = _summarize_optional_structured_file(
                directory / "pages.jsonl",
                repo_root,
            )
            toc = _summarize_optional_structured_file(
                directory / "toc.jsonl",
                repo_root,
            )
            total_records = sum(
                item.record_count for item in (manifest, pages, toc) if item is not None
            )
            state = "COMPLETE_NORMALIZED_ASSET"
            if manifest is None or pages is None:
                state = "PARTIAL_NORMALIZED_ASSET"
            recovered.append(
                RecoveredSourceSummary(
                    source_id=source_id,
                    manifest=manifest,
                    pages=pages,
                    toc=toc,
                    total_records=total_records,
                    candidate_event_ids=tuple(
                        sorted(candidate_links.get(source_id, ()))
                    ),
                    recovery_state=state,
                )
            )
        return tuple(recovered)

    def _recover_review_artifacts(
        self,
        repo_root: Path,
        secondary_root: Path,
        repair_root: Path,
    ) -> tuple[ReviewArtifactSummary, ...]:
        roots: list[tuple[str, Path]] = [
            (name, secondary_root / name) for name in self.REVIEW_ROOT_NAMES
        ]
        roots.append(("adam-truncated-window-repair-v1", repair_root))

        artifacts: list[ReviewArtifactSummary] = []
        for stage, root in roots:
            if not root.is_dir():
                continue
            for path in _iter_review_files(root):
                artifacts.append(
                    ReviewArtifactSummary(
                        artifact=_summarize_review_file(path, repo_root),
                        review_stage=stage,
                    )
                )
        artifacts.sort(
            key=lambda item: (
                item.review_stage,
                item.artifact.relative_path,
            )
        )
        return tuple(artifacts)

    @staticmethod
    def _build_gaps(
        source_package: Mapping[str, object],
        normalized_sources: tuple[RecoveredSourceSummary, ...],
        review_artifacts: tuple[ReviewArtifactSummary, ...],
        uncovered_event_ids: tuple[str, ...],
        unknown_event_ids: tuple[str, ...],
        unknown_source_ids: tuple[str, ...],
    ) -> tuple[str, ...]:
        gaps: list[str] = []
        if source_package.get("package_status") != "APPROVED":
            gaps.append("SOURCE_PACKAGE_NOT_HUMAN_APPROVED")

        source_items = source_package.get("source_items")
        if isinstance(source_items, list):
            if not any(
                isinstance(item, Mapping)
                and bool(str(item.get("checksum", "")).strip())
                for item in source_items
            ):
                gaps.append("TRACKED_SOURCE_PACKAGE_CHECKSUMS_MISSING")
            if not any(
                isinstance(item, Mapping)
                and bool(str(item.get("path", "")).strip())
                for item in source_items
            ):
                gaps.append("TRACKED_SOURCE_PACKAGE_PATHS_MISSING")
            if not any(
                isinstance(item, Mapping)
                and item.get("allowed_for_extraction") is True
                for item in source_items
            ):
                gaps.append("TRACKED_SOURCE_PACKAGE_EXTRACTION_NOT_ALLOWED")

        if any(
            item.recovery_state != "COMPLETE_NORMALIZED_ASSET"
            for item in normalized_sources
        ):
            gaps.append("PARTIAL_NORMALIZED_SOURCE_ASSETS_PRESENT")
        if not review_artifacts:
            gaps.append("NO_REVIEW_ARTIFACTS_RECOVERED")
        else:
            gaps.append("HUMAN_ADJUDICATION_NOT_YET_BOUND")
        if uncovered_event_ids:
            gaps.append("EVENTS_WITHOUT_CANDIDATE_SOURCE_LINKS")
        if unknown_event_ids:
            gaps.append("REVIEW_ARTIFACTS_REFERENCE_OUT_OF_SCOPE_EVENTS")
        if unknown_source_ids:
            gaps.append("REVIEW_ARTIFACTS_REFERENCE_UNREGISTERED_SOURCES")
        gaps.append("RECOVERED_METADATA_IS_NOT_APPROVED_EVIDENCE")
        return tuple(sorted(set(gaps)))


def write_recovered_evidence_knowledge(
    recovered: RecoveredEvidenceKnowledge,
    path: Path,
) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = recovered.to_json(pretty=True).replace("\r\n", "\n").replace("\r", "\n")
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def validate_recovered_manifest(payload: Mapping[str, object]) -> None:
    if payload.get("schema_version") != RECOVERED_EVIDENCE_KNOWLEDGE_SCHEMA_VERSION:
        raise EvidenceRecoveryError("Unexpected recovered evidence schema.")
    if payload.get("episode_id") != "episode-001-adam":
        raise EvidenceRecoveryError("Recovered manifest references another episode.")
    if payload.get("recovery_status") != RECOVERY_STATUS:
        raise EvidenceRecoveryError("Recovered manifest status changed unexpectedly.")
    if payload.get("evidence_gate_status") != EVIDENCE_GATE_STATUS:
        raise EvidenceRecoveryError("Recovered manifest opened the evidence gate.")
    if payload.get("automatic_evidence_approval") != AUTOMATIC_APPROVAL_STATUS:
        raise EvidenceRecoveryError("Recovered manifest enabled automatic approval.")
    if payload.get("live_provider_execution") != LIVE_EXECUTION_STATUS:
        raise EvidenceRecoveryError("Recovered manifest enabled live execution.")
    if int(payload.get("normalized_source_count", 0)) < 9:
        raise EvidenceRecoveryError("Recovered manifest has fewer than nine sources.")
    if int(payload.get("review_artifact_count", 0)) < 46:
        raise EvidenceRecoveryError("Recovered manifest has fewer than 46 review files.")
    _validate_manifest_safety(payload)


def _summary_or_none(
    value: StructuredFileSummary | None,
) -> dict[str, object] | None:
    return None if value is None else asdict(value)


def _source_package_candidate_links(
    source_package: Mapping[str, object],
) -> dict[str, tuple[str, ...]]:
    items = source_package.get("source_items")
    if not isinstance(items, list):
        raise EvidenceRecoveryError("Source package source_items must be a list.")

    links: dict[str, tuple[str, ...]] = {}
    for item in items:
        if not isinstance(item, Mapping):
            continue
        source_id = item.get("source_id")
        if not isinstance(source_id, str) or not SOURCE_ID_RE.fullmatch(source_id):
            continue
        notes = item.get("notes")
        event_ids: list[str] = []
        if isinstance(notes, Mapping):
            raw = notes.get("supports_event_ids")
            if isinstance(raw, list):
                event_ids = [
                    value
                    for value in raw
                    if isinstance(value, str) and EVENT_ID_RE.fullmatch(value)
                ]
        links[source_id] = tuple(sorted(set(event_ids)))
    return links


def _summarize_review_file(
    path: Path,
    repo_root: Path,
) -> StructuredFileSummary:
    if path.suffix.lower() in {".json", ".jsonl"}:
        return _summarize_structured_file(path, repo_root)
    if path.is_symlink():
        raise EvidenceRecoveryError(f"Symlinked evidence file is forbidden: {path}")
    if not path.is_file():
        raise EvidenceRecoveryError(f"Evidence file is missing: {path}")

    relative = _relative_to_repo(path, repo_root)
    source_ids = tuple(sorted(set(re.findall(r"SRC-[A-Z0-9][A-Z0-9-]*", relative))))
    event_ids = tuple(sorted(set(re.findall(r"EV-[A-Z0-9][A-Z0-9-]*", relative))))
    report_ids = tuple(
        sorted(
            set(
                re.findall(
                    r"(?:RP|REPORT|REP)-[A-Z0-9][A-Z0-9-]*",
                    relative,
                )
            )
        )
    )
    return StructuredFileSummary(
        relative_path=relative,
        sha256=_sha256_file(path),
        size_bytes=path.stat().st_size,
        format=path.suffix.lower().lstrip(".") or "opaque",
        record_count=0,
        schema_versions=(),
        source_ids=source_ids,
        event_ids=event_ids,
        report_ids=report_ids,
        statuses=(),
    )


def _summarize_optional_structured_file(
    path: Path,
    repo_root: Path,
) -> StructuredFileSummary | None:
    if not path.is_file():
        return None
    return _summarize_structured_file(path, repo_root)


def _summarize_structured_file(
    path: Path,
    repo_root: Path,
) -> StructuredFileSummary:
    if path.is_symlink():
        raise EvidenceRecoveryError(f"Symlinked evidence file is forbidden: {path}")
    if not path.is_file():
        raise EvidenceRecoveryError(f"Evidence file is missing: {path}")
    size = path.stat().st_size
    if size > MAX_STRUCTURED_FILE_BYTES:
        # Large files are streamed and summarized without retaining raw records.
        pass

    suffix = path.suffix.lower()
    if suffix not in {".json", ".jsonl"}:
        raise EvidenceRecoveryError(f"Unsupported structured file: {path}")

    record_count = 0
    if suffix == ".json":
        if size > MAX_STRUCTURED_FILE_BYTES:
            raise EvidenceRecoveryError(
                f"Structured JSON exceeds safe parse limit: {path}"
            )
        payload = _load_json(path)
        record_count = len(payload) if isinstance(payload, list) else 1
        identifiers = _extract_identifiers((payload,))
    else:
        identifiers = {
            "schema_versions": set(),
            "source_ids": set(),
            "event_ids": set(),
            "report_ids": set(),
            "statuses": set(),
        }
        for item in _iter_jsonl(path):
            record_count += 1
            extracted = _extract_identifiers((item,))
            for key, values in extracted.items():
                identifiers[key].update(values)
    return StructuredFileSummary(
        relative_path=_relative_to_repo(path, repo_root),
        sha256=_sha256_file(path),
        size_bytes=size,
        format=suffix.lstrip("."),
        record_count=record_count,
        schema_versions=tuple(sorted(identifiers["schema_versions"])),
        source_ids=tuple(sorted(identifiers["source_ids"])),
        event_ids=tuple(sorted(identifiers["event_ids"])),
        report_ids=tuple(sorted(identifiers["report_ids"])),
        statuses=tuple(sorted(identifiers["statuses"])),
    )


def _extract_identifiers(records: Iterable[object]) -> dict[str, set[str]]:
    result = {
        "schema_versions": set(),
        "source_ids": set(),
        "event_ids": set(),
        "report_ids": set(),
        "statuses": set(),
    }

    def visit(value: object, key: str | None = None) -> None:
        if isinstance(value, Mapping):
            for child_key, child_value in value.items():
                key_text = str(child_key)
                if SECRET_KEY_RE.search(key_text):
                    # Secret-bearing fields are ignored entirely and never copied.
                    continue
                if key_text.lower() in CONTENT_FIELD_NAMES:
                    # Raw source/review text is not inspected or copied.
                    continue
                visit(child_value, key_text)
            return
        if isinstance(value, list):
            for child in value:
                visit(child, key)
            return
        if not isinstance(value, str):
            return

        if ABSOLUTE_WINDOWS_RE.match(value) or value.startswith("/home/"):
            # Do not preserve absolute paths in output; they are merely ignored.
            return
        if key == "schema_version" and value.strip():
            result["schema_versions"].add(value.strip())
        if SOURCE_ID_RE.fullmatch(value):
            result["source_ids"].add(value)
        if EVENT_ID_RE.fullmatch(value):
            result["event_ids"].add(value)
        if REPORT_ID_RE.fullmatch(value):
            result["report_ids"].add(value)
        if key and "status" in key.lower() and 0 < len(value) <= 120:
            result["statuses"].add(value)

    for record in records:
        visit(record)
    return result


def _iter_review_files(root: Path):
    for current, directories, files in os.walk(root, followlinks=False):
        current_path = Path(current)
        directories[:] = sorted(
            name
            for name in directories
            if not (current_path / name).is_symlink()
            and name not in {"__pycache__", ".pytest_cache"}
        )
        for name in sorted(files):
            path = current_path / name
            if path.is_symlink():
                raise EvidenceRecoveryError(
                    f"Symlinked review artifact is forbidden: {path}"
                )
            if path.suffix.lower() not in {".pyc", ".pyo"}:
                yield path


def _iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8-sig") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as error:
                raise EvidenceRecoveryError(
                    f"Invalid JSONL at {path}:{line_number}: {error}"
                ) from error


def _load_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise EvidenceRecoveryError(f"Invalid JSON file {path}: {error}") from error


def _load_json_object(path: Path) -> dict[str, object]:
    payload = _load_json(path)
    if not isinstance(payload, dict):
        raise EvidenceRecoveryError(f"Expected JSON object: {path}")
    return payload


def _load_json_array(path: Path) -> list[object]:
    payload = _load_json(path)
    if not isinstance(payload, list):
        raise EvidenceRecoveryError(f"Expected JSON array: {path}")
    return payload


def _relative_to_repo(path: Path, repo_root: Path) -> str:
    resolved_root = repo_root.resolve()
    resolved_path = path.resolve()
    try:
        relative = resolved_path.relative_to(resolved_root)
    except ValueError as error:
        raise EvidenceRecoveryError(
            f"Evidence path escaped repository root: {path}"
        ) from error
    return relative.as_posix()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _deterministic_id(namespace: str, payload: object) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return f"{namespace}_{hashlib.sha256(canonical).hexdigest()[:16]}"


def _validate_manifest_safety(payload: object) -> None:
    def visit(value: object, key: str | None = None) -> None:
        if isinstance(value, Mapping):
            for child_key, child_value in value.items():
                key_text = str(child_key)
                if SECRET_KEY_RE.search(key_text):
                    raise EvidenceRecoveryError(
                        f"Secret-like key leaked into recovered manifest: {key_text}"
                    )
                visit(child_value, key_text)
            return
        if isinstance(value, list):
            for child in value:
                visit(child, key)
            return
        if isinstance(value, str):
            if ABSOLUTE_WINDOWS_RE.match(value) or value.startswith("/home/"):
                raise EvidenceRecoveryError(
                    f"Absolute local path leaked into recovered manifest: {value}"
                )
            lowered = value.lower()
            if any(
                marker in lowered
                for marker in (
                    "api_key=",
                    "authorization:",
                    "bearer ",
                    "password=",
                    "secret=",
                )
            ):
                raise EvidenceRecoveryError(
                    "Credential-like value leaked into recovered manifest."
                )

    visit(payload)
