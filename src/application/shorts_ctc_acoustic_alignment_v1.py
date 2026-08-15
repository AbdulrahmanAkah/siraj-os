"""SIRAJ compiler-free local CTC acoustic alignment adapter for Shorts.

The trusted SIRAJ transcript remains the only text authority. A local CTC
model supplies acoustic emissions only; decoded ASR text is never accepted.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence
import hashlib
import json
import os
import subprocess

ADAPTER_ID = "SIRAJ_ACOUSTIC_ALIGNMENT_BACKEND_V1"
ADAPTER_VERSION = "1.1.0"
SCHEMA_VERSION = "SIRAJ_FINE_GRAINED_TIMING_V1"
DEFAULT_RUNTIME_ROOT = (
    Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
    / "SIRAJ" / "runtimes" / "shorts-ctc-v1"
)
DEFAULT_CACHE_ROOT = (
    Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
    / "SIRAJ" / "cache" / "shorts-ctc-v1"
)


class CTCAlignmentUnavailable(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class CaptionTimingRefinement:
    status: str
    segments: tuple[Mapping[str, Any], ...]
    fine_timing_sha256: str
    authority: str
    coverage: float
    uncertain_regions: int
    cache_status: str
    evidence: Mapping[str, Any]


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _sha(value: Any) -> str:
    raw = value if isinstance(value, (bytes, bytearray)) else _canonical(value)
    return hashlib.sha256(bytes(raw)).hexdigest()


def _runtime_manifest() -> Path:
    override = os.environ.get("SIRAJ_SHORTS_CTC_RUNTIME_MANIFEST")
    return Path(override) if override else DEFAULT_RUNTIME_ROOT / "runtime-manifest.json"


def _read_manifest() -> dict[str, Any]:
    path = _runtime_manifest()
    if not path.is_file():
        raise CTCAlignmentUnavailable(f"CTC_RUNTIME_MANIFEST_MISSING:{path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("status") != "READY":
        raise CTCAlignmentUnavailable("CTC_RUNTIME_NOT_READY")
    for key in ("python_path", "helper_path", "model_path"):
        candidate = Path(str(value.get(key, "")))
        if not candidate.exists():
            raise CTCAlignmentUnavailable(f"CTC_RUNTIME_PATH_MISSING:{key}:{candidate}")
    return value


def _helper_path(runtime: Mapping[str, Any]) -> Path:
    override = os.environ.get("SIRAJ_SHORTS_CTC_HELPER_PATH")
    if override:
        candidate = Path(override)
        if candidate.is_file():
            return candidate
    local = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "shorts_alignment"
        / "ctc_sidecar_v1.py"
    )
    if local.is_file():
        return local
    return Path(str(runtime["helper_path"]))


def _segment_mapping(segment: Any) -> dict[str, Any]:
    if isinstance(segment, Mapping):
        raw = dict(segment)
        start = raw.get("start_time", raw.get("start_seconds", raw.get("start")))
        end = raw.get("end_time", raw.get("end_seconds", raw.get("end")))
        text = raw.get("text", raw.get("canonical_text_ar", raw.get("narration")))
        sid = raw.get("segment_id", raw.get("id", raw.get("block_id")))
    else:
        raw = {}
        start = getattr(segment, "start_time")
        end = getattr(segment, "end_time")
        text = getattr(segment, "text")
        sid = getattr(segment, "segment_id")
    return {
        **raw,
        "segment_id": str(sid),
        "start_time": float(start),
        "end_time": float(end),
        "text": str(text),
    }


def _native_ready(segments: Sequence[Mapping[str, Any]]) -> bool:
    if not segments:
        return False
    for segment in segments:
        words = (
            segment.get("word_boundaries")
            or segment.get("words")
            or segment.get("word_timings")
        )
        phrases = (
            segment.get("phrase_boundaries")
            or segment.get("phrases")
            or segment.get("clauses")
        )
        if words or phrases:
            continue
        duration = float(segment["end_time"]) - float(segment["start_time"])
        if duration > 8.0 or len(str(segment["text"])) > 120:
            return False
    return True


def refine_candidate_caption_segments(
    *,
    source_video_path: str | Path,
    episode_id: str,
    all_segments: Sequence[Any],
    candidate_start: float,
    candidate_end: float,
    source_video_sha256: str,
    source_audio_sha256: str,
    canonical_transcript_sha256: str,
    coarse_timing_sha256: str,
) -> CaptionTimingRefinement:
    """Return candidate-local trusted timing; acoustic alignment is cached per episode."""

    normalized = tuple(_segment_mapping(item) for item in all_segments)
    intersecting = tuple(
        item
        for item in normalized
        if float(item["end_time"]) > float(candidate_start) + 1e-6
        and float(item["start_time"]) < float(candidate_end) - 1e-6
    )
    if not intersecting:
        raise CTCAlignmentUnavailable("CANDIDATE_NO_TRANSCRIPT_SEGMENTS")

    if _native_ready(intersecting):
        digest = _sha(
            {
                "authority": "NATIVE_TRUSTED_TIMING",
                "coarse_timing_sha256": coarse_timing_sha256,
                "segments": intersecting,
            }
        )
        return CaptionTimingRefinement(
            status="READY",
            segments=intersecting,
            fine_timing_sha256=digest,
            authority="NATIVE_TRUSTED_TIMING",
            coverage=1.0,
            uncertain_regions=0,
            cache_status="NATIVE_FAST_PATH",
            evidence={
                "adapter": ADAPTER_ID,
                "version": ADAPTER_VERSION,
                "provider_calls": 0,
                "paid_calls": 0,
                "network_runtime_calls": 0,
            },
        )

    runtime = _read_manifest()
    helper_path = _helper_path(runtime)
    helper_sha256 = _sha(helper_path.read_bytes())
    DEFAULT_CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    episode_payload = {
        "schema_version": SCHEMA_VERSION,
        "adapter_id": ADAPTER_ID,
        "adapter_version": ADAPTER_VERSION,
        "episode_id": str(episode_id),
        "source_video_path": str(Path(source_video_path).resolve()),
        "source_video_sha256": str(source_video_sha256).lower(),
        "source_audio_sha256": str(source_audio_sha256).lower(),
        "canonical_transcript_sha256": str(canonical_transcript_sha256).lower(),
        "coarse_timing_sha256": str(coarse_timing_sha256).lower(),
        "model_repo_id": runtime["model_repo_id"],
        "model_revision": runtime["model_revision"],
        "model_sha256": runtime["model_sha256"],
        "helper_sha256": helper_sha256,
        "segments": list(normalized),
    }
    episode_key = _sha(episode_payload)
    cache_file = DEFAULT_CACHE_ROOT / f"{episode_key}.json"

    if cache_file.is_file():
        response = json.loads(cache_file.read_text(encoding="utf-8"))
        cache_status = "CACHE_REUSED"
    else:
        request_file = DEFAULT_CACHE_ROOT / f".{episode_key}.request.json"
        response_file = DEFAULT_CACHE_ROOT / f".{episode_key}.response.json"
        request_file.write_text(
            json.dumps(episode_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        env = dict(os.environ)
        env["SIRAJ_SHORTS_CTC_RUNTIME_ROOT"] = str(DEFAULT_RUNTIME_ROOT)
        env.update(
            {
                "HF_HUB_OFFLINE": "1",
                "TRANSFORMERS_OFFLINE": "1",
                "HF_DATASETS_OFFLINE": "1",
                "TOKENIZERS_PARALLELISM": "false",
            }
        )
        completed = subprocess.run(
            [
                str(runtime["python_path"]),
                str(helper_path),
                "--request",
                str(request_file),
                "--response",
                str(response_file),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            check=False,
        )
        request_file.unlink(missing_ok=True)
        if completed.returncode != 0 or not response_file.is_file():
            detail = (completed.stderr or completed.stdout or "NO_OUTPUT")[-1200:]
            raise CTCAlignmentUnavailable(
                "CTC_SIDECAR_FAILED:" + detail.replace("\n", " ")
            )
        response = json.loads(response_file.read_text(encoding="utf-8"))
        response_file.unlink(missing_ok=True)
        if response.get("status") != "PASS":
            raise CTCAlignmentUnavailable(
                f"CTC_ALIGNMENT_BLOCKED:{response.get('code')}:{response.get('detail')}"
            )
        temporary = cache_file.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(response, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        os.replace(temporary, cache_file)
        cache_status = "CACHE_CREATED"

    if response.get("episode_key") != episode_key:
        raise CTCAlignmentUnavailable("CTC_RESPONSE_HASH_BINDING_MISMATCH")

    candidate_segments: list[dict[str, Any]] = []
    uncertain = 0
    for segment in response.get("segments", []):
        start = float(segment["start_time"])
        end = float(segment["end_time"])
        if end <= float(candidate_start) + 1e-6 or start >= float(candidate_end) - 1e-6:
            continue
        if segment.get("alignment_status") != "PASS":
            uncertain += 1
            continue
        words = []
        for word in segment.get("word_boundaries", []):
            wstart = float(word["start_seconds"])
            wend = float(word["end_seconds"])
            intersects = (
                wend > float(candidate_start) + 1e-6
                and wstart < float(candidate_end) - 1e-6
            )
            if not intersects:
                continue
            if (
                word.get("status") == "TRUSTED"
                and wstart >= float(candidate_start) - 1e-6
                and wend <= float(candidate_end) + 1e-6
            ):
                words.append(dict(word))
            else:
                uncertain += 1

        if words:
            candidate_segments.append(
                {
                    "segment_id": str(segment["segment_id"]),
                    "start_time": start,
                    "end_time": end,
                    "text": str(segment["text"]),
                    "word_boundaries": words,
                    "alignment_authority": "LOCAL_CERTIFIED_CTC_ACOUSTIC_ALIGNMENT",
                }
            )

    if uncertain:
        raise CTCAlignmentUnavailable(
            f"CANDIDATE_CONTAINS_UNCERTAIN_ALIGNED_REGION:{uncertain}"
        )
    if not candidate_segments:
        raise CTCAlignmentUnavailable("CANDIDATE_HAS_NO_TRUSTED_ALIGNED_WORDS")

    fine_hash = _sha(
        {
            "episode_key": episode_key,
            "candidate_start": float(candidate_start),
            "candidate_end": float(candidate_end),
            "segments": candidate_segments,
            "authority": "LOCAL_CERTIFIED_CTC_ACOUSTIC_ALIGNMENT",
        }
    )
    return CaptionTimingRefinement(
        status="READY",
        segments=tuple(candidate_segments),
        fine_timing_sha256=fine_hash,
        authority="LOCAL_CERTIFIED_CTC_ACOUSTIC_ALIGNMENT",
        coverage=1.0,
        uncertain_regions=0,
        cache_status=cache_status,
        evidence={
            "adapter": ADAPTER_ID,
            "version": ADAPTER_VERSION,
            "episode_key": episode_key,
            "model_repo_id": runtime["model_repo_id"],
            "model_revision": runtime["model_revision"],
            "model_sha256": runtime["model_sha256"],
            "helper_path": str(helper_path),
            "helper_sha256": helper_sha256,
            "cache_file": str(cache_file),
            "provider_calls": 0,
            "paid_calls": 0,
            "network_runtime_calls": 0,
            "asr_text_authority": False,
        },
    )
