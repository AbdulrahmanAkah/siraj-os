"""Local audio, assembly, montage and QA runtime for Production Standard V2."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Any, Callable, Mapping, Sequence

from src.application.production_standard_v2_native_assets import (
    ASSET_PLAN_REL,
    CERTIFIED_STORYBOARD_REL,
    EPISODE_ID,
    EPISODE_ROOT_REL,
    GENERATION_ID,
    MEDIA_QUEUE_REL,
)


RELEASE = "SIRAJ_PRODUCTION_STANDARD_V2_LOCAL_RUNTIME"
ORCHESTRATOR_STATE_REL = Path(
    "projects/_orchestrator/autonomous-episode-orchestrator-state-v1.json"
)
V2_SCRIPT_REL = Path(
    "script/episode-script-production-standard-v2.json"
)
V2_AUDIO_ROOT_REL = Path("audio/mix/production-standard-v2")
V2_AUDIO_MASTER_REL = (
    V2_AUDIO_ROOT_REL / "episode-audio-master-v2.wav"
)
V2_MONTAGE_ROOT_REL = Path(
    "cinematic/final-render/production-standard-v2"
)
V2_RENDER_PLAN_REL = Path(
    "orchestration/structural-montage-render-plan-v2.json"
)
V2_RENDER_STATE_REL = Path(
    "orchestration/structural-montage-render-state-v2.json"
)
V2_QA_REPORT_REL = Path(
    "qa/automatic-qa-production-standard-v2.json"
)
FINAL_MASTER_REL = Path("deliverables/episode-master-v1.mp4")
FINAL_RECEIPT_REL = Path(
    "deliverables/episode-master-v1-receipt.json"
)
LEGACY_DELIVERABLE_ARCHIVE_REL = Path(
    "deliverables/legacy-v1-before-production-standard-v2"
)

ProgressCallback = Callable[[str, int | None], None]


class ProductionStandardV2RuntimeError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class V2QaResult:
    status: str
    report_path: Path
    blocking_issue_count: int


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProductionStandardV2RuntimeError(
            f"CANNOT_READ_JSON:{path}:{exc}"
        ) from exc
    if not isinstance(value, dict):
        raise ProductionStandardV2RuntimeError(
            f"JSON_OBJECT_REQUIRED:{path}"
        )
    return value


def _write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(
            value,
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
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        return value
    return ()


def _emit(
    progress: ProgressCallback | None,
    message: str,
    value: int | None = None,
) -> None:
    if progress is not None:
        progress(message, value)


def _active_paths(
    repo_root: Path,
) -> tuple[Path, Path, dict[str, Any], dict[str, Any]]:
    repo = repo_root.resolve()
    state_path = repo / ORCHESTRATOR_STATE_REL
    state = _read(state_path)
    if str(state.get("current_episode_id") or "") != EPISODE_ID:
        raise ProductionStandardV2RuntimeError(
            "ACTIVE_EPISODE_MISMATCH"
        )
    queue_path = repo / MEDIA_QUEUE_REL
    queue = _read(queue_path)
    if str(queue.get("production_generation_id") or "") != (
        GENERATION_ID
    ):
        raise ProductionStandardV2RuntimeError(
            "PRODUCTION_STANDARD_V2_QUEUE_REQUIRED"
        )
    return repo, state_path, state, queue


def run_v2_sfx_audio_mix(
    repo_root: Path,
    *,
    progress: ProgressCallback | None = None,
):
    """Run the proven local SFX engine against V2 paths and 43 TTS blocks."""
    from src.application import sfx_audio_mix_v1 as legacy

    repo, _, _, _ = _active_paths(repo_root)
    replacements = {
        "STORYBOARD_REL": Path(
            "cinematic/storyboard-and-media-plan-luna-certified-v2.json"
        ),
        "SCRIPT_REL": V2_SCRIPT_REL,
        "SFX_PLAN_REL": Path(
            "audio/sfx/production-standard-v2/sfx-audio-plan-v2.json"
        ),
        "SFX_ASSET_DIR_REL": Path(
            "audio/sfx/production-standard-v2/generated"
        ),
        "SFX_RECEIPT_DIR_REL": Path(
            "audio/sfx/production-standard-v2/receipts"
        ),
        "SFX_LICENSE_MANIFEST_REL": Path(
            "audio/sfx/production-standard-v2/"
            "sfx-license-manifest-v2.json"
        ),
        "AUDIO_MIX_DIR_REL": V2_AUDIO_ROOT_REL,
        "NARRATION_STEM_REL": (
            V2_AUDIO_ROOT_REL / "narration-stem-v2.wav"
        ),
        "SFX_STEM_REL": (
            V2_AUDIO_ROOT_REL / "sfx-stem-v2.wav"
        ),
        "MASTER_WAV_REL": V2_AUDIO_MASTER_REL,
        "MASTER_M4A_REL": (
            V2_AUDIO_ROOT_REL / "episode-audio-master-v2.m4a"
        ),
        "MASTER_RECEIPT_REL": (
            V2_AUDIO_ROOT_REL
            / "episode-audio-master-v2-receipt.json"
        ),
        "RUN_STATE_REL": Path(
            "orchestration/sfx-audio-mix-state-v2.json"
        ),
        "RUN_LOCK_REL": Path(
            "orchestration/sfx-audio-mix-v2.lock.json"
        ),
    }
    previous: dict[str, Any] = {}
    for name, value in replacements.items():
        if hasattr(legacy, name):
            previous[name] = getattr(legacy, name)
            setattr(legacy, name, value)
    try:
        _emit(
            progress,
            "بناء الماستر الصوتي V2 من 43 كتلة أداء والمؤثرات المحلية.",
            None,
        )
        result = legacy.run_sfx_audio_mix(
            repo,
            progress=progress,
        )
    finally:
        for name, value in previous.items():
            setattr(legacy, name, value)

    master = repo / EPISODE_ROOT_REL / V2_AUDIO_MASTER_REL
    if not master.is_file():
        raise ProductionStandardV2RuntimeError(
            "V2_AUDIO_MASTER_NOT_CREATED"
        )
    return result


def _queue_items(
    queue: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    queues = queue.get("queues")
    if not isinstance(queues, Mapping):
        raise ProductionStandardV2RuntimeError(
            "MEDIA_QUEUE_COLLECTIONS_REQUIRED"
        )
    result: dict[str, dict[str, Any]] = {}
    for key in (
        "runware_images",
        "runware_videos",
        "local_graphics",
        "elevenlabs_tts",
    ):
        for item in _sequence(queues.get(key)):
            if not isinstance(item, Mapping):
                raise ProductionStandardV2RuntimeError(
                    f"MEDIA_QUEUE_ITEM_INVALID:{key}"
                )
            queue_id = str(item.get("queue_id") or "")
            if not queue_id or queue_id in result:
                raise ProductionStandardV2RuntimeError(
                    f"MEDIA_QUEUE_ID_INVALID:{queue_id}"
                )
            result[queue_id] = dict(item)
    return result


def _all_media_complete(queue: Mapping[str, Any]) -> bool:
    return all(
        str(item.get("status") or "") == "COMPLETE"
        for item in _queue_items(queue).values()
    )


def _archive_legacy_deliverable(
    episode_root: Path,
) -> None:
    archive = episode_root / LEGACY_DELIVERABLE_ARCHIVE_REL
    for relative in (
        FINAL_MASTER_REL,
        FINAL_RECEIPT_REL,
    ):
        source = episode_root / relative
        if not source.is_file():
            continue
        target = archive / relative.name
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.is_file():
            shutil.copy2(source, target)


def _sequence_boundaries(
    assemblies: Sequence[Mapping[str, Any]],
) -> dict[str, tuple[bool, bool]]:
    result: dict[str, tuple[bool, bool]] = {}
    for index, shot in enumerate(assemblies):
        sequence_id = str(shot.get("sequence_id") or "")
        previous = (
            str(assemblies[index - 1].get("sequence_id") or "")
            if index
            else ""
        )
        following = (
            str(assemblies[index + 1].get("sequence_id") or "")
            if index + 1 < len(assemblies)
            else ""
        )
        result[str(shot["shot_id"])] = (
            index == 0 or previous != sequence_id,
            index + 1 == len(assemblies)
            or following != sequence_id,
        )
    return result


def _run_command(args: Sequence[str]) -> None:
    process = subprocess.run(
        [str(item) for item in args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if process.returncode:
        raise ProductionStandardV2RuntimeError(
            "COMMAND_FAILED:"
            + " ".join(str(item) for item in args)
            + "\nSTDOUT:\n"
            + process.stdout
            + "\nSTDERR:\n"
            + process.stderr
        )


def _concat_assets(
    legacy: Any,
    environment: Any,
    paths: list[Path],
    output: Path,
    work_root: Path,
    label: str,
) -> None:
    if not paths:
        raise ProductionStandardV2RuntimeError(
            f"NO_ASSETS_TO_CONCAT:{label}"
        )
    concat_list = work_root / f"{label}.concat.txt"
    legacy._concat_video(
        environment,
        paths,
        concat_list,
        output,
    )


def _render_asset_clip(
    legacy: Any,
    environment: Any,
    *,
    source: Path,
    output: Path,
    treatment: str,
    duration: float,
    motion_profile: str,
    graphics: bool = False,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    if treatment == "DYNAMIC_STILL_SEQUENCE":
        command = legacy.build_still_render_command(
            environment,
            source,
            output,
            duration=duration,
            motion_profile=motion_profile,
            fade_in=False,
            fade_out=False,
        )
    else:
        source_duration = legacy._probe_duration(
            environment,
            source,
        )
        if source_duration + 1.25 < duration:
            raise ProductionStandardV2RuntimeError(
                "SOURCE_TOO_SHORT_NO_LONG_FREEZE_ALLOWED:"
                f"{source}:{source_duration:.3f}:{duration:.3f}"
            )
        command = legacy.build_motion_render_command(
            environment,
            source,
            output,
            duration=duration,
            source_duration=source_duration,
            fade_in=False,
            fade_out=False,
            graphics=graphics,
        )
    _run_command(command)


def _render_shot(
    repo: Path,
    legacy: Any,
    environment: Any,
    assembly: Mapping[str, Any],
    queue_items: Mapping[str, Mapping[str, Any]],
    work_root: Path,
    boundaries: tuple[bool, bool],
) -> Path:
    shot_id = str(assembly["shot_id"])
    treatment = str(assembly["treatment"])
    duration = float(assembly["duration_seconds"])
    assets = [
        dict(item)
        for item in _sequence(assembly.get("assets"))
        if isinstance(item, Mapping)
    ]
    assets.sort(key=lambda item: int(item.get("asset_index", 0)))
    if not assets:
        raise ProductionStandardV2RuntimeError(
            f"SHOT_ASSETS_REQUIRED:{shot_id}"
        )

    rendered_assets: list[Path] = []
    motion_profiles = (
        "SLOW_PUSH_IN",
        "PAN_LEFT_TO_RIGHT",
        "PAN_RIGHT_TO_LEFT",
        "DIAGONAL_DOWN_RIGHT",
        "SLOW_PULL_OUT",
        "PAN_BOTTOM_TO_TOP",
    )
    for index, asset in enumerate(assets, start=1):
        queue_id = str(asset.get("queue_id") or "")
        item = queue_items.get(queue_id)
        if item is None:
            raise ProductionStandardV2RuntimeError(
                f"SHOT_QUEUE_ITEM_MISSING:{shot_id}:{queue_id}"
            )
        if str(item.get("status") or "") != "COMPLETE":
            raise ProductionStandardV2RuntimeError(
                f"SHOT_QUEUE_ITEM_NOT_COMPLETE:{queue_id}"
            )
        source = repo / str(item.get("output_path_relative") or "")
        if not source.is_file():
            raise ProductionStandardV2RuntimeError(
                f"SHOT_SOURCE_MISSING:{queue_id}:{source}"
            )
        asset_clip = (
            work_root
            / "assets"
            / shot_id
            / f"asset-{index:03d}.mp4"
        )
        _render_asset_clip(
            legacy,
            environment,
            source=source,
            output=asset_clip,
            treatment=treatment,
            duration=float(
                asset.get("timeline_duration_seconds", 0)
            ),
            motion_profile=motion_profiles[
                (index - 1) % len(motion_profiles)
            ],
            graphics=(treatment == "AUTHORED_GRAPHICS"),
        )
        rendered_assets.append(asset_clip)

    combined = work_root / "combined" / f"{shot_id}.mp4"
    combined.parent.mkdir(parents=True, exist_ok=True)
    _concat_assets(
        legacy,
        environment,
        rendered_assets,
        combined,
        work_root / "concat",
        shot_id,
    )
    source_duration = legacy._probe_duration(
        environment,
        combined,
    )
    if abs(source_duration - duration) > 0.35:
        raise ProductionStandardV2RuntimeError(
            f"SHOT_ASSEMBLY_DURATION_MISMATCH:{shot_id}:"
            f"{source_duration:.3f}:{duration:.3f}"
        )

    output = repo / str(assembly["output_path_relative"])
    output.parent.mkdir(parents=True, exist_ok=True)
    command = legacy.build_motion_render_command(
        environment,
        combined,
        output,
        duration=duration,
        source_duration=source_duration,
        fade_in=boundaries[0],
        fade_out=boundaries[1],
        graphics=(treatment == "AUTHORED_GRAPHICS"),
    )
    _run_command(command)
    legacy._validate_video_file(
        environment,
        output,
        duration,
        require_audio=False,
        tolerance=0.25,
    )
    return output


def run_v2_structural_montage(
    repo_root: Path,
    *,
    progress: ProgressCallback | None = None,
):
    from src.application import (
        structural_montage_final_render_v1 as legacy,
    )

    repo, state_path, state, queue = _active_paths(
        repo_root
    )
    if not _all_media_complete(queue):
        raise ProductionStandardV2RuntimeError(
            "MEDIA_ASSETS_MUST_BE_COMPLETE_BEFORE_V2_MONTAGE"
        )
    environment = legacy.require_montage_environment(repo)
    episode_root = repo / EPISODE_ROOT_REL
    audio_master = episode_root / V2_AUDIO_MASTER_REL
    if not audio_master.is_file():
        raise ProductionStandardV2RuntimeError(
            "V2_AUDIO_MASTER_REQUIRED_BEFORE_MONTAGE"
        )

    plan = _read(repo / ASSET_PLAN_REL)
    assemblies = [
        dict(item)
        for item in _sequence(plan.get("shot_assemblies"))
        if isinstance(item, Mapping)
    ]
    assemblies.sort(
        key=lambda item: int(item.get("queue_index", 0))
    )
    if len(assemblies) != 70:
        raise ProductionStandardV2RuntimeError(
            f"V2_ASSEMBLY_COUNT_INVALID:{len(assemblies)}"
        )
    if [int(item.get("queue_index", 0)) for item in assemblies] != (
        list(range(1, 71))
    ):
        raise ProductionStandardV2RuntimeError(
            "V2_ASSEMBLY_QUEUE_ORDER_INVALID"
        )

    queue_items = _queue_items(queue)
    boundaries = _sequence_boundaries(assemblies)
    work_root = (
        episode_root / V2_MONTAGE_ROOT_REL / "working"
    )
    work_root.mkdir(parents=True, exist_ok=True)
    state.update(
        {
            "status": "STRUCTURAL_MONTAGE_ACTIVE",
            "stage": "STRUCTURAL_MONTAGE",
            "next_stage": (
                "PRODUCTION_STANDARD_V2_STRUCTURAL_MONTAGE"
            ),
            "last_error": None,
            "updated_at_utc": _now(),
        }
    )
    _write(state_path, state)

    rendered_paths: list[Path] = []
    receipts: list[dict[str, Any]] = []
    try:
        for index, assembly in enumerate(
            assemblies,
            start=1,
        ):
            shot_id = str(assembly["shot_id"])
            _emit(
                progress,
                f"تركيب لقطة V2 رقم {index}/70 — {shot_id}",
                3 + int(index * 74 / 70),
            )
            output = _render_shot(
                repo,
                legacy,
                environment,
                assembly,
                queue_items,
                work_root,
                boundaries[shot_id],
            )
            rendered_paths.append(output)
            receipts.append(
                {
                    "shot_id": shot_id,
                    "treatment": assembly["treatment"],
                    "duration_seconds": assembly[
                        "duration_seconds"
                    ],
                    "asset_count": len(
                        list(_sequence(assembly.get("assets")))
                    ),
                    "output_path_relative": str(
                        output.relative_to(repo)
                    ).replace("\\", "/"),
                    "output_sha256": _sha256(output),
                }
            )

        _archive_legacy_deliverable(episode_root)
        concat_list = (
            episode_root
            / V2_MONTAGE_ROOT_REL
            / "episode-shot-concat-v2.txt"
        )
        video_only = (
            episode_root
            / V2_MONTAGE_ROOT_REL
            / "episode-video-only-v2.mp4"
        )
        final_master = episode_root / FINAL_MASTER_REL
        final_receipt = episode_root / FINAL_RECEIPT_REL
        duration = round(
            sum(
                float(item["duration_seconds"])
                for item in assemblies
            ),
            6,
        )
        _emit(
            progress,
            "تجميع اللقطات السبعين ودمج الماستر الصوتي V2.",
            82,
        )
        legacy._concat_video(
            environment,
            rendered_paths,
            concat_list,
            video_only,
        )
        legacy._validate_video_file(
            environment,
            video_only,
            duration,
            require_audio=False,
            tolerance=0.75,
        )
        legacy._mux_audio(
            environment,
            video_only,
            audio_master,
            final_master,
            duration,
        )
        validation = legacy._validate_video_file(
            environment,
            final_master,
            duration,
            require_audio=True,
            tolerance=0.75,
        )

        render_plan = {
            "schema_version": (
                "siraj-structural-montage-render-plan-v2"
            ),
            "release": RELEASE,
            "episode_id": EPISODE_ID,
            "production_generation_id": GENERATION_ID,
            "status": "COMPLETE_READY_FOR_AUTOMATIC_QA",
            "shot_count": 70,
            "episode_duration_seconds": duration,
            "generated_video_seconds": 891.0,
            "treatment_counts": {
                "GENERATED_VIDEO": 50,
                "DYNAMIC_STILL_SEQUENCE": 14,
                "AUTHORED_GRAPHICS": 6,
            },
            "render_profile": {
                "width": 1920,
                "height": 1080,
                "fps": 30,
                "video_codec": "libx264",
                "profile": "high",
                "level": "4.1",
                "pixel_format": "yuv420p",
                "color_space": "bt709",
                "audio_codec": "aac",
                "audio_sample_rate": 48000,
                "music": "FORBIDDEN",
                "maximum_last_frame_extension_seconds": 1.25,
            },
            "shots": receipts,
            "audio_master_relative": str(
                audio_master.relative_to(repo)
            ).replace("\\", "/"),
            "final_master_relative": str(
                final_master.relative_to(repo)
            ).replace("\\", "/"),
            "paid_provider_requests": 0,
            "completed_at_utc": _now(),
        }
        render_plan["render_plan_sha256"] = hashlib.sha256(
            json.dumps(
                render_plan,
                sort_keys=True,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        plan_path = episode_root / V2_RENDER_PLAN_REL
        _write(plan_path, render_plan)

        receipt = {
            "schema_version": "siraj-final-render-receipt-v2",
            "release": RELEASE,
            "episode_id": EPISODE_ID,
            "production_generation_id": GENERATION_ID,
            "status": "COMPLETE_READY_FOR_AUTOMATIC_QA",
            "provider": "LOCAL",
            "service": (
                "PRODUCTION_STANDARD_V2_STRUCTURAL_MONTAGE"
            ),
            "actual_cost_usd": 0.0,
            "estimated_cost_usd": 0.0,
            "music": "FORBIDDEN",
            "shot_count": 70,
            "duration_seconds": duration,
            "audio_master_relative": str(
                audio_master.relative_to(repo)
            ).replace("\\", "/"),
            "audio_master_sha256": _sha256(audio_master),
            "render_plan_relative": str(
                plan_path.relative_to(repo)
            ).replace("\\", "/"),
            "render_plan_sha256": _sha256(plan_path),
            "final_master_relative": str(
                final_master.relative_to(repo)
            ).replace("\\", "/"),
            "final_master_sha256": _sha256(final_master),
            "final_master_bytes": final_master.stat().st_size,
            "validation": validation,
            "paid_provider_requests": 0,
            "completed_at_utc": _now(),
        }
        _write(final_receipt, receipt)
        state.update(
            {
                "status": "FINAL_RENDER_READY_FOR_QA",
                "stage": "AUTOMATIC_QA",
                "next_stage": (
                    "AUTOMATIC_QA_PRODUCTION_STANDARD_V2"
                ),
                "production_generation_id": GENERATION_ID,
                "structural_montage_plan_path_relative": str(
                    plan_path.relative_to(repo)
                ).replace("\\", "/"),
                "final_master_path_relative": str(
                    final_master.relative_to(repo)
                ).replace("\\", "/"),
                "final_master_sha256": _sha256(final_master),
                "last_error": None,
                "updated_at_utc": _now(),
            }
        )
        _write(state_path, state)
        _write(
            episode_root / V2_RENDER_STATE_REL,
            {
                "schema_version": (
                    "siraj-structural-montage-state-v2"
                ),
                "release": RELEASE,
                "episode_id": EPISODE_ID,
                "status": "COMPLETE",
                "duration_seconds": duration,
                "shot_count": 70,
                "final_master_path_relative": str(
                    final_master.relative_to(repo)
                ).replace("\\", "/"),
                "final_master_sha256": _sha256(final_master),
                "paid_provider_requests": 0,
                "completed_at_utc": _now(),
            },
        )
        _emit(
            progress,
            "اكتمل الماستر V2 وانتقل إلى QA.",
            100,
        )
        return legacy.StructuralMontageResult(
            episode_id=EPISODE_ID,
            render_plan_path=plan_path,
            final_master_path=final_master,
            final_receipt_path=final_receipt,
            rendered_shot_count=70,
            reused_shot_count=0,
            duration_seconds=duration,
            status="FINAL_RENDER_READY_FOR_QA",
        )
    except Exception as exc:
        state.update(
            {
                "status": "STRUCTURAL_MONTAGE_FAILED",
                "stage": "STRUCTURAL_MONTAGE",
                "next_stage": (
                    "RESUME_PRODUCTION_STANDARD_V2_MONTAGE"
                ),
                "last_error": str(exc),
                "updated_at_utc": _now(),
            }
        )
        _write(state_path, state)
        raise


def _probe_streams(
    ffprobe: Path,
    source: Path,
) -> dict[str, Any]:
    process = subprocess.run(
        [
            str(ffprobe),
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(source),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if process.returncode:
        raise ProductionStandardV2RuntimeError(
            "FFPROBE_FAILED:" + process.stderr
        )
    value = json.loads(process.stdout)
    if not isinstance(value, dict):
        raise ProductionStandardV2RuntimeError(
            "FFPROBE_OBJECT_REQUIRED"
        )
    return value


def _quality_detection(
    ffmpeg: Path,
    source: Path,
) -> tuple[list[dict[str, Any]], str]:
    process = subprocess.run(
        [
            str(ffmpeg),
            "-hide_banner",
            "-nostats",
            "-i",
            str(source),
            "-vf",
            (
                "blackdetect=d=1.0:pix_th=0.10,"
                "freezedetect=n=-50dB:d=7.0"
            ),
            "-af",
            "silencedetect=noise=-50dB:d=3.0",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    text = process.stderr
    issues: list[dict[str, Any]] = []
    for match in re.finditer(
        r"black_duration:([0-9.]+)",
        text,
    ):
        duration = float(match.group(1))
        if duration > 1.0:
            issues.append(
                {
                    "code": "UNPLANNED_BLACK",
                    "duration_seconds": duration,
                }
            )
    for match in re.finditer(
        r"freeze_duration:\s*([0-9.]+)",
        text,
    ):
        duration = float(match.group(1))
        if duration > 7.0:
            issues.append(
                {
                    "code": "LONG_FREEZE",
                    "duration_seconds": duration,
                }
            )
    for match in re.finditer(
        r"silence_duration:\s*([0-9.]+)",
        text,
    ):
        duration = float(match.group(1))
        if duration > 3.0:
            issues.append(
                {
                    "code": "UNPLANNED_SILENCE",
                    "duration_seconds": duration,
                }
            )
    return issues, text[-12000:]


def _loudness(
    ffmpeg: Path,
    source: Path,
) -> dict[str, float]:
    process = subprocess.run(
        [
            str(ffmpeg),
            "-hide_banner",
            "-nostats",
            "-i",
            str(source),
            "-af",
            (
                "loudnorm=I=-16:TP=-1.5:LRA=11:"
                "print_format=json"
            ),
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    matches = list(
        re.finditer(
            r"\{\s*\"input_i\".*?\}",
            process.stderr,
            flags=re.DOTALL,
        )
    )
    if not matches:
        raise ProductionStandardV2RuntimeError(
            "LOUDNESS_ANALYSIS_JSON_NOT_FOUND"
        )
    value = json.loads(matches[-1].group(0))
    return {
        "integrated_lufs": float(value["input_i"]),
        "true_peak_dbtp": float(value["input_tp"]),
        "lra": float(value["input_lra"]),
    }


def run_v2_automatic_qa(
    repo_root: Path,
    *,
    progress: ProgressCallback | None = None,
) -> V2QaResult:
    from src.application import (
        structural_montage_final_render_v1 as legacy,
    )

    repo, state_path, state, queue = _active_paths(
        repo_root
    )
    episode_root = repo / EPISODE_ROOT_REL
    final_master = episode_root / FINAL_MASTER_REL
    report_path = episode_root / V2_QA_REPORT_REL
    blockers: list[dict[str, Any]] = []

    state.update(
        {
            "status": "AUTOMATIC_QA_ACTIVE",
            "stage": "AUTOMATIC_QA",
            "last_error": None,
            "updated_at_utc": _now(),
        }
    )
    _write(state_path, state)
    try:
        if not final_master.is_file():
            blockers.append(
                {"code": "FINAL_MASTER_MISSING"}
            )
        if not _all_media_complete(queue):
            blockers.append(
                {"code": "MEDIA_QUEUE_NOT_COMPLETE"}
            )

        environment = legacy.require_montage_environment(
            repo
        )
        probe: dict[str, Any] = {}
        loudness: dict[str, float] = {}
        detection_log = ""
        if final_master.is_file():
            probe = _probe_streams(
                environment.ffprobe_path,
                final_master,
            )
            streams = list(
                _sequence(probe.get("streams"))
            )
            video = next(
                (
                    item
                    for item in streams
                    if isinstance(item, Mapping)
                    and item.get("codec_type") == "video"
                ),
                None,
            )
            audio = next(
                (
                    item
                    for item in streams
                    if isinstance(item, Mapping)
                    and item.get("codec_type") == "audio"
                ),
                None,
            )
            if not isinstance(video, Mapping):
                blockers.append(
                    {"code": "VIDEO_STREAM_MISSING"}
                )
            else:
                if (
                    int(video.get("width", 0) or 0) != 1920
                    or int(video.get("height", 0) or 0)
                    != 1080
                ):
                    blockers.append(
                        {
                            "code": "VIDEO_RESOLUTION_INVALID",
                            "width": video.get("width"),
                            "height": video.get("height"),
                        }
                    )
                if str(
                    video.get("pix_fmt") or ""
                ) != "yuv420p":
                    blockers.append(
                        {
                            "code": "PIXEL_FORMAT_INVALID",
                            "value": video.get("pix_fmt"),
                        }
                    )
            if not isinstance(audio, Mapping):
                blockers.append(
                    {"code": "AUDIO_STREAM_MISSING"}
                )
            else:
                if int(
                    audio.get("sample_rate", 0) or 0
                ) != 48000:
                    blockers.append(
                        {
                            "code": "AUDIO_SAMPLE_RATE_INVALID",
                            "value": audio.get("sample_rate"),
                        }
                    )
            duration = float(
                (probe.get("format") or {}).get(
                    "duration", 0
                )
                or 0
            )
            if abs(duration - 1320.0) > 0.75:
                blockers.append(
                    {
                        "code": "FINAL_DURATION_INVALID",
                        "duration_seconds": duration,
                    }
                )
            detection, detection_log = _quality_detection(
                environment.ffmpeg_path,
                final_master,
            )
            blockers.extend(detection)
            loudness = _loudness(
                environment.ffmpeg_path,
                final_master,
            )
            if not (
                -17.0
                <= loudness["integrated_lufs"]
                <= -15.0
            ):
                blockers.append(
                    {
                        "code": "LOUDNESS_OUTSIDE_TARGET",
                        **loudness,
                    }
                )
            if loudness["true_peak_dbtp"] > -1.0:
                blockers.append(
                    {
                        "code": "TRUE_PEAK_TOO_HIGH",
                        **loudness,
                    }
                )

        certified = _read(
            repo / CERTIFIED_STORYBOARD_REL
        )
        shots = [
            item
            for item in _sequence(certified.get("shots"))
            if isinstance(item, Mapping)
        ]
        if len(shots) != 70:
            blockers.append(
                {
                    "code": "CERTIFIED_STORYBOARD_COUNT_INVALID",
                    "count": len(shots),
                }
            )
        for shot in shots:
            if shot.get("contains_music") is True:
                blockers.append(
                    {
                        "code": "MUSIC_FORBIDDEN",
                        "shot_id": shot.get("shot_id"),
                    }
                )
            certification = shot.get(
                "luna_prompt_certification_v2"
            )
            if (
                not isinstance(certification, Mapping)
                or str(certification.get("status") or "")
                != "PASS"
                or list(
                    _sequence(
                        certification.get("blocking_flags")
                    )
                )
            ):
                blockers.append(
                    {
                        "code": "LUNA_CERTIFICATION_INVALID",
                        "shot_id": shot.get("shot_id"),
                    }
                )

        status = (
            "AWAITING_HUMAN_FINAL_REVIEW"
            if not blockers
            else "AUTOMATIC_QA_BLOCKED"
        )
        report = {
            "schema_version": (
                "siraj-automatic-qa-production-standard-v2"
            ),
            "release": RELEASE,
            "episode_id": EPISODE_ID,
            "production_generation_id": GENERATION_ID,
            "status": status,
            "blocking_issue_count": len(blockers),
            "blocking_issues": blockers,
            "final_master_relative": str(
                final_master.relative_to(repo)
            ).replace("\\", "/")
            if final_master.is_file()
            else None,
            "final_master_sha256": (
                _sha256(final_master)
                if final_master.is_file()
                else None
            ),
            "probe": probe,
            "loudness": loudness,
            "detection_log_tail": detection_log,
            "policy": {
                "maximum_unplanned_black_seconds": 1.0,
                "maximum_freeze_seconds": 7.0,
                "maximum_unplanned_silence_seconds": 3.0,
                "target_integrated_lufs": -16.0,
                "maximum_true_peak_dbtp": -1.0,
                "music": "FORBIDDEN",
            },
            "automatic_paid_retry": "FORBIDDEN",
            "paid_provider_requests": 0,
            "completed_at_utc": _now(),
        }
        _write(report_path, report)

        state.update(
            {
                "status": status,
                "stage": (
                    "HUMAN_FINAL_REVIEW"
                    if not blockers
                    else "AUTOMATIC_QA"
                ),
                "next_stage": (
                    "HUMAN_FINAL_REVIEW_AND_PUBLISH_HANDOFF"
                    if not blockers
                    else "RESOLVE_V2_QA_BLOCKERS"
                ),
                "automatic_qa_report_path_relative": str(
                    report_path.relative_to(repo)
                ).replace("\\", "/"),
                "last_error": (
                    None
                    if not blockers
                    else json.dumps(
                        blockers,
                        ensure_ascii=False,
                    )
                ),
                "updated_at_utc": _now(),
            }
        )
        _write(state_path, state)
        if blockers:
            raise ProductionStandardV2RuntimeError(
                "AUTOMATIC_QA_BLOCKED:"
                + json.dumps(
                    blockers,
                    ensure_ascii=False,
                )
            )
        _emit(
            progress,
            "اجتازت الحلقة QA وأصبحت بانتظار المشاهدة البشرية النهائية.",
            100,
        )
        return V2QaResult(
            status=status,
            report_path=report_path,
            blocking_issue_count=0,
        )
    except Exception:
        if not report_path.is_file():
            state.update(
                {
                    "status": "AUTOMATIC_QA_FAILED",
                    "stage": "AUTOMATIC_QA",
                    "next_stage": "RESUME_V2_AUTOMATIC_QA",
                    "updated_at_utc": _now(),
                }
            )
            _write(state_path, state)
        raise
