"""SIRAJ V4+ production contract for every episode after Episode 001."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib, json, re
from pathlib import Path
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = "siraj-v4-plus-production-contract-v1"
PHASE_ORDER = (
    "SOURCE_RESEARCH_FROM_ZERO",
    "SOURCE_CLAIM_MATRIX",
    "FINAL_SCRIPT",
    "PRONUNCIATION_AND_PERFORMANCE_GATE",
    "FINAL_TTS",
    "AUDIO_TIMESTAMPS_AND_BEATS",
    "AUDIO_BOUND_STORYBOARD",
    "LUNA_SEMANTIC_PROMPT_DIRECTION",
    "NARRATION_VISUAL_ALIGNMENT_GATE",
    "PROMPT_SIMILARITY_AND_DUPLICATE_GATE",
    "COST_PREFLIGHT_AND_ATTEMPT_LEDGER",
    "EXPLICIT_PAID_AUTHORIZATION",
    "PROVIDER_EXECUTION",
    "LOCAL_ASSEMBLY_AND_QA",
)
ARABIC_RE = re.compile(r"[\u0600-\u06ff]")

class SirajV4PlusContractError(RuntimeError):
    pass

@dataclass(frozen=True, slots=True)
class EpisodeContext:
    episode_id: str
    generation_id: str
    episode_root_rel: Path
    target_duration_seconds: float | None = None
    expected_shot_count: int | None = None
    expected_tts_block_count: int | None = None

    @classmethod
    def from_json(cls, path: Path) -> "EpisodeContext":
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
        ep = str(raw.get("episode_id") or "").strip()
        gen = str(raw.get("generation_id") or "").strip()
        root = str(raw.get("episode_root_rel") or f"projects/{ep}").strip()
        if not ep or not gen:
            raise SirajV4PlusContractError("EPISODE_CONTEXT_ID_REQUIRED")
        if ep == "episode-001-adam":
            raise SirajV4PlusContractError("V4_PLUS_RESERVED_FOR_POST_EPISODE_001_PIPELINE")
        for key in ("target_duration_seconds", "expected_shot_count", "expected_tts_block_count"):
            if raw.get(key) not in (None, ""):
                raise SirajV4PlusContractError(f"FIXED_PRE_AUDIO_VALUE_FORBIDDEN:{key}")
        return cls(ep, gen, Path(root))

def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()

def require_phase_order(value: Sequence[str]) -> None:
    if tuple(value) != PHASE_ORDER:
        raise SirajV4PlusContractError("PIPELINE_PHASE_ORDER_INVALID")

def require_narration_bound_shot(shot: Mapping[str, Any]) -> None:
    sid = str(shot.get("shot_id") or "?")
    for key in ("narration_beat_id", "narration_text_ar", "visual_rationale_ar"):
        if not str(shot.get(key) or "").strip():
            raise SirajV4PlusContractError(f"SHOT_NARRATION_BINDING_REQUIRED:{sid}:{key}")
    if str(shot.get("semantic_alignment_status") or "") != "PASS":
        raise SirajV4PlusContractError(f"SHOT_SEMANTIC_ALIGNMENT_REQUIRED:{sid}")
    score = float(shot.get("semantic_alignment_score") or 0)
    if score < 0.90:
        raise SirajV4PlusContractError(f"SHOT_SEMANTIC_ALIGNMENT_LOW:{sid}:{score}")

def require_provider_prompt_text_policy(item: Mapping[str, Any]) -> None:
    aid = str(item.get("asset_id") or item.get("shot_id") or "?")
    prompt = str(
        item.get("provider_prompt")
        or item.get("certified_positive_prompt_en")
        or ""
    )
    if ARABIC_RE.search(prompt):
        raise SirajV4PlusContractError(f"GENERATED_ARABIC_TEXT_FORBIDDEN:{aid}")
    if (
        item.get("requires_exact_text") is True
        and str(item.get("exact_text_mode") or "") != "DETERMINISTIC_LOCAL_OVERLAY"
    ):
        raise SirajV4PlusContractError(f"EXACT_TEXT_LOCAL_OVERLAY_REQUIRED:{aid}")

def require_audio_markers(meta: Mapping[str, Any]) -> None:
    hook = float(meta.get("hook_end_seconds") or -1)
    intro = float(meta.get("intro_entry_seconds") or -2)
    outro = float(meta.get("outro_entry_seconds") or -3)
    total = float(meta.get("final_tts_duration_seconds") or -4)
    hook_pause = float(meta.get("hook_intro_pause_seconds") or 0)
    outro_pause = float(meta.get("pre_outro_pause_seconds") or 0)
    if hook < 0 or intro < hook or hook_pause < 0.6:
        raise SirajV4PlusContractError("HOOK_INTRO_PAUSE_GATE_FAILED")
    if total <= 0 or outro <= 0 or outro > total or outro_pause < 0.4:
        raise SirajV4PlusContractError("OUTRO_ENTRY_PAUSE_GATE_FAILED")
    if str(meta.get("closing_performance_status") or "") != "PASS":
        raise SirajV4PlusContractError("CLOSING_PERFORMANCE_GATE_FAILED")
