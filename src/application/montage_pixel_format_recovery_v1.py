from __future__ import annotations

import json
import os
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from src.application.structural_montage_final_render_v1 import (
    PIXEL_FORMAT,
    StructuralMontageError,
    _video_pixel_format,
    inspect_montage_environment,
)

RELEASE = "SIRAJ_MONTAGE_PIXEL_FORMAT_NORMALIZATION_AND_RECOVERY_V1"
ORCHESTRATOR_STATE_REL = Path(
    "projects/_orchestrator/autonomous-episode-orchestrator-state-v1.json"
)
RUN_STATE_REL = Path("orchestration/structural-montage-render-state-v1.json")
RUN_LOCK_REL = Path("orchestration/structural-montage-final-render-v1.lock.json")
SHOT_DIR_REL = Path("cinematic/final-render/shots")
BACKUP_ROOT_REL = Path(
    "projects/_orchestrator/montage-pixel-format-recovery-backups"
)


class MontagePixelFormatRecoveryError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class MontagePixelFormatRecoveryResult:
    episode_id: str | None
    invalid_rendering_files_found: int
    rendering_files_archived: int
    completed_shot_outputs_preserved: int
    completed_shot_receipts_preserved: int
    paid_media_items_reset: int
    provider_requests: int
    stale_lock_removed: bool
    state_backup_path: Path | None
    run_state_backup_path: Path | None
    archive_paths: tuple[Path, ...]
    detected_pixel_formats: tuple[str, ...]
    runtime_status: str
    runtime_stage: str

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        for key in ("state_backup_path", "run_state_backup_path"):
            value = payload[key]
            payload[key] = str(value) if value is not None else None
        payload["archive_paths"] = [str(value) for value in self.archive_paths]
        payload["detected_pixel_formats"] = list(self.detected_pixel_formats)
        return payload


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MontagePixelFormatRecoveryError(
            f"CANNOT_READ_JSON:{path}:{exc}"
        ) from exc
    if not isinstance(value, dict):
        raise MontagePixelFormatRecoveryError(f"JSON_OBJECT_REQUIRED:{path}")
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


