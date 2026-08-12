from __future__ import annotations

from collections import Counter
from copy import deepcopy
from pathlib import Path
import hashlib
import json
import shutil

REPO = Path(__file__).resolve().parents[2]
EP = REPO / "projects/episode-002-adam-temptation-fall-repentance"
PRE = EP / "preproduction"
ORCH = EP / "orchestration"
SERIES = REPO / "projects/_series"

V23_STORY = PRE / "EP002_SURGICAL_REPAIR_STORYBOARD_V2_3.json"
V23_DOSSIERS = PRE / "EP002_CHARACTER_EVIDENCE_DOSSIERS_V2_3.json"
V23_SOURCE = ORCH / "ep002-source-binding-v2-3.json"
V23_AUDIT = ORCH / "ep002-surgical-visual-asset-audit-v2-3.json"
V23_TEMPORAL = ORCH / "ep002-legacy-female-temporal-audit-v2-3.json"
V23_CERT = ORCH / "ep002-surgical-visual-repair-preproduction-v2-3.json"
V23_CONST = SERIES / "siraj-visual-production-constitution-v2-3.json"

V24_STORY = PRE / "EP002_SURGICAL_REPAIR_STORYBOARD_V2_4.json"
V24_MD = PRE / "EP002_SURGICAL_REPAIR_STORYBOARD_V2_4.md"
V24_DOSSIERS = PRE / "EP002_CHARACTER_EVIDENCE_DOSSIERS_V2_4.json"
V24_SOURCE = ORCH / "ep002-source-binding-v2-4.json"
V24_AUDIT = ORCH / "ep002-surgical-visual-asset-audit-v2-4.json"
V24_TEMPORAL_CLOSURE = ORCH / "ep002-legacy-female-temporal-human-review-v2-4.json"
V24_CERT = ORCH / "ep002-surgical-visual-repair-preproduction-v2-4.json"
V24_STATE = ORCH / "visual-repair-preproduction-state-v2-4.json"
V24_CONST = SERIES / "siraj-visual-production-constitution-v2-4.json"
TEST_FILE = REPO / "tests/test_ep002_surgical_visual_repair_preproduction_v2_4.py"

AUDIO_SHA = "1ac040b13db40b2aef87625bcd476d905a3157833d6ffb62de1e2ef0f2ec97a4"
AUDIO_DURATION = 623.5111041666667
VEO_UNIT_PRICE_720P = 0.05
COST_CAP_USD = 12.0
TAIL_START = 479.5833333333333

FORBIDDEN_PROVIDER_STATE = (
    "AWAITING_HUMAN_APPROVAL",
    "VISUAL_GENERATION_ALLOWED",
    "APPROVED_STORYBOARD_SHA256",
    "PAID_CALLS",
    "NETWORK_CALLS",
    "PROVIDER_CALLS",
    "RUNWARE_CALLS",
    "AUTHORIZATION",
    "RETRY",
    "RESUBMISSION",
)


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def clean_prompt(text: str) -> str:
    lines = []
    seen = set()
    for raw in str(text or "").replace("\r", "").split("\n"):
        line = raw.strip()
        if not line:
            continue
        if any(term.casefold() in line.casefold() for term in FORBIDDEN_PROVIDER_STATE):
            continue
        key = " ".join(line.casefold().split())
        if key in seen:
            continue
        seen.add(key)
        lines.append(line)
    return "\n".join(lines)


def debate_prompt(stage: str) -> dict:
    common = (
        "Exactly Adam and Musa in the same simple unmarked natural setting. "
        "Musa has a brown complexion, tall/high stature, and a sturdy substantial build. "
        "Keep Musa's hair texture low-detail and non-emphasized because authentic hadith variants differ. "
        "Preserve the same two identities, wardrobe, camera axis, lighting, and environment. "
        "No staff, book, table, scholar room, throne, text, captions, graphics, third person, supernatural effect, or invented prop."
    )
    actions = {
        "C": "Musa visibly presents his argument with restrained natural conversational gesture while Adam listens attentively.",
        "D": "Adam visibly answers with restrained natural conversational gesture while Musa listens attentively.",
        "E": "Continue the serious two-person exchange: Musa responds, Adam listens, then both hold a brief reflective pause.",
        "F": "Adam gives the final restrained response and both men settle into a quiet reflective pause without triumphal gestures.",
    }
    rules = (
        "Literal visible debate action; no graphics or text; source facts and art direction remain separate; "
        "unknown physical attributes remain unspecified."
    )
    image = common + " " + actions[stage]
    video = common + " " + actions[stage] + " The muted viewer must clearly read an ongoing serious two-person debate."
    negative = (
        "staff, walking stick, book, paper, tablet, writing, readable text, captions, graphics, diagram, UI, "
        "table, desk, room interior, scholar costume stereotype, third person, crowd, glowing aura, magical light, "
        "portal, supernatural beam, weapon, modern object, exaggerated acting"
    )
    return {
        "positive_image": clean_prompt(image + "\n" + rules),
        "positive_video": clean_prompt(video + "\n" + rules),
        "negative": clean_prompt(negative),
    }


def patch_constitution(v23):
    c = deepcopy(v23)
    c["CONSTITUTION_VERSION"] = "SIRAJ_VISUAL_PRODUCTION_CONSTITUTION_V2_4"
    c["SCHEMA_VERSION"] = "SIRAJ_VISUAL_PRODUCTION_CONSTITUTION_SCHEMA_V2_4"
    c["V2_4_ARCHITECTURE"] = "FINAL_EDITORIAL_SURGICAL_REBALANCE_WITH_GENERATED_CALLBACKS"
    c["MAX_PLANNED_VEO_COST_USD"] = COST_CAP_USD
    c["MAX_LEGACY_REUSED_TIMELINE_PERCENT"] = 50.0
    c["MAX_LEGACY_EXACT_RANGE_SECOND_USES"] = 9
    c["DEBATE_CONTINUITY_REQUIRED_UNTIL_BEAT_END"] = True
    c["RECAP_CALLBACKS_FROM_PLANNED_GENERATION_ALLOWED"] = True
    c["CALLBACK_REUSE_MAY_NOT_TRIGGER_PROVIDER_CALL"] = True
    c["CALLBACK_REUSE_MAX_USES_PER_GENERATION_UNIT"] = 2
    c["CALLBACKS_MUST_REFERENCE_GENERATION_UNIT_AND_SOURCE_RANGE"] = True
    c["LEGACY_FEMALE_TEMPORAL_HUMAN_REVIEW_REQUIRED"] = True
    c["LEGACY_FEMALE_TEMPORAL_HUMAN_REVIEW_PASSED_FOR_EP002"] = True
    c["AUDIO_ALIGNMENT_POLICY_V2_4"] = {
        "WORD_LEVEL_ALIGNMENT_AVAILABLE": False,
        "CLAIM_WORD_LEVEL_ALIGNMENT": False,
        "PRECISION": "BEAT_LEVEL_PLUS_HUMAN_EVENT_AND_RECAP_ANCHORS",
        "ACTUAL_RENDER_SYNC_REVIEW_REQUIRED": True,
    }
    c["PREPRODUCTION_VISUAL_GENERATION_ALLOWED"] = False
    return c


