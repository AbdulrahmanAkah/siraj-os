"""Deterministic, non-media, local file export adapter."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import hashlib
import os
import tempfile
from typing import Any

from src.application.operations_common import canonical_payload, deterministic_id
from src.application.security import SecurityPolicyEngine

from .security import SecurityBoundaryError, contained_relative_path, redact_sensitive


@dataclass(frozen=True)
class ExportPathPolicy:
    output_root: str
    maximum_file_size: int = 5_000_000


@dataclass(frozen=True)
class ExportOverwritePolicy:
    mode: str = "DENY"  # DENY or REPLACE


@dataclass(frozen=True)
class ExportArtifactResult:
    artifact_id: str
    relative_path: str
    size_bytes: int
    sha256: str
    completed: bool = True


@dataclass(frozen=True)
class ExportFailure:
    code: str
    relative_path: str
    detail: str = ""


@dataclass(frozen=True)
class ExportIntegrityReport:
    report_id: str
    artifacts: list[ExportArtifactResult] = field(default_factory=list)
    failures: list[ExportFailure] = field(default_factory=list)
    status: str = "VALID"


class FileExportAdapter:
    """Writes UTF-8 files atomically and only below an explicit output root."""

    def __init__(self, path_policy: ExportPathPolicy, overwrite: ExportOverwritePolicy | None = None, policy: SecurityPolicyEngine | None = None):
        self.path_policy = path_policy
        self.overwrite = overwrite or ExportOverwritePolicy()
        self.policy = policy or SecurityPolicyEngine()

    def _write(self, relative_path: str, content: str, classification: str = "INTERNAL") -> ExportArtifactResult | ExportFailure:
        if self.policy.decide("WRITE", classification).decision != "ALLOW":
            return ExportFailure("FILESYSTEM_WRITE_DENIED", relative_path)
        try:
            target = contained_relative_path(self.path_policy.output_root, relative_path)
        except SecurityBoundaryError as error:
            return ExportFailure(str(error), relative_path)
        data = content.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
        if len(data) > self.path_policy.maximum_file_size:
            return ExportFailure("EXPORT_TOO_LARGE", relative_path)
        if target.exists() and self.overwrite.mode != "REPLACE":
            return ExportFailure("OVERWRITE_DENIED", relative_path)
        temporary: str | None = None
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            handle = tempfile.NamedTemporaryFile(mode="wb", dir=target.parent, prefix=".siraj-", suffix=".tmp", delete=False)
            temporary = handle.name
            with handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
            digest = hashlib.sha256(data).hexdigest()
            return ExportArtifactResult(deterministic_id("export_artifact", [relative_path, digest]), Path(relative_path).as_posix(), len(data), digest)
        except OSError:
            return ExportFailure("ATOMIC_WRITE_FAILED", relative_path)
        finally:
            if temporary and Path(temporary).exists():
                Path(temporary).unlink(missing_ok=True)

    def export_json(self, relative_path: str, payload: Any, classification: str = "INTERNAL") -> ExportArtifactResult | ExportFailure:
        return self._write(relative_path, canonical_payload(redact_sensitive(payload)) + "\n", classification)

    def export_markdown(self, relative_path: str, markdown: str, classification: str = "INTERNAL") -> ExportArtifactResult | ExportFailure:
        return self._write(relative_path, markdown, classification)

    def export_credits(self, credits: list[dict[str, str]]) -> ExportArtifactResult | ExportFailure:
        lines = ["# Credits", ""]
        lines.extend(f"- {item.get('role', '')}: {item.get('name', '')}" for item in sorted(credits, key=lambda item: (item.get("role", ""), item.get("name", ""))))
        return self.export_markdown("credits.md", "\n".join(lines) + "\n")

    def export_source_appendix(self, sources: list[dict[str, str]]) -> ExportArtifactResult | ExportFailure:
        lines = ["# Source Appendix", ""]
        lines.extend(f"- {item.get('source_id', '')}: {item.get('title', '')}" for item in sorted(sources, key=lambda item: (item.get("source_id", ""), item.get("title", ""))))
        return self.export_markdown("source-appendix.md", "\n".join(lines) + "\n")

    @staticmethod
    def _timecode(milliseconds: int, separator: str) -> str:
        if milliseconds < 0:
            raise ValueError("NEGATIVE_TIMECODE")
        hours, remainder = divmod(milliseconds, 3_600_000)
        minutes, remainder = divmod(remainder, 60_000)
        seconds, millis = divmod(remainder, 1_000)
        return f"{hours:02}:{minutes:02}:{seconds:02}{separator}{millis:03}"

    def export_srt(self, cues: list[dict[str, Any]]) -> ExportArtifactResult | ExportFailure:
        ordered = sorted(cues, key=lambda cue: (cue["start_ms"], cue.get("position", 0), cue.get("cue_id", "")))
        try:
            lines: list[str] = []
            for index, cue in enumerate(ordered, 1):
                if cue["end_ms"] <= cue["start_ms"]:
                    raise ValueError("INVALID_SUBTITLE_RANGE")
                lines.extend([str(index), f"{self._timecode(cue['start_ms'], ',')} --> {self._timecode(cue['end_ms'], ',')}", str(cue["text"]), ""])
            return self._write("subtitles.srt", "\n".join(lines))
        except (KeyError, ValueError) as error:
            return ExportFailure(str(error), "subtitles.srt")

    def export_webvtt(self, cues: list[dict[str, Any]]) -> ExportArtifactResult | ExportFailure:
        ordered = sorted(cues, key=lambda cue: (cue["start_ms"], cue.get("position", 0), cue.get("cue_id", "")))
        try:
            lines = ["WEBVTT", ""]
            for cue in ordered:
                if cue["end_ms"] <= cue["start_ms"]:
                    raise ValueError("INVALID_SUBTITLE_RANGE")
                lines.extend([f"{self._timecode(cue['start_ms'], '.')} --> {self._timecode(cue['end_ms'], '.')}", str(cue["text"]), ""])
            return self._write("subtitles.vtt", "\n".join(lines))
        except (KeyError, ValueError) as error:
            return ExportFailure(str(error), "subtitles.vtt")

    def build_manifest(self, artifacts: list[ExportArtifactResult | ExportFailure], limitations: list[dict[str, str]] | None = None) -> ExportIntegrityReport:
        completed = sorted((item for item in artifacts if isinstance(item, ExportArtifactResult)), key=lambda item: item.relative_path)
        failures = sorted((item for item in artifacts if isinstance(item, ExportFailure)), key=lambda item: (item.relative_path, item.code))
        manifest = {"artifacts": [item.__dict__ for item in completed], "limitations": sorted(limitations or [], key=canonical_payload)}
        result = self.export_json("export-manifest.json", manifest)
        if isinstance(result, ExportArtifactResult):
            completed.append(result)
        else:
            failures.append(result)
        status = "VALID" if not failures else "INVALID"
        return ExportIntegrityReport(deterministic_id("export_integrity", [[item.artifact_id for item in completed], [item.code for item in failures]]), completed, failures, status)
