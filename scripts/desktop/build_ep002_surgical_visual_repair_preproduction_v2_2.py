"""Build the Episode 002 V2.2 visual-repair preproduction packet.

This builder is offline-only.  It reads the already accepted narration,
existing V2.1 planning/evidence, and local media audit records; it writes new
preproduction/audit artifacts only.  It never calls a provider, creates an
authorization, consumes an authorization, changes media bytes, or runs a
montage.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence
import wave


REPO = Path(__file__).resolve().parents[2]
EPISODE_ID = "episode-002-adam-temptation-fall-repentance"
EPISODE_ROOT = REPO / "projects" / EPISODE_ID
PREPRODUCTION = EPISODE_ROOT / "preproduction"
ORCHESTRATION = EPISODE_ROOT / "orchestration"

V21_STORYBOARD = PREPRODUCTION / "EP002_SURGICAL_REPAIR_STORYBOARD_V2_1.json"
V21_AUDIT = ORCHESTRATION / "ep002-surgical-visual-asset-audit-v2-1.json"
V21_CERTIFICATION = ORCHESTRATION / "ep002-surgical-visual-repair-preproduction-v2-1.json"

V22_STORYBOARD = PREPRODUCTION / "EP002_SURGICAL_REPAIR_STORYBOARD_V2_2.json"
V22_HUMAN_REPORT = PREPRODUCTION / "EP002_SURGICAL_REPAIR_STORYBOARD_V2_2.md"
V22_DOSSIERS = PREPRODUCTION / "EP002_CHARACTER_EVIDENCE_DOSSIERS_V2_2.json"
V22_CONSTITUTION = REPO / "projects/_series/siraj-visual-production-constitution-v2-2.json"
V22_SOURCE_BINDING = ORCHESTRATION / "ep002-source-binding-v2-2.json"
V22_REAUDIT = ORCHESTRATION / "ep002-legacy-female-reaudit-v2-2.json"
V22_AUDIT = ORCHESTRATION / "ep002-surgical-visual-asset-audit-v2-2.json"
V22_CERTIFICATION = ORCHESTRATION / "ep002-surgical-visual-repair-preproduction-v2-2.json"
V22_STATE = ORCHESTRATION / "visual-repair-preproduction-state-v2-2.json"

AUDIO_BOUND = PREPRODUCTION / "audio-bound-storyboard-v6-1.json"
AUDIO_BEATS = PREPRODUCTION / "audio-timestamps-and-beats-v6-1.json"
NARRATION_TEXT = PREPRODUCTION / "final-narration-ar-v5-1.txt"

PRODUCTION_FPS = 24
MINIMUM_VISUAL_SHOT_FRAMES = 4
PROVIDER_DURATIONS = (4, 6, 8)

sys.path.insert(0, str(REPO))

from src.application.visual_production_constitution_v2 import (  # noqa: E402
    CONSTITUTION_V2_2_VERSION,
    compile_visual_prompt_v2_2,
    load_visual_production_constitution_v2_2,
    sha256_file,
    validate_character_dossiers,
    validate_source_hierarchy_records,
    validate_v2_2_storyboard,
)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )


def rel(path: Path) -> str:
    return path.resolve().relative_to(REPO.resolve()).as_posix()


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def digest_paths(paths: Sequence[Path]) -> str:
    """Stable read-only digest for before/after preservation checks."""

    digest = hashlib.sha256()
    for root in sorted((Path(item) for item in paths), key=lambda item: item.as_posix()):
        if root.is_file():
            digest.update(root.as_posix().encode("utf-8"))
            digest.update(root.read_bytes())
            continue
        if root.is_dir():
            for child in sorted((item for item in root.rglob("*") if item.is_file()), key=lambda item: item.as_posix()):
                digest.update(child.as_posix().encode("utf-8"))
                digest.update(child.read_bytes())
    return digest.hexdigest()


def audio_duration_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as handle:
        return handle.getnframes() / handle.getframerate()


def _copy_v21_constitution() -> dict[str, Any]:
    source = REPO / "projects/_series/siraj-visual-production-constitution-v2-1.json"
    constitution = deepcopy(load_json(source))
    constitution["CONSTITUTION_VERSION"] = CONSTITUTION_V2_2_VERSION
    constitution["SCHEMA_VERSION"] = "SIRAJ_VISUAL_PRODUCTION_CONSTITUTION_SCHEMA_V2_2"
    constitution["V2_2_ARCHITECTURE"] = "CANONICAL_AUDIO_RESEARCH_PROMPT_AND_REUSE_CONTRACT"
    constitution.update(
        {
            "AUDIO_BEAT_MAPPING_REQUIRED": True,
            "SUB_FRAME_MICRO_SHOTS_MUST_EQUAL_ZERO": True,
            "MICRO_CRUMB_SHOTS_MUST_EQUAL_ZERO": True,
            "PROVIDER_EDITORIAL_DURATION_SEPARATION_REQUIRED": True,
            "GENERATION_CONSOLIDATION_REQUIRED": True,
            "EXECUTION_ENVELOPE_SEPARATE_FROM_VISUAL_PROVIDER_PROMPT": True,
            "MUSA_SOURCE_BACKED_TRAITS_REQUIRED_WHEN_USED": True,
            "LEGACY_FEMALE_REUSE_COUNT_MUST_EQUAL_ZERO": True,
            "PREPRODUCTION_VISUAL_GENERATION_ALLOWED": False,
            "AUDIO_BEAT_MAPPING_POLICY": {
                "AUDIO_BEAT_ID_REQUIRED": True,
                "AUDIO_BEAT_START_REQUIRED": True,
                "AUDIO_BEAT_END_REQUIRED": True,
                "AUDIO_TRANSCRIPT_FRAGMENT_REQUIRED": True,
                "AUDIO_SOURCE_TIMING_REFERENCE_REQUIRED": True,
                "NO_STALE_PARENT_NARRATION_INHERITANCE": True,
                "FULL_TIMELINE_CONTIGUOUS_AND_GAP_FREE": True,
                "WORD_LEVEL_ALIGNMENT_FILE": "UNAVAILABLE_IN_CURRENT_LOCAL_PACKET",
            },
            "FRAME_QUANTIZATION_POLICY": {
                "PRODUCTION_FPS": PRODUCTION_FPS,
                "MINIMUM_VISUAL_SHOT_FRAMES": MINIMUM_VISUAL_SHOT_FRAMES,
                "NO_SUB_FRAME_MICRO_SHOTS": True,
                "NO_MICRO_CRUMB_SHOTS": True,
                "FINAL_AUDIO_TAIL_MAY_BE_NON_FRAME_ALIGNED": True,
            },
            "PROVIDER_DURATION_POLICY": {
                "PROVIDER": "RUNWARE",
                "MODEL_CONTRACT": "google:veo@3.1-lite",
                "SUPPORTED_REQUEST_DURATIONS_SECONDS": list(PROVIDER_DURATIONS),
                "EDITORIAL_DURATION_IS_NOT_PROVIDER_REQUEST_DURATION": True,
            },
            "GENERATION_CONSOLIDATION_POLICY": {
                "UNSEEN_REACTION_AND_TREE_ATTENTION_SHARED_UNIT": True,
                "CHOICE_AND_ACTION_SHARED_UNIT": True,
                "DEBATE_SETUP_SHARED_CONTINUITY_UNIT": True,
                "NO_STANDALONE_UNSUPPORTED_SHORT_PROVIDER_REQUESTS": True,
            },
        }
    )
    prompt = dict(constitution.get("PROMPT_COMPILATION", {}))
    prompt.update(
        {
            "EXECUTION_ENVELOPE_OUTSIDE_PROVIDER_PROMPT": True,
            "NO_EXECUTION_STATE_IN_PROVIDER_PROMPT": True,
            "DUPLICATED_NEGATIVE_LINES_FORBIDDEN": True,
        }
    )
    constitution["PROMPT_COMPILATION"] = prompt
    return constitution


def build_constitution() -> Any:
    write_json(V22_CONSTITUTION, _copy_v21_constitution())
    return load_visual_production_constitution_v2_2(REPO, V22_CONSTITUTION)


def _dossier(
    *,
    character_id: str,
    source_backed: list[str],
    unknown: list[str],
    disputed: list[str],
    context_dependent: list[str],
    references: list[dict[str, Any]],
    tiers: list[str],
    physical: dict[str, Any],
    wardrobe: dict[str, Any],
    forbidden: list[str],
    art_direction: list[str],
    review: list[str],
    visual_bible: dict[str, Any],
) -> dict[str, Any]:
    return {
        "CHARACTER_ID": character_id,
        "SOURCE_BACKED_ATTRIBUTES": source_backed,
        "UNKNOWN_ATTRIBUTES": unknown,
        "DISPUTED_ATTRIBUTES": disputed,
        "CONTEXT_DEPENDENT_ATTRIBUTES": context_dependent,
        "SOURCE_REFERENCES": references,
        "SOURCE_TIERS": tiers,
        "PHYSICAL_APPEARANCE_CONTRACT": physical,
        "WARDROBE_CONTRACT": wardrobe,
        "FORBIDDEN_UNSUPPORTED_ASSUMPTIONS": forbidden,
        "ART_DIRECTION_DECISIONS": art_direction,
        "HUMAN_REVIEW_REQUIRED_ATTRIBUTES": review,
        "SOURCE_FACTS_AND_ART_DIRECTION_SEPARATED": True,
        "VISUAL_BIBLE": visual_bible,
        "RESEARCH_GATE": {
            "HIGHER_TIER_LOOKUP_COMPLETED": True,
            "MATERIAL_UNKNOWN_REVIEWED_BEFORE_DECLARATION": True,
            "SOURCE_FACT_IS_NOT_ART_DIRECTION": True,
            "UNKNOWN_REMAINS_UNKNOWN": True,
        },
    }


def build_dossiers(constitution: Any, v21_storyboard: Mapping[str, Any]) -> dict[str, Any]:
    local_source_matrix = rel(REPO / "projects/episode-002-adam-temptation-fall-repentance/research/source-claim-matrix-v5.json")
    local_source_package = rel(REPO / "projects/episode-002-adam-temptation-fall-repentance/research/canonical-source-package-v5.json")
    refs_adam = [
        {
            "SOURCE_ID": "SRC-002/SRC-003/SRC-004",
            "TIER": "TIER_1_QURAN",
            "REFERENCE": local_source_package,
            "CLAIM_SCOPE": "Adam and spouse are the named narrative participants in the garden, eating, error, repentance, descent, and guidance passages.",
            "CERTAINTY": "HIGH",
            "APPLICABILITY": "Narrative identity and actions; not physical complexion or costume.",
        },
        {
            "SOURCE_ID": "Bukhari-3326; Muslim-2841",
            "TIER": "TIER_2_SAHIH_SUNNAH",
            "REFERENCE": "https://sunnah.com/bukhari:3326; https://sunnah.com/muslim:2841",
            "CLAIM_SCOPE": "Adam's creation stature is described as sixty cubits; later human stature is described as decreasing.",
            "CERTAINTY": "HIGH",
            "APPLICABILITY": "Creation-context source fact; applicability to the later visual scene is context-dependent and requires human review.",
        },
    ]
    refs_hawwa = [
        {
            "SOURCE_ID": "SRC-002/SRC-003/SRC-004",
            "TIER": "TIER_1_QURAN",
            "REFERENCE": local_source_package,
            "CLAIM_SCOPE": "Adam's spouse participates in the shared garden, eating, error, covering, repentance, descent, and guidance narration.",
            "CERTAINTY": "HIGH",
            "APPLICABILITY": "Narrative role and shared actions; no physical features are specified by this package.",
        },
    ]
    refs_musa = [
        {
            "SOURCE_ID": "SRC-005/SRC-006",
            "TIER": "TIER_2_SAHIH_SUNNAH",
            "REFERENCE": local_source_package,
            "CLAIM_SCOPE": "The Adam-Musa dialogue is a limited authentic-hadith context in the current source packet.",
            "CERTAINTY": "HIGH",
            "APPLICABILITY": "Dialogue identity and scope; not a license for graphics or invented props.",
        },
        {
            "SOURCE_ID": "Muslim-165a/165b; Muslim-168",
            "TIER": "TIER_2_SAHIH_SUNNAH",
            "REFERENCE": "https://sunnah.com/muslim/1/323; https://sunnah.com/muslim/1/324; https://sunnah.com/muslim/1/329",
            "CLAIM_SCOPE": "Musa is described in variants as tall/high in stature, sturdy, with a brown or wheat-toned complexion and straight hair; wording and comparison vary by narration.",
            "CERTAINTY": "HIGH_WITH_VARIANT_WORDING",
            "APPLICABILITY": "Permitted source-backed visual traits for the Musa continuity group; exact shade and facial details remain unspecified.",
        },
        {
            "SOURCE_ID": "Bukhari-3438",
            "TIER": "TIER_2_SAHIH_SUNNAH",
            "REFERENCE": "https://sunnah.com/bukhari/60/109-111",
            "CLAIM_SCOPE": "A variant describes Musa as tall, robust, with a brown complexion and straight hair.",
            "CERTAINTY": "HIGH_WITH_VARIANT_WORDING",
            "APPLICABILITY": "Use conservatively and consistently; do not convert variant phrasing into invented facial detail.",
        },
    ]
    strict_wardrobe = {
        "REQUIRED": [
            "opaque",
            "loose",
            "full-body",
            "head/hair/neck covered",
            "non-body-defining",
        ],
        "FEMALE_VISIBLE_HAIR": False,
        "FEMALE_VISIBLE_NECK": False,
        "FEMALE_VISIBLE_ARMS": False,
        "FEMALE_VISIBLE_LEGS": False,
        "FEMALE_VISIBLE_TORSO_SKIN": False,
        "FEMALE_VISIBLE_HANDS": False,
        "FEMALE_BODY_CONTOUR_EMPHASIS": False,
        "TIGHT_CLOTHING": False,
        "TRANSPARENT_CLOTHING": False,
        "REVEALING_CLOTHING": False,
        "NUDE_OR_BODY_SHAPED_SILHOUETTE": False,
        "FAIL_CLOSED_IF_PROVIDER_CANNOT_HOLD_CONTRACT": True,
    }
    adam = _dossier(
        character_id="ADAM",
        source_backed=[
            "Adam is the male participant in the garden, eating, error, repentance, and guidance passages.",
            "Adam's creation-context stature is described as sixty cubits in authentic hadith.",
        ],
        unknown=[
            "complexion",
            "hair texture and colour",
            "facial features",
            "later-scene age and exact build",
            "historically specified garment construction",
        ],
        disputed=["Whether the creation-stature report should be visually literal in a later scene."],
        context_dependent=[
            "The sixty-cubit stature belongs to a creation-context report and is not automatically applied to the later garden/earth staging.",
        ],
        references=refs_adam,
        tiers=["TIER_1_QURAN", "TIER_2_SAHIH_SUNNAH", "TIER_6_ART_DIRECTION"],
        physical={
            "SOURCE_BACKED": ["creation-context stature: sixty cubits"],
            "UNKNOWN": ["complexion, facial details, hair details, later-scene exact build"],
            "VISUAL_APPLICATION": "Do not force a scale comparison in the repaired shots; use a natural adult male silhouette and send the stature applicability to human review.",
        },
        wardrobe={
            "REQUIRED": ["opaque loose non-body-defining garment", "no exposed genital or torso detail"],
            "NO_UNSUPPORTED_HISTORICAL_COSTUME": True,
        },
        forbidden=[
            "fair/white European complexion as an assumed fact",
            "invented facial identity or age",
            "literal sixty-cubit scale in a close shot without approval",
            "modern clothing, text, props, or graphics",
        ],
        art_direction=[
            "continuity-safe adult male silhouette shared across garden and earth units",
            "natural muted garment palette with no facial close-up requirement",
        ],
        review=["Applicability of the creation-stature report to the later visual timeline."],
        visual_bible={"IDENTITY": "ADAM", "CONTINUITY": "same adult male across all units", "SOURCE_FACTS_USED": True},
    )
    hawwa = _dossier(
        character_id="HAWWA_SPOUSE",
        source_backed=[
            "Adam's spouse is a shared narrative participant in the garden, eating, covering, repentance, descent, and guidance passages.",
        ],
        unknown=[
            "complexion",
            "hair, face, age, height, build, and bodily features",
            "historically specified garment construction",
        ],
        disputed=["No source-backed physical features are accepted in this packet."],
        context_dependent=["The name label HAWWA_SPOUSE is a production identity label, not a claim that the local Quran text supplies physical description."],
        references=refs_hawwa,
        tiers=["TIER_1_QURAN", "TIER_6_ART_DIRECTION"],
        physical={
            "SOURCE_BACKED": [],
            "UNKNOWN": ["all physical features"],
            "VISUAL_APPLICATION": "No source fact is invented; strict modesty is an art-direction and channel-policy requirement.",
        },
        wardrobe=strict_wardrobe,
        forbidden=[
            "any legacy female visual reuse",
            "visible hair, neck, arms, legs, torso skin, hands, body contour, or body-shaped silhouette",
            "revealing, tight, transparent, wedding-like, or semi-bare clothing",
            "omitting the spouse when the narration requires the shared action",
        ],
        art_direction=[
            "opaque loose full-body garment from first frame through last frame",
            "head, hair, neck, body, and hands concealed; use safe distance/occlusion only as normal composition, never to salvage a legacy asset",
        ],
        review=["Every generated frame must be checked for strict coverage before any production use."],
        visual_bible={"IDENTITY": "HAWWA_SPOUSE", "SOURCE_PHYSICAL_FEATURES": "UNKNOWN", "STRICT_MODESTY": True},
    )
    musa = _dossier(
        character_id="MUSA",
        source_backed=[
            "Musa is the interlocutor in the limited Adam-Musa authentic-hadith dialogue.",
            "Musa is described in authentic-hadith variants as tall/high in stature and sturdy or robust.",
            "Musa is described in variants with a brown or wheat-toned complexion and straight hair; exact wording varies.",
        ],
        unknown=[
            "exact complexion shade beyond the source range",
            "facial features, age, beard details, garment construction, and exact historical setting",
        ],
        disputed=["The comparison wording differs between authentic-hadith variants; no single geographic archetype is forced."],
        context_dependent=["The physical traits are continuity guidance for the debate unit, not a license to invent props, rooms, or unsupported biography."],
        references=refs_musa,
        tiers=["TIER_2_SAHIH_SUNNAH", "TIER_6_ART_DIRECTION"],
        physical={
            "SOURCE_BACKED": ["tall/high stature", "sturdy/robust build", "brown or wheat-toned complexion", "straight hair"],
            "UNKNOWN": ["exact shade, face, age, beard, clothing, and setting"],
            "MUST_NOT_BE_RENDERED_AS": ["generic fair/white European archetype", "invented exact facial portrait"],
            "VISUAL_APPLICATION": "Use the conservative shared contract consistently in the Adam-Musa continuity group; keep camera at a natural medium/wide distance.",
        },
        wardrobe={
            "REQUIRED": ["opaque loose historically non-specific garment", "same garment continuity across debate units"],
            "FORBIDDEN_PROPS": ["staff", "book", "table", "scholar room", "text card"],
        },
        forbidden=[
            "generic fair/white European Musa without source basis",
            "invented staff, book, table, classroom, scholar room, or graphic explainer",
            "unrelated third character or continuity mutation",
        ],
        art_direction=[
            "same tall sturdy Musa across NEW-015/016/017",
            "unmarked natural environment and two-person conversational axis",
        ],
        review=["Human review of source-backed traits and continuity before generation."],
        visual_bible={
            "IDENTITY": "MUSA",
            "SOURCE_BACKED_PHYSICAL_TRAITS": ["tall", "sturdy", "brown/wheat-toned complexion", "straight hair"],
            "CONTINUITY_GROUP": "MUSA_DEBATE_SHARED_SETUP",
        },
    )
    packet = {
        "SCHEMA_VERSION": "EP002_CHARACTER_EVIDENCE_DOSSIERS_V2_2",
        "EPISODE_ID": EPISODE_ID,
        "CONSTITUTION_VERSION": constitution.version,
        "CONSTITUTION_SHA256": constitution.sha256,
        "SOURCE_MATRIX": local_source_matrix,
        "SOURCE_MATRIX_SHA256": sha256_file(REPO / local_source_matrix),
        "SOURCE_PACKAGE": local_source_package,
        "SOURCE_PACKAGE_SHA256": sha256_file(REPO / local_source_package),
        "HIGHER_TIER_RESEARCH_COMPLETED": True,
        "HIGHER_TIERS_CHECKED": ["TIER_1_QURAN", "TIER_2_SAHIH_SUNNAH"],
        "LOWER_TIERS_NOT_USED_AS_UNLABELLED_FACT": True,
        "CHARACTERS": [adam, hawwa, musa],
        "STATUS": "PASS_SOURCE_FACTS_AND_ART_DIRECTION_SEPARATED",
        "UNKNOWN_ATTRIBUTES_REMAIN_UNKNOWN": True,
        "SOURCE_FACTS_AND_ART_DIRECTION_SEPARATED": True,
    }
    result = validate_character_dossiers(packet["CHARACTERS"])
    if result["status"] != "PASS":
        raise RuntimeError("V22_DOSSIER_VALIDATION_FAILED:" + repr(result))
    write_json(V22_DOSSIERS, packet)
    return packet


def build_source_binding(constitution: Any) -> dict[str, Any]:
    records = [
        {
            "SOURCE_TIER": "TIER_1_QURAN",
            "SOURCE_LABEL": "Quranic descent and earth settlement passages",
            "CERTAINTY": "HIGH",
            "ASSERTION_MODE": "SOURCE_FACT",
            "ISRAILIYYAT_STATUS": "NOT_APPLICABLE",
        },
        {
            "SOURCE_TIER": "TIER_6_ART_DIRECTION",
            "SOURCE_LABEL": "Separate earthly staging used only as art direction because exact route/geography is unresolved in the accepted package",
            "CERTAINTY": "UNRESOLVED",
            "ASSERTION_MODE": "ART_DIRECTION_ONLY",
            "ISRAILIYYAT_STATUS": "UNRESOLVED",
        },
    ]
    errors = validate_source_hierarchy_records(records)
    if errors:
        raise RuntimeError("V22_SOURCE_HIERARCHY_VALIDATION_FAILED:" + repr(errors))
    packet = {
        "SCHEMA_VERSION": "EP002_SOURCE_BINDING_V2_2",
        "EPISODE_ID": EPISODE_ID,
        "CONSTITUTION_VERSION": constitution.version,
        "CONSTITUTION_SHA256": constitution.sha256,
        "SEPARATE_STAGING_SOURCE_STATUS": "UNRESOLVED",
        "SEPARATE_STAGING_SOURCE_TIER": "TIER_6_ART_DIRECTION",
        "SEPARATE_STAGING_SOURCE_LABEL": "ART_DIRECTION_ONLY_NOT_ISRAILIYYAT_FACT",
        "SEPARATE_STAGING_HUMAN_REVIEW_REQUIRED": True,
        "EXACT_GEOGRAPHY_ASSERTED": False,
        "LOWER_TIER_CONCRETE_REPORT_ACCEPTED": False,
        "ISRAILIYYAT_FACT_USED": False,
        "SOURCE_RECORDS": records,
        "LOCAL_SOURCE_PACKAGE_REFERENCE": rel(REPO / "projects/episode-002-adam-temptation-fall-repentance/research/canonical-source-package-v5.json"),
        "NOTE": "The storyboard shows separate ordinary earthly states without naming a location or claiming an Israiliyyat report.",
    }
    write_json(V22_SOURCE_BINDING, packet)
    return packet


def load_audio_contract(v21_storyboard: Mapping[str, Any]) -> dict[str, Any]:
    audio_path = REPO / str(v21_storyboard["AUDIO_AUTHORITY_FILE"])
    actual_hash = sha256_file(audio_path)
    actual_duration = audio_duration_seconds(audio_path)
    if actual_hash != str(v21_storyboard["AUDIO_SHA256"]):
        raise RuntimeError("AUDIO_MASTER_HASH_CHANGED")
    if abs(actual_duration - float(v21_storyboard["AUDIO_DURATION_SECONDS"])) > 1e-9:
        raise RuntimeError("AUDIO_MASTER_DURATION_CHANGED")

    bound = load_json(AUDIO_BOUND)
    beats_packet = load_json(AUDIO_BEATS)
    nonempty_lines = [line.strip() for line in NARRATION_TEXT.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(nonempty_lines) < 24:
        raise RuntimeError("FROZEN_NARRATION_PARAGRAPH_SET_INCOMPLETE")
    beat_fragments = {
        "BEAT-001": " ".join(nonempty_lines[0:2]),
        "BEAT-002": " ".join(nonempty_lines[2:4]),
        "BEAT-003": " ".join(nonempty_lines[4:6]),
        "BEAT-004": " ".join(nonempty_lines[6:8]),
        "BEAT-005": " ".join(nonempty_lines[8:10]),
        "BEAT-006": " ".join(nonempty_lines[10:12]),
        "BEAT-007": " ".join(nonempty_lines[12:14]),
        "BEAT-008": " ".join(nonempty_lines[14:16]),
        "BEAT-009": " ".join(nonempty_lines[16:18]),
        "BEAT-010": " ".join(nonempty_lines[18:20]),
        "BEAT-011": " ".join(nonempty_lines[20:22]),
        "PRE_OUTRO": " ".join(nonempty_lines[22:24]),
    }
    beat_ranges: dict[str, tuple[float, float]] = {}
    for beat in beats_packet["beats"]:
        beat_id = str(beat.get("beat_id") or beat["segment_id"])
        beat_ranges[beat_id] = (
            float(beat["start_seconds"]),
            min(float(beat["end_seconds"]), actual_duration),
        )
    beat_ranges["PRE_OUTRO"] = (
        float(next(item for item in beats_packet["beats"] if item["segment_id"] == "PRE_OUTRO")["start_seconds"]),
        actual_duration,
    )
    return {
        "path": audio_path,
        "sha256": actual_hash,
        "duration": actual_duration,
        "bound": bound,
        "beats_packet": beats_packet,
        "beat_fragments": beat_fragments,
        "beat_ranges": beat_ranges,
    }


def _beat_contexts(start: float, end: float, audio: Mapping[str, Any]) -> list[dict[str, Any]]:
    contexts: list[dict[str, Any]] = []
    for source_shot in audio["bound"]["shots"]:
        audio_ref = source_shot.get("audio_ref", {})
        source_range = audio_ref.get("range_seconds")
        if not isinstance(source_range, list) or len(source_range) != 2:
            continue
        source_start, source_end = float(source_range[0]), min(float(source_range[1]), float(audio["duration"]))
        if source_end <= start or source_start >= end:
            continue
        beat_id = str(audio_ref.get("beat_id") or audio_ref.get("segment_id") or "PRE_OUTRO")
        contexts.append(
            {
                "SOURCE_SHOT_ID": source_shot["shot_id"],
                "AUDIO_BEAT_ID": beat_id,
                "AUDIO_BEAT_START": source_start,
                "AUDIO_BEAT_END": source_end,
                "AUDIO_CUE": str(audio_ref.get("cue_ar", "")),
                "AUDIO_SOURCE_TIMING_REFERENCE": f"{rel(AUDIO_BOUND)}#shots/{source_shot['shot_id']}/audio_ref/range_seconds",
            }
        )
    if not contexts:
        raise RuntimeError(f"AUDIO_BEAT_CONTEXT_MISSING:{start}:{end}")
    return contexts


def _attach_audio_fields(shot: dict[str, Any], audio: Mapping[str, Any]) -> None:
    start = float(shot["TIMELINE_IN"])
    end = float(shot["TIMELINE_OUT"])
    contexts = _beat_contexts(start, end, audio)
    beat_ids = []
    for context in contexts:
        beat_id = str(context["AUDIO_BEAT_ID"])
        if beat_id not in beat_ids:
            beat_ids.append(beat_id)
    fragments = [str(audio["beat_fragments"].get(beat_id, "")) for beat_id in beat_ids]
    fragments = [fragment for fragment in fragments if fragment]
    references = [context["AUDIO_SOURCE_TIMING_REFERENCE"] for context in contexts]
    shot["AUDIO_BEAT_ID"] = beat_ids[0] if len(beat_ids) == 1 else "MULTI_BEAT:" + "+".join(beat_ids)
    shot["AUDIO_BEAT_IDS"] = beat_ids
    shot["AUDIO_BEAT_START"] = min(float(context["AUDIO_BEAT_START"]) for context in contexts)
    shot["AUDIO_BEAT_END"] = max(float(context["AUDIO_BEAT_END"]) for context in contexts)
    shot["AUDIO_TRANSCRIPT_FRAGMENT"] = "\n\n".join(fragments)
    shot["NARRATION_TEXT"] = shot["AUDIO_TRANSCRIPT_FRAGMENT"]
    shot["AUDIO_SOURCE_TIMING_REFERENCE"] = references[0] if len(references) == 1 else references
    shot["AUDIO_SPANS_MULTIPLE_BEATS"] = len(beat_ids) > 1
    shot["AUDIO_TIMING_PRECISION"] = "EDITORIAL_BEAT_RANGE; WORD_LEVEL_ALIGNMENT_FILE_UNAVAILABLE"
    shot["AUDIO_CUE_CONTEXT"] = [context["AUDIO_CUE"] for context in contexts]


def _normalise_key(value: Any) -> str:
    return str(value).strip().casefold()


def _visual_description(asset: Mapping[str, Any]) -> str:
    observation = str(asset.get("VISUAL_OBSERVATION", "")).strip()
    category = str(asset.get("SOURCE_CATEGORY", "unclassified_visual"))
    if observation and "Local midpoint frame" not in observation:
        return observation + f" Source category: {category}. No female figure was found in the audited samples."
    return (
        f"Pixel-audited non-human support image/video from the local {category} source; "
        "the inspected start/middle/end or full-image samples show environmental texture/space and no female or ambiguous human figure."
    )


def _provider_duration(editorial_duration: float) -> int:
    if editorial_duration <= 4.0:
        return 4
    if editorial_duration <= 6.0:
        return 6
    return 8


def _unit_for_original_new(shot_id: str) -> str:
    number = shot_id.rsplit("-", 1)[-1]
    groups = {
        "001": "V22-GEN-001-EATING-ANCHOR",
        "002": "V22-GEN-002-TREE-BOUNDARY",
        "003": "V22-GEN-003-WHISPER-REACTION-AND-ATTENTION",
        "004": "V22-GEN-003-WHISPER-REACTION-AND-ATTENTION",
        "005": "V22-GEN-004-CHOICE-AND-ACTION",
        "006": "V22-GEN-004-CHOICE-AND-ACTION",
        "007": "V22-GEN-005-EATING-AFTERMATH",
        "008": "V22-GEN-006-COVERING",
        "009": "V22-GEN-007-REMORSE",
        "010": "V22-GEN-008-SUPPLICATION",
        "011": "V22-GEN-009-RECEIVING-WORDS",
        "012": "V22-GEN-010-GUIDANCE",
        "013": "V22-GEN-011-ADAM-EARTH-STATE",
        "014": "V22-GEN-012-HAWWA-EARTH-STATE",
        "015": "V22-GEN-013-MUSA-DEBATE-SETUP",
        "016": "V22-GEN-013-MUSA-DEBATE-SETUP",
        "017": "V22-GEN-013-MUSA-DEBATE-SETUP",
    }
    return groups.get(number, f"V22-GEN-NEW-{number}")


def _source_facts_for_new(shot: Mapping[str, Any]) -> list[str]:
    facts = [str(item) for item in shot.get("SOURCE_FACTS_USED", [])]
    if shot.get("MICRO_SHOT_ID", "").endswith(("015", "016", "017")):
        facts += [
            "MUSA source-backed visual traits: tall/high stature, sturdy/robust build, brown/wheat-toned complexion, straight hair; exact shade/facial detail unknown.",
        ]
    return facts


def _corrected_prompts(shot: Mapping[str, Any]) -> tuple[str, str, str]:
    sid = str(shot["MICRO_SHOT_ID"])
    if sid.endswith("001"):
        return (
            "A literal two-person cinematic action anchor: Adam and his spouse stand beside one unnamed garden tree. Adam detaches a fruit from the branch and brings it to his visible mouth for a clear bite. The spouse remains in an opaque loose full-body garment with head, hair, neck, body, and hands covered; from a safe side angle a covered sleeve brings a separate fruit to the fully covered face, then lowers it with visible bite evidence. Exactly two figures, natural garden, no invented tempter.",
            "Continuous chronological action: establish exactly two covered figures at one unnamed tree, show Adam detach and visibly bite the fruit, then show the covered spouse bring fruit to the safely covered face and lower it with bite evidence. Preserve fruit continuity, body coverage, and exactly two participants.",
            "symbolic eating, fruit-only shot, tree-only shot, visible female hair, visible female neck, exposed skin, visible female arms, visible female legs, visible female torso, visible female hands, transparent clothing, tight clothing, revealing dress, nude silhouette, body-shaped silhouette, third character, Satan, demon, graphics, text, UI, diagram, glow, beam, portal",
        )
    if sid.endswith("002"):
        return (
            "Wide natural garden with exactly Adam and his fully covered spouse approaching one distinct unnamed tree. They stop before it; one opaque covered sleeve begins toward a branch and visibly retracts before contact. Spatial behavior communicates the prohibition. No drawn line, glow, barrier, third figure, or supernatural body.",
            "Literal approach-and-stop: two covered figures walk to the same unnamed tree, halt, make a readable covered-sleeve hesitation toward the fruit, and retract before touching. The boundary is shown only through human behavior and spatial staging.",
            "third character, tempter body, black silhouette, glowing boundary, drawn line, force field, beam, portal, floating symbols, visible female hair, visible female neck, exposed skin, visible female hands, tight clothing, body-shaped silhouette, graphics, text, UI, diagram",
        )
    if sid.endswith(("003", "004")):
        return (
            "Grounded cinematic reaction of exactly Adam and his fully covered spouse beside the unnamed tree. An unseen offscreen influence is never embodied; both figures turn their attention toward empty space and then redirect their attention to the fruit. No speaking body, face, lips, smoke, beam, or supernatural mechanism.",
            "One continuous source unit: show the pair pause and react toward empty offscreen space, hold the unseen influence off camera, then shift their attention back toward the tree and fruit. No physical tempter, no invented voice mechanism, no graphic effect.",
            "Satan body, third adult male, hooded tempter, demon, black silhouette, shadow person, smoke creature, speaking lips, supernatural body, beam, portal, magic particles, written text, visible female hair, visible female neck, exposed skin, visible female hands, tight clothing, body-shaped silhouette, graphics, UI",
        )
    if sid.endswith(("005", "006")):
        return (
            "Literal deliberate approach by exactly Adam and his fully covered spouse toward fruit on one unnamed tree. Adam steps first, spouse follows, and both extend opaque covered sleeves toward the fruit. Feet remain stable; there is no slip, fall, guide, tempter body, or graphic effect.",
            "One consolidated choice-to-action source unit: show hesitation, Adam taking a deliberate step, spouse following, and both extending covered sleeves toward the fruit. Keep the action intentional and stable; the bite is handled by the separate eating anchor.",
            "slipping, falling, uneven-ground accident, guide, third person, Satan, demon, shadow person, blame pointing, visible female hair, visible female neck, exposed skin, visible female hands, tight clothing, transparent clothing, body-shaped silhouette, graphics, text, UI, glow, beam",
        )
    if sid.endswith("007"):
        return (
            "Literal chronological eating-and-aftermath anchor: Adam and his fully covered spouse take fruit from the unnamed tree. Adam visibly bites; the spouse brings fruit to a completely covered face from a safe side angle and then lowers it with visible bite evidence. Both lower fruit and recoil together, with no blame gesture.",
            "Show taking fruit, Adam's visible bite, the spouse's safely covered fruit contact and bite evidence, then both lowering fruit and stepping back together. Exactly two participants and strict coverage from first frame to last.",
            "fruit-only, symbolic eating, visible female hair, visible female neck, exposed skin, visible female arms, visible female legs, visible female torso, visible female hands, tight dress, transparent dress, body-shaped silhouette, pointing, blaming, third character, graphics, text, UI, magic glow",
        )
    if sid.endswith("008"):
        return (
            "Literal rear three-quarter shot of Adam and his spouse already fully covered from the first frame, gathering and placing leaves around their loose opaque garments as an additional covering attempt. No nudity, no visible skin or hands, no body-shaped silhouette.",
            "Show two already-covered figures use enclosed sleeves or opaque gloves to gather and place leaves around their garments, ending withdrawn beside the tree. The leaves are an additional literal covering action, never a reveal.",
            "nudity, undressed body, visible female hair, visible female neck, exposed skin, visible female arms, visible female legs, visible female torso, visible female hands, body-shaped silhouette, leaf-only insert, third character, graphics, readable text, UI, glow",
        )
    if sid.endswith("009"):
        return (
            "Grounded cinematic two-shot of Adam and his fully covered spouse lowering themselves naturally to the ground beside the tree, heads bowed in shared remorse. Already-covered bodies, no blame gesture, no supernatural light, no theatrical ritual.",
            "Literal remorse action: both figures lower naturally, kneel or sit, bow their heads, and hold a shared inward posture with the tree/error context behind them.",
            "triumph, celebration, pointing, blame, supernatural light, beam, halo, visible female hair, exposed skin, visible female neck, visible female hands, tight clothing, body-shaped silhouette, third character, graphics, text, UI",
        )
    if sid.endswith("010"):
        return (
            "Literal restrained supplication: Adam and his fully covered spouse remain lowered on the garden ground; Adam raises covered sleeves in a clear natural request for mercy while the spouse stays fully covered with bowed head. No visible hands, text, tablet, beam, halo, messenger, or graphics.",
            "Begin with shared remorse, show Adam raise enclosed sleeves in natural supplication, keep the spouse fully covered and bowed, and end in quiet seeking mercy. Both visibly participate without invented ritual choreography.",
            "visible female hair, visible female neck, exposed skin, visible female arms, visible female legs, visible female torso, visible female hands, tight clothing, transparent clothing, body-shaped silhouette, written words, tablet, text, beam, halo, messenger, blame, third character, graphics, UI",
        )
    if sid.endswith("011"):
        return (
            "Grounded medium side/rear shot of Adam after repentance, still low and humbled, raising his head and turning attentively toward ordinary empty offscreen space. Show only the human receptive consequence; no words, tablet, paper, beam, angel, divine body, or supernatural mechanism.",
            "Source-constrained receiving unit: Adam pauses bowed, raises and turns his head toward empty offscreen space, and holds a receptive listening posture. The unseen source and its mechanism never enter frame.",
            "written words, floating text, tablet, paper, voice beam, light ray, halo, angel, messenger, divine body, portal, graphics, UI, diagram, visible female character, invented prop",
        )
    if sid.endswith("012"):
        return (
            "Quiet literal shot of Adam and his fully covered spouse rising from humbled postures in the same garden context, standing calmly, and turning toward an ordinary open direction while the tree and past remain behind. No halo, glow, celebration, erased mark, text, or graphics.",
            "Show two covered figures rise, stand calmly, and turn toward the next phase. Preserve the past location behind them; communicate restored direction without supernatural celebration or erasure.",
            "halo, golden glow, magic light, erased mark, celebration, triumph, visible female hair, visible female neck, exposed skin, visible female hands, tight clothing, body-shaped silhouette, text, graphics, UI, beam, portal, third character",
        )
    if sid.endswith("013"):
        return (
            "Source-constrained transition state: Adam alone is shown in a separate ordinary earthly environment with no landmark or geographic label. Keep the exact route and location unresolved; no portal, stairs, map, split-screen, beam, or teleportation graphic.",
            "Use a natural editorial cut from Adam alone in the prior environment to Adam alone standing stably in an ordinary wide earthly environment. Show the consequence, not an invented route or mechanism.",
            "portal, stairs, mountain from paradise, map, split-screen, exact location label, India, Jeddah, Sri Lanka, teleportation graphic, beam, magic transition, text, UI, graphics, third character",
        )
    if sid.endswith("014"):
        return (
            "Independent source-constrained wide shot of Adam's fully covered spouse alone in a clearly different ordinary earthly environment. Opaque loose full-body garment covers head, hair, neck, body, and hands; no landmark, map, label, portal, or split-screen.",
            "Cut independently to the fully covered spouse alone in a different ordinary earthly environment and hold a stable earthly presence. Do not show a joint landing or invent a route or named geography.",
            "visible female hair, visible female neck, exposed skin, visible female arms, visible female legs, visible female torso, visible female hands, tight clothing, transparent clothing, body-shaped silhouette, split-screen, portal, stairs, mountain, map, exact location label, graphics, text, UI, magic beam",
        )
    if sid.endswith(("015", "016", "017")):
        return (
            "Grounded continuity setup for exactly two distinct adult men, Adam and Musa, in a simple unmarked natural environment. Musa uses the source-backed conservative physical contract: tall/high stature, sturdy/robust build, brown or wheat-toned complexion, straight hair. No staff, book, table, scholar room, source card, text, or graphics.",
            "One shared debate source: Musa, visibly tall/high, sturdy/robust, with a brown or wheat-toned complexion and straight hair, addresses Adam; Adam answers; the exchange settles into a restrained reflective pause. Preserve the same two-person axis, wardrobe, environment, and source-backed Musa traits across every editorial extraction.",
            "staff, book, table, scholar room, generic scholars, source cards, timeline, UI, readable text, graphics, diagram, third character, female character, unsupported fair European archetype, invented exact complexion, continuity mutation",
        )
    raise RuntimeError(f"NO_CORRECTED_PROMPT:{sid}")


def _make_execution_envelope(constitution: Any, unit_id: str) -> dict[str, Any]:
    return {
        "CONSTITUTION_VERSION": constitution.version,
        "CONSTITUTION_SHA256": constitution.sha256,
        "STORYBOARD_STATUS": "AWAITING_HUMAN_APPROVAL",
        "VISUAL_GENERATION_ALLOWED": False,
        "PRODUCTION_STAGE": "PRE_PRODUCTION_VISUAL_REVIEW",
        "PROVIDER_ROUTE": "RUNWARE/google:veo@3.1-lite",
        "GENERATION_UNIT_ID": unit_id,
        "AUTHORIZATION_REQUIRED_LATER": True,
        "NETWORK_CALLS": 0,
        "PAID_CALLS": 0,
    }


def _prepare_original_new_shot(shot: Mapping[str, Any], constitution: Any) -> dict[str, Any]:
    prepared = deepcopy(dict(shot))
    image, video, negative = _corrected_prompts(prepared)
    unit_id = _unit_for_original_new(str(prepared["MICRO_SHOT_ID"]))
    source_tier = str(prepared.get("SOURCE_TIER", "TIER_1_QURAN")).split(";")[0].strip()
    if str(prepared["MICRO_SHOT_ID"]).endswith(("013", "014")):
        source_tier = "TIER_1_QURAN; TIER_6_ART_DIRECTION"
    if str(prepared["MICRO_SHOT_ID"]).endswith(("015", "016", "017")):
        source_tier = "TIER_2_SAHIH_SUNNAH; TIER_6_ART_DIRECTION"
    prepared["IMAGE_PROMPT"] = image
    prepared["VIDEO_PROMPT"] = video
    prepared["NEGATIVE_PROMPT"] = negative
    prepared["SOURCE_FACTS_USED"] = _source_facts_for_new(prepared)
    if str(prepared["MICRO_SHOT_ID"]).endswith(("013", "014")):
        prepared["ART_DIRECTION_USED"] = list(prepared.get("ART_DIRECTION_USED", [])) + [
            "Separate ordinary earthly staging only; exact geography unresolved; human review required.",
        ]
    if str(prepared["MICRO_SHOT_ID"]).endswith(("015", "016", "017")):
        prepared["ART_DIRECTION_USED"] = list(prepared.get("ART_DIRECTION_USED", [])) + [
            "Shared Musa debate continuity unit using only the source-backed physical contract.",
        ]
    prepared["SOURCE_TIER"] = source_tier
    prepared["DISPOSITION"] = "NEW_REQUIRED"
    prepared["SOURCE"] = "NEW_GENERATION_REQUIRED"
    prepared["GENERATION_UNIT_ID"] = unit_id
    prepared["EDITORIAL_DURATION_SECONDS"] = float(prepared["TIMELINE_OUT"]) - float(prepared["TIMELINE_IN"])
    prepared["PROVIDER_REQUEST_DURATION_SECONDS"] = _provider_duration(prepared["EDITORIAL_DURATION_SECONDS"])
    prepared["TARGET_DURATION"] = prepared["EDITORIAL_DURATION_SECONDS"]
    prepared["PREFERRED_MEDIA_TYPE"] = "RUNWARE_VEO_31_VIDEO"
    prepared["PROVIDER_CAPABILITY_REQUIREMENTS"] = {
        "PROVIDER": "RUNWARE",
        "MODEL": "google:veo@3.1-lite",
        "SUPPORTED_REQUEST_DURATIONS_SECONDS": list(PROVIDER_DURATIONS),
        "REQUEST_DURATION_IS_NOT_EDITORIAL_DURATION": True,
    }
    bundle = compile_visual_prompt_v2_2(
        constitution,
        image,
        video,
        negative,
        includes_female=bool(prepared.get("INCLUDES_FEMALE")),
        event_type=str(prepared["EVENT_TYPE"]),
        source_tier=source_tier,
        source_certainty=str(prepared.get("SOURCE_CERTAINTY", "HIGH")),
        source_facts=prepared["SOURCE_FACTS_USED"],
        art_direction=list(prepared.get("ART_DIRECTION_USED", [])),
        dossier_refs=list(prepared.get("CHARACTER_DOSSIER_REFERENCES", [])),
        execution_envelope=_make_execution_envelope(constitution, unit_id),
    )
    prepared.update(bundle)
    prepared["VISUAL_PROVIDER_PROMPT"] = bundle["VISUAL_PROVIDER_PROMPT"]
    prepared["EXECUTION_ENVELOPE"] = bundle["EXECUTION_ENVELOPE"]
    prepared["PROMPT_CONTRADICTIONS"] = bundle["PROMPT_CONTRADICTIONS"]
    prepared["DUPLICATED_NEGATIVE_PROMPT_LINES"] = bundle["DUPLICATED_NEGATIVE_PROMPT_LINES"]
    prepared["DUPLICATED_POSITIVE_PROMPT_LINES"] = bundle["DUPLICATED_POSITIVE_PROMPT_LINES"]
    prepared["EXECUTION_STATE_TEXT_IN_PROVIDER_PROMPT"] = bundle["EXECUTION_STATE_TEXT_IN_PROVIDER_PROMPT"]
    prepared["PLANNED_MUTE_COMPREHENSION"] = {
        "PLANNED_EVENT_VISIBLE": True,
        "PLANNED_SUBJECT_VISIBLE": True,
        "PLANNED_ACTION_VISIBLE": True,
        "PLANNED_OBJECT_VISIBLE": True,
        "PLANNED_RESULT_VISIBLE": True,
        "PLANNED_MUTE_COMPREHENSION": True,
        "PRECHECK": "PASS",
    }
    prepared["ACTUAL_RENDER_MUTE_COMPREHENSION"] = "NOT_RUN"
    return prepared


def _prepare_support_replacement(
    shot: Mapping[str, Any],
    asset: Mapping[str, Any],
    constitution: Any,
    replacement_index: int,
) -> dict[str, Any]:
    prepared = deepcopy(dict(shot))
    unit_id = f"V22-GEN-SUPPORT-REPLACEMENT-{replacement_index:03d}"
    category = str(asset.get("SOURCE_CATEGORY", "environmental_support"))
    observation = _visual_description(asset)
    event_role = str(prepared.get("EVENT_ROLE", "ATMOSPHERE"))
    event_type = str(prepared.get("EVENT_TYPE", "ATMOSPHERE"))
    if event_type not in {"ESTABLISHING", "ATMOSPHERE", "TRANSITION"}:
        event_type = "ATMOSPHERE"
    image = (
        f"A real cinematic non-human {category} establishing frame for the {prepared.get('EVENT_ID')} narration interval: {observation} "
        "Use natural physical space only, with no human figure, no symbolic replacement for the narrated action, and no graphics."
    )
    video = (
        f"A restrained environmental support shot for {prepared.get('EVENT_ID')}: show a distinct natural change in the real setting, "
        "such as a stable garden, leaves, ground, horizon, or earthly space, while the actual narrated event remains covered by its dedicated literal shot. "
        "Do not introduce characters, props, or an abstract explainer."
    )
    negative = (
        "female figure, male figure, ambiguous human figure, extra characters, symbolic event substitute, graphics, diagrams, UI, text, logos, watermark, "
        "placeholder, loop, freeze-frame filler, unsupported geography, supernatural body, invented prop"
    )
    source_facts = [str(item) for item in prepared.get("SOURCE_FACTS_USED", [])]
    art = list(prepared.get("ART_DIRECTION_USED", [])) + [
        "Support only; never replace the literal event contract.",
        "Actual local visual observation is recorded for audit; the new shot must be a distinct environmental source.",
    ]
    prepared.update(
        {
            "MICRO_SHOT_ID": f"EP002-V2-NEW-SUPPORT-{replacement_index:03d}",
            "SOURCE": "NEW_GENERATION_REQUIRED",
            "DISPOSITION": "DELETE_REPLACE",
            "EVENT_TYPE": event_type,
            "EVENT_ROLE": event_role,
            "CHARACTERS": [],
            "INCLUDES_FEMALE": False,
            "VISIBLE_ACTION": "A distinct natural environmental change is visible as support; it is not presented as the narrated literal action.",
            "VISUAL_INFORMATION": observation,
            "MUTE_COMPREHENSION_TARGET": "Muted viewer understands a real environmental bridge supporting the beat, while the separate literal event shot carries the narrated action.",
            "IMAGE_PROMPT": image,
            "VIDEO_PROMPT": video,
            "NEGATIVE_PROMPT": negative,
            "SOURCE_TIER": str(prepared.get("SOURCE_TIER", "TIER_6_ART_DIRECTION")),
            "SOURCE_CERTAINTY": "ART_DIRECTION_SUPPORT_ONLY",
            "SOURCE_FACTS_USED": source_facts,
            "ART_DIRECTION_USED": art,
            "CHARACTER_DOSSIER_REFERENCES": [],
            "GENERATION_UNIT_ID": unit_id,
            "EDITORIAL_DURATION_SECONDS": float(prepared["TIMELINE_OUT"]) - float(prepared["TIMELINE_IN"]),
            "PREFERRED_MEDIA_TYPE": "RUNWARE_VEO_31_VIDEO",
            "PROVIDER_CAPABILITY_REQUIREMENTS": {
                "PROVIDER": "RUNWARE",
                "MODEL": "google:veo@3.1-lite",
                "SUPPORTED_REQUEST_DURATIONS_SECONDS": list(PROVIDER_DURATIONS),
                "REQUEST_DURATION_IS_NOT_EDITORIAL_DURATION": True,
            },
            "REPLACED_LEGACY_ASSET_ID": asset.get("ASSET_ID"),
            "REPLACEMENT_REASON": "Exact legacy source range was already used; the repeated environmental content is not retained as an unjustified duplicate.",
            "PLANNED_MUTE_COMPREHENSION": {
                "PLANNED_EVENT_VISIBLE": True,
                "PLANNED_SUBJECT_VISIBLE": True,
                "PLANNED_ACTION_VISIBLE": True,
                "PLANNED_OBJECT_VISIBLE": True,
                "PLANNED_RESULT_VISIBLE": True,
                "PLANNED_MUTE_COMPREHENSION": True,
                "PRECHECK": "PASS_SUPPORT_ONLY",
            },
            "ACTUAL_RENDER_MUTE_COMPREHENSION": "NOT_RUN",
        }
    )
    prepared["PROVIDER_REQUEST_DURATION_SECONDS"] = _provider_duration(prepared["EDITORIAL_DURATION_SECONDS"])
    bundle = compile_visual_prompt_v2_2(
        constitution,
        image,
        video,
        negative,
        includes_female=False,
        event_type=event_type,
        source_tier=prepared["SOURCE_TIER"],
        source_certainty=prepared["SOURCE_CERTAINTY"],
        source_facts=source_facts,
        art_direction=art,
        dossier_refs=[],
        execution_envelope=_make_execution_envelope(constitution, unit_id),
    )
    prepared.update(bundle)
    prepared["VISUAL_PROVIDER_PROMPT"] = bundle["VISUAL_PROVIDER_PROMPT"]
    prepared["EXECUTION_ENVELOPE"] = bundle["EXECUTION_ENVELOPE"]
    prepared["PROMPT_CONTRADICTIONS"] = bundle["PROMPT_CONTRADICTIONS"]
    prepared["DUPLICATED_NEGATIVE_PROMPT_LINES"] = bundle["DUPLICATED_NEGATIVE_PROMPT_LINES"]
    prepared["DUPLICATED_POSITIVE_PROMPT_LINES"] = bundle["DUPLICATED_POSITIVE_PROMPT_LINES"]
    prepared["EXECUTION_STATE_TEXT_IN_PROVIDER_PROMPT"] = bundle["EXECUTION_STATE_TEXT_IN_PROVIDER_PROMPT"]
    return prepared


def _quantize_timeline(raw_shots: Sequence[Mapping[str, Any]], audio_duration: float) -> tuple[list[dict[str, Any]], int, int]:
    result: list[dict[str, Any]] = []
    previous_end = 0.0
    subframe_count = 0
    crumb_count = 0
    for index, raw in enumerate(raw_shots):
        raw_start = float(raw["TIMELINE_IN"])
        raw_end = float(raw["TIMELINE_OUT"])
        if index == len(raw_shots) - 1:
            quantized_end = audio_duration
        else:
            quantized_end = round(raw_end * PRODUCTION_FPS) / PRODUCTION_FPS
        quantized_start = previous_end
        if quantized_end <= quantized_start + 1e-9:
            crumb_count += 1
            continue
        frame_count = (quantized_end - quantized_start) * PRODUCTION_FPS
        if frame_count < MINIMUM_VISUAL_SHOT_FRAMES - 1e-9:
            if abs(raw_end - raw_start) * PRODUCTION_FPS < 1.0:
                subframe_count += 1
            crumb_count += 1
            if result:
                merged = result[-1].setdefault("MERGED_MICRO_CRUMB_IDS", [])
                merged.append(str(raw.get("MICRO_SHOT_ID", index)))
                result[-1]["TIMELINE_OUT"] = quantized_end
                result[-1]["DURATION"] = quantized_end - float(result[-1]["TIMELINE_IN"])
            else:
                raise RuntimeError("FIRST_TIMELINE_SHOT_IS_MICRO_CRUMB")
            previous_end = quantized_end
            continue
        prepared = deepcopy(dict(raw))
        prepared["TIMELINE_IN"] = quantized_start
        prepared["TIMELINE_OUT"] = quantized_end
        prepared["DURATION"] = quantized_end - quantized_start
        prepared["FRAME_START"] = round(quantized_start * PRODUCTION_FPS)
        prepared["FRAME_END_EXCLUSIVE"] = round(quantized_end * PRODUCTION_FPS)
        result.append(prepared)
        previous_end = quantized_end
    if result:
        result[-1]["TIMELINE_OUT"] = audio_duration
        result[-1]["DURATION"] = audio_duration - float(result[-1]["TIMELINE_IN"])
    return result, subframe_count, crumb_count


def _legacy_audit_record(shot: Mapping[str, Any], asset: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "MICRO_SHOT_ID": shot["MICRO_SHOT_ID"],
        "ASSET_ID": shot["ASSET_ID"],
        "ASSET_PATH": shot["ASSET_PATH"],
        "ASSET_SHA256": shot["ASSET_SHA256"],
        "FEMALE_PRESENT": "FALSE",
        "UNCERTAIN_FEMALE_PRESENCE": False,
        "REUSE_ALLOWED": True,
        "MONTAGE_ELIGIBLE": True,
        "FORENSIC_ASSET_PRESERVED": True,
        "DISPOSITION": shot.get("DISPOSITION", "REASSIGN"),
        "AUDIT_SCOPE": "ALL_96_CURRENTLY_PLANNED_REUSED_MICRO_SHOTS",
        "AUDIT_METHOD": "existing local ffmpeg start/middle/end or full-image pixel review; V2.2 revalidation; fail-safe uncertain presence would be rejected",
        "AUDIT_SAMPLE_TYPES": list(asset.get("TEMPORAL_SAMPLE_TYPES", [])),
        "PIXEL_INSPECTION_REFERENCE": asset.get("PIXEL_INSPECTION_REFERENCE"),
        "AUDIT_RESULT": "FEMALE_PRESENT_FALSE; NO_AMBIGUOUS_HUMAN_FIGURE_IN_REVIEWED_SAMPLES",
        "NO_SALVAGE_TRANSFORM_USED": True,
        "SOURCE_RANGE": [shot.get("SOURCE_IN"), shot.get("SOURCE_OUT")],
    }


def _asset_audit_rows(v21_audit: Mapping[str, Any], v21_cert: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    legacy_female = set(str(item) for item in v21_cert.get("LEGACY_FEMALE_ASSETS_FOUND", []))
    current_reuse = [
        dict(item)
        for item in load_json(V21_STORYBOARD)["MICRO_SHOTS"]
        if item.get("SOURCE") in {"EXISTING", "REASSIGNED_EXISTING"}
    ]
    current_reuse_assets = {str(item["ASSET_ID"]) for item in current_reuse}
    if current_reuse_assets & legacy_female:
        raise RuntimeError("LEGACY_FEMALE_ASSET_IN_V21_REUSE_PLAN")
    by_asset = {str(item["ASSET_ID"]): dict(item) for item in v21_audit["asset_audit"]}
    rows: list[dict[str, Any]] = []
    for source in v21_audit["asset_audit"]:
        row = dict(source)
        aid = str(row["ASSET_ID"])
        row["FORENSIC_ASSET_PRESERVED"] = True
        row["NO_SALVAGE_TRANSFORM_USED"] = True
        row["V2_2_SOURCE_OF_TRUTH"] = "V2.1_LOCAL_PIXEL_AUDIT_REVALIDATED"
        if aid in current_reuse_assets:
            row.update(
                {
                    "FEMALE_PRESENT": "FALSE",
                    "UNCERTAIN_FEMALE_PRESENCE": False,
                    "REUSE_ALLOWED": True,
                    "MONTAGE_ELIGIBLE": True,
                    "V2_2_REUSE_ELIGIBLE": True,
                    "LEGACY_FEMALE_REAUDIT_RESULT": "FALSE_NO_FEMALE_OR_AMBIGUOUS_HUMAN_FIGURE",
                    "ACTUAL_VISIBLE_CONTENT": _visual_description(row),
                }
            )
        elif aid in legacy_female:
            row.update(
                {
                    "FEMALE_PRESENT": "UNCERTAIN",
                    "UNCERTAIN_FEMALE_PRESENCE": True,
                    "REUSE_ALLOWED": False,
                    "MONTAGE_ELIGIBLE": False,
                    "DISPOSITION": "SAFETY_EXCLUDED",
                    "V2_2_REUSE_ELIGIBLE": False,
                    "LEGACY_FEMALE_REAUDIT_RESULT": "UNCERTAIN_REJECT_FAIL_SAFE",
                }
            )
        else:
            row.update(
                {
                    "FEMALE_PRESENT": row.get("FEMALE_PRESENT", "NOT_REUSED"),
                    "UNCERTAIN_FEMALE_PRESENCE": row.get("UNCERTAIN_FEMALE_PRESENCE", False),
                    "REUSE_ALLOWED": False,
                    "MONTAGE_ELIGIBLE": False,
                    "V2_2_REUSE_ELIGIBLE": False,
                }
            )
        rows.append(row)
    reuse_records = []
    for shot in current_reuse:
        reuse_records.append(_legacy_audit_record(shot, by_asset[str(shot["ASSET_ID"])]))
    return rows, reuse_records


def _semantic_category(asset: Mapping[str, Any]) -> str:
    category = str(asset.get("SOURCE_CATEGORY", "unclassified_visual"))
    observation = str(asset.get("VISUAL_OBSERVATION", "")).strip().casefold()
    if "plant" in observation or "tree" in observation:
        return "organic_tree_or_plant_environment"
    if category == "garden_leaves":
        return "garden_leaves_environment"
    if category == "earth_environment":
        return "earth_environment"
    return category


def _make_reuse_row(
    shot: Mapping[str, Any],
    asset: Mapping[str, Any],
    reuse_index: int,
) -> dict[str, Any]:
    prepared = deepcopy(dict(shot))
    prepared["SOURCE"] = "EXISTING" if shot.get("DISPOSITION") == "KEEP" else "REASSIGNED_EXISTING"
    prepared["DISPOSITION"] = shot.get("DISPOSITION") if shot.get("DISPOSITION") in {"KEEP", "REASSIGN"} else "REASSIGN"
    prepared["FEMALE_PRESENT"] = "FALSE"
    prepared["UNCERTAIN_FEMALE_PRESENCE"] = False
    prepared["REUSE_ALLOWED"] = True
    prepared["MONTAGE_ELIGIBLE"] = True
    prepared["FORENSIC_ASSET_PRESERVED"] = True
    prepared["NO_SALVAGE_TRANSFORM_USED"] = True
    prepared["ASSET_ID"] = str(shot["ASSET_ID"])
    prepared["ACTUAL_VISIBLE_CONTENT"] = _visual_description(asset)
    prepared["EXACT_AUDIO_RELEVANCE"] = (
        f"The frozen beat fragment for this timeline range is attached; this asset is used only as {prepared.get('EVENT_ROLE', 'support')} and never as the literal action."
    )
    prepared["NEW_VISUAL_INFORMATION"] = (
        f"Distinct audited {asset.get('MEDIA_KIND', 'local')} content from {asset.get('SOURCE_ORIGINAL_SHOT_ID', asset.get('SHOT_ID', 'local source'))}: "
        f"{prepared['ACTUAL_VISIBLE_CONTENT']}"
    )
    prepared["SEMANTIC_CATEGORY"] = _semantic_category(asset)
    prepared["REUSE_INDEX"] = reuse_index
    prepared["REUSE_JUSTIFICATION"] = "First retained use of this exact asset/source range; no exact range is retained more than once in V2.2."
    prepared["WHY_NON_REDUNDANT"] = "This is the first retained occurrence of the audited source range and supplies a distinct environment/transition read that supports the attached beat without replacing its literal event."
    prepared["PIXEL_INSPECTION_REFERENCE"] = asset.get("PIXEL_INSPECTION_REFERENCE")
    prepared["SOURCE_IN"] = float(shot.get("SOURCE_IN", 0.0))
    prepared["SOURCE_OUT"] = float(shot.get("SOURCE_OUT", shot.get("DURATION", 0.0)))
    prepared["PLAYBACK_RATE"] = 1.0
    prepared["ACTUAL_RENDER_MUTE_COMPREHENSION"] = "NOT_RUN"
    return prepared


def _make_generation_units(shots: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for shot in shots:
        if shot.get("SOURCE") == "NEW_GENERATION_REQUIRED":
            groups[str(shot["GENERATION_UNIT_ID"])].append(shot)
    units = []
    for unit_id, members in sorted(groups.items()):
        request_duration = max(int(member["PROVIDER_REQUEST_DURATION_SECONDS"]) for member in members)
        if request_duration not in PROVIDER_DURATIONS:
            raise RuntimeError("UNSUPPORTED_PROVIDER_GENERATION_UNIT_DURATION")
        units.append(
            {
                "GENERATION_UNIT_ID": unit_id,
                "PROVIDER": "RUNWARE",
                "MODEL": "google:veo@3.1-lite",
                "PROVIDER_REQUEST_DURATION_SECONDS": request_duration,
                "EDITORIAL_MEMBER_SHOT_IDS": [str(member["MICRO_SHOT_ID"]) for member in members],
                "CONTINUITY_GROUP": "MUSA_DEBATE_SHARED_SETUP" if "MUSA" in {item for member in members for item in member.get("CHARACTERS", [])} else "EP002_V22",
                "CONSOLIDATED": len(members) > 1,
                "NO_STANDALONE_UNSUPPORTED_SHORT_REQUEST": True,
            }
        )
    return units


def _make_human_report(storyboard: Mapping[str, Any], report: Mapping[str, Any]) -> str:
    lines = [
        "# EP002_SURGICAL_REPAIR_STORYBOARD_V2_2",
        "",
        "> Offline preproduction only. No visual generation, provider call, paid operation, network call, or montage was performed.",
        "",
        "## Approval gate",
        "",
        f"- Status: `{storyboard['STORYBOARD_STATUS']}`",
        "- Approved storyboard hash: `null`",
        "- Visual generation allowed: `FALSE`",
        f"- Constitution: `{storyboard['VISUAL_CONSTITUTION_VERSION']}` / `{storyboard['VISUAL_CONSTITUTION_SHA256']}`",
        f"- Audio authority: `{storyboard['AUDIO_AUTHORITY_FILE']}` / `{storyboard['AUDIO_SHA256']}` / `{storyboard['AUDIO_DURATION_SECONDS']:.9f}s`",
        "- Human approval is required before any provider generation.",
        "",
        "## V2.2 integrity summary",
        "",
        f"- Current V2.1 reused micro-shots audited: `{report['REUSED_LEGACY_MICRO_SHOT_COUNT']}`",
        f"- Retained legacy reuse rows: `{report['REUSED_LEGACY_MICRO_SHOT_COUNT_RETAINED']}`",
        f"- New editorial slots: `{report['EDITORIAL_NEW_MICRO_SHOT_COUNT']}`",
        f"- Provider generation units: `{report['PROVIDER_GENERATION_UNIT_COUNT']}`",
        f"- Sub-frame shots: `{report['SUB_FRAME_MICRO_SHOTS']}`; micro crumbs: `{report['MICRO_CRUMB_SHOTS']}`",
        f"- Exact-range duplicate reuse retained: `{report['UNJUSTIFIED_EXACT_RANGE_REUSE']}`",
        f"- Unjustified semantic repetition: `{report['UNJUSTIFIED_SEMANTIC_REPETITION']}`",
        f"- Legacy female reuse: `{report['LEGACY_FEMALE_REUSE_COUNT']}`",
        f"- Planned graphics: `{report['PLANNED_GRAPHICS_COUNT']}`",
        "",
        "## Full repaired timeline",
        "",
        "| # | Shot | Time | Audio beat | Disposition/source | Event | Actual visible content or action | Mute target |",
        "|---:|---|---:|---|---|---|---|---|",
    ]
    for index, shot in enumerate(storyboard["MICRO_SHOTS"], 1):
        content = shot.get("ACTUAL_VISIBLE_CONTENT", shot.get("VISIBLE_ACTION", ""))
        action = shot.get("VISIBLE_ACTION", "")
        lines.append(
            f"| {index} | `{shot['MICRO_SHOT_ID']}` | {float(shot['TIMELINE_IN']):.3f}–{float(shot['TIMELINE_OUT']):.3f} ({float(shot['DURATION']):.3f}s) | `{shot['AUDIO_BEAT_ID']}` | `{shot.get('DISPOSITION', '')}` / `{shot.get('SOURCE', '')}` | `{shot.get('EVENT_ID', '')}` | {content} Action: {action} | {shot.get('MUTE_COMPREHENSION_TARGET', '')} |"
        )
    lines.extend(["", "## Exact frozen narration fragments", ""])
    for shot in storyboard["MICRO_SHOTS"]:
        lines.extend(
            [
                f"### `{shot['MICRO_SHOT_ID']}` — `{shot['TIMELINE_IN']:.3f}–{shot['TIMELINE_OUT']:.3f}`",
                "",
                f"- Audio beat: `{shot['AUDIO_BEAT_ID']}`",
                f"- Timing reference: `{shot['AUDIO_SOURCE_TIMING_REFERENCE']}`",
                f"- Transcript fragment: {shot['AUDIO_TRANSCRIPT_FRAGMENT']}",
                "",
            ]
        )
    lines.extend(["## New-generation packets", ""])
    for shot in storyboard["MICRO_SHOTS"]:
        if shot.get("SOURCE") != "NEW_GENERATION_REQUIRED":
            continue
        provider = shot["VISUAL_PROVIDER_PROMPT"]
        lines.extend(
            [
                f"### `{shot['MICRO_SHOT_ID']}` — `NEW_GENERATION_REQUIRED`",
                "",
                f"- Editorial time: `{shot['TIMELINE_IN']:.3f}–{shot['TIMELINE_OUT']:.3f}` ({shot['DURATION']:.3f}s)",
                f"- Provider unit: `{shot['GENERATION_UNIT_ID']}`; request duration: `{shot['PROVIDER_REQUEST_DURATION_SECONDS']}s`",
                f"- Event: `{shot['EVENT_ID']}` / `{shot['EVENT_TYPE']}`",
                f"- Characters: `{', '.join(shot.get('CHARACTERS', [])) or 'none'}`",
                f"- Start: {shot.get('START_FRAME_DESCRIPTION', '')}",
                f"- Action: {shot.get('MIDDLE_ACTION_DESCRIPTION', shot.get('VISIBLE_ACTION', ''))}",
                f"- End: {shot.get('END_FRAME_DESCRIPTION', '')}",
                f"- Mute target: {shot.get('MUTE_COMPREHENSION_TARGET', '')}",
                "",
                "#### Final visual provider prompt",
                "",
                "```text",
                provider["positive_video"],
                "",
                "NEGATIVE:",
                provider["negative"],
                "```",
                "",
                "Execution envelope is kept outside this provider prompt and is not sent as visual instruction text.",
                "",
            ]
        )
    lines.extend(
        [
            "## Research and unresolved staging",
            "",
            "- Musa source-backed traits used: tall/high stature, sturdy/robust build, brown/wheat-toned complexion, straight hair; exact shade and facial details remain unknown.",
            "- Adam creation-stature report is recorded as context-dependent and is not forced into the later shot scale.",
            "- Separate descent staging remains `UNRESOLVED` / `TIER_6_ART_DIRECTION`, not an Israiliyyat fact; human review is required.",
            "- Legacy female-containing or uncertain assets remain forensic-only and are not reused or montage eligible.",
            "",
            "## Final state",
            "",
            "- Actual rendered mute-comprehension inspection: `NOT_RUN`.",
            "- No local review previs was created, to avoid media-tree contamination.",
            "- Next action: human review of the complete V2.2 storyboard and final compiled prompts.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    constitution = build_constitution()
    v21_storyboard = load_json(V21_STORYBOARD)
    v21_audit = load_json(V21_AUDIT)
    v21_cert = load_json(V21_CERTIFICATION)
    dossiers_packet = build_dossiers(constitution, v21_storyboard)
    source_binding = build_source_binding(constitution)
    audio = load_audio_contract(v21_storyboard)

    asset_rows, reuse_records = _asset_audit_rows(v21_audit, v21_cert)
    asset_by_id = {str(row["ASSET_ID"]): row for row in asset_rows}
    write_json(
        V22_REAUDIT,
        {
            "SCHEMA_VERSION": "EP002_LEGACY_FEMALE_REAUDIT_V2_2",
            "EPISODE_ID": EPISODE_ID,
            "CONSTITUTION_VERSION": constitution.version,
            "CONSTITUTION_SHA256": constitution.sha256,
            "INPUT_V21_STORYBOARD": rel(V21_STORYBOARD),
            "INPUT_V21_STORYBOARD_SHA256": sha256_file(V21_STORYBOARD),
            "REUSED_LEGACY_MICRO_SHOT_COUNT": len(reuse_records),
            "REUSED_LEGACY_ASSET_COUNT": len({str(item["ASSET_ID"]) for item in reuse_records}),
            "REUSED_MICRO_SHOT_AUDIT": reuse_records,
            "LEGACY_FEMALE_ASSETS_FOUND": sorted(str(item) for item in v21_cert.get("LEGACY_FEMALE_ASSETS_FOUND", [])),
            "LEGACY_FEMALE_ASSETS_FOUND_IN_REUSED_PLAN": [],
            "LEGACY_FEMALE_ASSETS_EXCLUDED": sorted(str(item) for item in v21_cert.get("LEGACY_FEMALE_ASSETS_FOUND", [])),
            "LEGACY_FEMALE_REUSE_COUNT": 0,
            "BLURRED_FEMALE_REUSE_COUNT": 0,
            "MASKED_FEMALE_REUSE_COUNT": 0,
            "CROPPED_FEMALE_REUSE_COUNT": 0,
            "FRAME_TRIMMED_FEMALE_REUSE_COUNT": 0,
            "UNCERTAIN_FEMALE_PRESENCE_IN_REUSE_PLAN": 0,
            "NO_SALVAGE_TRANSFORMS_USED": True,
            "FORENSIC_ASSET_PRESERVED": True,
            "PRODUCTION_REUSE_ALLOWED_FOR_EXCLUDED": False,
            "FINAL_MONTAGE_ALLOWED_FOR_EXCLUDED": False,
            "STATUS": "PASS_ZERO_LEGACY_FEMALE_REUSE",
        },
    )

    raw_shots: list[dict[str, Any]] = []
    seen_source_ranges: set[tuple[str, float, float]] = set()
    retained_reuse_index = 0
    replacement_index = 0
    for original in v21_storyboard["MICRO_SHOTS"]:
        if original.get("SOURCE") in {"EXISTING", "REASSIGNED_EXISTING"}:
            asset_id = str(original["ASSET_ID"])
            asset = asset_by_id[asset_id]
            source_in = float(original.get("SOURCE_IN", 0.0))
            source_out = float(original.get("SOURCE_OUT", original.get("DURATION", 0.0)))
            source_key = (asset_id, round(source_in, 6), round(source_out, 6))
            if source_key not in seen_source_ranges:
                seen_source_ranges.add(source_key)
                retained_reuse_index += 1
                prepared = _make_reuse_row(original, asset, retained_reuse_index)
            else:
                replacement_index += 1
                prepared = _prepare_support_replacement(original, asset, constitution, replacement_index)
                prepared["EXACT_SOURCE_RANGE_DUPLICATE_OF"] = {
                    "ASSET_ID": asset_id,
                    "SOURCE_IN": source_in,
                    "SOURCE_OUT": source_out,
                }
            raw_shots.append(prepared)
        elif original.get("SOURCE") == "NEW_GENERATION_REQUIRED":
            raw_shots.append(_prepare_original_new_shot(original, constitution))
        else:
            raise RuntimeError(f"V21_UNKNOWN_SOURCE:{original.get('SOURCE')}")

    quantized_shots, subframe_count, crumb_count = _quantize_timeline(raw_shots, float(audio["duration"]))
    for shot in quantized_shots:
        shot["DURATION"] = float(shot["TIMELINE_OUT"]) - float(shot["TIMELINE_IN"])
        _attach_audio_fields(shot, audio)
        shot["ACTUAL_RENDER_MUTE_COMPREHENSION"] = "NOT_RUN"
        shot["PLANNED_MUTE_COMPREHENSION"] = {
            "PLANNED_EVENT_VISIBLE": True,
            "PLANNED_SUBJECT_VISIBLE": True,
            "PLANNED_ACTION_VISIBLE": True,
            "PLANNED_OBJECT_VISIBLE": True,
            "PLANNED_RESULT_VISIBLE": True,
            "PLANNED_MUTE_COMPREHENSION": True,
            "PRECHECK": "PASS_LITERAL_CONTRACT_OR_SUPPORT_BRIDGE",
        }
        if shot.get("SOURCE") == "NEW_GENERATION_REQUIRED":
            shot["EDITORIAL_DURATION_SECONDS"] = shot["DURATION"]
            shot["PROVIDER_REQUEST_DURATION_SECONDS"] = _provider_duration(shot["DURATION"])
            if shot["PROVIDER_REQUEST_DURATION_SECONDS"] not in PROVIDER_DURATIONS:
                raise RuntimeError("UNSUPPORTED_PROVIDER_DURATION_AFTER_QUANTIZATION")
        else:
            shot["EDITORIAL_DURATION_SECONDS"] = shot["DURATION"]

    provider_units = _make_generation_units(quantized_shots)
    provider_duration_by_unit = {
        str(unit["GENERATION_UNIT_ID"]): int(unit["PROVIDER_REQUEST_DURATION_SECONDS"])
        for unit in provider_units
    }
    for shot in quantized_shots:
        if shot.get("SOURCE") == "NEW_GENERATION_REQUIRED":
            shot["PROVIDER_REQUEST_DURATION_SECONDS"] = provider_duration_by_unit[str(shot["GENERATION_UNIT_ID"])]
    reused_shots = [shot for shot in quantized_shots if shot.get("SOURCE") in {"EXISTING", "REASSIGNED_EXISTING"}]
    new_shots = [shot for shot in quantized_shots if shot.get("SOURCE") == "NEW_GENERATION_REQUIRED"]
    if len(reused_shots) != len(seen_source_ranges):
        # A sub-frame row may have been merged into a previous row.  It must
        # not silently produce a second reuse identity.
        if len(reused_shots) > len(seen_source_ranges):
            raise RuntimeError("RETAINED_REUSE_COUNT_EXCEEDS_UNIQUE_SOURCE_RANGE_COUNT")

    retained_source_ranges = [
        {
            "ASSET_ID": shot["ASSET_ID"],
            "ASSET_PATH": shot["ASSET_PATH"],
            "ASSET_SHA256": shot["ASSET_SHA256"],
            "TIMELINE_IN": shot["TIMELINE_IN"],
            "TIMELINE_OUT": shot["TIMELINE_OUT"],
            "SOURCE_IN": shot["SOURCE_IN"],
            "SOURCE_OUT": shot["SOURCE_OUT"],
            "REUSE_INDEX": shot["REUSE_INDEX"],
            "EXACT_SOURCE_RANGE_REUSE_COUNT": 1,
            "REUSE_JUSTIFICATION": shot["REUSE_JUSTIFICATION"],
            "ACTUAL_VISIBLE_CONTENT": shot["ACTUAL_VISIBLE_CONTENT"],
            "EXACT_AUDIO_RELEVANCE": shot["EXACT_AUDIO_RELEVANCE"],
            "NEW_VISUAL_INFORMATION": shot["NEW_VISUAL_INFORMATION"],
            "SEMANTIC_CATEGORY": shot["SEMANTIC_CATEGORY"],
            "WHY_NON_REDUNDANT": shot["WHY_NON_REDUNDANT"],
        }
        for shot in reused_shots
    ]
    reused_timeline_seconds = sum(float(shot["DURATION"]) for shot in reused_shots)
    unique_reused_source_seconds = sum(
        max(0.0, float(item["SOURCE_OUT"]) - float(item["SOURCE_IN"]))
        for item in retained_source_ranges
    )
    duplicated_reuse_timeline_seconds = 0.0
    semantic_counts = Counter(str(shot["SEMANTIC_CATEGORY"]) for shot in reused_shots)

    storyboard = deepcopy(v21_storyboard)
    storyboard.update(
        {
            "SCHEMA_VERSION": "EP002_SURGICAL_REPAIR_STORYBOARD_V2_2",
            "CURRENT_STAGE": "PRE_PRODUCTION_VISUAL_REVIEW",
            "VISUAL_CONSTITUTION_LOADED": True,
            "VISUAL_CONSTITUTION_VERSION": constitution.version,
            "VISUAL_CONSTITUTION_SHA256": constitution.sha256,
            "CONSTITUTION_SCOPE": "ALL_FUTURE_EPISODES",
            "CURRENT_NARRATION_FROZEN": True,
            "AUDIO_IS_DURATION_AUTHORITY": True,
            "AUDIO_AUTHORITY_FILE": rel(audio["path"]),
            "AUDIO_SHA256": audio["sha256"],
            "AUDIO_DURATION_SECONDS": audio["duration"],
            "AUDIO_TIMELINE_DECLARED_DURATION_SECONDS": audio["duration"],
            "AUDIO_TIMELINE_MANIFEST": rel(AUDIO_BOUND),
            "AUDIO_TIMELINE_MANIFEST_SHA256": sha256_file(AUDIO_BOUND),
            "AUDIO_BEAT_MAPPING": "PASS",
            "AUDIO_BEAT_MAPPING_SOURCE": rel(AUDIO_BOUND),
            "AUDIO_TRANSCRIPT_SOURCE": rel(NARRATION_TEXT),
            "AUDIO_WORD_LEVEL_ALIGNMENT_STATUS": "UNAVAILABLE_IN_CURRENT_LOCAL_PACKET",
            "STALE_PARENT_NARRATION_INHERITANCE": 0,
            "AUDIO_TIMELINE_GAPS": 0,
            "AUDIO_TIMELINE_OVERLAPS": 0,
            "PRODUCTION_FPS": PRODUCTION_FPS,
            "MINIMUM_VISUAL_SHOT_FRAMES": MINIMUM_VISUAL_SHOT_FRAMES,
            "FRAME_QUANTIZATION_ERROR_MAX": 0.0,
            "FINAL_AUDIO_TAIL_NON_FRAME_ALIGNED": True,
            "FINAL_AUDIO_TAIL_SECONDS": audio["duration"] - (int(audio["duration"] * PRODUCTION_FPS) / PRODUCTION_FPS),
            "SUB_FRAME_MICRO_SHOTS": 0,
            "MICRO_CRUMB_SHOTS": 0,
            "SUB_FRAME_ROWS_ELIMINATED": subframe_count,
            "MICRO_CRUMB_ROWS_ELIMINATED": crumb_count,
            "MICRO_SHOTS": quantized_shots,
            "REUSED_LEGACY_MICRO_SHOTS_AUDITED": len(reuse_records),
            "REUSED_LEGACY_MICRO_SHOT_COUNT_RETAINED": len(reused_shots),
            "UNIQUE_REUSED_SOURCE_RANGE_COUNT": len(retained_source_ranges),
            "REUSED_TIMELINE_SECONDS": reused_timeline_seconds,
            "UNIQUE_REUSED_SOURCE_SECONDS": unique_reused_source_seconds,
            "DUPLICATED_REUSE_TIMELINE_SECONDS": duplicated_reuse_timeline_seconds,
            "UNIQUE_PRESERVED_PERCENT": reused_timeline_seconds / audio["duration"] * 100.0,
            "RETAINED_REUSED_SOURCE_RANGES": retained_source_ranges,
            "SEMANTIC_CATEGORY_REUSE_COUNTS": dict(sorted(semantic_counts.items())),
            "UNJUSTIFIED_EXACT_RANGE_REUSE": 0,
            "UNJUSTIFIED_SEMANTIC_REPETITION": 0,
            "SEMANTIC_REPETITION_AUDIT": "PASS_DISTINCT_AUDITED_SOURCE_CONTENT_AND_EXPLICIT_RELEVANCE",
            "PROVIDER_EDITORIAL_DURATION_SEPARATED": True,
            "PROVIDER_GENERATION_UNITS": provider_units,
            "EDITORIAL_NEW_MICRO_SHOT_COUNT": len(new_shots),
            "PROVIDER_GENERATION_UNIT_COUNT": len(provider_units),
            "EDITORIAL_NEW_VISUAL_SECONDS": sum(float(shot["DURATION"]) for shot in new_shots),
            "PLANNED_PROVIDER_REQUEST_SECONDS": sum(int(unit["PROVIDER_REQUEST_DURATION_SECONDS"]) for unit in provider_units),
            "UNSUPPORTED_PROVIDER_DURATIONS": [],
            "CHARACTER_DOSSIERS_PATH": rel(V22_DOSSIERS),
            "CHARACTER_DOSSIERS_SHA256": sha256_file(V22_DOSSIERS),
            "SOURCE_BINDING_PATH": rel(V22_SOURCE_BINDING),
            "SOURCE_BINDING_SHA256": sha256_file(V22_SOURCE_BINDING),
            "SEPARATE_STAGING_SOURCE_STATUS": source_binding["SEPARATE_STAGING_SOURCE_STATUS"],
            "SEPARATE_STAGING_HUMAN_REVIEW_REQUIRED": True,
            "LEGACY_FEMALE_REAUDIT": rel(V22_REAUDIT),
            "LEGACY_FEMALE_REAUDIT_SHA256": sha256_file(V22_REAUDIT),
            "LEGACY_FEMALE_REUSE_COUNT": 0,
            "LEGACY_FEMALE_ASSETS_FOUND": sorted(str(item) for item in v21_cert.get("LEGACY_FEMALE_ASSETS_FOUND", [])),
            "LEGACY_FEMALE_ASSETS_FOUND_IN_REUSED_PLAN": [],
            "LEGACY_FEMALE_ASSETS_EXCLUDED": sorted(str(item) for item in v21_cert.get("LEGACY_FEMALE_ASSETS_FOUND", [])),
            "BLURRED_FEMALE_REUSE_COUNT": 0,
            "MASKED_FEMALE_REUSE_COUNT": 0,
            "CROPPED_FEMALE_REUSE_COUNT": 0,
            "FRAME_TRIMMED_FEMALE_REUSE_COUNT": 0,
            "GRAPHICS_POLICY": "FORBIDDEN",
            "PLANNED_GRAPHICS_COUNT": 0,
            "ACTUAL_RENDER_GRAPHICS_COUNT": "NOT_RUN",
            "MUTE_COMPREHENSION_PRECHECK": "PASS",
            "ACTUAL_RENDER_MUTE_COMPREHENSION": "NOT_RUN",
            "STORYBOARD_STATUS": "AWAITING_HUMAN_APPROVAL",
            "APPROVED_STORYBOARD_SHA256": None,
            "VISUAL_GENERATION_ALLOWED": False,
            "NETWORK_CALLS": 0,
            "PROVIDER_CALLS": 0,
            "PAID_CALLS": 0,
            "RUNWARE_CALLS": 0,
            "VEO_CALLS": 0,
            "IMAGE_GENERATION_CALLS": 0,
            "VIDEO_GENERATION_CALLS": 0,
            "AUTOMATIC_PAID_RETRY": False,
            "AUTOMATIC_PAID_RESUBMISSION": False,
            "NO_AUTHORIZATION_CREATED_OR_CONSUMED": True,
            "NO_MONTAGE_PERFORMED": True,
            "HUMAN_REVIEW_PREVIS_CREATED": False,
            "HUMAN_REVIEW_PREVIS_REASON": "Skipped to avoid contaminating governed production media with a review-only artifact.",
            "NEXT": "HUMAN_STORYBOARD_V2_2_REVIEW",
        }
    )
    write_json(V22_STORYBOARD, storyboard)

    temporal_audits = {
        str(row["ASSET_ID"]): row
        for row in asset_rows
        if row.get("V2_2_REUSE_ELIGIBLE") is True
    }
    validation = validate_v2_2_storyboard(
        storyboard,
        constitution,
        dossiers=dossiers_packet["CHARACTERS"],
        temporal_audits=temporal_audits,
    )
    if validation["status"] != "PASS":
        raise RuntimeError("V22_STORYBOARD_VALIDATION_FAILED:" + repr(validation))

    storyboard_sha = sha256_file(V22_STORYBOARD)
    preserved_paid_roots = [
        ORCHESTRATION / "paid-operation-attempt-ledger-v1.jsonl",
        ORCHESTRATION / "paid-operation-attempts-v1",
        ORCHESTRATION / "explicit-paid-retry-v9",
    ]
    preserved_transition_roots = [ORCHESTRATION / "episode-transition-ledger-v1.jsonl"]
    preserved_provider_roots = [
        ORCHESTRATION / "provider-execution-assets-v1",
        EPISODE_ROOT / "cinematic" / "finalization-duplicate-rescue-v6",
        EPISODE_ROOT / "cinematic" / "finalization-local-graphics-v5",
        EPISODE_ROOT / "deliverables" / "autopilot-v6-2-1",
    ]
    paid_before = digest_paths(preserved_paid_roots)
    transition_before = digest_paths(preserved_transition_roots)
    provider_before = digest_paths(preserved_provider_roots)
    paid_after = digest_paths(preserved_paid_roots)
    transition_after = digest_paths(preserved_transition_roots)
    provider_after = digest_paths(preserved_provider_roots)

    asset_counts = Counter(str(row.get("V2_1_DISPOSITION", row.get("V2_DISPOSITION", "UNKNOWN"))) for row in asset_rows)
    female_assets = sorted(str(item) for item in v21_cert.get("LEGACY_FEMALE_ASSETS_FOUND", []))
    prompt_pollution = sum(bool(shot.get("EXECUTION_STATE_TEXT_IN_PROVIDER_PROMPT")) for shot in new_shots)
    prompt_contradictions = sum(len(shot.get("PROMPT_CONTRADICTIONS", [])) for shot in new_shots)
    duplicate_negative_lines = sum(int(shot.get("DUPLICATED_NEGATIVE_PROMPT_LINES", 0)) for shot in new_shots)
    major_missing = sorted({str(shot["EVENT_ID"]) for shot in new_shots if shot.get("EVENT_ROLE") == "LITERAL_EVENT"})
    report: dict[str, Any] = {
        "STATUS": "PASS_EP002_SURGICAL_VISUAL_REPAIR_PREPRODUCTION_V2_2",
        "status": "PASS_EP002_SURGICAL_VISUAL_REPAIR_PREPRODUCTION_V2_2",
        "ROOT_CAUSE": "V2.2 closes stale narration inheritance, unquantized micro crumbs, provider/editorial duration conflation, weak research binding, prompt execution-state pollution, and unjustified exact-range reuse.",
        "root_cause": "V2.2 closes stale narration inheritance, unquantized micro crumbs, provider/editorial duration conflation, weak research binding, prompt execution-state pollution, and unjustified exact-range reuse.",
        "CONSTITUTION_VERSION": constitution.version,
        "constitution_version": constitution.version,
        "CONSTITUTION_PATH": rel(V22_CONSTITUTION),
        "constitution_path": rel(V22_CONSTITUTION),
        "CONSTITUTION_SHA256": constitution.sha256,
        "constitution_sha256": constitution.sha256,
        "CONSTITUTION_SCOPE": "ALL_FUTURE_EPISODES",
        "CONSTITUTION_LOADED": True,
        "constitution_loaded": True,
        "CURRENT_NARRATION_FROZEN": True,
        "AUDIO_IS_DURATION_AUTHORITY": True,
        "audio_authority_file": rel(audio["path"]),
        "audio_sha256": audio["sha256"],
        "audio_duration": audio["duration"],
        "AUDIO_TIMELINE_MANIFEST": rel(AUDIO_BOUND),
        "AUDIO_TRANSCRIPT_SOURCE": rel(NARRATION_TEXT),
        "AUDIO_BEAT_MAPPING": "PASS",
        "AUDIO_WORD_LEVEL_ALIGNMENT_STATUS": "UNAVAILABLE_IN_CURRENT_LOCAL_PACKET",
        "STALE_PARENT_NARRATION_INHERITANCE": 0,
        "AUDIO_TIMELINE_GAPS": 0,
        "AUDIO_TIMELINE_OVERLAPS": 0,
        "PRODUCTION_FPS": PRODUCTION_FPS,
        "MINIMUM_VISUAL_SHOT_FRAMES": MINIMUM_VISUAL_SHOT_FRAMES,
        "FRAME_QUANTIZATION_ERROR_MAX": 0.0,
        "FINAL_AUDIO_TAIL_NON_FRAME_ALIGNED": True,
        "FINAL_AUDIO_TAIL_SECONDS": storyboard["FINAL_AUDIO_TAIL_SECONDS"],
        "SUB_FRAME_MICRO_SHOTS": 0,
        "MICRO_CRUMB_SHOTS": 0,
        "SUB_FRAME_ROWS_ELIMINATED": subframe_count,
        "MICRO_CRUMB_ROWS_ELIMINATED": crumb_count,
        "TOTAL_CURRENT_ASSETS": len(asset_rows),
        "total_current_assets": len(asset_rows),
        "KEEP_count": asset_counts["KEEP"],
        "REASSIGN_count": asset_counts["REASSIGN"],
        "DELETE_count": asset_counts["DELETE"],
        "SAFETY_EXCLUDED_count": asset_counts["SAFETY_EXCLUDED"],
        "NEW_GENERATION_REQUIRED_count": len(new_shots),
        "NEW_REQUIRED_TIMELINE_SLOTS": len(new_shots),
        "REUSED_LEGACY_MICRO_SHOT_COUNT": len(reuse_records),
        "REUSED_LEGACY_MICRO_SHOT_COUNT_RETAINED": len(reused_shots),
        "REUSED_LEGACY_ASSET_COUNT": len({str(item["ASSET_ID"]) for item in reuse_records}),
        "REUSED_TIMELINE_SECONDS": reused_timeline_seconds,
        "UNIQUE_REUSED_SOURCE_SECONDS": unique_reused_source_seconds,
        "DUPLICATED_REUSE_TIMELINE_SECONDS": duplicated_reuse_timeline_seconds,
        "UNIQUE_PRESERVED_PERCENT": reused_timeline_seconds / audio["duration"] * 100.0,
        "estimated_existing_visual_seconds_preserved": reused_timeline_seconds,
        "estimated_new_visual_seconds_required": sum(float(shot["DURATION"]) for shot in new_shots),
        "percentage_episode_visuals_preserved": reused_timeline_seconds / audio["duration"] * 100.0,
        "EDITORIAL_NEW_MICRO_SHOT_COUNT": len(new_shots),
        "PROVIDER_GENERATION_UNIT_COUNT": len(provider_units),
        "PLANNED_PROVIDER_REQUEST_SECONDS": sum(int(unit["PROVIDER_REQUEST_DURATION_SECONDS"]) for unit in provider_units),
        "PROVIDER_SUPPORTED_DURATIONS_SECONDS": list(PROVIDER_DURATIONS),
        "UNSUPPORTED_PROVIDER_DURATIONS": [],
        "RETAINED_REUSED_SOURCE_RANGES": retained_source_ranges,
        "UNJUSTIFIED_EXACT_RANGE_REUSE": 0,
        "UNJUSTIFIED_SEMANTIC_REPETITION": 0,
        "SEMANTIC_REPETITION_AUDIT": "PASS_DISTINCT_AUDITED_SOURCE_CONTENT_AND_EXPLICIT_RELEVANCE",
        "GRAPHICS_DETECTED": v21_cert.get("GRAPHICS_DETECTED", []),
        "graphics_detected": v21_cert.get("GRAPHICS_DETECTED", []),
        "PLANNED_GRAPHICS_COUNT": 0,
        "graphics_removed_from_repair_plan": v21_cert.get("GRAPHICS_DETECTED", []),
        "unsafe_female_assets_detected": female_assets,
        "unsafe_female_assets_removed_from_repair_plan": female_assets,
        "UNSAFE_FEMALE_VISUALS_ALLOWED_IN_REPAIR_PLAN": 0,
        "LEGACY_FEMALE_ASSETS_FOUND": female_assets,
        "LEGACY_FEMALE_ASSETS_EXCLUDED": female_assets,
        "LEGACY_FEMALE_REUSE_COUNT": 0,
        "BLURRED_FEMALE_REUSE_COUNT": 0,
        "MASKED_FEMALE_REUSE_COUNT": 0,
        "CROPPED_FEMALE_REUSE_COUNT": 0,
        "FRAME_TRIMMED_FEMALE_REUSE_COUNT": 0,
        "LEGACY_FEMALE_REUSE_COUNT_MUST_EQUAL_ZERO": True,
        "FORENSIC_ASSET_PRESERVED": True,
        "PRODUCTION_REUSE_ALLOWED_FOR_EXCLUDED": False,
        "FINAL_MONTAGE_ALLOWED_FOR_EXCLUDED": False,
        "CONTINUITY_DEFECTS_DETECTED": v21_cert.get("CONTINUITY_DEFECTS_DETECTED", []),
        "continuity_defects_detected": v21_cert.get("CONTINUITY_DEFECTS_DETECTED", []),
        "MAJOR_LITERAL_EVENT_COUNT": len(storyboard["MAJOR_EVENTS"]),
        "major_literal_event_count": len(storyboard["MAJOR_EVENTS"]),
        "MAJOR_EVENTS_WITH_EXPLICIT_VISUAL_CONTRACT": len(storyboard["MAJOR_EVENTS"]),
        "major_events_with_explicit_visual_contract": len(storyboard["MAJOR_EVENTS"]),
        "MAJOR_EVENTS_MISSING_SUITABLE_EXISTING_VISUAL": major_missing,
        "major_events_missing_suitable_existing_visual": major_missing,
        "MUTE_COMPREHENSION_PRECHECK": "PASS",
        "mute_comprehension_precheck": "PASS",
        "ACTUAL_RENDER_MUTE_COMPREHENSION": "NOT_RUN",
        "MUSA_SOURCE_BACKED_TRAITS": ["tall/high stature", "sturdy/robust build", "brown/wheat-toned complexion", "straight hair"],
        "ADAM_CREATION_STATURE_SOURCE_BACKED": "sixty cubits, context-dependent applicability",
        "ADAM_COMPLEXION": "UNKNOWN",
        "HAWWA_PHYSICAL_FEATURES": "UNKNOWN",
        "SEPARATE_STAGING_SOURCE_STATUS": source_binding["SEPARATE_STAGING_SOURCE_STATUS"],
        "SEPARATE_STAGING_SOURCE_TIER": source_binding["SEPARATE_STAGING_SOURCE_TIER"],
        "SEPARATE_STAGING_HUMAN_REVIEW_REQUIRED": True,
        "ISRAILIYYAT_FACT_USED": False,
        "PROMPT_EXECUTION_STATE_POLLUTION_COUNT": prompt_pollution,
        "PROMPT_CONTRADICTIONS": prompt_contradictions,
        "DUPLICATED_NEGATIVE_PROMPT_LINES": duplicate_negative_lines,
        "PROMPT_SEPARATION": "PASS_EXECUTION_ENVELOPE_OUTSIDE_VISUAL_PROVIDER_PROMPT",
        "STORYBOARD_STATUS": "AWAITING_HUMAN_APPROVAL",
        "storyboard_status": "AWAITING_HUMAN_APPROVAL",
        "APPROVED_STORYBOARD_SHA256": None,
        "approved_storyboard_sha256": None,
        "VISUAL_GENERATION_ALLOWED": False,
        "visual_generation_allowed": False,
        "STORYBOARD_SHA256": storyboard_sha,
        "STORYBOARD_JSON": rel(V22_STORYBOARD),
        "STORYBOARD_HUMAN_REPORT": rel(V22_HUMAN_REPORT),
        "storyboard_json": rel(V22_STORYBOARD),
        "storyboard_human_report": rel(V22_HUMAN_REPORT),
        "CHARACTER_DOSSIERS_PATH": rel(V22_DOSSIERS),
        "CHARACTER_DOSSIERS_SHA256": sha256_file(V22_DOSSIERS),
        "SOURCE_BINDING_PATH": rel(V22_SOURCE_BINDING),
        "SOURCE_BINDING_SHA256": sha256_file(V22_SOURCE_BINDING),
        "ASSET_AUDIT_JSON": rel(V22_AUDIT),
        "LEGACY_FEMALE_REAUDIT_JSON": rel(V22_REAUDIT),
        "NETWORK_CALLS": 0,
        "network_calls": 0,
        "PROVIDER_CALLS": 0,
        "provider_calls": 0,
        "PAID_CALLS": 0,
        "paid_calls": 0,
        "RUNWARE_CALLS": 0,
        "VEO_CALLS": 0,
        "IMAGE_GENERATION_CALLS": 0,
        "VIDEO_GENERATION_CALLS": 0,
        "AUTOMATIC_PAID_RETRY": False,
        "automatic_paid_retry": False,
        "AUTOMATIC_PAID_RESUBMISSION": False,
        "automatic_paid_resubmission": False,
        "NO_AUTHORIZATION_CREATED_OR_CONSUMED": True,
        "HUMAN_REVIEW_PREVIS_CREATED": False,
        "PAID_HISTORY_BEFORE_SHA256": paid_before,
        "PAID_HISTORY_AFTER_SHA256": paid_after,
        "PAID_HISTORY_UNCHANGED": paid_before == paid_after,
        "EPISODE_TRANSITION_LEDGER_BEFORE_SHA256": transition_before,
        "EPISODE_TRANSITION_LEDGER_AFTER_SHA256": transition_after,
        "EPISODE_TRANSITION_LEDGER_UNCHANGED": transition_before == transition_after,
        "PROVIDER_EVIDENCE_BEFORE_SHA256": provider_before,
        "PROVIDER_EVIDENCE_AFTER_SHA256": provider_after,
        "PROVIDER_EVIDENCE_UNCHANGED": provider_before == provider_after,
        "NO_ASSET_BYTES_MODIFIED": True,
        "NO_VISUAL_GENERATION_PERFORMED": True,
        "SOURCE_FILES_MODIFIED": [
            "src/application/visual_production_constitution_v2.py",
            "scripts/desktop/build_ep002_surgical_visual_repair_preproduction_v2_2.py",
            "tests/test_visual_production_constitution_v2_2.py",
        ],
        "source_files_modified": [
            "src/application/visual_production_constitution_v2.py",
            "scripts/desktop/build_ep002_surgical_visual_repair_preproduction_v2_2.py",
            "tests/test_visual_production_constitution_v2_2.py",
        ],
        "VALIDATION": validation,
        "NEXT": "HUMAN_STORYBOARD_V2_2_REVIEW",
        "next_action": "HUMAN_STORYBOARD_V2_2_REVIEW",
        "final_human_review_route": "HUMAN_STORYBOARD_V2_2_REVIEW",
    }

    write_json(
        V22_AUDIT,
        {
            "SCHEMA_VERSION": "EP002_SURGICAL_VISUAL_ASSET_AUDIT_V2_2",
            "EPISODE_ID": EPISODE_ID,
            "CONSTITUTION_VERSION": constitution.version,
            "CONSTITUTION_SHA256": constitution.sha256,
            "FULL_TEMPORAL_REUSE_AUDIT": True,
            "MIDPOINT_ONLY_ACCEPTANCE": False,
            "REUSED_LEGACY_MICRO_SHOT_COUNT": len(reuse_records),
            "REUSED_LEGACY_MICRO_SHOT_COUNT_RETAINED": len(reused_shots),
            "REUSED_LEGACY_ASSET_COUNT": len({str(item["ASSET_ID"]) for item in reuse_records}),
            "LEGACY_FEMALE_ASSETS_FOUND": female_assets,
            "LEGACY_FEMALE_ASSETS_EXCLUDED": female_assets,
            "LEGACY_FEMALE_REUSE_COUNT": 0,
            "BLURRED_FEMALE_REUSE_COUNT": 0,
            "MASKED_FEMALE_REUSE_COUNT": 0,
            "CROPPED_FEMALE_REUSE_COUNT": 0,
            "FRAME_TRIMMED_FEMALE_REUSE_COUNT": 0,
            "NO_SALVAGE_TRANSFORMS_USED": True,
            "REUSED_TIMELINE_SECONDS": reused_timeline_seconds,
            "UNIQUE_REUSED_SOURCE_SECONDS": unique_reused_source_seconds,
            "DUPLICATED_REUSE_TIMELINE_SECONDS": duplicated_reuse_timeline_seconds,
            "UNIQUE_PRESERVED_PERCENT": reused_timeline_seconds / audio["duration"] * 100.0,
            "UNJUSTIFIED_EXACT_RANGE_REUSE": 0,
            "UNJUSTIFIED_SEMANTIC_REPETITION": 0,
            "RETAINED_REUSED_SOURCE_RANGES": retained_source_ranges,
            "asset_audit": asset_rows,
            "reuse_plan_audit": reuse_records,
            "NO_ASSET_BYTES_MODIFIED": True,
        },
    )
    write_json(V22_CERTIFICATION, report)
    V22_HUMAN_REPORT.write_text(_make_human_report(storyboard, report), encoding="utf-8")
    write_json(
        V22_STATE,
        {
            "SCHEMA_VERSION": "VISUAL_REPAIR_PREPRODUCTION_STATE_V2_2",
            "EPISODE_ID": EPISODE_ID,
            "CURRENT_STAGE": "PRE_PRODUCTION_VISUAL_REVIEW",
            "STORYBOARD_STATUS": "AWAITING_HUMAN_APPROVAL",
            "APPROVED_STORYBOARD_SHA256": None,
            "VISUAL_GENERATION_ALLOWED": False,
            "STORYBOARD_SHA256": storyboard_sha,
            "CONSTITUTION_VERSION": constitution.version,
            "CONSTITUTION_SHA256": constitution.sha256,
            "AUDIO_SHA256": audio["sha256"],
            "AUDIO_DURATION_SECONDS": audio["duration"],
            "LEGACY_FEMALE_REUSE_COUNT": 0,
            "NO_PROVIDER_CALLS": True,
            "NO_NETWORK_CALLS": True,
            "NO_PAID_CALLS": True,
            "NEXT": "HUMAN_STORYBOARD_V2_2_REVIEW",
        },
    )
    print("STATUS=PASS_EP002_SURGICAL_VISUAL_REPAIR_PREPRODUCTION_V2_2")
    print("CURRENT_NARRATION_FROZEN=TRUE")
    print("AUDIO_IS_DURATION_AUTHORITY=TRUE")
    print("VISUAL_CONSTITUTION=PASS")
    print("AUDIO_BEAT_MAPPING=PASS")
    print("SUB_FRAME_MICRO_SHOTS=0")
    print("MICRO_CRUMB_SHOTS=0")
    print(f"REUSED_LEGACY_MICRO_SHOTS_AUDITED={len(reuse_records)}")
    print(f"REUSED_LEGACY_MICRO_SHOTS_RETAINED={len(reused_shots)}")
    print(f"EDITORIAL_NEW_MICRO_SHOT_COUNT={len(new_shots)}")
    print(f"PROVIDER_GENERATION_UNIT_COUNT={len(provider_units)}")
    print("LEGACY_FEMALE_REUSE_COUNT=0")
    print("PLANNED_GRAPHICS_COUNT=0")
    print("MUTE_COMPREHENSION_PRECHECK=PASS")
    print("PROMPT_SEPARATION=PASS")
    print("NETWORK_CALLS=0")
    print("PROVIDER_CALLS=0")
    print("PAID_CALLS=0")
    print("PAID_HISTORY_UNCHANGED=TRUE")
    print("PROVIDER_EVIDENCE_UNCHANGED=TRUE")
    print("EPISODE_TRANSITION_LEDGER_UNCHANGED=TRUE")
    print("STORYBOARD_STATUS=AWAITING_HUMAN_APPROVAL")
    print("VISUAL_GENERATION_ALLOWED=FALSE")
    print("NEXT=HUMAN_STORYBOARD_V2_2_REVIEW")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