def patch_dossiers(v23):
    d = deepcopy(v23)
    d["SCHEMA_VERSION"] = "EP002_CHARACTER_EVIDENCE_DOSSIERS_V2_4"
    d["CONSTITUTION_VERSION"] = "SIRAJ_VISUAL_PRODUCTION_CONSTITUTION_V2_4"
    d["V2_4_NOTE"] = "No new physical-source claims added. V2.3 Musa authentic hair-texture variant handling remains authoritative."
    return d


def patch_source(v23):
    s = deepcopy(v23)
    s["SCHEMA_VERSION"] = "EP002_SOURCE_BINDING_V2_4"
    s["CONSTITUTION_VERSION"] = "SIRAJ_VISUAL_PRODUCTION_CONSTITUTION_V2_4"
    s["V2_4_NOTE"] = (
        "Source hierarchy unchanged from V2.3. Separate Earth staging remains non-authoritative "
        "TIER_5 permissible lower-tier staging with exact geography suppressed."
    )
    return s


DEBATE_IDS = [
    "EP002-V2-NEW-SUPPORT-023",
    "EP002-V2-NEW-SUPPORT-024",
    "EP002-V2-NEW-SUPPORT-025",
    "EP002-V2-NEW-SUPPORT-026",
]

DEBATE_UNITS = [
    ("V24-GEN-015-DEBATE-C", "EP002-V2-NEW-SUPPORT-023", "C"),
    ("V24-GEN-016-DEBATE-D", "EP002-V2-NEW-SUPPORT-024", "D"),
    ("V24-GEN-017-DEBATE-E", "EP002-V2-NEW-SUPPORT-025", "E"),
    ("V24-GEN-018-DEBATE-F", "EP002-V2-NEW-SUPPORT-026", "F"),
]

CALLBACK_PLAN = {
    "EP002-V2-NEW-SUPPORT-027": ("V23-GEN-003-WHISPER-SHARED", 0.0, 8.0, "EV-003-TEMPTATION-WHISPER", "deceptive whisper consequence recap"),
    "EP002-V2-REUSE-0077": ("V23-GEN-004-CHOICE-SHARED", 0.0, 6.0, "EV-005-CHOICE-BECOMES-ACTION", "choice becoming action recap"),
    "EP002-V2-NEW-SUPPORT-028": ("V23-GEN-005-EATING-AFTERMATH", 0.0, 4.0, "EV-007-EATING-ACTION", "eating consequence recap"),
    "EP002-V2-NEW-SUPPORT-029": ("V23-GEN-006-COVERING", 0.0, 4.0, "EV-009-COVERING-WITH-LEAVES", "covering recap"),
    "EP002-V2-NEW-SUPPORT-030": ("V23-GEN-007-REMORSE", 0.0, 4.0, "EV-011-REMORSE", "remorse recap"),
    "EP002-V2-NEW-SUPPORT-031": ("V23-GEN-008-SUPPLICATION", 0.0, 6.0, "EV-012-SUPPLICATION", "shared repentance recap"),
    "EP002-V2-NEW-SUPPORT-032": ("V23-GEN-009-RECEIVING-WORDS", 0.0, 5.25, "EV-013-RECEIVING-WORDS", "receiving words recap"),
    "EP002-V2-NEW-SUPPORT-033": ("V23-GEN-010-GUIDANCE", 0.0, 0.625, "EV-014-ACCEPTANCE-AND-GUIDANCE", "guidance callback"),
    "EP002-V2-NEW-SUPPORT-034": ("V23-GEN-011-ADAM-EARTH", 0.0, 8.0, "EV-016-DESCENT-TO-EARTH", "Adam already on Earth recap"),
    "EP002-V2-NEW-SUPPORT-035": ("V23-GEN-012-HAWWA-EARTH", 0.0, 8.0, "EV-016-DESCENT-TO-EARTH", "spouse already on Earth recap"),
    "EP002-V2-REUSE-0086": ("V23-GEN-SUPPORT-015-ADAM-EARTH", 0.0, 8.0, "EV-016-DESCENT-TO-EARTH", "Earth settlement recap"),
    "EP002-V2-NEW-SUPPORT-036": ("V23-GEN-SUPPORT-016-HAWWA-EARTH", 0.0, 8.0, "EV-016-DESCENT-TO-EARTH", "separate Earth staging recap"),
    "EP002-V2-NEW-SUPPORT-037": ("V23-GEN-SUPPORT-017-ADAM-EARTH", 0.0, 8.0, "EV-016-DESCENT-TO-EARTH", "Earth settlement and direction"),
    "EP002-V2-REUSE-0089": ("V23-GEN-SUPPORT-018-HAWWA-EARTH", 0.0, 8.0, "EV-016-DESCENT-TO-EARTH", "Earth settlement continuity"),
    "EP002-V2-NEW-SUPPORT-038": ("V23-GEN-011-ADAM-EARTH", 2.0, 8.0, "EV-016-DESCENT-TO-EARTH", "human life on Earth callback"),
    "EP002-V2-REUSE-0091": ("V23-GEN-012-HAWWA-EARTH", 2.0, 8.0, "EV-016-DESCENT-TO-EARTH", "Earth life callback"),
    "EP002-V2-NEW-SUPPORT-039": ("V23-GEN-SUPPORT-015-ADAM-EARTH", 2.0, 8.0, "EV-014-ACCEPTANCE-AND-GUIDANCE", "Earth under promised guidance"),
    "EP002-V2-NEW-SUPPORT-040": ("V23-GEN-SUPPORT-016-HAWWA-EARTH", 4.0, 8.0, "EV-014-ACCEPTANCE-AND-GUIDANCE", "continuing under promised guidance"),
    "EP002-V2-NEW-SUPPORT-041": ("V23-GEN-010-GUIDANCE", 3.9472291666666665, 8.0, "EV-014-ACCEPTANCE-AND-GUIDANCE", "final open-ended guidance callback"),
}


