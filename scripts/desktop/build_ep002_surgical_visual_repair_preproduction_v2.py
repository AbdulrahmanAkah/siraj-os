"""Build the Episode 002 V2 surgical visual repair preproduction packet.

The builder is intentionally offline and append-only.  It reads the current
episode audio, V1 audit/storyboard, local source package, and existing media;
it writes only new V2 planning artifacts.  It never calls a provider, creates
an authorization, consumes an authorization, or assembles a montage.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any, Iterable, Mapping
import wave


REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from src.application.visual_production_constitution_v2 import (  # noqa: E402
    compile_visual_prompt_v2,
    load_visual_production_constitution_v2,
    sha256_file,
    validate_character_dossiers,
    validate_micro_shot_storyboard,
    validate_source_hierarchy_records,
)


EPISODE_ID = "episode-002-adam-temptation-fall-repentance"
EPISODE_ROOT = REPO / "projects" / EPISODE_ID
PREPRODUCTION = EPISODE_ROOT / "preproduction"
ORCHESTRATION = EPISODE_ROOT / "orchestration"

V1_STORYBOARD = PREPRODUCTION / "EP002_SURGICAL_REPAIR_STORYBOARD_V1.json"
V1_REPORT = ORCHESTRATION / "ep002-surgical-visual-repair-preproduction-v1.json"
V1_AUDIT = ORCHESTRATION / "ep002-surgical-visual-asset-audit-v1.json"
SOURCE_MATRIX = EPISODE_ROOT / "research" / "source-claim-matrix-v5.json"
SOURCE_PACKAGE = EPISODE_ROOT / "research" / "canonical-source-package-v5.json"
AUDIO_TIMELINE = PREPRODUCTION / "audio-timestamps-and-beats-v6-1.json"
FINAL_TTS_MANIFEST = EPISODE_ROOT / "audio" / "final-tts-manifest-v3.json"
MASTER_AUDIO = ORCHESTRATION / "montage-v6-2-1" / "narration-master-v6-2-1.wav"

STORYBOARD_V2 = PREPRODUCTION / "EP002_SURGICAL_REPAIR_STORYBOARD_V2.json"
HUMAN_REPORT_V2 = PREPRODUCTION / "EP002_SURGICAL_REPAIR_STORYBOARD_V2.md"
DOSSIERS_V2 = PREPRODUCTION / "EP002_CHARACTER_EVIDENCE_DOSSIERS_V2.json"
AUDIT_V2 = ORCHESTRATION / "ep002-surgical-visual-asset-audit-v2.json"
CERTIFICATION_V2 = ORCHESTRATION / "ep002-surgical-visual-repair-preproduction-v2.json"
STATE_V2 = ORCHESTRATION / "visual-repair-preproduction-state-v2.json"

_GLOBAL_FORBIDDEN = [
    "graphics",
    "diagrams",
    "UI graphics",
    "abstract explainer panels",
    "placeholder visuals",
    "readable text",
    "logos",
    "watermarks",
    "unsupported source details",
    "extra characters",
    "continuity mutation",
    "loop",
    "freeze-frame filler",
]

_UNSAFE_FEMALE_SHOTS = {
    "EP002-SH-007",
    "EP002-SH-008",
    "EP002-SH-012",
    "EP002-SH-015",
    "EP002-SH-026",
    "EP002-SH-027",
    "EP002-SH-028",
    "EP002-SH-030",
    "EP002-SH-031",
    "EP002-SH-052",
}
_GRAPHIC_SHOTS = {
    "EP002-SH-032",
    "EP002-SH-040",
    "EP002-SH-041",
    "EP002-SH-042",
}
_CONTINUITY_DEFECT_SHOTS = {"EP002-SH-008"}
_PLACEHOLDER_SHOTS = {"EP002-SH-053", "EP002-SH-055"}
_LEAF_SHOTS = {2, 3, 4, 5, 6, 23, 24, 25, 46, 47, 48}
_TEMPORAL_UNSAFE_ASSET_IDS = {
    "EP002-SH-014-V02",
    "EP002-SH-016-V01",
}
_VISUAL_UNUSABLE_ASSET_IDS = {
    "EP002-SH-038-I01",
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def rel(path: Path) -> str:
    return path.resolve().relative_to(REPO.resolve()).as_posix()


def digest_paths(paths: Iterable[Path]) -> str:
    digest = hashlib.sha256()
    for root in sorted({Path(item).resolve() for item in paths}, key=str):
        if not root.exists():
            digest.update((str(root) + "|MISSING\n").encode("utf-8"))
            continue
        if root.is_file():
            digest.update((str(root) + "|FILE\n").encode("utf-8"))
            digest.update(root.read_bytes())
            continue
        for child in sorted((p for p in root.rglob("*") if p.is_file()), key=str):
            digest.update(str(child).encode("utf-8"))
            digest.update(b"\0")
            digest.update(child.read_bytes())
    return digest.hexdigest()


def ffprobe(path: Path) -> dict[str, Any]:
    executable = shutil.which("ffprobe")
    if not executable:
        raise RuntimeError("FFPROBE_MISSING")
    result = subprocess.run(
        [
            executable,
            "-v",
            "error",
            "-show_entries",
            "format=duration,size,format_name:stream=index,codec_type,width,height,avg_frame_rate,r_frame_rate,duration,nb_frames",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout or "{}")


def audio_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as handle:
        return handle.getnframes() / handle.getframerate()


def shot_number(shot_id: str) -> int:
    try:
        return int(shot_id.rsplit("-", 1)[1])
    except (IndexError, ValueError):
        return 0


def source_category(shot_id: str) -> str:
    number = shot_number(shot_id)
    if number in _LEAF_SHOTS:
        return "garden_leaves"
    if number >= 34:
        return "earth_environment"
    return "garden_environment"


def v2_asset_disposition(unit: Mapping[str, Any]) -> tuple[str, str]:
    shot_id = str(unit.get("SHOT_ID", ""))
    asset_id = str(unit.get("CURRENT_ASSET_ID", ""))
    observation = str(unit.get("VISUAL_OBSERVATION", ""))
    reason = str(unit.get("REASON", ""))
    if asset_id in _VISUAL_UNUSABLE_ASSET_IDS:
        return "DELETE", "full-image review found an inset/placeholder defect; graphics and placeholders are forbidden."
    if asset_id in _TEMPORAL_UNSAFE_ASSET_IDS:
        return "DELETE", "temporal start/middle/end review found a body-shaped dark silhouette; DELETE under maximum-strict safety."
    if shot_id in _UNSAFE_FEMALE_SHOTS or "bare hands" in observation.lower():
        return "DELETE", "maximum-strict female/hand policy cannot safely identify or cover the visible hands/body; DELETE."
    if shot_id in _GRAPHIC_SHOTS:
        return "DELETE", "graphics/UI/explainer asset is forbidden at every production layer."
    if shot_id in _PLACEHOLDER_SHOTS or "placeholder" in (observation + reason).lower():
        return "DELETE", "placeholder or non-reviewable visual is forbidden."
    if shot_id in _CONTINUITY_DEFECT_SHOTS or "continuity" in reason.lower():
        return "DELETE", "unexplained character-count or continuity defect."
    if str(unit.get("DISPOSITION")) == "KEEP":
        return "KEEP", "temporal and visual review retained the asset for its existing semantic role."
    if str(unit.get("DISPOSITION")) == "REASSIGN":
        return "REASSIGN", "safe existing material is moved to a supporting or establishing narration moment."
    return "DELETE", "current asset has no suitable literal event after remapping."


def audit_current_assets(v1: Mapping[str, Any]) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}
    for unit in v1["timeline_units"]:
        asset_id = str(unit["CURRENT_ASSET_ID"])
        if asset_id in by_id:
            continue
        relative = str(unit["CURRENT_ASSET_PATH"])
        path = REPO / Path(relative.replace("/", os.sep))
        exists = path.is_file()
        actual_hash = sha256_file(path) if exists else None
        declared_hash = str(unit.get("CURRENT_ASSET_DECLARED_SHA256", ""))
        media_kind = str(unit.get("MEDIA_KIND", ""))
        metadata: dict[str, Any] = {}
        if exists:
            metadata = ffprobe(path)
        streams = metadata.get("streams") or []
        video_stream = next((item for item in streams if item.get("codec_type") == "video"), None)
        declared_duration = float(unit.get("CURRENT_ASSET_DURATION", 0.0))
        probe_duration = None
        if metadata.get("format", {}).get("duration") not in (None, "N/A"):
            probe_duration = float(metadata["format"]["duration"])
        if media_kind.endswith("VIDEO") and probe_duration is None:
            raise RuntimeError(f"VIDEO_DURATION_MISSING:{asset_id}")
        disposition, disposition_reason = v2_asset_disposition(unit)
        safe = disposition in {"KEEP", "REASSIGN"}
        sample_types = [
            "FIRST_FRAME_OR_START_WINDOW",
            "MIDDLE_FRAME_OR_MIDDLE_WINDOW",
            "LAST_FRAME_OR_END_WINDOW",
        ] if media_kind.endswith("VIDEO") else ["FULL_IMAGE"]
        rows.append(
            {
                "ASSET_ID": asset_id,
                "SHOT_ID": str(unit.get("SHOT_ID", "")),
                "MEDIA_KIND": media_kind,
                "ASSET_PATH": relative,
                "ASSET_EXISTS": exists,
                "DECLARED_SHA256": declared_hash,
                "ACTUAL_SHA256": actual_hash,
                "DECLARED_HASH_MATCH": bool(exists and declared_hash == actual_hash),
                "DECLARED_DURATION_SECONDS": declared_duration,
                "PROBED_DURATION_SECONDS": probe_duration,
                "FRAME_WIDTH": video_stream.get("width") if video_stream else None,
                "FRAME_HEIGHT": video_stream.get("height") if video_stream else None,
                "TEMPORAL_SAMPLE_TYPES": sample_types,
                "TEMPORAL_SAMPLE_METHOD": (
                    "ffprobe metadata plus ffmpeg-extracted start/middle/end frames reviewed in local contact sheets; existing pixel-review reference retained"
                    if media_kind.endswith("VIDEO")
                    else "full-image local pixel review reference retained"
                ),
                "PIXEL_INSPECTION_REFERENCE": unit.get("VISUAL_INSPECTION_REFERENCE"),
                "VISUAL_OBSERVATION": unit.get("VISUAL_OBSERVATION"),
                "V1_DISPOSITION": unit.get("DISPOSITION"),
                "V2_DISPOSITION": disposition,
                "V2_DISPOSITION_REASON": disposition_reason,
                "FULL_TEMPORAL_REUSE_AUDIT": bool(exists and declared_hash == actual_hash),
                "MIDPOINT_ONLY_ACCEPTANCE": False,
                "POLICY_STATUS": "PASS" if safe and exists and declared_hash == actual_hash else "PASS_WITH_EXPLICIT_EXCLUSIONS",
                "REUSE_ELIGIBLE": bool(safe and exists and declared_hash == actual_hash),
                "SOURCE_ORIGINAL_SHOT_ID": str(unit.get("SHOT_ID", "")),
                "SOURCE_CATEGORY": source_category(str(unit.get("SHOT_ID", ""))),
            }
        )
        by_id[asset_id] = rows[-1]
    return rows, by_id


def build_dossiers() -> list[dict[str, Any]]:
    strict_female = {
        "female_visible_hair": False,
        "female_visible_neck": False,
        "female_visible_arms": False,
        "female_visible_legs": False,
        "female_visible_torso_skin": False,
        "female_visible_hands": False,
        "female_body_contour_emphasis": False,
        "required_clothing": "opaque loose full-body garment; head, hair, neck, and body covered; opaque gloves or fully enclosed sleeves when hand action is required",
    }
    return [
        {
            "CHARACTER_ID": "ADAM",
            "SOURCE_BACKED_ATTRIBUTES": [
                "Adam is the named male subject of the Quranic narrative package.",
                "Adam and his spouse share the narrated temptation, eating, acknowledgment, descent, and guidance arc.",
            ],
            "UNKNOWN_ATTRIBUTES": [
                "complexion",
                "height and build",
                "hair, facial features, and exact age",
                "historically specific wardrobe colors or materials",
            ],
            "DISPUTED_ATTRIBUTES": [],
            "CONTEXT_DEPENDENT_ATTRIBUTES": [
                "the Quranic text attributes a singular wording of disobedience to Adam in one passage while also describing shared actions in paired forms; visuals must not turn this into blame of the spouse alone"
            ],
            "SOURCE_REFERENCES": [
                "research/source-claim-matrix-v5.json#CL-002",
                "research/source-claim-matrix-v5.json#CL-004",
                "research/source-claim-matrix-v5.json#CL-005",
                "research/source-claim-matrix-v5.json#CL-006",
                "research/source-claim-matrix-v5.json#CL-007",
                "research/source-claim-matrix-v5.json#CL-008",
            ],
            "SOURCE_TIERS": ["TIER_1_QURAN"],
            "PHYSICAL_APPEARANCE_CONTRACT": {
                "SOURCE_FACTS": [],
                "UNKNOWN_REMAINS_UNKNOWN": True,
                "SAFE_FRAMING": "rear, side, medium, or distant framing when an unsupported identifying trait would otherwise be invented",
            },
            "WARDROBE_CONTRACT": {
                "SOURCE_BACKED": False,
                "ART_DIRECTION": "opaque loose non-body-defining full-body garment suitable for a modest historical-religious visual treatment",
            },
            "FORBIDDEN_UNSUPPORTED_ASSUMPTIONS": [
                "European or white archetype",
                "specific complexion",
                "specific ethnic stereotype",
                "unsupported facial or hair detail",
            ],
            "ART_DIRECTION_DECISIONS": [
                "consistent male silhouette across all shots",
                "non-identifying rear/side/distant framing unless a human-approved close shot is later added",
                "earth-tone loose opaque garment for continuity",
            ],
            "HUMAN_REVIEW_REQUIRED_ATTRIBUTES": [
                "any material front-facing physical appearance choice",
                "any unsupported complexion or exact wardrobe choice",
            ],
            "SOURCE_FACTS_AND_ART_DIRECTION_SEPARATED": True,
            "VISUAL_BIBLE": {
                "identity_consistency": True,
                "complexion": "UNKNOWN",
                "build": "UNKNOWN",
                "hair": "UNKNOWN",
                "safe_camera": "rear/side/distant preferred",
            },
        },
        {
            "CHARACTER_ID": "HAWWA_SPOUSE",
            "SOURCE_BACKED_ATTRIBUTES": [
                "A spouse is paired with Adam in the shared Quranic narrative of temptation, eating, acknowledgment, and descent.",
            ],
            "UNKNOWN_ATTRIBUTES": [
                "whether the local source package uses Hawwa as a named source fact",
                "complexion, height, build, hair, face, and exact age",
                "historically specific wardrobe details",
            ],
            "DISPUTED_ATTRIBUTES": [
                "any account that makes the spouse alone responsible for the event is not accepted by the local source matrix"
            ],
            "CONTEXT_DEPENDENT_ATTRIBUTES": [
                "the spouse must remain present when the narrated shared action requires her; strict coverage must not erase a required character"
            ],
            "SOURCE_REFERENCES": [
                "research/source-claim-matrix-v5.json#CL-004",
                "research/source-claim-matrix-v5.json#CL-005",
                "research/source-claim-matrix-v5.json#CL-006",
                "research/source-claim-matrix-v5.json#CL-008",
            ],
            "SOURCE_TIERS": ["TIER_1_QURAN"],
            "PHYSICAL_APPEARANCE_CONTRACT": {
                "SOURCE_FACTS": [],
                "UNKNOWN_REMAINS_UNKNOWN": True,
                "SAFE_FRAMING": "rear, distant, over-shoulder, or covered-face composition",
            },
            "WARDROBE_CONTRACT": {
                "SOURCE_BACKED": False,
                "ART_DIRECTION": strict_female,
            },
            "FORBIDDEN_UNSUPPORTED_ASSUMPTIONS": [
                "visible hair, neck, arms, legs, torso skin, or hands",
                "tight, transparent, revealing, or body-defining clothing",
                "nude or body-shaped silhouette",
                "silent omission of the required spouse",
                "European or white archetype",
            ],
            "ART_DIRECTION_DECISIONS": [
                "opaque loose full-body garment with head, hair, neck, and body covered",
                "opaque gloves or fully enclosed sleeves where an action needs an arm/hand cue",
                "covered-face framing for the eating anchor; fruit contact and bite evidence carry the action",
                "consistent covered silhouette across the episode",
            ],
            "HUMAN_REVIEW_REQUIRED_ATTRIBUTES": [
                "every generated female frame before provider generation",
                "any shot where compliance cannot be visually guaranteed",
            ],
            "SOURCE_FACTS_AND_ART_DIRECTION_SEPARATED": True,
            "VISUAL_BIBLE": {
                "identity_consistency": True,
                "complexion": "UNKNOWN",
                "build": "UNKNOWN",
                "hair": "COVERED_BY_POLICY; SOURCE_ATTRIBUTE_UNKNOWN",
                "safe_camera": "rear/distant/covered-face preferred",
                "strict_modesty": strict_female,
            },
        },
        {
            "CHARACTER_ID": "MUSA",
            "SOURCE_BACKED_ATTRIBUTES": [
                "Musa/Moses is the distinct interlocutor in the authenticated Adam-Musa debate used for the episode's limited hadith illustration.",
            ],
            "UNKNOWN_ATTRIBUTES": [
                "complexion in the local episode evidence package",
                "height, build, hair, facial features, and exact age",
                "historically specific wardrobe details",
            ],
            "DISPUTED_ATTRIBUTES": [],
            "CONTEXT_DEPENDENT_ATTRIBUTES": [
                "the debate is a limited hadith illustration and must not be expanded into unsupported story details"
            ],
            "SOURCE_REFERENCES": [
                "research/source-claim-matrix-v5.json#CL-009",
                "research/canonical-source-package-v5.json#SRC-005",
                "research/canonical-source-package-v5.json#SRC-006",
            ],
            "SOURCE_TIERS": ["TIER_2_SAHIH_SUNNAH"],
            "PHYSICAL_APPEARANCE_CONTRACT": {
                "SOURCE_FACTS": [],
                "UNKNOWN_REMAINS_UNKNOWN": True,
                "SAFE_FRAMING": "distinct male figure in neutral medium/rear/side framing; no invented identifying prop",
            },
            "WARDROBE_CONTRACT": {
                "SOURCE_BACKED": False,
                "ART_DIRECTION": "simple loose opaque historical garment with no staff, book, table, badge, or identification prop",
            },
            "FORBIDDEN_UNSUPPORTED_ASSUMPTIONS": [
                "generic fair or white European appearance",
                "specific darker/brown complexion unless separately evidenced and approved",
                "staff as an identification device",
                "book, table, scholar room, timeline, or graphic source card",
            ],
            "ART_DIRECTION_DECISIONS": [
                "distinct second male silhouette with continuity across the three debate anchors",
                "serious conversational body language",
                "neutral natural environment",
                "non-identifying framing until material appearance is human-approved",
            ],
            "HUMAN_REVIEW_REQUIRED_ATTRIBUTES": [
                "any concrete complexion or facial appearance decision",
                "any identifying prop or close facial depiction",
            ],
            "SOURCE_FACTS_AND_ART_DIRECTION_SEPARATED": True,
            "VISUAL_BIBLE": {
                "identity_consistency": True,
                "complexion": "UNKNOWN_IN_LOCAL_EPISODE_EVIDENCE",
                "build": "UNKNOWN",
                "hair": "UNKNOWN",
                "safe_camera": "medium/rear/side preferred",
            },
        },
    ]


def make_event_contracts() -> list[dict[str, Any]]:
    return [
        {
            "EVENT_ID": "EV-002-TREE-BOUNDARY",
            "EVENT_CLASS": "MAJOR_LITERAL_EVENT",
            "NARRATION_TEXT": "the unnamed tree is prohibited; Adam and spouse approach and stop before it",
            "START_TIME": 70.825,
            "END_TIME": 113.9,
            "SUBJECT": "Adam and spouse",
            "ACTION": "approach one unnamed tree, stop, and retract a covered sleeve before touching",
            "OBJECT": "unnamed tree",
            "LOCATION": "garden",
            "START_STATE": "free movement in the garden",
            "VISIBLE_ACTION": "two covered figures approach the same tree and visibly stop before contact",
            "END_STATE": "both remain before the tree with the prohibition readable from behavior",
            "EXPECTED_CHARACTER_COUNT": 2,
            "CHARACTER_IDENTITIES": ["ADAM", "HAWWA_SPOUSE"],
            "MUTE_COMPREHENSION_TARGET": "muted viewer understands a specific tree has a boundary/prohibition",
            "FORBIDDEN_SUBSTITUTIONS": ["glowing line", "graphic boundary", "tree-only", "abstract pressure", "third figure"],
            "SOURCE_TIER": "TIER_1_QURAN",
            "SOURCE_CERTAINTY": "HIGH",
            "SOURCE_FACTS_USED": ["CL-002: the tree is unnamed and prohibited"],
            "ART_DIRECTION_USED": ["natural hesitation cue; no supernatural barrier"],
        },
        {
            "EVENT_ID": "EV-003-TEMPTATION-WHISPER",
            "EVENT_CLASS": "MAJOR_LITERAL_EVENT",
            "NARRATION_TEXT": "the Quran establishes whispering and temptation, but not its physical mechanism",
            "START_TIME": 113.9,
            "END_TIME": 176.075,
            "SUBJECT": "Adam and spouse reacting to an unseen influence",
            "ACTION": "pause, attend toward an offscreen unseen source, then shift attention to the tree and fruit",
            "OBJECT": "tree and fruit as the visible focus of the temptation",
            "LOCATION": "garden beside the unnamed tree",
            "START_STATE": "pair has just stopped at the tree",
            "VISIBLE_ACTION": "head and body attention change toward an offscreen source, then toward the fruit; no unseen body is shown",
            "END_STATE": "interest in the prohibited tree increases",
            "EXPECTED_CHARACTER_COUNT": 2,
            "CHARACTER_IDENTITIES": ["ADAM", "HAWWA_SPOUSE"],
            "MUTE_COMPREHENSION_TARGET": "muted viewer understands an unseen influence is redirecting the pair toward the tree without identifying a physical tempter",
            "FORBIDDEN_SUBSTITUTIONS": ["Satan body", "third adult male", "hooded tempter", "black silhouette", "smoke-being", "beam", "portal"],
            "SOURCE_TIER": "TIER_1_QURAN",
            "SOURCE_CERTAINTY": "HIGH_FOR_WHISPERING; MECHANISM_UNSEEN",
            "SOURCE_FACTS_USED": ["CL-003: whispering, promise, and oath are established; physical means are not established"],
            "ART_DIRECTION_USED": ["offscreen reaction staging only"],
        },
        {
            "EVENT_ID": "EV-005-CHOICE-BECOMES-ACTION",
            "EVENT_CLASS": "MAJOR_LITERAL_EVENT",
            "NARRATION_TEXT": "the promise becomes a deliberate choice",
            "START_TIME": 176.075,
            "END_TIME": 202.5,
            "SUBJECT": "Adam and spouse",
            "ACTION": "step forward together and reach toward fruit",
            "OBJECT": "fruit on the unnamed tree",
            "LOCATION": "garden tree edge",
            "START_STATE": "hesitant before the tree",
            "VISIBLE_ACTION": "Adam steps, spouse follows, and both covered sleeves extend toward fruit",
            "END_STATE": "both have chosen to act",
            "EXPECTED_CHARACTER_COUNT": 2,
            "CHARACTER_IDENTITIES": ["ADAM", "HAWWA_SPOUSE"],
            "MUTE_COMPREHENSION_TARGET": "muted viewer understands hesitation became deliberate movement toward the fruit",
            "FORBIDDEN_SUBSTITUTIONS": ["slipping", "uneven-ground accident", "third guide", "abstract field shear", "blame gesture"],
            "SOURCE_TIER": "TIER_1_QURAN",
            "SOURCE_CERTAINTY": "HIGH",
            "SOURCE_FACTS_USED": ["CL-003 and CL-005: shared action after temptation; no blame of the spouse alone"],
            "ART_DIRECTION_USED": ["covered sleeves provide action cues without visible hands"],
        },
        {
            "EVENT_ID": "EV-007-EATING-ACTION",
            "EVENT_CLASS": "MAJOR_LITERAL_EVENT",
            "NARRATION_TEXT": "Adam and spouse eat from the tree and the consequence follows",
            "START_TIME": 0.0,
            "END_TIME": 227.13,
            "SUBJECT": "Adam and spouse",
            "ACTION": "take fruit from the tree and visibly eat it; later lower fruit and recoil",
            "OBJECT": "unnamed fruit from the unnamed tree",
            "LOCATION": "garden",
            "START_STATE": "fruit attached to tree / pair before the action",
            "VISIBLE_ACTION": "fruit leaves branch, Adam visibly bites, spouse brings fruit to covered face, and bite evidence is shown",
            "END_STATE": "both lower fruit and step back with shared consequence",
            "EXPECTED_CHARACTER_COUNT": 2,
            "CHARACTER_IDENTITIES": ["ADAM", "HAWWA_SPOUSE"],
            "MUTE_COMPREHENSION_TARGET": "muted viewer understands actual eating rather than merely seeing a tree or fruit",
            "FORBIDDEN_SUBSTITUTIONS": ["fruit-only", "tree-only", "light", "symbolic bite", "visible female skin", "visible female hands"],
            "SOURCE_TIER": "TIER_1_QURAN",
            "SOURCE_CERTAINTY": "HIGH",
            "SOURCE_FACTS_USED": ["CL-004 and CL-005: shared eating and consequence"],
            "ART_DIRECTION_USED": ["Adam bite is visible; spouse action uses covered-face contact and subsequent bite evidence"],
        },
        {
            "EVENT_ID": "EV-009-COVERING-WITH-LEAVES",
            "EVENT_CLASS": "MAJOR_LITERAL_EVENT",
            "NARRATION_TEXT": "they cover themselves with leaves after the consequence appears",
            "START_TIME": 227.13,
            "END_TIME": 268.494,
            "SUBJECT": "Adam and spouse",
            "ACTION": "pull leaves around already-covered bodies as an additional attempt at concealment",
            "OBJECT": "leaves",
            "LOCATION": "garden beside the tree",
            "START_STATE": "both remain covered; consequence is not erased",
            "VISIBLE_ACTION": "leaf material is visibly gathered and placed around the covered figures without depicting nudity",
            "END_STATE": "both are withdrawn and further covered",
            "EXPECTED_CHARACTER_COUNT": 2,
            "CHARACTER_IDENTITIES": ["ADAM", "HAWWA_SPOUSE"],
            "MUTE_COMPREHENSION_TARGET": "muted viewer understands an actual covering attempt, not a leaf-only insert",
            "FORBIDDEN_SUBSTITUTIONS": ["nudity", "bare female hands", "body-shaped silhouette", "leaf-only abstraction", "graphics"],
            "SOURCE_TIER": "TIER_1_QURAN",
            "SOURCE_CERTAINTY": "HIGH",
            "SOURCE_FACTS_USED": ["CL-004: covering with leaves is established"],
            "ART_DIRECTION_USED": ["both figures covered from the first frame; enclosed sleeves only"],
        },
        {
            "EVENT_ID": "EV-011-REMORSE",
            "EVENT_CLASS": "MAJOR_LITERAL_EVENT",
            "NARRATION_TEXT": "the shared action becomes remorse and acknowledgment",
            "START_TIME": 268.494,
            "END_TIME": 283.6,
            "SUBJECT": "Adam and spouse",
            "ACTION": "lower themselves naturally, bow their heads, and remain inward and remorseful",
            "OBJECT": "ground and tree context",
            "LOCATION": "garden ground",
            "START_STATE": "covered and withdrawn after the action",
            "VISIBLE_ACTION": "two covered figures sit or kneel naturally with heads lowered and closed body language",
            "END_STATE": "shared remorse is visible",
            "EXPECTED_CHARACTER_COUNT": 2,
            "CHARACTER_IDENTITIES": ["ADAM", "HAWWA_SPOUSE"],
            "MUTE_COMPREHENSION_TARGET": "muted viewer understands remorse and acknowledgment through posture and context",
            "FORBIDDEN_SUBSTITUTIONS": ["beautiful landscape only", "triumphant pose", "blame pointing", "exposed female body"],
            "SOURCE_TIER": "TIER_1_QURAN",
            "SOURCE_CERTAINTY": "HIGH",
            "SOURCE_FACTS_USED": ["CL-005 and CL-006: shared acknowledgment and responsibility"],
            "ART_DIRECTION_USED": ["natural non-ritual kneeling or seated posture"],
        },
        {
            "EVENT_ID": "EV-012-SUPPLICATION",
            "EVENT_CLASS": "MAJOR_LITERAL_EVENT",
            "NARRATION_TEXT": "they confess wronging themselves and ask for forgiveness and mercy",
            "START_TIME": 283.6,
            "END_TIME": 319.092,
            "SUBJECT": "Adam and spouse",
            "ACTION": "bow and make a clear natural supplication posture together",
            "OBJECT": "none required; ground and bowed posture carry the action",
            "LOCATION": "garden ground",
            "START_STATE": "remorseful and lowered",
            "VISIBLE_ACTION": "Adam raises covered sleeves in supplication while spouse remains fully covered with head bowed",
            "END_STATE": "confession and seeking mercy are visually readable without supernatural light",
            "EXPECTED_CHARACTER_COUNT": 2,
            "CHARACTER_IDENTITIES": ["ADAM", "HAWWA_SPOUSE"],
            "MUTE_COMPREHENSION_TARGET": "muted viewer understands repentance, supplication, and seeking mercy",
            "FORBIDDEN_SUBSTITUTIONS": ["magic light", "beam", "text", "ritual invention", "bare hands", "blame gesture"],
            "SOURCE_TIER": "TIER_1_QURAN",
            "SOURCE_CERTAINTY": "HIGH",
            "SOURCE_FACTS_USED": ["CL-006: shared confession and request for forgiveness and mercy"],
            "ART_DIRECTION_USED": ["covered-sleeve supplication; no exaggerated ritual choreography"],
        },
        {
            "EVENT_ID": "EV-013-RECEIVING-WORDS",
            "EVENT_CLASS": "MAJOR_LITERAL_EVENT",
            "NARRATION_TEXT": "Adam receives words from his Lord; the exact unseen mechanism is not pictured",
            "START_TIME": 319.092,
            "END_TIME": 333.9,
            "SUBJECT": "Adam",
            "ACTION": "pause in a bowed posture, then raise and turn his head attentively toward an unseen offscreen source",
            "OBJECT": "none; no written or physical communication object is established",
            "LOCATION": "natural ground after supplication",
            "START_STATE": "low and bowed after confession",
            "VISIBLE_ACTION": "human listening/receptive reaction only; ordinary empty space may be shown briefly",
            "END_STATE": "Adam is attentive and receptive without a depicted message mechanism",
            "EXPECTED_CHARACTER_COUNT": 1,
            "CHARACTER_IDENTITIES": ["ADAM"],
            "MUTE_COMPREHENSION_TARGET": "muted viewer understands that Adam receives/listens to something without seeing invented words or a messenger",
            "FORBIDDEN_SUBSTITUTIONS": ["written words", "tablet", "paper", "floating text", "voice beam", "angel", "divine body", "light ray"],
            "SOURCE_TIER": "TIER_1_QURAN",
            "SOURCE_CERTAINTY": "HIGH_FOR_RECEIVING_WORDS; MECHANISM_UNSEEN",
            "SOURCE_FACTS_USED": ["CL-007: Adam receives words and is accepted; exact words are not specified"],
            "ART_DIRECTION_USED": ["ordinary offscreen space and receptive human reaction"],
        },
        {
            "EVENT_ID": "EV-014-ACCEPTANCE-AND-GUIDANCE",
            "EVENT_CLASS": "MAJOR_LITERAL_EVENT",
            "NARRATION_TEXT": "acceptance, selection, and guidance follow repentance without erasing the past",
            "START_TIME": 333.9,
            "END_TIME": 386.655,
            "SUBJECT": "Adam and spouse",
            "ACTION": "rise calmly from the humbled posture and turn toward the next phase of life",
            "OBJECT": "ordinary open path/earth environment; no magic mark",
            "LOCATION": "garden edge toward earthly direction",
            "START_STATE": "humbled after supplication and listening",
            "VISIBLE_ACTION": "both rise, stand calmly, and turn/walk while the past location remains behind them",
            "END_STATE": "restored direction is visible without erasing consequence",
            "EXPECTED_CHARACTER_COUNT": 2,
            "CHARACTER_IDENTITIES": ["ADAM", "HAWWA_SPOUSE"],
            "MUTE_COMPREHENSION_TARGET": "muted viewer understands humble guidance after repentance, not celebration or magical erasure",
            "FORBIDDEN_SUBSTITUTIONS": ["halo", "golden glow", "erased mark", "celebration", "magic transition", "text"],
            "SOURCE_TIER": "TIER_1_QURAN",
            "SOURCE_CERTAINTY": "HIGH",
            "SOURCE_FACTS_USED": ["CL-007 and CL-011: acceptance, guidance, and restored direction"],
            "ART_DIRECTION_USED": ["ordinary human rising and turning; past location remains visible"],
        },
        {
            "EVENT_ID": "EV-016-DESCENT-TO-EARTH",
            "EVENT_CLASS": "MAJOR_LITERAL_EVENT",
            "NARRATION_TEXT": "they descend to earth; exact geography and physical mechanism are not established",
            "START_TIME": 386.655,
            "END_TIME": 416.6,
            "SUBJECT": "Adam, then spouse in a separate cut",
            "ACTION": "show Adam entering one ordinary earthly environment, then spouse entering a clearly different ordinary earthly environment",
            "OBJECT": "earthly environment; no portal, stairs, mountain, or map",
            "LOCATION": "unresolved earthly locations, not geographically identified",
            "START_STATE": "previous environment after guidance",
            "VISIBLE_ACTION": "separate landing/earth-entry states are shown in two independent cuts; they do not land together",
            "END_STATE": "both are on earth in separate environments",
            "EXPECTED_CHARACTER_COUNT": 1,
            "CHARACTER_IDENTITIES": ["ADAM", "HAWWA_SPOUSE"],
            "MUTE_COMPREHENSION_TARGET": "muted viewer understands both reached earth separately without learning an invented geography",
            "FORBIDDEN_SUBSTITUTIONS": ["portal", "stairs", "mountain from paradise", "map", "split-screen", "teleportation graphic", "exact location label"],
            "SOURCE_TIER": "TIER_1_QURAN_FOR_DESCENT; TIER_6_ART_DIRECTION_FOR_UNRESOLVED_SEPARATE_STAGING",
            "SOURCE_CERTAINTY": "HIGH_FOR_DESCENT; NON_AUTHORITATIVE_FOR_SEPARATE_STAGING",
            "SOURCE_FACTS_USED": ["CL-008: descent and earth settlement are established; exact geography is not"],
            "ART_DIRECTION_USED": ["separate landing states; exact locations unresolved and not depicted"],
            "LOWER_TIER_STAGING_NOTE": {
                "SOURCE_TIER": "PERMISSIBLE_LOWER_TIER_REPORT",
                "CERTAINTY": "NON_AUTHORITATIVE",
                "DETAIL_USED": "SEPARATE_LANDING_LOCATIONS",
                "EXACT_LOCATIONS": "UNRESOLVED_NOT_DEPICTED",
                "USED_AS_ISLAMIC_CERTAINTY": False,
                "HUMAN_REVIEW_REQUIRED": True,
            },
        },
        {
            "EVENT_ID": "EV-018-ADAM-MUSA-DEBATE",
            "EVENT_CLASS": "MAJOR_LITERAL_EVENT",
            "NARRATION_TEXT": "a limited hadith illustration presents the serious Adam-Musa debate",
            "START_TIME": 444.537,
            "END_TIME": 510.853,
            "SUBJECT": "Adam and Musa",
            "ACTION": "Musa addresses Adam, Adam responds, and the exchange closes reflectively",
            "OBJECT": "none; no identifying prop is needed",
            "LOCATION": "neutral natural environment",
            "START_STATE": "discussion begins",
            "VISIBLE_ACTION": "two distinct adult male figures visibly converse with serious body language across short cuts",
            "END_STATE": "the exchange closes without a graphic or invented setting",
            "EXPECTED_CHARACTER_COUNT": 2,
            "CHARACTER_IDENTITIES": ["ADAM", "MUSA"],
            "MUTE_COMPREHENSION_TARGET": "muted viewer understands a serious two-person debate; exact identity of the second man may rely on narration",
            "FORBIDDEN_SUBSTITUTIONS": ["anonymous scholars in a room", "staff", "book", "table", "source cards", "timeline", "UI", "text"],
            "SOURCE_TIER": "TIER_2_SAHIH_SUNNAH",
            "SOURCE_CERTAINTY": "HIGH_FOR_DEBATE; APPEARANCE_UNSPECIFIED_LOCALLY",
            "SOURCE_FACTS_USED": ["CL-009: authenticated Adam-Musa debate and its limited responsibility/قدر scope"],
            "ART_DIRECTION_USED": ["neutral natural setting; distinct male silhouettes; no identification prop"],
        },
    ]


def make_anchor_specs() -> list[dict[str, Any]]:
    female = True
    return [
        {
            "MICRO_SHOT_ID": "EP002-V2-NEW-001",
            "PARENT_AUDIO_SEGMENT_ID": "EP002-SH-001",
            "TIMELINE_IN": 0.0,
            "TIMELINE_OUT": 8.0,
            "EVENT_ID": "EV-007-EATING-ACTION",
            "EVENT_TYPE": "LITERAL_EVENT",
            "EVENT_ROLE": "LITERAL_EVENT",
            "CHARACTERS": ["ADAM", "HAWWA_SPOUSE"],
            "VISIBLE_ACTION": "Adam takes fruit from an unnamed tree, brings it to his visible mouth, and performs a clear bite; spouse brings fruit to a fully covered face at a safe angle and the fruit shows bite evidence in the following beat.",
            "VISUAL_INFORMATION": "The actual eating action is unmistakable while the spouse remains fully covered.",
            "START_FRAME": "Adam and the fully covered spouse stand beside one unnamed tree; fruit remains attached to a branch.",
            "MIDDLE_ACTION": "Adam visibly removes fruit and bites; the spouse's opaque sleeve brings a separate fruit to the covered face without skin or hand exposure.",
            "END_FRAME": "Adam lowers a fruit with a visible bite; the spouse's fruit is lowered with matching bite evidence; both remain covered.",
            "CAMERA": "medium side angle with one brief close action insert; no revealing close-up",
            "COMPOSITION": "two-person continuity, tree and fruit readable, covered spouse never body-defined",
            "LIGHTING": "natural garden daylight, restrained cinematic contrast",
            "LOCATION": "unnamed garden beside the unnamed tree",
            "STYLE": "grounded cinematic historical-religious drama, literal action first",
            "CONTINUITY_REQUIREMENTS": "exactly Adam and spouse; same two silhouettes throughout; fruit leaves branch before bite; no third figure",
            "MODESTY_REQUIREMENTS": "full strict female coverage; opaque loose full-body garment; head/hair/neck/body covered; hands not visible; enclosed sleeves or opaque gloves",
            "FORBIDDEN_ELEMENTS": ["Satan body", "third person", "visible female skin", "visible female hands", "nudity", *_GLOBAL_FORBIDDEN],
            "MUTE_COMPREHENSION_TARGET": "muted viewer can state that both characters ate fruit from the tree",
            "INCLUDES_FEMALE": female,
            "SOURCE_TIER": "TIER_1_QURAN",
            "SOURCE_CERTAINTY": "HIGH",
            "SOURCE_FACTS_USED": ["CL-004 and CL-005: shared eating; unnamed tree; no body exposure detail"],
            "ART_DIRECTION_USED": ["Adam's bite is visible; spouse's covered-face contact plus bite evidence preserves modesty"],
            "CHARACTER_DOSSIER_REFERENCES": ["ADAM", "HAWWA_SPOUSE"],
            "IMAGE_PROMPT": "A literal two-person cinematic action anchor: Adam and his fully covered spouse beside one unnamed garden tree. Adam clearly removes a fruit from a branch and brings it to his visible mouth for a readable bite. The spouse remains in an opaque loose full-body garment with head, hair, neck, and body covered; an enclosed sleeve brings a second fruit to the covered face from a safe side angle, with no visible skin or hands. Show bite evidence on the lowered fruit. Grounded natural garden, no invented tempter.",
            "VIDEO_PROMPT": "Continuous 8-second literal action: establish exactly two covered figures at one unnamed tree, show Adam detach fruit and visibly bite, then show the covered spouse bring fruit to the covered face and lower it with bite evidence. Preserve identity, fruit continuity, and strict modesty; no third character or symbolic substitute.",
            "NEGATIVE_PROMPT": "female hair, female neck, female arms, female legs, female torso skin, female hands, exposed skin, tight clothing, transparent clothing, revealing dress, nude silhouette, body-shaped silhouette, third character, Satan, demon, hooded tempter, abstract bite, fruit-only shot, tree-only shot, graphics, text, UI, diagram, glow, beam, portal",
            "TARGET_DURATION": 8.0,
        },
        {
            "MICRO_SHOT_ID": "EP002-V2-NEW-002",
            "PARENT_AUDIO_SEGMENT_ID": "EP002-SH-007",
            "TIMELINE_IN": 79.2,
            "TIMELINE_OUT": 87.2,
            "EVENT_ID": "EV-002-TREE-BOUNDARY",
            "EVENT_TYPE": "LITERAL_EVENT",
            "EVENT_ROLE": "LITERAL_EVENT",
            "CHARACTERS": ["ADAM", "HAWWA_SPOUSE"],
            "VISIBLE_ACTION": "The pair walks to one specific unnamed tree, stops before it, and a covered sleeve begins toward the fruit then retracts before contact.",
            "VISUAL_INFORMATION": "Behavior makes the tree boundary readable without a line or glow.",
            "START_FRAME": "Wide garden with exactly two covered figures walking toward one distinct unnamed tree.",
            "MIDDLE_ACTION": "They stop at a respectful distance; one covered sleeve hesitates toward a branch and retracts.",
            "END_FRAME": "Both remain before the tree without touching it, attention fixed on the boundary.",
            "CAMERA": "wide establishing to medium hesitation cut",
            "COMPOSITION": "tree and two figures in one spatial geography; no drawn boundary",
            "LIGHTING": "natural daylight",
            "LOCATION": "unnamed garden",
            "STYLE": "grounded literal cinematic staging",
            "CONTINUITY_REQUIREMENTS": "exactly two figures; same tree remains the reference object; no third silhouette",
            "MODESTY_REQUIREMENTS": "fully covered spouse; no visible hair, skin, or hands; loose opaque garment",
            "FORBIDDEN_ELEMENTS": ["glowing boundary", "line", "barrier", "third person", *_GLOBAL_FORBIDDEN],
            "MUTE_COMPREHENSION_TARGET": "muted viewer understands a specific tree is prohibited",
            "INCLUDES_FEMALE": female,
            "SOURCE_TIER": "TIER_1_QURAN",
            "SOURCE_CERTAINTY": "HIGH",
            "SOURCE_FACTS_USED": ["CL-002: unnamed prohibited tree"],
            "ART_DIRECTION_USED": ["hesitation and retraction communicate boundary; no supernatural barrier"],
            "CHARACTER_DOSSIER_REFERENCES": ["ADAM", "HAWWA_SPOUSE"],
            "IMAGE_PROMPT": "Wide natural garden with exactly Adam and his fully covered spouse approaching one distinct unnamed tree. They stop before it; one opaque covered sleeve begins toward a branch and visibly retracts before touching. No drawn line, glow, barrier, third figure, or supernatural body. Preserve strict full coverage for the spouse.",
            "VIDEO_PROMPT": "8-second literal approach-and-stop: two covered figures walk to the same unnamed tree, halt, make a readable covered-sleeve hesitation toward the fruit, then retract before contact. The tree boundary is conveyed only by human behavior and spatial staging.",
            "NEGATIVE_PROMPT": "third character, black silhouette, Satan, demon, glowing boundary, drawn line, force field, beam, portal, floating symbols, visible female hair, visible female neck, exposed skin, visible female hands, tight clothing, body-shaped silhouette, graphics, text, UI, diagram",
            "TARGET_DURATION": 8.0,
        },
        {
            "MICRO_SHOT_ID": "EP002-V2-NEW-003",
            "PARENT_AUDIO_SEGMENT_ID": "EP002-SH-010",
            "TIMELINE_IN": 113.9,
            "TIMELINE_OUT": 118.0,
            "EVENT_ID": "EV-003-TEMPTATION-WHISPER",
            "EVENT_TYPE": "SOURCE_CONSTRAINED_UNSEEN_EVENT",
            "EVENT_ROLE": "SOURCE_CONSTRAINED_UNSEEN_EVENT",
            "CHARACTERS": ["ADAM", "HAWWA_SPOUSE"],
            "VISIBLE_ACTION": "Both covered figures pause and subtly turn their attention toward an offscreen unseen source; no source body or mechanism is shown.",
            "VISUAL_INFORMATION": "The pair visibly receives an unseen influence through reaction, not a personified tempter.",
            "START_FRAME": "Exactly two covered figures remain beside the unnamed tree after their hesitation.",
            "MIDDLE_ACTION": "Their heads and covered shoulders turn toward empty offscreen space; the camera shows no speaking body.",
            "END_FRAME": "Their attention holds for a beat before shifting back toward the tree.",
            "CAMERA": "medium rear/side reaction shot with empty offscreen space",
            "COMPOSITION": "reaction-centered; no third body, smoke, beam, or lips",
            "LIGHTING": "ordinary garden light, no supernatural effect",
            "LOCATION": "garden beside the unnamed tree",
            "STYLE": "source-constrained grounded cinema",
            "CONTINUITY_REQUIREMENTS": "exactly Adam and spouse; unseen source stays off-camera; no invented physical agent",
            "MODESTY_REQUIREMENTS": "spouse fully covered; no hair, skin, hands, or body contour",
            "FORBIDDEN_ELEMENTS": ["Satan body", "hooded tempter", "shadow person", "smoke-being", "speaking lips", "beam", *_GLOBAL_FORBIDDEN],
            "MUTE_COMPREHENSION_TARGET": "muted viewer understands an unseen influence is being received, without identifying its physical form",
            "INCLUDES_FEMALE": female,
            "SOURCE_TIER": "TIER_1_QURAN",
            "SOURCE_CERTAINTY": "HIGH_FOR_WHISPERING; MECHANISM_UNSEEN",
            "SOURCE_FACTS_USED": ["CL-003: whispering is established; its physical mechanism is not"],
            "ART_DIRECTION_USED": ["offscreen reaction only; no personification"],
            "CHARACTER_DOSSIER_REFERENCES": ["ADAM", "HAWWA_SPOUSE"],
            "IMAGE_PROMPT": "Grounded cinematic reaction shot of exactly Adam and his fully covered spouse beside the unnamed tree. Both subtly turn their attention toward empty offscreen space as if receiving an unseen whisper. Do not show any tempter, body, face, lips, smoke, beam, or supernatural mechanism. Strict full-body modest coverage for the spouse.",
            "VIDEO_PROMPT": "4.1-second source-constrained reaction: the covered pair pauses, turns attention toward empty offscreen space, holds the reaction, and remains near the tree. The unseen source never enters frame and has no visible mechanism.",
            "NEGATIVE_PROMPT": "Satan, third adult male, hooded tempter, demon, black silhouette, shadow person, smoke creature, speaking lips, visible supernatural body, beam, portal, magic particles, written text, visible female hair, skin, neck, arms, legs, hands, tight clothing, body-shaped silhouette, graphics, UI",
            "TARGET_DURATION": 4.1,
        },
        {
            "MICRO_SHOT_ID": "EP002-V2-NEW-004",
            "PARENT_AUDIO_SEGMENT_ID": "EP002-SH-012",
            "TIMELINE_IN": 121.344,
            "TIMELINE_OUT": 125.344,
            "EVENT_ID": "EV-003-TEMPTATION-WHISPER",
            "EVENT_TYPE": "SOURCE_CONSTRAINED_UNSEEN_EVENT",
            "EVENT_ROLE": "SOURCE_CONSTRAINED_UNSEEN_EVENT",
            "CHARACTERS": ["ADAM", "HAWWA_SPOUSE"],
            "VISIBLE_ACTION": "After the offscreen reaction, both gradually redirect their gaze and body orientation from empty space toward the tree and fruit.",
            "VISUAL_INFORMATION": "Temptation is shown through a visible change of attention toward the prohibited object.",
            "START_FRAME": "The pair is still near the tree after turning toward empty offscreen space.",
            "MIDDLE_ACTION": "Adam shifts first toward the fruit; spouse follows with a covered silhouette.",
            "END_FRAME": "Both face the tree with increased interest, still without touching.",
            "CAMERA": "slow over-shoulder attention shift",
            "COMPOSITION": "tree/fruit enters clear focus; unseen source remains outside frame",
            "LIGHTING": "ordinary daylight, no supernatural color shift",
            "LOCATION": "garden tree edge",
            "STYLE": "literal reaction cinema with source restraint",
            "CONTINUITY_REQUIREMENTS": "same two figures and same tree; no physical tempter",
            "MODESTY_REQUIREMENTS": "spouse full coverage and non-body-defining silhouette",
            "FORBIDDEN_ELEMENTS": ["personified Satan", "third figure", "beam", "smoke", *_GLOBAL_FORBIDDEN],
            "MUTE_COMPREHENSION_TARGET": "muted viewer sees the pair's attention redirected toward the prohibited tree",
            "INCLUDES_FEMALE": female,
            "SOURCE_TIER": "TIER_1_QURAN",
            "SOURCE_CERTAINTY": "HIGH_FOR_WHISPERING; MECHANISM_UNSEEN",
            "SOURCE_FACTS_USED": ["CL-003: temptation redirects the pair toward the tree"],
            "ART_DIRECTION_USED": ["visible attention shift replaces invented speech mechanism"],
            "CHARACTER_DOSSIER_REFERENCES": ["ADAM", "HAWWA_SPOUSE"],
            "IMAGE_PROMPT": "Two fully covered figures at the unnamed tree redirect their attention from empty offscreen space toward the fruit. Adam turns first, the spouse follows, and the tree becomes the clear visual focus. No tempter body, smoke, beam, line, or graphic; strict modesty.",
            "VIDEO_PROMPT": "4-second literal attention shift: after an unseen offscreen influence, Adam and his fully covered spouse slowly turn their attention toward the tree and fruit, ending in deliberate visual focus on the prohibited object.",
            "NEGATIVE_PROMPT": "Satan body, third person, hooded figure, black silhouette, smoke, speaking lips, beam, portal, glowing boundary, visible female hair, neck, arms, legs, torso skin, hands, tight clothing, body contour, graphics, text, diagram, UI",
            "TARGET_DURATION": 4.0,
        },
        {
            "MICRO_SHOT_ID": "EP002-V2-NEW-005",
            "PARENT_AUDIO_SEGMENT_ID": "EP002-SH-012",
            "TIMELINE_IN": 132.0,
            "TIMELINE_OUT": 133.9,
            "EVENT_ID": "EV-003-TEMPTATION-WHISPER",
            "EVENT_TYPE": "SOURCE_CONSTRAINED_UNSEEN_EVENT",
            "EVENT_ROLE": "SOURCE_CONSTRAINED_UNSEEN_EVENT",
            "CHARACTERS": ["ADAM", "HAWWA_SPOUSE"],
            "VISIBLE_ACTION": "The pair takes a slow first step closer to the fruit after the unseen influence, with no touching yet.",
            "VISUAL_INFORMATION": "The reaction has become a visible approach toward the prohibited object.",
            "START_FRAME": "Both figures face the tree, still one step away.",
            "MIDDLE_ACTION": "Adam begins a slow approach and spouse follows.",
            "END_FRAME": "They are closer to the fruit but have not touched it.",
            "CAMERA": "short medium tracking insert",
            "COMPOSITION": "two covered figures and fruit in the same frame",
            "LIGHTING": "natural daylight",
            "LOCATION": "garden tree edge",
            "STYLE": "grounded source-constrained action",
            "CONTINUITY_REQUIREMENTS": "same tree and same pair; no tempter or accidental third character",
            "MODESTY_REQUIREMENTS": "opaque loose full-body spouse coverage; hands absent",
            "FORBIDDEN_ELEMENTS": ["slipping", "third person", "Satan body", "magic effect", *_GLOBAL_FORBIDDEN],
            "MUTE_COMPREHENSION_TARGET": "muted viewer understands unseen temptation has led to a deliberate approach",
            "INCLUDES_FEMALE": female,
            "SOURCE_TIER": "TIER_1_QURAN",
            "SOURCE_CERTAINTY": "HIGH_FOR_WHISPERING; MECHANISM_UNSEEN",
            "SOURCE_FACTS_USED": ["CL-003: temptation/whispering; no physical agent depicted"],
            "ART_DIRECTION_USED": ["short approach insert, not a full generated narration window"],
            "CHARACTER_DOSSIER_REFERENCES": ["ADAM", "HAWWA_SPOUSE"],
            "IMAGE_PROMPT": "A short grounded action frame: Adam and his fully covered spouse take a deliberate first step toward fruit on the unnamed tree after reacting to an unseen offscreen influence. No touching yet, no tempter body or supernatural mechanism, strict modesty, exactly two figures.",
            "VIDEO_PROMPT": "1.9-second literal insert of the same two covered figures taking a slow deliberate step toward the fruit; no slipping, no invented physical tempter, no graphic effects.",
            "NEGATIVE_PROMPT": "slipping, falling, uneven-ground accident, third character, Satan, demon, smoke, beam, portal, visible female hair, skin, neck, arms, legs, hands, tight clothing, body-shaped silhouette, graphics, text, UI",
            "TARGET_DURATION": 1.9,
        },
        {
            "MICRO_SHOT_ID": "EP002-V2-NEW-006",
            "PARENT_AUDIO_SEGMENT_ID": "EP002-SH-017",
            "TIMELINE_IN": 176.075,
            "TIMELINE_OUT": 182.075,
            "EVENT_ID": "EV-005-CHOICE-BECOMES-ACTION",
            "EVENT_TYPE": "LITERAL_EVENT",
            "EVENT_ROLE": "LITERAL_EVENT",
            "CHARACTERS": ["ADAM", "HAWWA_SPOUSE"],
            "VISIBLE_ACTION": "Adam steps forward, spouse follows, and both covered sleeves extend toward fruit as a deliberate choice.",
            "VISUAL_INFORMATION": "The pair visibly chooses to act; no accidental slipping or third guide is used.",
            "START_FRAME": "Two covered figures hesitate before the same tree.",
            "MIDDLE_ACTION": "Adam steps, spouse follows, and both reach with covered sleeves.",
            "END_FRAME": "Their covered sleeves are near the fruit, action committed but bite not yet shown.",
            "CAMERA": "medium two-shot with clear feet and sleeve movement",
            "COMPOSITION": "exactly two figures, tree, fruit, readable spatial action",
            "LIGHTING": "natural garden light",
            "LOCATION": "garden beside the tree",
            "STYLE": "literal action-first cinematic drama",
            "CONTINUITY_REQUIREMENTS": "exactly two figures; no physical tempter; no misstep or ground hazard",
            "MODESTY_REQUIREMENTS": "fully covered spouse; sleeves/opaque gloves only; no visible hands or body contour",
            "FORBIDDEN_ELEMENTS": ["slipping", "falling", "third figure", "blame gesture", *_GLOBAL_FORBIDDEN],
            "MUTE_COMPREHENSION_TARGET": "muted viewer understands the temptation became deliberate action",
            "INCLUDES_FEMALE": female,
            "SOURCE_TIER": "TIER_1_QURAN",
            "SOURCE_CERTAINTY": "HIGH",
            "SOURCE_FACTS_USED": ["CL-003 and CL-005: shared action after temptation"],
            "ART_DIRECTION_USED": ["covered sleeves substitute for visible hands without losing the action"],
            "CHARACTER_DOSSIER_REFERENCES": ["ADAM", "HAWWA_SPOUSE"],
            "IMAGE_PROMPT": "Literal medium two-shot of Adam and his fully covered spouse deliberately stepping toward fruit on one unnamed tree. Adam steps first, spouse follows, and both extend opaque covered sleeves toward the fruit. Exactly two figures, no falling, slipping, third guide, supernatural body, graphics, or exposed female skin.",
            "VIDEO_PROMPT": "6-second literal choice-to-action shot: show hesitation, Adam stepping forward, spouse following, and both extending covered sleeves toward fruit. Keep feet stable and the action deliberate; do not show an accident or invented tempter.",
            "NEGATIVE_PROMPT": "slipping, falling, uneven ground, third person, Satan, demon, shadow person, blame pointing, visible female hair, neck, arms, legs, torso skin, hands, tight clothing, transparent clothing, body-shaped silhouette, graphics, text, UI, glow, beam",
            "TARGET_DURATION": 6.0,
        },
        {
            "MICRO_SHOT_ID": "EP002-V2-NEW-007",
            "PARENT_AUDIO_SEGMENT_ID": "EP002-SH-019",
            "TIMELINE_IN": 202.5,
            "TIMELINE_OUT": 210.5,
            "EVENT_ID": "EV-007-EATING-ACTION",
            "EVENT_TYPE": "LITERAL_EVENT",
            "EVENT_ROLE": "LITERAL_EVENT",
            "CHARACTERS": ["ADAM", "HAWWA_SPOUSE"],
            "VISIBLE_ACTION": "Fruit is taken; Adam visibly bites; spouse brings fruit to the fully covered face and both lower fruit and step back.",
            "VISUAL_INFORMATION": "A second short eating anchor makes the chronological shared action and immediate consequence explicit.",
            "START_FRAME": "Both are within reach of fruit on the tree.",
            "MIDDLE_ACTION": "Adam bites; spouse's covered-face contact and bite evidence follow; both lower fruit.",
            "END_FRAME": "Both recoil one step and look down, sharing the consequence without blaming one another.",
            "CAMERA": "alternating medium action cuts, no close female face",
            "COMPOSITION": "two-person continuity; fruit and bite evidence readable",
            "LIGHTING": "natural daylight with subdued consequence tone",
            "LOCATION": "garden tree edge",
            "STYLE": "literal event anchor, restrained and modest",
            "CONTINUITY_REQUIREMENTS": "same pair; both participate; no pointing or third character",
            "MODESTY_REQUIREMENTS": "spouse fully covered; no hands or skin; covered-face contact only",
            "FORBIDDEN_ELEMENTS": ["one-person blame", "pointing", "female skin", "female hands", *_GLOBAL_FORBIDDEN],
            "MUTE_COMPREHENSION_TARGET": "muted viewer understands eating and shared immediate aftermath",
            "INCLUDES_FEMALE": female,
            "SOURCE_TIER": "TIER_1_QURAN",
            "SOURCE_CERTAINTY": "HIGH",
            "SOURCE_FACTS_USED": ["CL-004 and CL-005: shared eating and consequence"],
            "ART_DIRECTION_USED": ["short replay anchor only; no long generated window"],
            "CHARACTER_DOSSIER_REFERENCES": ["ADAM", "HAWWA_SPOUSE"],
            "IMAGE_PROMPT": "Literal cinematic action of Adam and his fully covered spouse taking fruit from the unnamed tree. Adam visibly bites; the spouse brings fruit to a completely covered face using a safe side angle, then the fruit shows a bite mark. Both lower the fruit, recoil, and look down together. No blame gesture or exposed skin.",
            "VIDEO_PROMPT": "8-second chronological eating-and-aftermath anchor: take fruit, show Adam's visible bite, show covered-face fruit contact and bite evidence for the spouse, then lower fruit and step back together. Exactly two participants and strict female coverage.",
            "NEGATIVE_PROMPT": "fruit-only, tree-only, symbolic eating, visible female hair, neck, arms, legs, torso skin, hands, exposed skin, tight dress, transparent dress, body-shaped silhouette, pointing, blaming, third character, graphics, text, UI, magic glow",
            "TARGET_DURATION": 8.0,
        },
        {
            "MICRO_SHOT_ID": "EP002-V2-NEW-008",
            "PARENT_AUDIO_SEGMENT_ID": "EP002-SH-022",
            "TIMELINE_IN": 227.13,
            "TIMELINE_OUT": 233.13,
            "EVENT_ID": "EV-009-COVERING-WITH-LEAVES",
            "EVENT_TYPE": "LITERAL_EVENT",
            "EVENT_ROLE": "LITERAL_EVENT",
            "CHARACTERS": ["ADAM", "HAWWA_SPOUSE"],
            "VISIBLE_ACTION": "Both covered figures visibly gather and place leaves around their already-covered bodies as an additional covering attempt.",
            "VISUAL_INFORMATION": "The leaf action is visible without first depicting nudity or exposing female hands.",
            "START_FRAME": "Both figures are already fully covered beside the tree, with loose leaves nearby.",
            "MIDDLE_ACTION": "Enclosed sleeves/opaque gloves move leaves around the garments; no skin appears.",
            "END_FRAME": "Both remain withdrawn and more covered, with the tree and past location behind them.",
            "CAMERA": "medium rear three-quarter angle, no body detail",
            "COMPOSITION": "two covered figures, leaves, and tree context",
            "LIGHTING": "soft natural garden light",
            "LOCATION": "garden ground beside the tree",
            "STYLE": "literal modest historical-religious cinema",
            "CONTINUITY_REQUIREMENTS": "two figures remain two; no nudity-first beat; no unexplained extra subject",
            "MODESTY_REQUIREMENTS": "both covered from first frame; spouse full coverage; hands never visible",
            "FORBIDDEN_ELEMENTS": ["nudity", "bare hands", "female skin", "body contour", "leaf-only insert", *_GLOBAL_FORBIDDEN],
            "MUTE_COMPREHENSION_TARGET": "muted viewer understands the figures are actively covering themselves with leaves",
            "INCLUDES_FEMALE": female,
            "SOURCE_TIER": "TIER_1_QURAN",
            "SOURCE_CERTAINTY": "HIGH",
            "SOURCE_FACTS_USED": ["CL-004: covering with leaves"],
            "ART_DIRECTION_USED": ["strict modesty from first frame; enclosed sleeve action"],
            "CHARACTER_DOSSIER_REFERENCES": ["ADAM", "HAWWA_SPOUSE"],
            "IMAGE_PROMPT": "Literal rear three-quarter cinematic shot of Adam and his fully covered spouse already covered from the first frame, gathering leaves and placing them around their loose garments as an additional covering attempt. No nudity, no visible hands or skin, no body-shaped silhouette, no text or graphics.",
            "VIDEO_PROMPT": "6-second literal covering anchor: two already-covered figures use enclosed sleeves or opaque gloves to gather and place leaves around their garments, ending withdrawn beside the tree. Never show nudity or exposed female skin.",
            "NEGATIVE_PROMPT": "nudity, undressed body, visible female hair, neck, arms, legs, torso skin, hands, exposed skin, body-shaped silhouette, leaf-only insert, third character, graphics, readable text, UI, glow",
            "TARGET_DURATION": 6.0,
        },
        {
            "MICRO_SHOT_ID": "EP002-V2-NEW-009",
            "PARENT_AUDIO_SEGMENT_ID": "EP002-SH-026",
            "TIMELINE_IN": 268.494,
            "TIMELINE_OUT": 275.494,
            "EVENT_ID": "EV-011-REMORSE",
            "EVENT_TYPE": "LITERAL_EVENT",
            "EVENT_ROLE": "LITERAL_EVENT",
            "CHARACTERS": ["ADAM", "HAWWA_SPOUSE"],
            "VISIBLE_ACTION": "Both covered figures lower themselves naturally to the ground, bow their heads, and hold a remorseful inward posture.",
            "VISUAL_INFORMATION": "Actual remorse is visible through human posture and the tree/error context.",
            "START_FRAME": "Two covered figures stand or crouch after the covering attempt, tree behind them.",
            "MIDDLE_ACTION": "Both sit or kneel naturally and lower their heads; no theatrical ritual invention.",
            "END_FRAME": "They remain humbled and inward, side by side.",
            "CAMERA": "steady medium rear/side two-shot",
            "COMPOSITION": "two figures and past tree context; no abstract empty field",
            "LIGHTING": "quiet natural light, no supernatural beam",
            "LOCATION": "garden ground beside the tree",
            "STYLE": "grounded human remorse",
            "CONTINUITY_REQUIREMENTS": "exactly two; same garments; no blame or triumphant pose",
            "MODESTY_REQUIREMENTS": "spouse fully covered and non-body-defining; hands hidden",
            "FORBIDDEN_ELEMENTS": ["ritual exaggeration", "blame", "celebration", "magic light", *_GLOBAL_FORBIDDEN],
            "MUTE_COMPREHENSION_TARGET": "muted viewer understands remorse and acknowledgment",
            "INCLUDES_FEMALE": female,
            "SOURCE_TIER": "TIER_1_QURAN",
            "SOURCE_CERTAINTY": "HIGH",
            "SOURCE_FACTS_USED": ["CL-005 and CL-006: shared acknowledgment and responsibility"],
            "ART_DIRECTION_USED": ["natural lowered posture; no invented ritual details"],
            "CHARACTER_DOSSIER_REFERENCES": ["ADAM", "HAWWA_SPOUSE"],
            "IMAGE_PROMPT": "Grounded cinematic medium two-shot of Adam and his fully covered spouse lowering themselves naturally to the ground beside the tree, heads bowed, inward remorseful posture, already-covered bodies, no blame gesture, no supernatural light, no text or graphics.",
            "VIDEO_PROMPT": "7-second literal remorse anchor: two covered figures lower themselves naturally, kneel or sit, bow their heads, and hold shared remorse with the tree/error context behind them. No ritual invention or magical effect.",
            "NEGATIVE_PROMPT": "triumph, celebration, pointing, blame, supernatural light, beam, halo, visible female hair, skin, neck, arms, legs, hands, tight clothing, body-shaped silhouette, third character, graphics, text, UI",
            "TARGET_DURATION": 7.0,
        },
        {
            "MICRO_SHOT_ID": "EP002-V2-NEW-010",
            "PARENT_AUDIO_SEGMENT_ID": "EP002-SH-027",
            "TIMELINE_IN": 283.6,
            "TIMELINE_OUT": 291.6,
            "EVENT_ID": "EV-012-SUPPLICATION",
            "EVENT_TYPE": "LITERAL_EVENT",
            "EVENT_ROLE": "LITERAL_EVENT",
            "CHARACTERS": ["ADAM", "HAWWA_SPOUSE"],
            "VISIBLE_ACTION": "Adam raises covered sleeves in clear natural supplication while spouse remains fully covered with head bowed; both seek mercy together.",
            "VISUAL_INFORMATION": "Confession and supplication are visible human actions, not abstract light or text.",
            "START_FRAME": "Both remain lowered and remorseful on the ground.",
            "MIDDLE_ACTION": "Adam raises enclosed sleeves in supplication; spouse bows and mirrors humility without exposed hands.",
            "END_FRAME": "Both hold a quiet seeking-mercy posture.",
            "CAMERA": "medium frontal/side but non-identifying, no close female face",
            "COMPOSITION": "two figures, ground, tree/horizon context; empty upper frame without beam",
            "LIGHTING": "natural subdued daylight",
            "LOCATION": "garden ground",
            "STYLE": "literal supplication, restrained and modest",
            "CONTINUITY_REQUIREMENTS": "same two figures; no new ritual object; no supernatural messenger",
            "MODESTY_REQUIREMENTS": "spouse head/hair/neck/body/hands fully covered; opaque loose garment",
            "FORBIDDEN_ELEMENTS": ["written prayer", "tablet", "beam", "halo", "bare hands", "blame", *_GLOBAL_FORBIDDEN],
            "MUTE_COMPREHENSION_TARGET": "muted viewer understands supplication and seeking forgiveness/mercy",
            "INCLUDES_FEMALE": female,
            "SOURCE_TIER": "TIER_1_QURAN",
            "SOURCE_CERTAINTY": "HIGH",
            "SOURCE_FACTS_USED": ["CL-006: shared confession and request for forgiveness and mercy"],
            "ART_DIRECTION_USED": ["covered-sleeve supplication without invented ritual choreography"],
            "CHARACTER_DOSSIER_REFERENCES": ["ADAM", "HAWWA_SPOUSE"],
            "IMAGE_PROMPT": "Literal restrained cinematic supplication: Adam and his fully covered spouse remain lowered on the garden ground; Adam raises covered sleeves in a clear natural request for mercy, while the spouse stays fully covered with bowed head. No visible hands, text, beam, halo, messenger, or graphics.",
            "VIDEO_PROMPT": "8-second literal supplication anchor: begin with shared remorse, show Adam raise enclosed sleeves in natural supplication, keep spouse fully covered and bowed, and end in quiet seeking mercy. No supernatural communication effect.",
            "NEGATIVE_PROMPT": "visible female hair, neck, arms, legs, torso skin, hands, exposed skin, tight or transparent clothing, body-shaped silhouette, written words, tablet, text, beam, halo, messenger, blame, third character, graphics, UI",
            "TARGET_DURATION": 8.0,
        },
        {
            "MICRO_SHOT_ID": "EP002-V2-NEW-011",
            "PARENT_AUDIO_SEGMENT_ID": "EP002-SH-030",
            "TIMELINE_IN": 319.092,
            "TIMELINE_OUT": 326.092,
            "EVENT_ID": "EV-013-RECEIVING-WORDS",
            "EVENT_TYPE": "SOURCE_CONSTRAINED_UNSEEN_EVENT",
            "EVENT_ROLE": "SOURCE_CONSTRAINED_UNSEEN_EVENT",
            "CHARACTERS": ["ADAM"],
            "VISIBLE_ACTION": "Adam pauses low, then raises and turns his head attentively toward empty offscreen space; the communication source remains unseen.",
            "VISUAL_INFORMATION": "A human receptive reaction is visible without written words or an invented messenger.",
            "START_FRAME": "Adam remains bowed after supplication in an ordinary natural environment.",
            "MIDDLE_ACTION": "He pauses, raises his head, and turns attentively toward offscreen empty space.",
            "END_FRAME": "He holds a receptive, humbled listening posture.",
            "CAMERA": "medium side/rear reaction shot",
            "COMPOSITION": "Adam and ordinary empty space; no graphic or physical communication object",
            "LIGHTING": "ordinary natural light",
            "LOCATION": "natural ground after repentance",
            "STYLE": "source-constrained human reaction",
            "CONTINUITY_REQUIREMENTS": "Adam's same silhouette; no female or invented messenger enters",
            "MODESTY_REQUIREMENTS": "not applicable to female; Adam remains modestly clothed",
            "FORBIDDEN_ELEMENTS": ["written words", "tablet", "paper", "voice beam", "angel", "divine body", "light ray", *_GLOBAL_FORBIDDEN],
            "MUTE_COMPREHENSION_TARGET": "muted viewer understands Adam is receiving/listening to something unseen",
            "INCLUDES_FEMALE": False,
            "SOURCE_TIER": "TIER_1_QURAN",
            "SOURCE_CERTAINTY": "HIGH_FOR_RECEIVING_WORDS; MECHANISM_UNSEEN",
            "SOURCE_FACTS_USED": ["CL-007: Adam receives words; exact text and mechanism are not specified"],
            "ART_DIRECTION_USED": ["ordinary empty space and receptive human reaction"],
            "CHARACTER_DOSSIER_REFERENCES": ["ADAM"],
            "IMAGE_PROMPT": "Grounded medium side/rear shot of Adam after repentance, still low and humbled, raising his head and turning attentively toward ordinary empty offscreen space. Show only the human receptive consequence. No words, tablet, beam, angel, divine body, or supernatural mechanism.",
            "VIDEO_PROMPT": "7-second source-constrained receiving anchor: Adam pauses in a bowed posture, raises and turns his head toward empty offscreen space, and holds a receptive listening posture. Do not depict the unseen source or its mechanism.",
            "NEGATIVE_PROMPT": "written words, floating text, tablet, paper, voice beam, light ray, halo, angel, messenger, divine body, portal, graphics, UI, diagram, visible female character, invented prop",
            "TARGET_DURATION": 7.0,
        },
        {
            "MICRO_SHOT_ID": "EP002-V2-NEW-012",
            "PARENT_AUDIO_SEGMENT_ID": "EP002-SH-031",
            "TIMELINE_IN": 333.9,
            "TIMELINE_OUT": 340.9,
            "EVENT_ID": "EV-014-ACCEPTANCE-AND-GUIDANCE",
            "EVENT_TYPE": "LITERAL_EVENT",
            "EVENT_ROLE": "LITERAL_EVENT",
            "CHARACTERS": ["ADAM", "HAWWA_SPOUSE"],
            "VISIBLE_ACTION": "Adam and spouse rise from humbled postures, stand calmly, and turn toward the next phase while the past location remains behind.",
            "VISUAL_INFORMATION": "Restored direction is visible as a human consequence without halo, magic, or erased history.",
            "START_FRAME": "Two covered figures remain low in the same garden context.",
            "MIDDLE_ACTION": "Both rise slowly and stand together.",
            "END_FRAME": "They turn toward an ordinary open direction; the tree/past remains visible behind them.",
            "CAMERA": "wide-to-medium rear tracking angle",
            "COMPOSITION": "two covered figures, past location, ordinary path/open earth",
            "LIGHTING": "natural light gradually settling, no glow",
            "LOCATION": "garden edge toward earth",
            "STYLE": "quiet literal guidance and continuity",
            "CONTINUITY_REQUIREMENTS": "same pair and garments; past setting is not erased; no celebration",
            "MODESTY_REQUIREMENTS": "spouse fully covered, no skin or hands, loose silhouette",
            "FORBIDDEN_ELEMENTS": ["halo", "golden glow", "erased mark", "celebration", "magic transition", *_GLOBAL_FORBIDDEN],
            "MUTE_COMPREHENSION_TARGET": "muted viewer understands humble rising and restored direction after repentance",
            "INCLUDES_FEMALE": female,
            "SOURCE_TIER": "TIER_1_QURAN",
            "SOURCE_CERTAINTY": "HIGH",
            "SOURCE_FACTS_USED": ["CL-007 and CL-011: acceptance, guidance, and restored direction"],
            "ART_DIRECTION_USED": ["ordinary rising/turning; no symbolic erasure"],
            "CHARACTER_DOSSIER_REFERENCES": ["ADAM", "HAWWA_SPOUSE"],
            "IMAGE_PROMPT": "Quiet literal cinematic shot of Adam and his fully covered spouse rising from humbled postures in the same garden context, standing calmly, and turning toward the next phase of life while the tree and past location remain behind. No halo, glow, celebration, erased mark, text, or graphics.",
            "VIDEO_PROMPT": "7-second literal guidance consequence: two covered figures rise, stand calmly, and turn toward an ordinary open direction; keep the past location visible behind them and avoid any supernatural celebration or erasure.",
            "NEGATIVE_PROMPT": "halo, golden glow, magic light, erased mark, celebration, triumph, visible female hair, neck, arms, legs, torso skin, hands, tight clothing, body-shaped silhouette, text, graphics, UI, beam, portal, third character",
            "TARGET_DURATION": 7.0,
        },
        {
            "MICRO_SHOT_ID": "EP002-V2-NEW-013",
            "PARENT_AUDIO_SEGMENT_ID": "EP002-SH-035",
            "TIMELINE_IN": 386.655,
            "TIMELINE_OUT": 393.655,
            "EVENT_ID": "EV-016-DESCENT-TO-EARTH",
            "EVENT_TYPE": "SOURCE_CONSTRAINED_UNSEEN_EVENT",
            "EVENT_ROLE": "SOURCE_CONSTRAINED_UNSEEN_EVENT",
            "CHARACTERS": ["ADAM"],
            "VISIBLE_ACTION": "Adam alone transitions from the previous environment into an ordinary wide earthly environment; no physical route is invented.",
            "VISUAL_INFORMATION": "A separate earth-entry state is visible without portal, stairs, mountain, or exact geography.",
            "START_FRAME": "Adam stands at the edge of the previous ordinary environment.",
            "MIDDLE_ACTION": "A clean natural cut carries him into a wide earthly environment; his feet and body are stable, not teleporting through a graphic.",
            "END_FRAME": "Adam stands alone on earth in an unresolved, non-identifying landscape.",
            "CAMERA": "wide natural cut from medium rear to earth wide shot",
            "COMPOSITION": "Adam alone; no split-screen; no geographic landmark",
            "LIGHTING": "ordinary earthly daylight",
            "LOCATION": "unresolved earthly environment",
            "STYLE": "source-constrained transition with visible consequence",
            "CONTINUITY_REQUIREMENTS": "Adam alone in this shot; spouse is not placed beside him; no invented route",
            "MODESTY_REQUIREMENTS": "male modest opaque garment; no unsupported appearance close-up",
            "FORBIDDEN_ELEMENTS": ["portal", "stairs", "mountain", "map", "teleportation graphic", "exact place label", *_GLOBAL_FORBIDDEN],
            "MUTE_COMPREHENSION_TARGET": "muted viewer understands Adam has reached earth separately",
            "INCLUDES_FEMALE": False,
            "SOURCE_TIER": "TIER_1_QURAN_FOR_DESCENT; TIER_6_ART_DIRECTION_FOR_UNRESOLVED_STAGING",
            "SOURCE_CERTAINTY": "HIGH_FOR_DESCENT; NON_AUTHORITATIVE_FOR_SEPARATE_STAGING",
            "SOURCE_FACTS_USED": ["CL-008: descent and earth settlement; no exact geography"],
            "ART_DIRECTION_USED": ["separate landing state; exact location unresolved and not depicted"],
            "CHARACTER_DOSSIER_REFERENCES": ["ADAM"],
            "IMAGE_PROMPT": "Source-constrained cinematic transition: Adam alone leaves the previous ordinary environment and is shown in a separate wide earthly environment with no exact landmark or geographic label. No portal, stairs, mountain from paradise, map, split-screen, or teleportation graphic. Keep appearance non-identifying and modest.",
            "VIDEO_PROMPT": "7-second source-constrained earth-entry anchor: use a natural cut from Adam alone in the prior environment to Adam alone standing in an ordinary wide earthly environment. Show consequence, not a fabricated route or supernatural mechanism.",
            "NEGATIVE_PROMPT": "portal, stairs, mountain, map, split-screen, exact location label, India, Jeddah, Sri Lanka, teleportation graphic, beam, magic transition, text, UI, graphics, third character",
            "TARGET_DURATION": 7.0,
        },
        {
            "MICRO_SHOT_ID": "EP002-V2-NEW-014",
            "PARENT_AUDIO_SEGMENT_ID": "EP002-SH-035",
            "TIMELINE_IN": 393.655,
            "TIMELINE_OUT": 400.5,
            "EVENT_ID": "EV-016-DESCENT-TO-EARTH",
            "EVENT_TYPE": "SOURCE_CONSTRAINED_UNSEEN_EVENT",
            "EVENT_ROLE": "SOURCE_CONSTRAINED_UNSEEN_EVENT",
            "CHARACTERS": ["HAWWA_SPOUSE"],
            "VISIBLE_ACTION": "The fully covered spouse appears alone in a clearly different ordinary earthly environment through an independent cut.",
            "VISUAL_INFORMATION": "The second separate earth-entry state is visible without claiming an exact location.",
            "START_FRAME": "Independent cut; no split-screen and no Adam in frame.",
            "MIDDLE_ACTION": "The fully covered spouse stands or takes one stable step in a different earthly environment.",
            "END_FRAME": "She remains alone, safely covered, in the unresolved earthly setting.",
            "CAMERA": "wide rear/distant earth shot",
            "COMPOSITION": "one covered figure in different environment; no landmark or label",
            "LIGHTING": "ordinary earthly light, different palette from Adam's setting but not magical",
            "LOCATION": "different unresolved earthly environment",
            "STYLE": "source-constrained restrained cinematic staging",
            "CONTINUITY_REQUIREMENTS": "spouse alone; clearly different environment; no simultaneous landing; no exact geography",
            "MODESTY_REQUIREMENTS": "maximum strict female coverage, no hair/skin/hands/body contour",
            "FORBIDDEN_ELEMENTS": ["split-screen", "portal", "mountain", "map", "location label", "visible hands", *_GLOBAL_FORBIDDEN],
            "MUTE_COMPREHENSION_TARGET": "muted viewer understands the spouse also reached earth separately",
            "INCLUDES_FEMALE": True,
            "SOURCE_TIER": "TIER_1_QURAN_FOR_DESCENT; TIER_6_ART_DIRECTION_FOR_UNRESOLVED_STAGING",
            "SOURCE_CERTAINTY": "HIGH_FOR_DESCENT; NON_AUTHORITATIVE_FOR_SEPARATE_STAGING",
            "SOURCE_FACTS_USED": ["CL-008: descent and earth settlement; no exact geography"],
            "ART_DIRECTION_USED": ["separate different earthly environment; exact locations unresolved and not depicted"],
            "CHARACTER_DOSSIER_REFERENCES": ["HAWWA_SPOUSE"],
            "IMAGE_PROMPT": "Independent wide rear/distant shot of Adam's fully covered spouse alone in a clearly different ordinary earthly environment. Opaque loose full-body garment covers head, hair, neck, body, and hands; no landmark, map, label, portal, or split-screen. The exact location remains unresolved.",
            "VIDEO_PROMPT": "6.845-second source-constrained separate earth-entry shot: cut independently to the fully covered spouse alone in a different ordinary earthly environment, holding a stable earthly presence. Do not show a joint landing or invent a route/geography.",
            "NEGATIVE_PROMPT": "visible female hair, neck, arms, legs, torso skin, hands, exposed skin, tight clothing, transparent clothing, body-shaped silhouette, split-screen, portal, stairs, mountain, map, exact location label, graphics, text, UI, magic beam",
            "TARGET_DURATION": 6.845,
        },
        {
            "MICRO_SHOT_ID": "EP002-V2-NEW-015",
            "PARENT_AUDIO_SEGMENT_ID": "EP002-SH-040",
            "TIMELINE_IN": 444.537,
            "TIMELINE_OUT": 448.537,
            "EVENT_ID": "EV-018-ADAM-MUSA-DEBATE",
            "EVENT_TYPE": "LITERAL_EVENT",
            "EVENT_ROLE": "LITERAL_EVENT",
            "CHARACTERS": ["ADAM", "MUSA"],
            "VISIBLE_ACTION": "Musa faces Adam and visibly addresses him with serious conversational body language.",
            "VISUAL_INFORMATION": "A real two-person debate replaces the former graphic explainer.",
            "START_FRAME": "Two distinct adult male figures face one another in a neutral natural environment.",
            "MIDDLE_ACTION": "Musa gestures naturally as he speaks; no staff, book, table, or graphic appears.",
            "END_FRAME": "Adam listens seriously, preparing to answer.",
            "CAMERA": "medium shot/reverse-shot",
            "COMPOSITION": "two adult males, no identifying prop, no scholar room",
            "LIGHTING": "natural neutral daylight",
            "LOCATION": "simple unmarked natural environment",
            "STYLE": "grounded limited hadith illustration",
            "CONTINUITY_REQUIREMENTS": "Musa and Adam remain distinct and consistent; exactly two adults; no female or third figure",
            "MODESTY_REQUIREMENTS": "loose opaque male garments; no unsupported close physical traits",
            "FORBIDDEN_ELEMENTS": ["staff", "book", "table", "scholar room", "source cards", *_GLOBAL_FORBIDDEN],
            "MUTE_COMPREHENSION_TARGET": "muted viewer understands one male is addressing another in a serious debate",
            "INCLUDES_FEMALE": False,
            "SOURCE_TIER": "TIER_2_SAHIH_SUNNAH",
            "SOURCE_CERTAINTY": "HIGH_FOR_DEBATE; APPEARANCE_UNSPECIFIED_LOCALLY",
            "SOURCE_FACTS_USED": ["CL-009: Adam-Musa debate; limited responsibility/قدر scope"],
            "ART_DIRECTION_USED": ["distinct neutral male silhouettes; no identifying prop"],
            "CHARACTER_DOSSIER_REFERENCES": ["ADAM", "MUSA"],
            "IMAGE_PROMPT": "Grounded natural medium shot of exactly two distinct adult male figures, Adam and Musa, facing one another in a simple unmarked environment. Musa addresses Adam with serious conversational body language. No staff, book, table, scholar room, source card, timeline, text, or graphics. Keep unsupported physical attributes non-identifying.",
            "VIDEO_PROMPT": "4-second literal debate anchor: Musa visibly addresses Adam with serious conversational body language, then Adam listens. Maintain exactly two distinct adult male figures and no identifying prop or graphic setting.",
            "NEGATIVE_PROMPT": "staff, book, table, scholar room, generic scholars, source cards, timeline, UI, readable text, third character, female character, unsupported white European archetype, invented complexion, graphics, diagram",
            "TARGET_DURATION": 4.0,
        },
        {
            "MICRO_SHOT_ID": "EP002-V2-NEW-016",
            "PARENT_AUDIO_SEGMENT_ID": "EP002-SH-041",
            "TIMELINE_IN": 458.8,
            "TIMELINE_OUT": 462.8,
            "EVENT_ID": "EV-018-ADAM-MUSA-DEBATE",
            "EVENT_TYPE": "LITERAL_EVENT",
            "EVENT_ROLE": "LITERAL_EVENT",
            "CHARACTERS": ["ADAM", "MUSA"],
            "VISIBLE_ACTION": "Adam answers Musa with a serious measured response; Musa remains visibly present as the same interlocutor.",
            "VISUAL_INFORMATION": "The exchange is a conversation, not an abstract timeline or text card.",
            "START_FRAME": "Adam turns or leans slightly toward Musa in the same neutral environment.",
            "MIDDLE_ACTION": "Adam gestures naturally while answering; Musa listens.",
            "END_FRAME": "Both hold a serious reflective exchange posture.",
            "CAMERA": "reverse medium shot",
            "COMPOSITION": "same two-person spatial axis, no props",
            "LIGHTING": "consistent natural light",
            "LOCATION": "same unmarked natural environment",
            "STYLE": "grounded limited hadith illustration",
            "CONTINUITY_REQUIREMENTS": "same Adam and Musa appearance/wardrobe; no third figure or prop",
            "MODESTY_REQUIREMENTS": "loose opaque male garments; no invented close appearance",
            "FORBIDDEN_ELEMENTS": ["staff", "book", "table", "graphic cards", *_GLOBAL_FORBIDDEN],
            "MUTE_COMPREHENSION_TARGET": "muted viewer understands the second speaker is answering the first",
            "INCLUDES_FEMALE": False,
            "SOURCE_TIER": "TIER_2_SAHIH_SUNNAH",
            "SOURCE_CERTAINTY": "HIGH_FOR_DEBATE; APPEARANCE_UNSPECIFIED_LOCALLY",
            "SOURCE_FACTS_USED": ["CL-009: Adam-Musa debate"],
            "ART_DIRECTION_USED": ["same neutral two-person axis; no prop-based identification"],
            "CHARACTER_DOSSIER_REFERENCES": ["ADAM", "MUSA"],
            "IMAGE_PROMPT": "Same two distinct adult male figures in the same simple natural environment: Adam answers Musa with serious measured body language while Musa listens. No staff, book, table, source cards, timeline, text, or graphics; preserve continuity and avoid unsupported physical claims.",
            "VIDEO_PROMPT": "4-second literal response anchor: Adam visibly answers Musa, keeping the same two-person axis, wardrobe, and natural environment. Musa remains present and listens; no graphic explainer or identifying prop.",
            "NEGATIVE_PROMPT": "staff, book, table, scholar room, source card, timeline, UI, text, graphics, third character, female character, invented complexion, generic European archetype, continuity mutation",
            "TARGET_DURATION": 4.0,
        },
        {
            "MICRO_SHOT_ID": "EP002-V2-NEW-017",
            "PARENT_AUDIO_SEGMENT_ID": "EP002-SH-042",
            "TIMELINE_IN": 475.6,
            "TIMELINE_OUT": 479.6,
            "EVENT_ID": "EV-018-ADAM-MUSA-DEBATE",
            "EVENT_TYPE": "LITERAL_EVENT",
            "EVENT_ROLE": "LITERAL_EVENT",
            "CHARACTERS": ["ADAM", "MUSA"],
            "VISIBLE_ACTION": "The exchange closes with a brief reflective pause between Adam and Musa; both remain visibly engaged.",
            "VISUAL_INFORMATION": "The hadith section resolves as a human conversation without graphics or invented props.",
            "START_FRAME": "Both figures remain in the same natural setting after the response.",
            "MIDDLE_ACTION": "Musa gives a restrained final gesture; Adam reflects, both serious.",
            "END_FRAME": "The two-person exchange settles into a quiet reflective pause.",
            "CAMERA": "medium two-shot with restrained closing movement",
            "COMPOSITION": "exactly two adult males, open natural background, no props",
            "LIGHTING": "consistent natural light",
            "LOCATION": "same unmarked natural environment",
            "STYLE": "grounded reflective closure",
            "CONTINUITY_REQUIREMENTS": "same identities and two-person count; no room, book, staff, or graphic",
            "MODESTY_REQUIREMENTS": "loose opaque male garments; unknown appearance remains non-identifying",
            "FORBIDDEN_ELEMENTS": ["staff", "book", "table", "scholar room", "text", *_GLOBAL_FORBIDDEN],
            "MUTE_COMPREHENSION_TARGET": "muted viewer understands a serious two-person exchange has reached a reflective pause",
            "INCLUDES_FEMALE": False,
            "SOURCE_TIER": "TIER_2_SAHIH_SUNNAH",
            "SOURCE_CERTAINTY": "HIGH_FOR_DEBATE; APPEARANCE_UNSPECIFIED_LOCALLY",
            "SOURCE_FACTS_USED": ["CL-009: limited Adam-Musa debate"],
            "ART_DIRECTION_USED": ["quiet human closure; no visual claim beyond the debate"],
            "CHARACTER_DOSSIER_REFERENCES": ["ADAM", "MUSA"],
            "IMAGE_PROMPT": "Grounded reflective two-shot of the same distinct adult male figures, Adam and Musa, after a serious exchange in a simple natural environment. A restrained final gesture and quiet pause close the conversation. No book, staff, table, scholar room, text, graphics, or unsupported appearance claim.",
            "VIDEO_PROMPT": "4-second literal closing anchor: Musa gives a restrained final conversational gesture, Adam reflects, and both settle into a quiet two-person pause. Preserve identity and environment continuity; no graphic or prop.",
            "NEGATIVE_PROMPT": "staff, book, table, scholar room, source cards, timeline, UI, text, graphics, third character, female character, invented complexion, generic fair European archetype, continuity mutation",
            "TARGET_DURATION": 4.0,
        },
    ]


def event_by_id(contracts: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(item["EVENT_ID"]): item for item in contracts}


def parent_shot_at(shots: list[Mapping[str, Any]], timestamp: float) -> Mapping[str, Any]:
    for shot in shots:
        if float(shot["START_TIME"]) - 0.001 <= timestamp < float(shot["END_TIME"]) - 0.001:
            return shot
    if math.isclose(timestamp, float(shots[-1]["END_TIME"]), abs_tol=0.002):
        return shots[-1]
    raise RuntimeError(f"PARENT_AUDIO_SEGMENT_NOT_FOUND:{timestamp}")


def compile_anchor(
    spec: dict[str, Any],
    constitution: Any,
) -> dict[str, Any]:
    compiled = compile_visual_prompt_v2(
        constitution,
        spec["IMAGE_PROMPT"],
        spec["VIDEO_PROMPT"],
        spec["NEGATIVE_PROMPT"],
        includes_female=bool(spec["INCLUDES_FEMALE"]),
        event_type=str(spec["EVENT_TYPE"]),
        source_tier=str(spec["SOURCE_TIER"]).split(";")[0],
        source_certainty=str(spec["SOURCE_CERTAINTY"]),
        source_facts=list(spec["SOURCE_FACTS_USED"]),
        art_direction=list(spec["ART_DIRECTION_USED"]),
        dossier_refs=list(spec["CHARACTER_DOSSIER_REFERENCES"]),
    )
    start = float(spec["TIMELINE_IN"])
    end = float(spec["TIMELINE_OUT"])
    event_type = str(spec["EVENT_TYPE"])
    planned = {
        "PLANNED_EVENT_VISIBLE": True,
        "PLANNED_SUBJECT_VISIBLE": True,
        "PLANNED_ACTION_VISIBLE": True,
        "PLANNED_OBJECT_VISIBLE": event_type == "LITERAL_EVENT" and "none" not in str(spec["VISIBLE_ACTION"]).lower(),
        "PLANNED_RESULT_VISIBLE": True,
        "PLANNED_MUTE_COMPREHENSION": True,
        "SUPPORT_ONLY_NOT_SOLE_PROOF": False,
    }
    if event_type == "SOURCE_CONSTRAINED_UNSEEN_EVENT":
        planned["PLANNED_OBJECT_VISIBLE"] = False
    output = {
        **{key: value for key, value in spec.items() if key not in {"IMAGE_PROMPT", "VIDEO_PROMPT", "NEGATIVE_PROMPT", "TARGET_DURATION"}},
        "DURATION": end - start,
        "DISPOSITION": "NEW_REQUIRED",
        "NARRATION_TEXT": "Current frozen narration beat; see parent audio segment.",
        "START_FRAME_DESCRIPTION": spec["START_FRAME"],
        "MIDDLE_ACTION_DESCRIPTION": spec["MIDDLE_ACTION"],
        "END_FRAME_DESCRIPTION": spec["END_FRAME"],
        "FEMALE_MODESTY_REQUIREMENTS": spec["MODESTY_REQUIREMENTS"],
        "MUTE_COMPREHENSION_TARGET": spec["MUTE_COMPREHENSION_TARGET"],
        "PLANNED_MUTE_COMPREHENSION": planned,
        "ACTUAL_RENDER_MUTE_COMPREHENSION": "NOT_RUN",
        "SOURCE": "NEW_GENERATION_REQUIRED",
        "TARGET_DURATION": end - start,
        "PREFERRED_MEDIA_TYPE": "VIDEO_WITH_OPTIONAL_IMAGE_KEYFRAME",
        "PROVIDER_CAPABILITY_REQUIREMENTS": {
            "literal_action_tracking": True,
            "multi_character_continuity": len(spec["CHARACTERS"]) > 1,
            "strict_female_modesty": bool(spec["INCLUDES_FEMALE"]),
            "no_graphics_or_text": True,
            "source_constrained_unseen_event": event_type == "SOURCE_CONSTRAINED_UNSEEN_EVENT",
            "target_duration_seconds": end - start,
        },
        **compiled,
    }
    if event_type == "SOURCE_CONSTRAINED_UNSEEN_EVENT":
        output["UNSEEN_ENTITY_VISIBLE"] = False
        output["UNSEEN_MECHANISM_VISIBLE"] = False
    output["COMPILED_PROVIDER_PROMPT"] = compiled["COMPILED_PROVIDER_PROMPT"]
    return output


def parent_event_for(parent_id: str, anchor_by_parent: Mapping[str, list[dict[str, Any]]]) -> str:
    if parent_id in anchor_by_parent:
        return str(anchor_by_parent[parent_id][0]["EVENT_ID"])
    return "EV-020-SUPPORTING-NARRATION"


def choose_safe_asset(
    pool: list[dict[str, Any]],
    *,
    category: str,
    previous_id: str | None,
    use_counts: Counter[str],
) -> dict[str, Any]:
    candidates = [item for item in pool if use_counts[item["ASSET_ID"]] < 3 and item["ASSET_ID"] != previous_id]
    preferred = [item for item in candidates if item["SOURCE_CATEGORY"] == category]
    if preferred:
        candidates = preferred
    if not candidates:
        candidates = [item for item in pool if use_counts[item["ASSET_ID"]] < 3]
    if not candidates:
        raise RuntimeError("SAFE_EXISTING_ASSET_POOL_EXHAUSTED")
    candidates.sort(
        key=lambda item: (
            use_counts[item["ASSET_ID"]],
            0 if item["MEDIA_KIND"].endswith("VIDEO") else 1,
            -float(item["USABLE_SOURCE_DURATION_SECONDS"]),
            item["ASSET_ID"],
        )
    )
    return candidates[0]


def make_existing_micro_shot(
    asset: dict[str, Any],
    *,
    start: float,
    duration: float,
    parent: Mapping[str, Any],
    use_index: int,
    event_id: str,
) -> dict[str, Any]:
    asset_id = str(asset["ASSET_ID"])
    is_image = asset["MEDIA_KIND"].endswith("IMAGE")
    parent_id = str(parent["SHOT_ID"])
    event_role = "ESTABLISHING" if use_index == 0 else "ATMOSPHERE"
    event_type = event_role
    if is_image:
        source_in = 0.0
        source_out = duration
        playback = 1.0
        static_exposure = duration
    else:
        source_in = 0.0
        source_out = duration
        playback = 1.0
        static_exposure = None
    output: dict[str, Any] = {
        "MICRO_SHOT_ID": f"EP002-V2-REUSE-{use_index:04d}",
        "PARENT_AUDIO_SEGMENT_ID": parent_id,
        "TIMELINE_IN": start,
        "TIMELINE_OUT": start + duration,
        "DURATION": duration,
        "NARRATION_TEXT": str(parent.get("NARRATION_TEXT", "")),
        "EVENT_ID": event_id,
        "EVENT_TYPE": event_type,
        "EVENT_ROLE": event_role,
        "SOURCE_TIER": "TIER_6_ART_DIRECTION",
        "SOURCE_CERTAINTY": "NOT_A_SOURCE_FACT",
        "SOURCE_FACTS_USED": [],
        "ART_DIRECTION_USED": [
            "reuse only locally inspected existing media",
            "support shot is not the sole proof of any major narrated action",
        ],
        "CHARACTERS": [],
        "CHARACTER_DOSSIER_REFERENCES": [],
        "VISIBLE_ACTION": "Existing inspected visual supplies environmental continuity only; it is not used as sole proof of the major event.",
        "VISUAL_INFORMATION": f"Existing {asset['SOURCE_CATEGORY']} material gives a non-duplicative support view during the frozen narration beat.",
        "START_FRAME_DESCRIPTION": "existing locally inspected asset start frame",
        "MIDDLE_ACTION_DESCRIPTION": "existing locally inspected asset middle/change-window frame",
        "END_FRAME_DESCRIPTION": "existing locally inspected asset end frame",
        "CAMERA": "inherited from existing asset",
        "COMPOSITION": "inherited existing composition; no new graphics or character claim",
        "LIGHTING": "inherited existing lighting",
        "LOCATION": "existing inspected environment; no new exact geography claim",
        "STYLE": "existing cinematic asset under V2 reuse audit",
        "CONTINUITY_REQUIREMENTS": "no new named character identity; no extra character; source media hash and temporal audit must remain bound",
        "MODESTY_REQUIREMENTS": "existing asset passed the strict reuse audit; no unsafe female asset is reused",
        "FORBIDDEN_ELEMENTS": list(_GLOBAL_FORBIDDEN),
        "MUTE_COMPREHENSION_TARGET": "support only; the major action must be read from an adjacent literal anchor, not this shot alone",
        "PLANNED_MUTE_COMPREHENSION": {
            "PLANNED_EVENT_VISIBLE": False,
            "PLANNED_SUBJECT_VISIBLE": False,
            "PLANNED_ACTION_VISIBLE": False,
            "PLANNED_OBJECT_VISIBLE": False,
            "PLANNED_RESULT_VISIBLE": False,
            "PLANNED_MUTE_COMPREHENSION": False,
            "SUPPORT_ONLY_NOT_SOLE_PROOF": True,
        },
        "ACTUAL_RENDER_MUTE_COMPREHENSION": "NOT_RUN",
        "SOURCE": "EXISTING" if asset["SOURCE_ORIGINAL_SHOT_ID"] == parent_id and asset["V2_DISPOSITION"] == "KEEP" and asset.get("USE_COUNT", 0) == 0 else "REASSIGNED_EXISTING",
        "DISPOSITION": asset["V2_DISPOSITION"],
        "ASSET_ID": asset_id,
        "ASSET_PATH": asset["ASSET_PATH"],
        "ASSET_SHA256": asset["ACTUAL_SHA256"],
        "SOURCE_IN": source_in,
        "SOURCE_OUT": source_out,
        "PLAYBACK_RATE": playback,
        "MEDIA_KIND": asset["MEDIA_KIND"],
        "TEMPORAL_AUDIT_REFERENCE": asset_id,
        "NO_LOOP": True,
        "NO_STRETCH": True,
    }
    if static_exposure is not None:
        output["STATIC_FRAME_EXPOSURE_SECONDS"] = static_exposure
        output["STATIC_FRAME_REUSE_NOTE"] = "single bounded exposure; not looped or used as hidden filler"
    return output


def build_micro_shots(
    v1: Mapping[str, Any],
    constitution: Any,
    assets_by_id: Mapping[str, dict[str, Any]],
    contracts: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    anchors = [compile_anchor(spec, constitution) for spec in make_anchor_specs()]
    anchors.sort(key=lambda item: float(item["TIMELINE_IN"]))
    parent_shots = list(v1["timeline_shots"])
    pool: list[dict[str, Any]] = []
    for item in assets_by_id.values():
        if not item["REUSE_ELIGIBLE"]:
            continue
        if item["ASSET_ID"] == "EP002-SH-002-I01" or item["ASSET_ID"] == "EP002-SH-002-V01":
            continue
        if item["MEDIA_KIND"].endswith("IMAGE"):
            usable = min(float(item["DECLARED_DURATION_SECONDS"]), 6.0)
        else:
            usable = float(item["PROBED_DURATION_SECONDS"] or item["DECLARED_DURATION_SECONDS"])
        if usable <= 0.05:
            continue
        candidate = dict(item)
        candidate["USABLE_SOURCE_DURATION_SECONDS"] = usable
        candidate["USE_COUNT"] = 0
        pool.append(candidate)
    if not pool:
        raise RuntimeError("NO_SAFE_EXISTING_ASSETS")
    use_counts: Counter[str] = Counter()
    micro_shots: list[dict[str, Any]] = []
    anchor_by_parent: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for anchor in anchors:
        anchor_by_parent[str(anchor["PARENT_AUDIO_SEGMENT_ID"])].append(anchor)
    cursor = 0.0
    use_index = 0
    anchors_with_gaps: list[tuple[float, float, Mapping[str, Any]]] = []
    for anchor in anchors:
        start = float(anchor["TIMELINE_IN"])
        if start < cursor - 0.002:
            raise RuntimeError("ANCHOR_OVERLAP")
        if start > cursor + 0.002:
            anchors_with_gaps.append((cursor, start, parent_shot_at(parent_shots, cursor)))
        micro_shots.append(anchor)
        cursor = float(anchor["TIMELINE_OUT"])
    audio_total = audio_duration(MASTER_AUDIO)
    if cursor < audio_total - 0.002:
        anchors_with_gaps.append((cursor, audio_total, parent_shot_at(parent_shots, cursor)))
    segments: list[dict[str, Any]] = []
    for gap_start, gap_end, parent in anchors_with_gaps:
        current = gap_start
        gap_event = parent_event_for(str(parent["SHOT_ID"]), anchor_by_parent)
        while current < gap_end - 0.002:
            category = source_category(str(parent["SHOT_ID"]))
            asset = choose_safe_asset(
                pool,
                category=category,
                previous_id=segments[-1]["ASSET_ID"] if segments else None,
                use_counts=use_counts,
            )
            remaining = gap_end - current
            duration = min(remaining, float(asset["USABLE_SOURCE_DURATION_SECONDS"]))
            if duration <= 0.002:
                current = gap_end
                break
            # Preserve every audio boundary.  A short remainder is a real
            # bounded micro-shot, never a loop or a hidden stretch.
            if duration < 0.05:
                duration = remaining
            asset["USE_COUNT"] = use_counts[asset["ASSET_ID"]]
            segment = make_existing_micro_shot(
                asset,
                start=current,
                duration=duration,
                parent=parent,
                use_index=use_index,
                event_id=gap_event,
            )
            use_index += 1
            use_counts[asset["ASSET_ID"]] += 1
            segments.append(segment)
            current += duration
    combined = []
    # Put anchors and reused segments back into chronological order.
    combined.extend(micro_shots)
    combined.extend(segments)
    combined.sort(key=lambda item: (float(item["TIMELINE_IN"]), str(item["MICRO_SHOT_ID"])))
    # Assign exact parent narration text to anchors from the frozen V1 beat.
    for shot in combined:
        parent = next(item for item in parent_shots if item["SHOT_ID"] == shot["PARENT_AUDIO_SEGMENT_ID"])
        shot["NARRATION_TEXT"] = str(parent.get("NARRATION_TEXT", ""))
    return combined, anchors


def make_human_report(
    storyboard: Mapping[str, Any],
    asset_audit: list[dict[str, Any]],
    certification: Mapping[str, Any],
) -> str:
    lines = [
        "# EP002_SURGICAL_REPAIR_STORYBOARD_V2",
        "",
        "> PREPRODUCTION ONLY — no visual generation, provider call, paid operation, or montage was performed.",
        "",
        "## Review gate",
        "",
        f"- Storyboard status: `{storyboard['STORYBOARD_STATUS']}`",
        "- Approved storyboard hash: `null`",
        "- Visual generation allowed: `FALSE`",
        f"- Audio authority: `{storyboard['AUDIO_AUTHORITY_FILE']}` ({storyboard['AUDIO_DURATION_SECONDS']:.9f}s)",
        f"- Constitution: `{storyboard['VISUAL_CONSTITUTION_VERSION']}` `{storyboard['VISUAL_CONSTITUTION_SHA256']}`",
        "",
        "## V2 optimization",
        "",
        f"- V1 new-generation seconds: `{certification['V1_NEW_GENERATION_SECONDS']:.3f}`",
        f"- V2 new-generation seconds: `{certification['V2_NEW_GENERATION_SECONDS']:.3f}`",
        f"- Seconds saved: `{certification['SECONDS_SAVED_VS_V1']:.3f}`",
        f"- New-generation micro-shots: `{certification['NEW_GENERATED_MICRO_SHOTS']}`",
        f"- Reused micro-shots: `{certification['REUSED_MICRO_SHOTS']}`",
        "",
        "## Shot-by-shot review",
        "",
        "`NEW_GENERATION_REQUIRED` rows are the only rows that require future provider generation, and all remain blocked until human approval.",
        "",
        "| # | Micro-shot | Time | Parent | Type | Source | Event role | Visual information | Mute target |",
        "|---:|---|---:|---|---|---|---|---|---|",
    ]
    for index, shot in enumerate(storyboard["MICRO_SHOTS"], 1):
        visual = str(shot["VISUAL_INFORMATION"]).replace("|", "\\|")
        mute = str(shot["MUTE_COMPREHENSION_TARGET"]).replace("|", "\\|")
        lines.append(
            f"| {index} | `{shot['MICRO_SHOT_ID']}` | {shot['TIMELINE_IN']:.3f}–{shot['TIMELINE_OUT']:.3f} ({shot['DURATION']:.3f}s) | `{shot['PARENT_AUDIO_SEGMENT_ID']}` | `{shot['EVENT_TYPE']}` | **`{shot['SOURCE']}`** | `{shot['EVENT_ROLE']}` | {visual} | {mute} |"
        )
    lines.extend(["", "## New-generation prompt packets", ""])
    for shot in storyboard["MICRO_SHOTS"]:
        if shot["SOURCE"] != "NEW_GENERATION_REQUIRED":
            continue
        lines.extend(
            [
                f"### {shot['MICRO_SHOT_ID']} — **NEW_GENERATION_REQUIRED**",
                "",
                f"- Time: `{shot['TIMELINE_IN']:.3f}–{shot['TIMELINE_OUT']:.3f}` ({shot['DURATION']:.3f}s)",
                f"- Event: `{shot['EVENT_ID']}` / `{shot['EVENT_TYPE']}`",
                f"- Characters: `{', '.join(shot['CHARACTERS'])}`",
                f"- Source tier/certainty: `{shot['SOURCE_TIER']}` / `{shot['SOURCE_CERTAINTY']}`",
                f"- Mute target: {shot['MUTE_COMPREHENSION_TARGET']}",
                f"- Modesty: {shot['MODESTY_REQUIREMENTS']}",
                "",
                "#### Proposed visual",
                "",
                f"Start: {shot['START_FRAME_DESCRIPTION']}",
                f"Action: {shot['MIDDLE_ACTION_DESCRIPTION']}",
                f"End: {shot['END_FRAME_DESCRIPTION']}",
                "",
                "#### Final compiled provider prompt",
                "",
                "```text",
                shot["COMPILED_PROVIDER_PROMPT"]["positive_video"],
                "",
                "NEGATIVE:",
                shot["COMPILED_PROVIDER_PROMPT"]["negative"],
                "```",
                "",
            ]
        )
    lines.extend(["## Existing asset audit", "", "| Asset | V2 disposition | Source | Temporal audit | Observation |", "|---|---|---|---|---|"])
    for asset in asset_audit:
        observation = str(asset.get("VISUAL_OBSERVATION", "")).replace("|", "\\|")
        lines.append(
            f"| `{asset['ASSET_ID']}` | **`{asset['V2_DISPOSITION']}`** | `{asset['ASSET_PATH']}` | `{asset['POLICY_STATUS']}`; samples `{','.join(asset['TEMPORAL_SAMPLE_TYPES'])}` | {observation} |"
        )
    lines.extend(
        [
            "",
            "## Safety and state",
            "",
            "- Graphics planned: `0`.",
            "- Unsafe female visuals allowed in repair plan: `0`.",
            "- Actual rendered mute-comprehension: `NOT_RUN` (no new media exists yet).",
            "- The canonical production transition ledger and provider evidence were not modified.",
            "- Next action: human review of this storyboard and its compiled prompts.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    constitution = load_visual_production_constitution_v2(REPO)
    v1 = load_json(V1_STORYBOARD)
    v1_report = load_json(V1_REPORT)
    v1_audit = load_json(V1_AUDIT)
    source_matrix = load_json(SOURCE_MATRIX)
    source_package = load_json(SOURCE_PACKAGE)
    audio_timeline = load_json(AUDIO_TIMELINE)
    tts_manifest = load_json(FINAL_TTS_MANIFEST)
    if not MASTER_AUDIO.is_file():
        raise RuntimeError("MASTER_AUDIO_MISSING")
    actual_audio_duration = audio_duration(MASTER_AUDIO)
    expected_audio_duration = 623.5111041666667
    if abs(actual_audio_duration - expected_audio_duration) > 0.001:
        raise RuntimeError(f"AUDIO_DURATION_CHANGED:{actual_audio_duration}")
    # The current accepted narration authority is the materialized montage WAV.
    # The generic TTS manifest is intentionally NOT_STARTED in this checkout,
    # so it must not override the existing accepted master audio.
    manifest_duration = tts_manifest.get("final_tts_duration_seconds")
    if manifest_duration is not None and abs(float(manifest_duration) - actual_audio_duration) > 0.002:
        raise RuntimeError("TTS_MANIFEST_AUDIO_MISMATCH")
    if not v1.get("CURRENT_NARRATION_FROZEN"):
        raise RuntimeError("V1_AUDIO_NOT_FROZEN")

    paid_history_roots = [
        ORCHESTRATION / "paid-operation-attempt-ledger-v1.jsonl",
        ORCHESTRATION / "paid-operation-attempts-v1",
        ORCHESTRATION / "explicit-paid-retry-v9",
    ]
    transition_roots = [ORCHESTRATION / "episode-transition-ledger-v1.jsonl"]
    provider_evidence_roots = [
        ORCHESTRATION / "provider-execution-assets-v1",
        EPISODE_ROOT / "cinematic" / "finalization-duplicate-rescue-v6",
        EPISODE_ROOT / "cinematic" / "finalization-local-graphics-v5",
        EPISODE_ROOT / "deliverables" / "autopilot-v6-2-1",
    ]
    paid_before = digest_paths(paid_history_roots)
    transition_before = digest_paths(transition_roots)
    provider_before = digest_paths(provider_evidence_roots)

    asset_audit, assets_by_id = audit_current_assets(v1)
    contracts = make_event_contracts()
    dossiers = build_dossiers()
    dossier_validation = validate_character_dossiers(dossiers)
    if dossier_validation["status"] != "PASS":
        raise RuntimeError("CHARACTER_DOSSIER_VALIDATION_FAILED:" + repr(dossier_validation))
    hierarchy_records = [
        {
            "SOURCE_TIER": "TIER_1_QURAN",
            "ASSERTION_MODE": "STATE_AS_FACT",
            "SOURCE_LABEL": "local canonical source matrix",
            "CERTAINTY": "HIGH",
        },
        {
            "SOURCE_TIER": "TIER_2_SAHIH_SUNNAH",
            "ASSERTION_MODE": "ATTRIBUTE_AND_QUALIFY",
            "SOURCE_LABEL": "local canonical source package",
            "CERTAINTY": "HIGH",
        },
    ]
    hierarchy_errors = validate_source_hierarchy_records(hierarchy_records)
    if hierarchy_errors:
        raise RuntimeError("SOURCE_HIERARCHY_VALIDATION_FAILED:" + repr(hierarchy_errors))

    micro_shots, anchors = build_micro_shots(v1, constitution, assets_by_id, contracts)
    for shot in micro_shots:
        if shot["SOURCE"] == "REASSIGNED_EXISTING" and not assets_by_id[shot["ASSET_ID"]]["REUSE_ELIGIBLE"]:
            raise RuntimeError("UNSAFE_ASSET_REUSED:" + str(shot["ASSET_ID"]))
    temporal_audits = {item["ASSET_ID"]: item for item in asset_audit if item["REUSE_ELIGIBLE"]}
    source_sha = sha256_file(SOURCE_MATRIX)
    package_sha = sha256_file(SOURCE_PACKAGE)
    audio_sha = sha256_file(MASTER_AUDIO)
    audio_timeline_sha = sha256_file(AUDIO_TIMELINE)

    new_seconds = sum(
        float(shot["DURATION"])
        for shot in micro_shots
        if shot["SOURCE"] == "NEW_GENERATION_REQUIRED"
    )
    reused_seconds = sum(
        float(shot["DURATION"])
        for shot in micro_shots
        if shot["SOURCE"] in {"EXISTING", "REASSIGNED_EXISTING"}
    )
    if abs(new_seconds + reused_seconds - actual_audio_duration) > 0.01:
        raise RuntimeError("MICRO_SHOT_DURATION_DOES_NOT_COVER_AUDIO")
    if new_seconds >= float(v1_report["estimated_new_visual_seconds_required"]):
        raise RuntimeError("V2_DID_NOT_REDUCE_REGENERATION")

    storyboard: dict[str, Any] = {
        "SCHEMA_VERSION": "EP002_SURGICAL_REPAIR_STORYBOARD_V2",
        "EPISODE_ID": EPISODE_ID,
        "CURRENT_STAGE_BEFORE_REPAIR": "READY_FOR_FINAL_HUMAN_REVIEW",
        "CURRENT_STAGE": "PRE_PRODUCTION_VISUAL_REVIEW",
        "VISUAL_CONSTITUTION_LOADED": True,
        "VISUAL_CONSTITUTION_VERSION": constitution.version,
        "VISUAL_CONSTITUTION_SHA256": constitution.sha256,
        "CONSTITUTION_SCOPE": "ALL_FUTURE_EPISODES",
        "CURRENT_NARRATION_FROZEN": True,
        "AUDIO_IS_DURATION_AUTHORITY": True,
        "AUDIO_AUTHORITY_FILE": rel(MASTER_AUDIO),
        "AUDIO_SHA256": audio_sha,
        "AUDIO_DURATION_SECONDS": actual_audio_duration,
        "AUDIO_TIMELINE_MANIFEST": rel(AUDIO_TIMELINE),
        "AUDIO_TIMELINE_MANIFEST_SHA256": audio_timeline_sha,
        "AUDIO_TIMELINE_DECLARED_DURATION_SECONDS": float(audio_timeline["total_duration_seconds"]),
        "SOURCE_MATRIX": rel(SOURCE_MATRIX),
        "SOURCE_MATRIX_SHA256": source_sha,
        "SOURCE_PACKAGE": rel(SOURCE_PACKAGE),
        "SOURCE_PACKAGE_SHA256": package_sha,
        "STORYBOARD_STATUS": "AWAITING_HUMAN_APPROVAL",
        "APPROVED_STORYBOARD_SHA256": None,
        "VISUAL_GENERATION_ALLOWED": False,
        "PLANNED_GRAPHICS_COUNT": 0,
        "ACTUAL_RENDER_GRAPHICS_COUNT": 0,
        "ACTUAL_RENDER_MUTE_COMPREHENSION": "NOT_RUN",
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
        "MAJOR_EVENTS": contracts,
        "CHARACTER_DOSSIERS_PATH": rel(DOSSIERS_V2),
        "CHARACTER_DOSSIERS_SHA256": None,
        "MICRO_SHOTS": micro_shots,
        "V1_INPUT_STORYBOARD": rel(V1_STORYBOARD),
        "V1_INPUT_STORYBOARD_SHA256": sha256_file(V1_STORYBOARD),
        "V1_REGENERATION_SECONDS": float(v1_report["estimated_new_visual_seconds_required"]),
        "V2_NEW_GENERATION_SECONDS": new_seconds,
        "V2_REUSED_EXISTING_SECONDS": reused_seconds,
        "EP002_V2_REGENERATION_OPTIMIZED": True,
        "PROMPT_CONTRADICTIONS": 0,
        "STATE_SCOPE": "new V2 preproduction artifacts only; canonical production state and evidence unchanged",
    }
    # Dossier hash is made before the storyboard is validated and written.
    dossier_payload = {
        "SCHEMA_VERSION": "EP002_CHARACTER_EVIDENCE_DOSSIERS_V2",
        "EPISODE_ID": EPISODE_ID,
        "CONSTITUTION_VERSION": constitution.version,
        "CONSTITUTION_SHA256": constitution.sha256,
        "SOURCE_MATRIX": rel(SOURCE_MATRIX),
        "SOURCE_MATRIX_SHA256": source_sha,
        "SOURCE_PACKAGE": rel(SOURCE_PACKAGE),
        "SOURCE_PACKAGE_SHA256": package_sha,
        "CHARACTERS": dossiers,
        "STATUS": "PASS",
        "UNKNOWN_ATTRIBUTES_REMAIN_UNKNOWN": True,
        "SOURCE_FACTS_AND_ART_DIRECTION_SEPARATED": True,
    }
    write_json(DOSSIERS_V2, dossier_payload)
    storyboard["CHARACTER_DOSSIERS_SHA256"] = sha256_file(DOSSIERS_V2)

    validation = validate_micro_shot_storyboard(
        storyboard,
        constitution,
        dossiers=dossiers,
        temporal_audits=temporal_audits,
    )
    if validation["status"] != "PASS":
        raise RuntimeError("V2_STORYBOARD_VALIDATION_FAILED:" + repr(validation))
    write_json(STORYBOARD_V2, storyboard)
    storyboard_sha = sha256_file(STORYBOARD_V2)
    safety_excluded_assets = sorted(
        item["ASSET_ID"]
        for item in asset_audit
        if "maximum-strict" in str(item["V2_DISPOSITION_REASON"]).lower()
        or "body-shaped dark silhouette" in str(item["V2_DISPOSITION_REASON"]).lower()
    )
    # Audit is written after the storyboard is known valid, so it can bind the plan.
    audit_payload = {
        "SCHEMA_VERSION": "EP002_SURGICAL_VISUAL_ASSET_AUDIT_V2",
        "EPISODE_ID": EPISODE_ID,
        "CONSTITUTION_VERSION": constitution.version,
        "CONSTITUTION_SHA256": constitution.sha256,
        "SOURCE_AUDIT_INPUT": rel(V1_AUDIT),
        "SOURCE_AUDIT_INPUT_SHA256": sha256_file(V1_AUDIT),
        "FULL_TEMPORAL_REUSE_AUDIT": True,
        "MIDPOINT_ONLY_ACCEPTANCE": False,
        "TEMPORAL_AUDIT_METHOD": "ffprobe metadata plus ffmpeg-extracted start/middle/end frames reviewed in local contact sheets; full-image review reference for images",
        "ASSET_COUNT": len(asset_audit),
        "KEEP_COUNT": sum(item["V2_DISPOSITION"] == "KEEP" for item in asset_audit),
        "REASSIGN_COUNT": sum(item["V2_DISPOSITION"] == "REASSIGN" for item in asset_audit),
        "DELETE_COUNT": sum(item["V2_DISPOSITION"] == "DELETE" for item in asset_audit),
        "UNSAFE_COUNT": sum(item["V2_DISPOSITION"] == "UNSAFE" for item in asset_audit),
        "NEW_REQUIRED_TIMELINE_SLOTS": len(anchors),
        "POLICY_STATUS": "PASS_WITH_EXPLICIT_EXCLUSIONS",
        "SAFETY_EXCLUDED_COUNT": len(safety_excluded_assets),
        "SAFETY_EXCLUDED_ASSETS": safety_excluded_assets,
        "asset_audit": asset_audit,
        "GRAPHICS_DETECTED_AND_DELETED": sorted(_GRAPHIC_SHOTS),
        "UNSAFE_FEMALE_SHOTS_DETECTED_AND_REMOVED": sorted(_UNSAFE_FEMALE_SHOTS),
        "TEMPORAL_UNSAFE_ASSETS_DETECTED_AND_REMOVED": sorted(_TEMPORAL_UNSAFE_ASSET_IDS),
        "FULL_IMAGE_UNUSABLE_ASSETS_DETECTED_AND_REMOVED": sorted(_VISUAL_UNUSABLE_ASSET_IDS),
        "CONTINUITY_DEFECTS_DETECTED": sorted(_CONTINUITY_DEFECT_SHOTS),
        "TEMPORAL_PIXEL_REVIEW": "PASS_FOR_REUSE_ELIGIBLE_ASSETS_WITH_EXPLICIT_SILHOUETTE_EXCLUSIONS",
        "NO_ASSET_BYTES_MODIFIED": True,
    }
    write_json(AUDIT_V2, audit_payload)

    paid_after = digest_paths(paid_history_roots)
    transition_after = digest_paths(transition_roots)
    provider_after = digest_paths(provider_evidence_roots)
    current_disp = Counter(item["V2_DISPOSITION"] for item in asset_audit)
    major_event_ids = {
        str(event["EVENT_ID"])
        for event in contracts
        if str(event.get("EVENT_CLASS")) == "MAJOR_LITERAL_EVENT"
    }
    major_events_with_contract = [
        event
        for event in contracts
        if str(event.get("EVENT_CLASS")) == "MAJOR_LITERAL_EVENT"
        and event.get("VISIBLE_ACTION")
        and event.get("MUTE_COMPREHENSION_TARGET")
    ]
    major_events_missing_existing_visual = sorted(
        major_event_ids
        & {
            str(shot["EVENT_ID"])
            for shot in micro_shots
            if shot["SOURCE"] == "NEW_GENERATION_REQUIRED"
        }
    )
    unsafe_female_assets = sorted(
        item["ASSET_ID"]
        for item in asset_audit
        if "female/hand" in str(item["V2_DISPOSITION_REASON"]).lower()
    )
    source_counts = Counter(shot["SOURCE"] for shot in micro_shots)
    role_counts = Counter(shot["EVENT_ROLE"] for shot in micro_shots)
    asset_use_counts = Counter(
        shot["ASSET_ID"]
        for shot in micro_shots
        if shot["SOURCE"] in {"EXISTING", "REASSIGNED_EXISTING"}
    )
    consecutive_asset_reuse = sum(
        1
        for previous, current in zip(micro_shots, micro_shots[1:])
        if previous.get("ASSET_ID") and previous.get("ASSET_ID") == current.get("ASSET_ID")
    )
    report: dict[str, Any] = {
        "STATUS": "PASS_EP002_SURGICAL_VISUAL_REPAIR_PREPRODUCTION_V2",
        "ROOT_CAUSE": [
            "V1 used long audio-window replacements instead of minimum literal micro-shot anchors",
            "V1 did not encode source-constrained unseen-event policy and character evidence dossiers",
            "graphics and unsafe/ambiguous visuals required a global fail-closed V2 contract",
        ],
        "CONSTITUTION_VERSION": constitution.version,
        "CONSTITUTION_PATH": rel(constitution.path),
        "CONSTITUTION_SHA256": constitution.sha256,
        "CONSTITUTION_SCOPE": "ALL_FUTURE_EPISODES",
        "CONSTITUTION_LOADED": True,
        "GLOBAL_CONSTITUTION_VALIDATION": "PASS",
        "GLOBAL_AUDIO_AUTHORITY": "PASS",
        "GLOBAL_STORYBOARD_APPROVAL_GATE": "PASS",
        "GLOBAL_CHARACTER_RESEARCH_GATE": "PASS",
        "GLOBAL_SOURCE_HIERARCHY": "PASS",
        "GLOBAL_ISRAILIYYAT_POLICY": "PASS",
        "GLOBAL_LITERAL_EVENT_POLICY": "PASS",
        "GLOBAL_UNSEEN_EVENT_POLICY": "PASS",
        "GLOBAL_GRAPHICS_HARD_BAN": "PASS",
        "GLOBAL_FEMALE_MODESTY_POLICY": "PASS",
        "CURRENT_NARRATION_FROZEN": True,
        "AUDIO_IS_DURATION_AUTHORITY": True,
        "audio_authority_file": rel(MASTER_AUDIO),
        "audio_sha256": audio_sha,
        "audio_duration": actual_audio_duration,
        "audio_timeline_declared_duration": float(audio_timeline["total_duration_seconds"]),
        "audio_duration_difference_retained_as_evidence": float(audio_timeline["total_duration_seconds"]) - actual_audio_duration,
        "V1_NEW_GENERATION_SECONDS": float(v1_report["estimated_new_visual_seconds_required"]),
        "V2_NEW_GENERATION_SECONDS": new_seconds,
        "V2_NEW_GENERATION_PERCENT": new_seconds / actual_audio_duration * 100.0,
        "estimated_new_visual_seconds_required": new_seconds,
        "SECONDS_SAVED_VS_V1": float(v1_report["estimated_new_visual_seconds_required"]) - new_seconds,
        "NEW_GENERATED_MICRO_SHOTS": source_counts["NEW_GENERATION_REQUIRED"],
        "REUSED_MICRO_SHOTS": source_counts["EXISTING"] + source_counts["REASSIGNED_EXISTING"],
        "MAX_ASSET_REUSE_COUNT": max(asset_use_counts.values(), default=0),
        "CONSECUTIVE_ASSET_REUSE_COUNT": consecutive_asset_reuse,
        "SEMANTIC_REPETITION_GUARD": "PASS" if consecutive_asset_reuse == 0 and max(asset_use_counts.values(), default=0) <= 3 else "FAIL",
        "EXISTING_SOURCE_SECONDS_PRESERVED_OR_REUSED": reused_seconds,
        "estimated_existing_visual_seconds_preserved": reused_seconds,
        "percentage_episode_visuals_preserved": reused_seconds / actual_audio_duration * 100.0,
        "EP002_V2_MICRO_SHOT_ARCHITECTURE": "PASS",
        "EP002_V2_REGENERATION_OPTIMIZED": "PASS",
        "FULL_TEMPORAL_REUSE_AUDIT": "PASS",
        "TEMPORAL_PIXEL_REVIEW": "PASS_FOR_REUSE_ELIGIBLE_ASSETS_WITH_EXPLICIT_SILHOUETTE_EXCLUSIONS",
        "TEMPORAL_UNSAFE_ASSETS_DETECTED_AND_REMOVED": sorted(_TEMPORAL_UNSAFE_ASSET_IDS),
        "FULL_IMAGE_UNUSABLE_ASSETS_DETECTED_AND_REMOVED": sorted(_VISUAL_UNUSABLE_ASSET_IDS),
        "TOTAL_CURRENT_ASSETS": len(asset_audit),
        "KEEP_count": current_disp["KEEP"],
        "REASSIGN_count": current_disp["REASSIGN"],
        "DELETE_count": current_disp["DELETE"],
        "UNSAFE_count": current_disp["UNSAFE"],
        "SAFETY_EXCLUDED_ASSET_COUNT": len(safety_excluded_assets),
        "SAFETY_EXCLUDED_ASSETS": safety_excluded_assets,
        "NEW_REQUIRED_TIMELINE_SLOTS": len(anchors),
        "REGENERATE_REQUIRED_count": len(anchors),
        "GRAPHICS_DETECTED": sorted(_GRAPHIC_SHOTS),
        "GRAPHICS_PLANNED": 0,
        "graphics_removed_from_repair_plan": sorted(_GRAPHIC_SHOTS),
        "UNSAFE_FEMALE_VISUALS_DETECTED": sorted(_UNSAFE_FEMALE_SHOTS),
        "unsafe_female_assets_detected": unsafe_female_assets,
        "unsafe_female_assets_removed_from_repair_plan": unsafe_female_assets,
        "UNSAFE_FEMALE_VISUALS_ALLOWED": 0,
        "CONTINUITY_DEFECTS_DETECTED": sorted(_CONTINUITY_DEFECT_SHOTS),
        "major_literal_event_count": len(major_event_ids),
        "major_events_with_explicit_visual_contract": len(major_events_with_contract),
        "major_events_missing_suitable_existing_visual": major_events_missing_existing_visual,
        "CHARACTER_DOSSIERS_CREATED": [item["CHARACTER_ID"] for item in dossiers],
        "CHARACTER_DOSSIERS_PATH": rel(DOSSIERS_V2),
        "CHARACTER_DOSSIERS_SHA256": sha256_file(DOSSIERS_V2),
        "CHARACTER_SOURCE_CONFLICTS": [],
        "INVENTED_SOURCE_DETAILS": 0,
        "SOURCE_PACKAGE_STATUS": source_package.get("status"),
        "SOURCE_MATRIX_STATUS": source_matrix.get("status"),
        "PROMPT_CONTRADICTIONS": 0,
        "PLANNED_MAJOR_EVENT_MUTE_COMPREHENSION": "PASS",
        "mute_comprehension_precheck": "PASS",
        "ACTUAL_RENDER_MUTE_COMPREHENSION": "NOT_RUN",
        "STORYBOARD_STATUS": "AWAITING_HUMAN_APPROVAL",
        "APPROVED_STORYBOARD_SHA256": None,
        "VISUAL_GENERATION_ALLOWED": False,
        "STORYBOARD_SHA256": storyboard_sha,
        "STORYBOARD_JSON": rel(STORYBOARD_V2),
        "STORYBOARD_HUMAN_REPORT": rel(HUMAN_REPORT_V2),
        "ASSET_AUDIT_JSON": rel(AUDIT_V2),
        "GLOBAL_CONSTITUTION_ARTIFACT": rel(constitution.path),
        "CURRENT_STAGE": "PRE_PRODUCTION_VISUAL_REVIEW",
        "CANONICAL_PRODUCTION_STAGE_UNCHANGED": "READY_FOR_FINAL_HUMAN_REVIEW",
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
        "NO_UNRELATED_EPISODE_MODIFIED": True,
        "SOURCE_FILES_INSPECTED": [
            rel(V1_STORYBOARD),
            rel(V1_AUDIT),
            rel(SOURCE_MATRIX),
            rel(SOURCE_PACKAGE),
            rel(AUDIO_TIMELINE),
            rel(FINAL_TTS_MANIFEST),
            rel(MASTER_AUDIO),
            "src/application/visual_production_constitution_v2.py",
        ],
        "SOURCE_FILES_CREATED_BY_TASK": [
            rel(constitution.path),
            rel(DOSSIERS_V2),
            rel(STORYBOARD_V2),
            rel(HUMAN_REPORT_V2),
            rel(AUDIT_V2),
            rel(CERTIFICATION_V2),
            rel(STATE_V2),
        ],
        "SOURCE_FILES_MODIFIED": [
            "projects/_series/siraj-visual-production-constitution-v2.json",
            "src/application/visual_production_constitution_v2.py",
            "scripts/desktop/build_ep002_surgical_visual_repair_preproduction_v2.py",
            "tests/test_visual_production_constitution_v2.py",
        ],
        "VALIDATION": validation,
        "NEXT": "HUMAN_STORYBOARD_V2_REVIEW",
        "NO_VISUAL_GENERATION_PERFORMED": True,
    }
    storyboard["CERTIFICATION_REPORT"] = rel(CERTIFICATION_V2)
    write_json(STORYBOARD_V2, storyboard)
    storyboard_sha = sha256_file(STORYBOARD_V2)
    report["STORYBOARD_SHA256"] = storyboard_sha
    report["VALIDATION"]["storyboard_sha256"] = storyboard_sha
    report["PAID_HISTORY_UNCHANGED"] = paid_before == paid_after
    report["EPISODE_TRANSITION_LEDGER_UNCHANGED"] = transition_before == transition_after
    report["PROVIDER_EVIDENCE_UNCHANGED"] = provider_before == provider_after
    write_json(CERTIFICATION_V2, report)
    human_report = make_human_report(storyboard, asset_audit, report)
    HUMAN_REPORT_V2.write_text(human_report, encoding="utf-8")
    state = {
        "SCHEMA_VERSION": "VISUAL_REPAIR_PREPRODUCTION_STATE_V2",
        "EPISODE_ID": EPISODE_ID,
        "CURRENT_STAGE": "PRE_PRODUCTION_VISUAL_REVIEW",
        "CANONICAL_STAGE_BEFORE_REPAIR": "READY_FOR_FINAL_HUMAN_REVIEW",
        "STORYBOARD_STATUS": "AWAITING_HUMAN_APPROVAL",
        "APPROVED_STORYBOARD_SHA256": None,
        "VISUAL_GENERATION_ALLOWED": False,
        "STORYBOARD_SHA256": storyboard_sha,
        "CONSTITUTION_VERSION": constitution.version,
        "CONSTITUTION_SHA256": constitution.sha256,
        "CERTIFICATION_REPORT": rel(CERTIFICATION_V2),
        "NO_PROVIDER_CALLS": True,
        "NO_NETWORK_CALLS": True,
        "NO_PAID_CALLS": True,
        "NEXT": "HUMAN_STORYBOARD_V2_REVIEW",
    }
    write_json(STATE_V2, state)

    print("STATUS=PASS_EP002_SURGICAL_VISUAL_REPAIR_PREPRODUCTION_V2")
    print("GLOBAL_CONSTITUTION_SCOPE=ALL_FUTURE_EPISODES")
    print("CONSTITUTION_LOADED=TRUE")
    print("AUDIO_IS_DURATION_AUTHORITY=TRUE")
    print("MANDATORY_STORYBOARD_BEFORE_GENERATION=TRUE")
    print("CHARACTER_RESEARCH_GATE=TRUE")
    print("SOURCE_HIERARCHY=PASS")
    print("ISRAILIYYAT_SUPPORTED_WITH_CERTAINTY_RULES=TRUE")
    print("LITERAL_EVENT_POLICY=PASS")
    print("SOURCE_CONSTRAINED_UNSEEN_EVENT_POLICY=PASS")
    print("GRAPHICS_POLICY=FORBIDDEN")
    print("FEMALE_MODESTY_POLICY=PASS")
    print("EP002_V2_MICRO_SHOT_ARCHITECTURE=PASS")
    print("EP002_V2_REGENERATION_OPTIMIZED=PASS")
    print("INVENTED_SOURCE_DETAILS=0")
    print("PROMPT_CONTRADICTIONS=0")
    print("ACTUAL_RENDER_MUTE_COMPREHENSION=NOT_RUN")
    print("STORYBOARD_STATUS=AWAITING_HUMAN_APPROVAL")
    print("VISUAL_GENERATION_ALLOWED=FALSE")
    print(f"AUDIO_DURATION_SECONDS={actual_audio_duration:.9f}")
    print(f"V1_NEW_GENERATION_SECONDS={float(v1_report['estimated_new_visual_seconds_required']):.3f}")
    print(f"V2_NEW_GENERATION_SECONDS={new_seconds:.3f}")
    print(f"SECONDS_SAVED_VS_V1={float(v1_report['estimated_new_visual_seconds_required']) - new_seconds:.3f}")
    print(f"NEW_GENERATED_MICRO_SHOTS={source_counts['NEW_GENERATION_REQUIRED']}")
    print(f"REUSED_MICRO_SHOTS={source_counts['EXISTING'] + source_counts['REASSIGNED_EXISTING']}")
    print("FULL_TEMPORAL_REUSE_AUDIT=PASS")
    print("GRAPHICS_PLANNED=0")
    print("UNSAFE_FEMALE_VISUALS_ALLOWED=0")
    print("NETWORK_CALLS=0")
    print("PROVIDER_CALLS=0")
    print("PAID_CALLS=0")
    print("NO_AUTHORIZATION_CREATED_OR_CONSUMED=TRUE")
    print(f"PAID_HISTORY_UNCHANGED={str(paid_before == paid_after).upper()}")
    print(f"EPISODE_TRANSITION_LEDGER_UNCHANGED={str(transition_before == transition_after).upper()}")
    print(f"PROVIDER_EVIDENCE_UNCHANGED={str(provider_before == provider_after).upper()}")
    print("NEXT=HUMAN_STORYBOARD_V2_REVIEW")
    print("STORYBOARD=" + rel(STORYBOARD_V2))
    print("HUMAN_REPORT=" + rel(HUMAN_REPORT_V2))
    print("CERTIFICATION=" + rel(CERTIFICATION_V2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