def _backup(path: Path, root: Path) -> Path | None:
    if not path.is_file():
        return None
    destination = root / path.name
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, destination)
    return destination


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def recover_montage_pixel_format_failure(
    repo_root: Path,
) -> MontagePixelFormatRecoveryResult:
    repo = repo_root.resolve()
    state_path = repo / ORCHESTRATOR_STATE_REL
    state = _read(state_path)
    episode_id = state.get("current_episode_id")
    if not isinstance(episode_id, str) or not episode_id.strip():
        return MontagePixelFormatRecoveryResult(
            episode_id=None,
            invalid_rendering_files_found=0,
            rendering_files_archived=0,
            completed_shot_outputs_preserved=0,
            completed_shot_receipts_preserved=0,
            paid_media_items_reset=0,
            provider_requests=0,
            stale_lock_removed=False,
            state_backup_path=None,
            run_state_backup_path=None,
            archive_paths=(),
            detected_pixel_formats=(),
            runtime_status=str(state.get("status", "")),
            runtime_stage=str(state.get("stage", "")),
        )
    episode_id = episode_id.strip()
    episode_root = repo / "projects" / episode_id
    shot_root = episode_root / SHOT_DIR_REL
    run_state_path = episode_root / RUN_STATE_REL
    lock_path = episode_root / RUN_LOCK_REL
    candidates = tuple(sorted(shot_root.glob("*.rendering.mp4"))) if shot_root.is_dir() else ()

    environment = inspect_montage_environment(repo)
    invalid: list[tuple[Path, str]] = []
    formats: list[str] = []
    for path in candidates:
        detected = "UNKNOWN"
        if environment.ffprobe_path is not None:
            try:
                detected = _video_pixel_format(environment, path)
            except (StructuralMontageError, OSError):
                detected = "UNREADABLE"
        formats.append(detected)
        if detected != PIXEL_FORMAT:
            invalid.append((path, detected))

    completed_outputs = (
        sum(
            1
            for path in shot_root.glob("SH-*.mp4")
            if ".rendering" not in path.name
            and ".pixel-normalized" not in path.name
        )
        if shot_root.is_dir()
        else 0
    )
    receipt_root = episode_root / "cinematic/final-render/shot-receipts"
    completed_receipts = len(tuple(receipt_root.glob("SH-*-receipt.json"))) if receipt_root.is_dir() else 0

    if not invalid:
        return MontagePixelFormatRecoveryResult(
            episode_id=episode_id,
            invalid_rendering_files_found=0,
            rendering_files_archived=0,
            completed_shot_outputs_preserved=completed_outputs,
            completed_shot_receipts_preserved=completed_receipts,
            paid_media_items_reset=0,
            provider_requests=0,
            stale_lock_removed=False,
            state_backup_path=None,
            run_state_backup_path=None,
            archive_paths=(),
            detected_pixel_formats=tuple(formats),
            runtime_status=str(state.get("status", "")),
            runtime_stage=str(state.get("stage", "")),
        )

    backup_root = repo / BACKUP_ROOT_REL / _stamp()
    state_backup = _backup(state_path, backup_root / "state")
    run_state_backup = _backup(run_state_path, backup_root / "run-state")
    archive_root = backup_root / "invalid-rendering-files"
    archive_root.mkdir(parents=True, exist_ok=True)
    archive_paths: list[Path] = []
    diagnostics: list[dict[str, Any]] = []
    for path, detected in invalid:
        destination = archive_root / path.name
        counter = 1
        while destination.exists():
            destination = archive_root / f"{path.stem}-{counter:02d}{path.suffix}"
            counter += 1
        shutil.move(str(path), str(destination))
        archive_paths.append(destination)
        diagnostics.append(
            {
                "source_path_relative": str(path.relative_to(repo)).replace("\\", "/"),
                "archive_path_relative": str(destination.relative_to(repo)).replace("\\", "/"),
                "detected_pixel_format": detected,
                "required_pixel_format": PIXEL_FORMAT,
                "archived_at_utc": _now(),
            }
        )
    _write(backup_root / "diagnostics.json", {"files": diagnostics})

    stale_lock_removed = False
    if lock_path.is_file():
        try:
            lock = _read(lock_path)
            pid = int(lock.get("pid", 0))
        except (MontagePixelFormatRecoveryError, TypeError, ValueError):
            pid = 0
        if not _pid_alive(pid):
            lock_path.unlink(missing_ok=True)
            stale_lock_removed = True

    if run_state_path.is_file():
        run_state = _read(run_state_path)
        run_state.update(
            {
                "status": "RECOVERED_READY_TO_RESUME",
                "last_error": None,
                "pixel_format_recovery_release": RELEASE,
                "invalid_rendering_files_archived": len(archive_paths),
                "updated_at_utc": _now(),
            }
        )
        _write(run_state_path, run_state)

    state.update(
        {
            "status": "STRUCTURAL_MONTAGE_FAILED",
            "stage": "STRUCTURAL_MONTAGE",
            "next_stage": "STRUCTURAL_MONTAGE_AND_FINAL_RENDER_V1",
            "last_error": None,
            "montage_pixel_format_recovery_release": RELEASE,
            "montage_pixel_format_recovery_status": "READY_TO_RESUME",
            "updated_at_utc": _now(),
        }
    )
    _write(state_path, state)

    return MontagePixelFormatRecoveryResult(
        episode_id=episode_id,
        invalid_rendering_files_found=len(invalid),
        rendering_files_archived=len(archive_paths),
        completed_shot_outputs_preserved=completed_outputs,
        completed_shot_receipts_preserved=completed_receipts,
        paid_media_items_reset=0,
        provider_requests=0,
        stale_lock_removed=stale_lock_removed,
        state_backup_path=state_backup,
        run_state_backup_path=run_state_backup,
        archive_paths=tuple(archive_paths),
        detected_pixel_formats=tuple(formats),
        runtime_status=str(state.get("status", "")),
        runtime_stage=str(state.get("stage", "")),
    )