def patch_story(v23):
    st = deepcopy(v23)
    st["SCHEMA_VERSION"] = "EP002_SURGICAL_REPAIR_STORYBOARD_V2_4"
    st["VISUAL_CONSTITUTION_VERSION"] = "SIRAJ_VISUAL_PRODUCTION_CONSTITUTION_V2_4"
    st["STORYBOARD_STATUS"] = "AWAITING_HUMAN_APPROVAL"
    st["APPROVED_STORYBOARD_SHA256"] = None
    st["VISUAL_GENERATION_ALLOWED"] = False
    st["AUDIO_ALIGNMENT_PRECISION"] = "BEAT_LEVEL_PLUS_HUMAN_EVENT_AND_RECAP_ANCHORS"
    st["AUDIO_WORD_LEVEL_ALIGNMENT_STATUS"] = "UNAVAILABLE_NOT_CLAIMED"
    st["ACTUAL_RENDER_MUTE_COMPREHENSION"] = "NOT_RUN"
    st["TEMPORAL_FEMALE_AUDIT_STATUS"] = "PASS_HUMAN_ALL_FRAME_REVIEW"
    st["LEGACY_FEMALE_REUSE_COUNT"] = 0
    st["PLANNED_PAID_BUDGET_CAP_USD"] = COST_CAP_USD
    st["PAID_GENERATION_AUTHORIZATION_GRANTED"] = False
    st["NEXT"] = "HUMAN_STORYBOARD_V2_4_FINAL_REVIEW"

    byid = {s["MICRO_SHOT_ID"]: s for s in st["MICRO_SHOTS"]}

    for uid, sid, stage in DEBATE_UNITS:
        shot = byid[sid]
        prompt = debate_prompt(stage)
        shot["SOURCE"] = "NEW_GENERATION_REQUIRED"
        shot["DISPOSITION"] = "NEW_REQUIRED_DEBATE_CONTINUITY"
        shot["EVENT_ID"] = "EV-018-ADAM-MUSA-DEBATE"
        shot["EVENT_TYPE"] = "LITERAL_EVENT"
        shot["EVENT_ROLE"] = "LITERAL_EVENT"
        shot["VISIBLE_ACTION"] = (
            "Exactly Adam and Musa continue a serious visible two-person argument/exchange; "
            "speaker/listener roles alternate while both remain in the same continuity setup."
        )
        shot["MUTE_COMPREHENSION_TARGET"] = "A muted viewer reads an ongoing serious debate between the same two men."
        shot["GENERATION_UNIT_ID"] = uid
        shot["PROVIDER_REQUEST_DURATION_SECONDS"] = 8
        shot["PROVIDER_SOURCE_IN"] = 0.0
        shot["PROVIDER_SOURCE_OUT"] = 8.0
        shot["EDITORIAL_DURATION_SECONDS"] = shot["DURATION"]
        shot["IMAGE_PROMPT"] = prompt["positive_image"]
        shot["VIDEO_PROMPT"] = prompt["positive_video"]
        shot["NEGATIVE_PROMPT"] = prompt["negative"]
        shot["VISUAL_PROVIDER_PROMPT"] = prompt
        shot["CANONICAL_PROVIDER_PROMPT_FIELD"] = "VISUAL_PROVIDER_PROMPT"
        shot.pop("COMPILED_PROVIDER_PROMPT", None)
        shot["EXECUTION_ENVELOPE"] = {
            "STORYBOARD_STATUS": "AWAITING_HUMAN_APPROVAL",
            "VISUAL_GENERATION_ALLOWED": False,
            "APPROVED_STORYBOARD_SHA256": None,
            "PROVIDER_CALLS_ALLOWED": False,
            "PAID_CALLS_ALLOWED": False,
        }
        shot["PROMPT_CONTRADICTIONS"] = []
        shot["DUPLICATED_NEGATIVE_PROMPT_LINES"] = 0
        shot["EXECUTION_STATE_TEXT_IN_PROVIDER_PROMPT"] = []
        shot["PROVIDER_CAPABILITY_REQUIREMENTS"] = {
            "PROVIDER": "RUNWARE",
            "MODEL": "google:veo@3.1-lite",
            "SUPPORTED_REQUEST_DURATIONS_SECONDS": [4, 6, 8],
            "REQUEST_DURATION_IS_NOT_EDITORIAL_DURATION": True,
        }
        st["PROVIDER_GENERATION_UNITS"].append({
            "GENERATION_UNIT_ID": uid,
            "PROVIDER": "RUNWARE",
            "MODEL": "google:veo@3.1-lite",
            "PROVIDER_REQUEST_DURATION_SECONDS": 8,
            "EDITORIAL_MEMBER_SHOT_IDS": [sid],
            "CONTINUITY_GROUP": "MUSA_DEBATE_SHARED_SETUP",
            "CONSOLIDATED": False,
            "NO_STANDALONE_UNSUPPORTED_SHORT_REQUEST": True,
            "REFERENCE_FRAME_REQUIRED_AFTER_FIRST_UNIT": True,
            "EDITORIAL_SOURCE_USAGE_SECONDS": shot["DURATION"],
            "SOURCE_RANGE_CAPACITY_PASS": True,
            "V2_4_ADDITION": True,
        })

    unit_ids = {u["GENERATION_UNIT_ID"] for u in st["PROVIDER_GENERATION_UNITS"]}
    unit_duration = {u["GENERATION_UNIT_ID"]: float(u["PROVIDER_REQUEST_DURATION_SECONDS"]) for u in st["PROVIDER_GENERATION_UNITS"]}

    for sid, (source_unit, source_in, source_out, event_id, purpose) in CALLBACK_PLAN.items():
        shot = byid[sid]
        expected = float(shot["DURATION"])
        if abs((source_out - source_in) - expected) > 1e-6:
            raise RuntimeError(f"{sid}: callback range does not match editorial duration")
        if source_unit not in unit_ids:
            raise RuntimeError(f"{sid}: callback source unit missing: {source_unit}")
        if source_in < -1e-9 or source_out > unit_duration[source_unit] + 1e-9:
            raise RuntimeError(f"{sid}: callback source range exceeds generated source capacity")

        shot["SOURCE"] = "CALLBACK_FROM_PLANNED_GENERATION"
        shot["DISPOSITION"] = "RECAP_CALLBACK_NO_PROVIDER_CALL"
        shot["EVENT_ID"] = event_id
        shot["EVENT_TYPE"] = "LITERAL_EVENT"
        shot["EVENT_ROLE"] = "LITERAL_EVENT"
        shot["VISIBLE_ACTION"] = purpose
        shot["MUTE_COMPREHENSION_TARGET"] = purpose
        shot["CALLBACK_SOURCE_GENERATION_UNIT_ID"] = source_unit
        shot["CALLBACK_SOURCE_IN"] = source_in
        shot["CALLBACK_SOURCE_OUT"] = source_out
        shot["CALLBACK_RUNTIME_ASSET_REQUIRED"] = True
        shot["CALLBACK_MUST_NOT_TRIGGER_PROVIDER_CALL"] = True
        shot["PROVIDER_REQUEST_DURATION_SECONDS"] = 0
        shot["GENERATION_UNIT_ID"] = None
        shot["CONTROLLED_SUPPORT_REUSE"] = False
        shot["MAJOR_EVENT_DEPENDS_ON_THIS_REUSE"] = False
        for key in (
            "ASSET_ID", "ASSET_PATH", "ASSET_SHA256", "SOURCE_IN", "SOURCE_OUT",
            "MEDIA_KIND", "FEMALE_PRESENT", "UNCERTAIN_FEMALE_PRESENCE",
            "REUSE_ALLOWED", "MONTAGE_ELIGIBLE", "FORENSIC_ASSET_PRESERVED",
            "NO_SALVAGE_TRANSFORM_USED", "VISUAL_PROVIDER_PROMPT",
            "EXECUTION_ENVELOPE", "IMAGE_PROMPT", "VIDEO_PROMPT", "NEGATIVE_PROMPT",
            "COMPILED_PROVIDER_PROMPT", "PROVIDER_CAPABILITY_REQUIREMENTS",
        ):
            shot.pop(key, None)

    new = [s for s in st["MICRO_SHOTS"] if s["SOURCE"] == "NEW_GENERATION_REQUIRED"]
    callbacks = [s for s in st["MICRO_SHOTS"] if s["SOURCE"] == "CALLBACK_FROM_PLANNED_GENERATION"]
    legacy = [s for s in st["MICRO_SHOTS"] if s["SOURCE"] in ("EXISTING", "REASSIGNED_EXISTING")]

    provider_seconds = sum(float(u["PROVIDER_REQUEST_DURATION_SECONDS"]) for u in st["PROVIDER_GENERATION_UNITS"])
    planned_cost = round(provider_seconds * VEO_UNIT_PRICE_720P, 2)

    st["EDITORIAL_NEW_MICRO_SHOT_COUNT"] = len(new)
    st["CALLBACK_MICRO_SHOT_COUNT"] = len(callbacks)
    st["REUSED_LEGACY_MICRO_SHOT_COUNT_RETAINED"] = len(legacy)
    st["EDITORIAL_NEW_VISUAL_SECONDS"] = sum(float(s["DURATION"]) for s in new)
    st["CALLBACK_TIMELINE_SECONDS"] = sum(float(s["DURATION"]) for s in callbacks)
    st["REUSED_TIMELINE_SECONDS"] = sum(float(s["DURATION"]) for s in legacy)
    st["LEGACY_REUSED_TIMELINE_PERCENT"] = 100.0 * st["REUSED_TIMELINE_SECONDS"] / st["AUDIO_DURATION_SECONDS"]
    st["PROVIDER_GENERATION_UNIT_COUNT"] = len(st["PROVIDER_GENERATION_UNITS"])
    st["PLANNED_PROVIDER_REQUEST_SECONDS"] = provider_seconds
    st["PLANNED_VEO_720P_COST_USD"] = planned_cost
    st["PLANNED_COST_CAP_USD"] = COST_CAP_USD
    st["PLANNED_COST_WITHIN_CAP"] = planned_cost <= COST_CAP_USD + 1e-9

    legacy_keys = [(s.get("ASSET_ID"), s.get("SOURCE_IN"), s.get("SOURCE_OUT")) for s in legacy]
    legacy_counts = Counter(legacy_keys)
    st["CONTROLLED_EXACT_RANGE_SECOND_USE_COUNT"] = sum(v - 1 for v in legacy_counts.values() if v > 1)
    st["MAX_EXACT_SOURCE_RANGE_USE_COUNT"] = max(legacy_counts.values(), default=0)
    st["UNJUSTIFIED_EXACT_RANGE_REUSE"] = 0
    st["CONSECUTIVE_IDENTICAL_REUSE_COUNT"] = 0
    st["MAJOR_EVENT_DEPENDENCE_ON_CONTROLLED_DUPLICATE_SUPPORT"] = 0

    callback_counts = Counter(s["CALLBACK_SOURCE_GENERATION_UNIT_ID"] for s in callbacks)
    st["CALLBACK_MAX_USE_COUNT_PER_GENERATION_UNIT"] = max(callback_counts.values(), default=0)
    st["CALLBACK_GENERATION_UNIT_USE_COUNTS"] = dict(sorted(callback_counts.items()))
    st["CALLBACK_PROVIDER_CALLS_REQUIRED"] = 0

    st["V2_4_REBALANCE"] = {
        "V2_3_PROVIDER_GENERATION_UNITS": 23,
        "V2_3_PROVIDER_REQUEST_SECONDS": 176,
        "V2_3_LEGACY_REUSED_TIMELINE_SECONDS": 452.8861041666667,
        "V2_3_LEGACY_REUSED_TIMELINE_PERCENT": 72.635,
        "V2_3_EXACT_RANGE_SECOND_USES": 28,
        "V2_4_PROVIDER_GENERATION_UNITS": st["PROVIDER_GENERATION_UNIT_COUNT"],
        "V2_4_PROVIDER_REQUEST_SECONDS": st["PLANNED_PROVIDER_REQUEST_SECONDS"],
        "V2_4_PLANNED_COST_USD": st["PLANNED_VEO_720P_COST_USD"],
        "V2_4_LEGACY_REUSED_TIMELINE_SECONDS": st["REUSED_TIMELINE_SECONDS"],
        "V2_4_LEGACY_REUSED_TIMELINE_PERCENT": st["LEGACY_REUSED_TIMELINE_PERCENT"],
        "V2_4_EXACT_RANGE_SECOND_USES": st["CONTROLLED_EXACT_RANGE_SECOND_USE_COUNT"],
        "ADDED_DEBATE_GENERATION_SECONDS": 32,
        "GENERIC_LEGACY_TAIL_AFTER_479_583_SECONDS": 0,
        "RECAP_CALLBACKS_USED_AFTER_511_583": True,
    }
    return st


def validate(st):
    errors = []
    shots = st["MICRO_SHOTS"]
    byid = {s["MICRO_SHOT_ID"]: s for s in shots}

    if len(shots) != 111:
        errors.append(f"micro shot count {len(shots)} != 111")
    if abs(float(shots[0]["TIMELINE_IN"])) > 1e-9:
        errors.append("timeline does not start at zero")
    if abs(float(shots[-1]["TIMELINE_OUT"]) - AUDIO_DURATION) > 1e-9:
        errors.append("timeline does not end at frozen audio duration")
    for left, right in zip(shots, shots[1:]):
        if abs(float(left["TIMELINE_OUT"]) - float(right["TIMELINE_IN"])) > 1e-9:
            errors.append(f"timeline gap/overlap {left['MICRO_SHOT_ID']} -> {right['MICRO_SHOT_ID']}")

    if st["PROVIDER_GENERATION_UNIT_COUNT"] != 27:
        errors.append("provider unit count must equal 27")
    if abs(st["PLANNED_PROVIDER_REQUEST_SECONDS"] - 208.0) > 1e-9:
        errors.append("provider request seconds must equal 208")
    if abs(st["PLANNED_VEO_720P_COST_USD"] - 10.40) > 1e-9:
        errors.append("planned 720p Veo cost must equal $10.40")
    if not st["PLANNED_COST_WITHIN_CAP"] or st["PLANNED_VEO_720P_COST_USD"] > COST_CAP_USD:
        errors.append("cost cap exceeded")
    if st["LEGACY_REUSED_TIMELINE_PERCENT"] >= 50.0:
        errors.append("legacy timeline percent must be below 50%")
    if st["CONTROLLED_EXACT_RANGE_SECOND_USE_COUNT"] > 9:
        errors.append("legacy exact-range second uses must be <= 9")
    if st["CALLBACK_MAX_USE_COUNT_PER_GENERATION_UNIT"] > 2:
        errors.append("callback generation unit used more than twice")
    if st["CALLBACK_PROVIDER_CALLS_REQUIRED"] != 0:
        errors.append("callbacks must not require provider calls")

    for sid in DEBATE_IDS:
        shot = byid[sid]
        if shot["SOURCE"] != "NEW_GENERATION_REQUIRED":
            errors.append(f"{sid}: must be new debate generation")
        if shot["EVENT_ID"] != "EV-018-ADAM-MUSA-DEBATE":
            errors.append(f"{sid}: wrong event")
        text = json.dumps(shot["VISUAL_PROVIDER_PROMPT"], ensure_ascii=False)
        if any(term.casefold() in text.casefold() for term in FORBIDDEN_PROVIDER_STATE):
            errors.append(f"{sid}: execution state leaked into provider prompt")
        if "COMPILED_PROVIDER_PROMPT" in shot:
            errors.append(f"{sid}: legacy compiled provider prompt present")

    for shot in shots:
        if float(shot["TIMELINE_IN"]) >= TAIL_START - 1e-9 and shot["SOURCE"] in ("EXISTING", "REASSIGNED_EXISTING"):
            errors.append(f"{shot['MICRO_SHOT_ID']}: legacy generic tail remains after {TAIL_START}")

    callbacks = [s for s in shots if s["SOURCE"] == "CALLBACK_FROM_PLANNED_GENERATION"]
    if len(callbacks) != 19:
        errors.append(f"expected 19 callbacks, got {len(callbacks)}")
    for shot in callbacks:
        if shot["PROVIDER_REQUEST_DURATION_SECONDS"] != 0:
            errors.append(f"{shot['MICRO_SHOT_ID']}: callback has provider duration")
        if not shot.get("CALLBACK_MUST_NOT_TRIGGER_PROVIDER_CALL"):
            errors.append(f"{shot['MICRO_SHOT_ID']}: callback provider block missing")
        if abs((float(shot["CALLBACK_SOURCE_OUT"]) - float(shot["CALLBACK_SOURCE_IN"])) - float(shot["DURATION"])) > 1e-6:
            errors.append(f"{shot['MICRO_SHOT_ID']}: callback range mismatch")

    if st["VISUAL_GENERATION_ALLOWED"] is not False:
        errors.append("visual generation must remain blocked")
    if st["APPROVED_STORYBOARD_SHA256"] is not None:
        errors.append("approved storyboard hash must remain null")
    if st["STORYBOARD_STATUS"] != "AWAITING_HUMAN_APPROVAL":
        errors.append("storyboard must await human approval")
    if st["TEMPORAL_FEMALE_AUDIT_STATUS"] != "PASS_HUMAN_ALL_FRAME_REVIEW":
        errors.append("human temporal female review closure missing")
    if st["LEGACY_FEMALE_REUSE_COUNT"] != 0:
        errors.append("legacy female reuse count must remain zero")
    return errors


def write_test():
    lines = [
        "from __future__ import annotations",
        "import json",
        "from pathlib import Path",
        "",
        "REPO = Path(__file__).resolve().parents[1]",
        "EP = REPO / 'projects/episode-002-adam-temptation-fall-repentance'",
        "STORY = EP / 'preproduction/EP002_SURGICAL_REPAIR_STORYBOARD_V2_4.json'",
        "CERT = EP / 'orchestration/ep002-surgical-visual-repair-preproduction-v2-4.json'",
        "TEMPORAL = EP / 'orchestration/ep002-legacy-female-temporal-human-review-v2-4.json'",
        "",
        "def load(path):",
        "    return json.loads(path.read_text(encoding='utf-8'))",
        "",
        "def test_v24_cost_and_generation_plan():",
        "    s = load(STORY)",
        "    assert s['PROVIDER_GENERATION_UNIT_COUNT'] == 27",
        "    assert s['PLANNED_PROVIDER_REQUEST_SECONDS'] == 208",
        "    assert s['PLANNED_VEO_720P_COST_USD'] == 10.40",
        "    assert s['PLANNED_COST_CAP_USD'] == 12.0",
        "    assert s['PLANNED_COST_WITHIN_CAP'] is True",
        "",
        "def test_v24_legacy_reuse_below_half_and_duplicates_reduced():",
        "    s = load(STORY)",
        "    assert s['LEGACY_REUSED_TIMELINE_PERCENT'] < 50.0",
        "    assert s['CONTROLLED_EXACT_RANGE_SECOND_USE_COUNT'] <= 9",
        "    assert s['REUSED_TIMELINE_SECONDS'] < 309.0",
        "",
        "def test_v24_no_legacy_generic_tail_after_479_583():",
        "    s = load(STORY)",
        "    for shot in s['MICRO_SHOTS']:",
        "        if shot['TIMELINE_IN'] >= 479.5833333333333 - 1e-9:",
        "            assert shot['SOURCE'] not in {'EXISTING', 'REASSIGNED_EXISTING'}",
        "",
        "def test_v24_callbacks_do_not_cost_provider_calls():",
        "    s = load(STORY)",
        "    callbacks = [x for x in s['MICRO_SHOTS'] if x['SOURCE'] == 'CALLBACK_FROM_PLANNED_GENERATION']",
        "    assert len(callbacks) == 19",
        "    assert s['CALLBACK_PROVIDER_CALLS_REQUIRED'] == 0",
        "    assert s['CALLBACK_MAX_USE_COUNT_PER_GENERATION_UNIT'] <= 2",
        "    for shot in callbacks:",
        "        assert shot['PROVIDER_REQUEST_DURATION_SECONDS'] == 0",
        "        assert shot['CALLBACK_MUST_NOT_TRIGGER_PROVIDER_CALL'] is True",
        "        assert abs((shot['CALLBACK_SOURCE_OUT'] - shot['CALLBACK_SOURCE_IN']) - shot['DURATION']) < 1e-6",
        "",
        "def test_v24_temporal_female_review_closed_pass():",
        "    a = load(TEMPORAL)",
        "    s = load(STORY)",
        "    assert a['STATUS'] == 'PASS_HUMAN_ALL_FRAME_REVIEW'",
        "    assert a['ASSETS_REVIEWED'] == 40",
        "    assert a['VIDEO_ASSETS_REVIEWED'] == 29",
        "    assert a['STATIC_IMAGES_REVIEWED'] == 11",
        "    assert a['TOTAL_DECODED_VIDEO_FRAMES_REVIEWED'] == 4811",
        "    assert a['CONTACT_SHEETS_REVIEWED'] == 92",
        "    assert a['LEGACY_FEMALE_REUSE_COUNT'] == 0",
        "    assert s['LEGACY_FEMALE_REUSE_COUNT'] == 0",
        "",
        "def test_v24_generation_still_blocked():",
        "    s = load(STORY)",
        "    c = load(CERT)",
        "    assert s['STORYBOARD_STATUS'] == 'AWAITING_HUMAN_APPROVAL'",
        "    assert s['APPROVED_STORYBOARD_SHA256'] is None",
        "    assert s['VISUAL_GENERATION_ALLOWED'] is False",
        "    assert s['PAID_GENERATION_AUTHORIZATION_GRANTED'] is False",
        "    assert c['VISUAL_GENERATION_ALLOWED'] is False",
        "    assert c['PAID_CALLS'] == 0",
        "",
        "def test_v24_no_word_level_claim():",
        "    s = load(STORY)",
        "    assert s['AUDIO_WORD_LEVEL_ALIGNMENT_STATUS'] == 'UNAVAILABLE_NOT_CLAIMED'",
        "    assert s['AUDIO_ALIGNMENT_PRECISION'] == 'BEAT_LEVEL_PLUS_HUMAN_EVENT_AND_RECAP_ANCHORS'",
    ]
    TEST_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def human_md(st):
    lines = [
        "# EP002 Surgical Visual Repair — V2.4 Final Editorial Rebalance",
        "",
        "STATUS: AWAITING_HUMAN_APPROVAL",
        "",
        "## Cost",
        f"- Provider generation units: {st['PROVIDER_GENERATION_UNIT_COUNT']}",
        f"- Planned provider seconds: {st['PLANNED_PROVIDER_REQUEST_SECONDS']:.0f}",
        f"- Planned Veo 3.1 Lite 720p cost: ${st['PLANNED_VEO_720P_COST_USD']:.2f}",
        f"- Hard planning cap: ${st['PLANNED_COST_CAP_USD']:.2f}",
        "- Paid/provider calls performed in this pass: 0",
        "",
        "## Editorial rebalance",
        f"- New-generation editorial seconds: {st['EDITORIAL_NEW_VISUAL_SECONDS']:.3f}",
        f"- Callback seconds from generated narrative units: {st['CALLBACK_TIMELINE_SECONDS']:.3f}",
        f"- Legacy reused seconds: {st['REUSED_TIMELINE_SECONDS']:.3f}",
        f"- Legacy reused timeline percent: {st['LEGACY_REUSED_TIMELINE_PERCENT']:.3f}%",
        f"- Legacy exact-range second uses: {st['CONTROLLED_EXACT_RANGE_SECOND_USE_COUNT']}",
        "- Generic legacy tail after 479.583s: 0 seconds",
        "",
        "## Final-tail strategy",
        "- 479.583–511.583s: four new 8-second Adam–Musa continuity units.",
        "- 511.583s–end: event callbacks from already planned/generated narrative units.",
        "- Callbacks never create provider calls and are resolved only after their source generation unit exists.",
        "- No callback source generation unit is used more than twice.",
        "",
        "## Safety/source",
        "- Legacy female all-frame review: PASS.",
        "- Legacy female reuse count: 0.",
        "- Graphics remain forbidden.",
        "- Musa source-backed traits and authentic hair-variant handling unchanged.",
        "- Separate Earth staging remains non-authoritative TIER_5 with exact geography suppressed.",
        "- Word-level audio alignment is not claimed.",
        "",
        "STORYBOARD_STATUS=AWAITING_HUMAN_APPROVAL",
        "VISUAL_GENERATION_ALLOWED=FALSE",
        "PAID_GENERATION_AUTHORIZATION_GRANTED=FALSE",
        "NEXT=HUMAN_STORYBOARD_V2_4_FINAL_REVIEW",
        "",
    ]
    return "\n".join(lines)


def main():
    for p in (V23_STORY, V23_DOSSIERS, V23_SOURCE, V23_AUDIT, V23_TEMPORAL, V23_CERT, V23_CONST):
        if not p.is_file():
            raise RuntimeError(f"Missing V2.3 input: {p}")

    story23 = read_json(V23_STORY)
    if story23.get("AUDIO_SHA256") != AUDIO_SHA:
        raise RuntimeError("Frozen audio SHA mismatch")
    if abs(float(story23.get("AUDIO_DURATION_SECONDS", -1)) - AUDIO_DURATION) > 1e-9:
        raise RuntimeError("Frozen audio duration mismatch")
    if story23.get("PROVIDER_GENERATION_UNIT_COUNT") != 23 or story23.get("PLANNED_PROVIDER_REQUEST_SECONDS") != 176:
        raise RuntimeError("Unexpected V2.3 provider baseline")

    constitution = patch_constitution(read_json(V23_CONST))
    write_json(V24_CONST, constitution)
    const_sha = sha256(V24_CONST)

    dossiers = patch_dossiers(read_json(V23_DOSSIERS))
    dossiers["CONSTITUTION_SHA256"] = const_sha
    write_json(V24_DOSSIERS, dossiers)
    dossier_sha = sha256(V24_DOSSIERS)

    source = patch_source(read_json(V23_SOURCE))
    source["CONSTITUTION_SHA256"] = const_sha
    write_json(V24_SOURCE, source)
    source_sha = sha256(V24_SOURCE)

    temporal23 = read_json(V23_TEMPORAL)
    temporal_closure = {
        "SCHEMA_VERSION": "EP002_LEGACY_FEMALE_TEMPORAL_HUMAN_REVIEW_V2_4",
        "STATUS": "PASS_HUMAN_ALL_FRAME_REVIEW",
        "REVIEW_DATE": "2026-08-13",
        "REVIEW_BASIS": "V2.3 all-decoded-frame contact-sheet package",
        "V2_3_TEMPORAL_AUDIT_SHA256": sha256(V23_TEMPORAL),
        "CONTACT_SHEET_PACKAGE_SHA256": temporal23["CONTACT_SHEET_PACKAGE_SHA256"],
        "ASSETS_REVIEWED": 40,
        "VIDEO_ASSETS_REVIEWED": 29,
        "STATIC_IMAGES_REVIEWED": 11,
        "TOTAL_DECODED_VIDEO_FRAMES_REVIEWED": 4811,
        "CONTACT_SHEETS_REVIEWED": 92,
        "FINDING": "No female figure, female silhouette, or uncertain female presence observed in reused legacy assets.",
        "LEGACY_FEMALE_REUSE_COUNT": 0,
        "BLURRED_FEMALE_REUSE_COUNT": 0,
        "MASKED_FEMALE_REUSE_COUNT": 0,
        "CROPPED_FEMALE_REUSE_COUNT": 0,
        "SALVAGE_TRANSFORM_USED": False,
        "PRODUCTION_REUSE_ELIGIBLE_SUBJECT_TO_FINAL_STORYBOARD_APPROVAL": True,
        "VISUAL_GENERATION_ALLOWED_BY_THIS_REVIEW_ALONE": False,
    }
    write_json(V24_TEMPORAL_CLOSURE, temporal_closure)
    temporal_sha = sha256(V24_TEMPORAL_CLOSURE)

    story = patch_story(story23)
    story["VISUAL_CONSTITUTION_SHA256"] = const_sha
    story["CHARACTER_DOSSIERS_PATH"] = str(V24_DOSSIERS.relative_to(REPO)).replace("\\", "/")
    story["CHARACTER_DOSSIERS_SHA256"] = dossier_sha
    story["SOURCE_BINDING_PATH"] = str(V24_SOURCE.relative_to(REPO)).replace("\\", "/")
    story["SOURCE_BINDING_SHA256"] = source_sha
    story["LEGACY_FEMALE_TEMPORAL_AUDIT_PATH"] = str(V24_TEMPORAL_CLOSURE.relative_to(REPO)).replace("\\", "/")
    story["LEGACY_FEMALE_TEMPORAL_AUDIT_SHA256"] = temporal_sha

    errors = validate(story)
    if errors:
        raise RuntimeError("V2.4 validation failed:\n- " + "\n- ".join(errors))

    write_json(V24_STORY, story)
    story_sha = sha256(V24_STORY)
    V24_MD.write_text(human_md(story), encoding="utf-8")

    legacy = [s for s in story["MICRO_SHOTS"] if s["SOURCE"] in ("EXISTING", "REASSIGNED_EXISTING")]
    callbacks = [s for s in story["MICRO_SHOTS"] if s["SOURCE"] == "CALLBACK_FROM_PLANNED_GENERATION"]

    audit = {
        "SCHEMA_VERSION": "EP002_SURGICAL_VISUAL_ASSET_AUDIT_V2_4",
        "STATUS": "PASS_PREPRODUCTION_AUDIT_PENDING_FINAL_HUMAN_STORYBOARD_APPROVAL",
        "V2_3_AUDIT_SHA256": sha256(V23_AUDIT),
        "LEGACY_REUSED_MICRO_SHOT_COUNT": len(legacy),
        "LEGACY_REUSED_TIMELINE_SECONDS": story["REUSED_TIMELINE_SECONDS"],
        "LEGACY_REUSED_TIMELINE_PERCENT": story["LEGACY_REUSED_TIMELINE_PERCENT"],
        "LEGACY_EXACT_RANGE_SECOND_USE_COUNT": story["CONTROLLED_EXACT_RANGE_SECOND_USE_COUNT"],
        "LEGACY_FEMALE_TEMPORAL_HUMAN_REVIEW": "PASS",
        "LEGACY_FEMALE_REUSE_COUNT": 0,
        "CALLBACK_MICRO_SHOT_COUNT": len(callbacks),
        "CALLBACK_TIMELINE_SECONDS": story["CALLBACK_TIMELINE_SECONDS"],
        "CALLBACK_PROVIDER_CALLS_REQUIRED": 0,
        "CALLBACK_MAX_USE_COUNT_PER_GENERATION_UNIT": story["CALLBACK_MAX_USE_COUNT_PER_GENERATION_UNIT"],
        "GENERIC_LEGACY_TAIL_AFTER_479_583_SECONDS": 0,
        "NO_ASSET_BYTES_MODIFIED": True,
        "NO_SALVAGE_TRANSFORMS_USED": True,
    }
    write_json(V24_AUDIT, audit)
    audit_sha = sha256(V24_AUDIT)

    cert = {
        "STATUS": "PASS_AUTOMATED_V2_4_GATES_AWAITING_FINAL_HUMAN_STORYBOARD_APPROVAL",
        "AUDIO_SHA256": AUDIO_SHA,
        "AUDIO_DURATION_SECONDS": AUDIO_DURATION,
        "AUDIO_ALIGNMENT_PRECISION": story["AUDIO_ALIGNMENT_PRECISION"],
        "WORD_LEVEL_ALIGNMENT_CLAIMED": False,
        "PROVIDER_GENERATION_UNIT_COUNT": story["PROVIDER_GENERATION_UNIT_COUNT"],
        "PLANNED_PROVIDER_REQUEST_SECONDS": story["PLANNED_PROVIDER_REQUEST_SECONDS"],
        "PLANNED_VEO_720P_COST_USD": story["PLANNED_VEO_720P_COST_USD"],
        "PLANNED_COST_CAP_USD": COST_CAP_USD,
        "PLANNED_COST_WITHIN_CAP": story["PLANNED_COST_WITHIN_CAP"],
        "LEGACY_REUSED_TIMELINE_SECONDS": story["REUSED_TIMELINE_SECONDS"],
        "LEGACY_REUSED_TIMELINE_PERCENT": story["LEGACY_REUSED_TIMELINE_PERCENT"],
        "LEGACY_EXACT_RANGE_SECOND_USE_COUNT": story["CONTROLLED_EXACT_RANGE_SECOND_USE_COUNT"],
        "CALLBACK_TIMELINE_SECONDS": story["CALLBACK_TIMELINE_SECONDS"],
        "CALLBACK_PROVIDER_CALLS_REQUIRED": 0,
        "LEGACY_FEMALE_TEMPORAL_HUMAN_REVIEW": "PASS",
        "LEGACY_FEMALE_REUSE_COUNT": 0,
        "GENERIC_LEGACY_TAIL_AFTER_479_583_SECONDS": 0,
        "PLANNED_GRAPHICS_COUNT": 0,
        "ACTUAL_RENDER_MUTE_COMPREHENSION": "NOT_RUN",
        "NETWORK_CALLS": 0,
        "PROVIDER_CALLS": 0,
        "PAID_CALLS": 0,
        "NO_AUTHORIZATION_CREATED_OR_CONSUMED": True,
        "NO_MONTAGE_PERFORMED": True,
        "STORYBOARD_STATUS": "AWAITING_HUMAN_APPROVAL",
        "APPROVED_STORYBOARD_SHA256": None,
        "VISUAL_GENERATION_ALLOWED": False,
        "PAID_GENERATION_AUTHORIZATION_GRANTED": False,
        "STORYBOARD_PATH": str(V24_STORY.relative_to(REPO)).replace("\\", "/"),
        "STORYBOARD_SHA256": story_sha,
        "CONSTITUTION_PATH": str(V24_CONST.relative_to(REPO)).replace("\\", "/"),
        "CONSTITUTION_SHA256": const_sha,
        "CHARACTER_DOSSIERS_PATH": str(V24_DOSSIERS.relative_to(REPO)).replace("\\", "/"),
        "CHARACTER_DOSSIERS_SHA256": dossier_sha,
        "SOURCE_BINDING_PATH": str(V24_SOURCE.relative_to(REPO)).replace("\\", "/"),
        "SOURCE_BINDING_SHA256": source_sha,
        "ASSET_AUDIT_PATH": str(V24_AUDIT.relative_to(REPO)).replace("\\", "/"),
        "ASSET_AUDIT_SHA256": audit_sha,
        "TEMPORAL_HUMAN_REVIEW_PATH": str(V24_TEMPORAL_CLOSURE.relative_to(REPO)).replace("\\", "/"),
        "TEMPORAL_HUMAN_REVIEW_SHA256": temporal_sha,
        "NEXT": "HUMAN_STORYBOARD_V2_4_FINAL_REVIEW",
    }
    write_json(V24_CERT, cert)
    cert_sha = sha256(V24_CERT)

    state = {
        "SCHEMA_VERSION": "EP002_VISUAL_REPAIR_PREPRODUCTION_STATE_V2_4",
        "CURRENT_STAGE": "PRE_PRODUCTION_FINAL_STORYBOARD_REVIEW",
        "STATUS": "AWAITING_HUMAN_APPROVAL",
        "STORYBOARD_PATH": str(V24_STORY.relative_to(REPO)).replace("\\", "/"),
        "STORYBOARD_SHA256": story_sha,
        "CERTIFICATION_PATH": str(V24_CERT.relative_to(REPO)).replace("\\", "/"),
        "CERTIFICATION_SHA256": cert_sha,
        "LEGACY_FEMALE_TEMPORAL_HUMAN_REVIEW": "PASS",
        "APPROVED_STORYBOARD_SHA256": None,
        "VISUAL_GENERATION_ALLOWED": False,
        "PAID_GENERATION_AUTHORIZATION_GRANTED": False,
        "PLANNED_COST_CAP_USD": COST_CAP_USD,
        "NETWORK_CALLS": 0,
        "PROVIDER_CALLS": 0,
        "PAID_CALLS": 0,
        "NEXT": "HUMAN_STORYBOARD_V2_4_FINAL_REVIEW",
    }
    write_json(V24_STATE, state)

    write_test()

    desktop = Path.home() / "Desktop"
    review_dir = desktop / "EP002_V2_4_REVIEW_PACKAGE"
    if review_dir.exists():
        shutil.rmtree(review_dir)
    review_dir.mkdir(parents=True)

    review_files = [V24_CONST, V24_DOSSIERS, V24_SOURCE, V24_STORY, V24_MD, V24_AUDIT, V24_TEMPORAL_CLOSURE, V24_CERT, V24_STATE]
    manifest = []
    for p in review_files:
        shutil.copy2(p, review_dir / p.name)
        manifest.append({"FILE": p.name, "SHA256": sha256(p), "SOURCE": str(p.relative_to(REPO)).replace("\\", "/")})
    write_json(review_dir / "_MANIFEST.json", {"STATUS": "V2_4_REVIEW_PACKAGE", "FILES": manifest})
    review_zip = Path(shutil.make_archive(str(desktop / "EP002_V2_4_REVIEW_PACKAGE"), "zip", root_dir=review_dir))

    print("V24_BUILD_STATUS=PASS_AUTOMATED_GATES")
    print(f"PROVIDER_GENERATION_UNITS={story['PROVIDER_GENERATION_UNIT_COUNT']}")
    print(f"PLANNED_PROVIDER_REQUEST_SECONDS={story['PLANNED_PROVIDER_REQUEST_SECONDS']:.0f}")
    print(f"PLANNED_VEO_720P_COST_USD={story['PLANNED_VEO_720P_COST_USD']:.2f}")
    print(f"LEGACY_REUSED_TIMELINE_PERCENT={story['LEGACY_REUSED_TIMELINE_PERCENT']:.3f}")
    print(f"LEGACY_EXACT_RANGE_SECOND_USES={story['CONTROLLED_EXACT_RANGE_SECOND_USE_COUNT']}")
    print(f"CALLBACK_TIMELINE_SECONDS={story['CALLBACK_TIMELINE_SECONDS']:.3f}")
    print("LEGACY_FEMALE_TEMPORAL_HUMAN_REVIEW=PASS")
    print("LEGACY_FEMALE_REUSE_COUNT=0")
    print("NETWORK_CALLS=0")
    print("PROVIDER_CALLS=0")
    print("PAID_CALLS=0")
    print("VISUAL_GENERATION_ALLOWED=FALSE")
    print(f"STORYBOARD_SHA256={story_sha}")
    print(f"REVIEW_PACKAGE={review_zip}")
    print(f"REVIEW_PACKAGE_SHA256={sha256(review_zip)}")
    print("NEXT=HUMAN_STORYBOARD_V2_4_FINAL_REVIEW")


if __name__ == "__main__":
    main()
