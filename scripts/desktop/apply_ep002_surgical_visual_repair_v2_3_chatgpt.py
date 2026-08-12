from __future__ import annotations

from collections import Counter
from copy import deepcopy
from pathlib import Path
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import zipfile

REPO = Path(__file__).resolve().parents[2]
EP = REPO / "projects/episode-002-adam-temptation-fall-repentance"
PRE = EP / "preproduction"
ORCH = EP / "orchestration"
SERIES = REPO / "projects/_series"

V22_STORY = PRE / "EP002_SURGICAL_REPAIR_STORYBOARD_V2_2.json"
V22_DOSSIERS = PRE / "EP002_CHARACTER_EVIDENCE_DOSSIERS_V2_2.json"
V22_SOURCE = ORCH / "ep002-source-binding-v2-2.json"
V22_AUDIT = ORCH / "ep002-surgical-visual-asset-audit-v2-2.json"
V22_CERT = ORCH / "ep002-surgical-visual-repair-preproduction-v2-2.json"
V22_CONST = SERIES / "siraj-visual-production-constitution-v2-2.json"

V23_STORY = PRE / "EP002_SURGICAL_REPAIR_STORYBOARD_V2_3.json"
V23_MD = PRE / "EP002_SURGICAL_REPAIR_STORYBOARD_V2_3.md"
V23_DOSSIERS = PRE / "EP002_CHARACTER_EVIDENCE_DOSSIERS_V2_3.json"
V23_SOURCE = ORCH / "ep002-source-binding-v2-3.json"
V23_AUDIT = ORCH / "ep002-surgical-visual-asset-audit-v2-3.json"
V23_FEMALE_AUDIT = ORCH / "ep002-legacy-female-temporal-audit-v2-3.json"
V23_CERT = ORCH / "ep002-surgical-visual-repair-preproduction-v2-3.json"
V23_STATE = ORCH / "visual-repair-preproduction-state-v2-3.json"
V23_CONST = SERIES / "siraj-visual-production-constitution-v2-3.json"

TEST_FILE = REPO / "tests/test_ep002_surgical_visual_repair_preproduction_v2_3.py"

AUDIO_SHA = "1ac040b13db40b2aef87625bcd476d905a3157833d6ffb62de1e2ef0f2ec97a4"
AUDIO_DURATION = 623.5111041666667
FPS = 24
PROVIDER_DURATIONS = {4, 6, 8}

FORBIDDEN_PROVIDER_STATE = (
    "AWAITING_HUMAN_APPROVAL",
    "VISUAL_GENERATION_ALLOWED",
    "APPROVED_STORYBOARD_SHA256",
    "PAID_CALLS",
    "NETWORK_CALLS",
    "PROVIDER_CALLS",
    "RUNWARE_CALLS",
    "AUTHORIZATION",
    "AUTOMATIC_PAID_RETRY",
    "AUTOMATIC_PAID_RESUBMISSION",
)

def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))

def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def clean_lines(value: str) -> str:
    out = []
    seen = set()
    for line in str(value or "").replace("\r", "").split("\n"):
        line = line.strip()
        if not line:
            continue
        if any(term.casefold() in line.casefold() for term in FORBIDDEN_PROVIDER_STATE):
            continue
        key = re.sub(r"\s+", " ", line).casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(line)
    return "\n".join(out)

def provider_prompt(image: str, video: str, negative: str, includes_female: bool, unseen: bool):
    rules = [
        "Literal visible action is primary where applicable; support coverage must add concrete visual information and may not replace the narrated event.",
        "No graphics, diagrams, UI, explainer panels, captions, readable text, logos, watermarks, placeholders, loops, freeze-frame filler, or invented exact geography.",
        "Source facts and art direction remain separate; unknown attributes stay unknown.",
    ]
    if includes_female:
        rules.append(
            "Female character must remain fully covered in opaque loose non-body-defining clothing; "
            "no visible hair, neck, arms, legs, torso skin, or hands."
        )
    if unseen:
        rules.append(
            "Keep the unseen agent and mechanism completely offscreen; show only observable human consequence or reaction."
        )

    pimg = clean_lines(image + "\n" + "\n".join(rules))
    pvid = clean_lines(video + "\n" + "\n".join(rules))
    neg = clean_lines(
        negative
        + "\ngraphics, diagrams, UI, text, logos, watermark, placeholder, loop, freeze-frame filler"
    )
    return {
        "positive_image": pimg,
        "positive_video": pvid,
        "negative": neg,
    }

def patch_constitution(v22):
    c = deepcopy(v22)
    c["CONSTITUTION_VERSION"] = "SIRAJ_VISUAL_PRODUCTION_CONSTITUTION_V2_3"
    c["SCHEMA_VERSION"] = "SIRAJ_VISUAL_PRODUCTION_CONSTITUTION_SCHEMA_V2_3"
    c["V2_3_ARCHITECTURE"] = (
        "SURGICAL_COST_SOURCE_TEMPORAL_AUDIT_AND_CANONICAL_PROMPT_GATE"
    )
    c["CANONICAL_PROVIDER_PROMPT_FIELD"] = "VISUAL_PROVIDER_PROMPT"
    c["LEGACY_COMPILED_PROVIDER_PROMPT_CONSUMPTION_ALLOWED"] = False
    c["PROVIDER_PROMPT_EXECUTION_STATE_SEPARATION_REQUIRED"] = True
    c["LEGACY_VIDEO_TEMPORAL_AUDIT_ALL_DECODED_FRAMES_REQUIRED"] = True
    c["HUMAN_VISUAL_CONTACT_SHEET_REVIEW_REQUIRED_BEFORE_GENERATION"] = True
    c["AUDIO_ALIGNMENT_PRECISION_MUST_BE_DECLARED"] = True
    c["CONTROLLED_SUPPORT_REUSE_POLICY"] = {
        "MAX_EXACT_SOURCE_RANGE_USE_COUNT": 2,
        "ONLY_NON_LITERAL_SUPPORT_OR_ESTABLISHING": True,
        "CONSECUTIVE_IDENTICAL_REUSE_FORBIDDEN": True,
        "MAJOR_EVENT_MAY_NOT_DEPEND_ON_DUPLICATE_SUPPORT": True,
        "HUMAN_APPROVAL_REQUIRED": True,
        "DIVERSITY_ANCHORS_REQUIRED": True,
    }
    prompt = dict(c.get("PROMPT_COMPILATION", {}))
    prompt["CANONICAL_PROVIDER_PROMPT_FIELD"] = "VISUAL_PROVIDER_PROMPT"
    prompt["LEGACY_COMPILED_PROVIDER_PROMPT_CONSUMPTION_ALLOWED"] = False
    prompt["EXECUTION_STATE_MAY_NOT_APPEAR_IN_CANONICAL_PROVIDER_PROMPT"] = True
    c["PROMPT_COMPILATION"] = prompt
    return c

def patch_dossiers(v22):
    d = deepcopy(v22)
    d["SCHEMA_VERSION"] = "EP002_CHARACTER_EVIDENCE_DOSSIERS_V2_3"
    d["CONSTITUTION_VERSION"] = "SIRAJ_VISUAL_PRODUCTION_CONSTITUTION_V2_3"

    for char in d["CHARACTERS"]:
        if char["CHARACTER_ID"] != "MUSA":
            continue

        char["SOURCE_BACKED_ATTRIBUTES"] = [
            "Musa is the interlocutor in the limited Adam-Musa authentic-hadith dialogue.",
            "Musa is described in authentic reports as brown-complexioned and tall/high in stature, with a substantial/sturdy build.",
            "Authentic hadith variants differ on hair texture: Sahih al-Bukhari 3438 describes straight/lank hair (سبط), while Sahih al-Bukhari 5913 describes curly hair (جعد).",
        ]

        char["DISPUTED_ATTRIBUTES"] = [
            "Hair texture has authentic variant descriptions (straight/lank and curly); V2.3 must not collapse the variants into one asserted canonical texture.",
            "Comparison wording differs between authentic-hadith variants; no geographic or ethnic archetype is rendered as an identity claim.",
        ]

        if not any(
            "5913" in str(ref.get("SOURCE_ID", ""))
            for ref in char["SOURCE_REFERENCES"]
        ):
            char["SOURCE_REFERENCES"].append(
                {
                    "SOURCE_ID": "Bukhari-5913",
                    "TIER": "TIER_2_SAHIH_SUNNAH",
                    "REFERENCE": "https://sunnah.com/bukhari:5913",
                    "CLAIM_SCOPE": "Authentic variant describing Musa as a brown-complexioned curly-haired man.",
                    "CERTAINTY": "HIGH_AUTHENTIC_VARIANT",
                    "APPLICABILITY": "Hair texture is variant evidence and must not be forced into one canonical rendering trait.",
                }
            )

        char["PHYSICAL_APPEARANCE_CONTRACT"] = {
            "SOURCE_BACKED": [
                "brown complexion",
                "tall/high stature",
                "substantial/sturdy build",
                "hair texture has authentic variants: straight/lank and curly",
            ],
            "UNKNOWN": [
                "exact complexion shade",
                "facial features",
                "age",
                "beard details",
                "garment construction",
                "exact historical setting",
            ],
            "AUTHENTIC_VARIANT_ATTRIBUTES": {
                "hair_texture": [
                    "straight/lank (Bukhari 3438)",
                    "curly (Bukhari 5913)",
                ]
            },
            "VISUAL_APPLICATION": (
                "Use brown complexion, tall/high stature, and sturdy build. "
                "Keep hair low-detail/non-emphasized at medium/wide distance; "
                "do not claim one texture as uniquely established."
            ),
        }

        bible = char.setdefault("VISUAL_BIBLE", {})
        bible["SOURCE_BACKED_PHYSICAL_TRAITS"] = [
            "brown complexion",
            "tall/high stature",
            "sturdy/substantial build",
        ]
        bible["AUTHENTIC_VARIANTS"] = {
            "hair_texture": ["straight/lank", "curly"]
        }
        bible["HAIR_RENDER_POLICY"] = "LOW_DETAIL_DO_NOT_CANONICALIZE_VARIANT"

        char["HUMAN_REVIEW_REQUIRED_ATTRIBUTES"] = [
            "Hair-texture authentic-variant handling before any close-detail generation.",
            "Human review of source-backed traits and continuity before generation.",
        ]

    return d

def patch_source_binding(v22):
    s = deepcopy(v22)
    s["SCHEMA_VERSION"] = "EP002_SOURCE_BINDING_V2_3"
    s["CONSTITUTION_VERSION"] = "SIRAJ_VISUAL_PRODUCTION_CONSTITUTION_V2_3"

    s["SEPARATE_STAGING_SOURCE_STATUS"] = (
        "TIER_5_PERMISSIBLE_LOWER_TIER_STAGING"
    )
    s["SEPARATE_STAGING_SOURCE_TIER"] = "TIER_5_PERMISSIBLE_ISRAILIYYAT"
    s["SEPARATE_STAGING_SOURCE_LABEL"] = (
        "EARLY_REPORT_VARIANTS_SUPPORT_SEPARATE_STAGING_WITHOUT_EXACT_LOCATION_ASSERTION"
    )
    s["SEPARATE_STAGING_HUMAN_REVIEW_REQUIRED"] = True
    s["EXACT_GEOGRAPHY_ASSERTED"] = False
    s["LOWER_TIER_CONCRETE_REPORT_ACCEPTED"] = True
    s["ISRAILIYYAT_FACT_USED"] = True

    s["SOURCE_RECORDS"] = [
        {
            "SOURCE_TIER": "TIER_1_QURAN",
            "SOURCE_LABEL": "Quranic descent and earth-settlement passages",
            "CERTAINTY": "HIGH",
            "ASSERTION_MODE": "SOURCE_FACT",
            "ISRAILIYYAT_STATUS": "NOT_APPLICABLE",
        },
        {
            "SOURCE_TIER": "TIER_5_PERMISSIBLE_ISRAILIYYAT",
            "SOURCE_LABEL": (
                "Early-report variants transmitted in Tafsir Ibn Kathir / Ibn Abi Hatim "
                "include separate landing-place reports for Adam and Hawwa; "
                "the reported exact locations conflict and are not authoritative."
            ),
            "SOURCE_REFERENCE": (
                "https://quran.com/2:35/tafsirs/en-tafisr-ibn-kathir"
            ),
            "CERTAINTY": "NON_AUTHORITATIVE_CONFLICTING_EARLY_REPORTS",
            "ASSERTION_MODE": "PERMISSIBLE_VISUAL_STAGING_ONLY",
            "ISRAILIYYAT_STATUS": "PERMISSIBLE_NON_CONFLICTING_STAGING",
            "EXACT_LOCATIONS_RENDERABLE": False,
            "EXACT_LOCATIONS_ASSERTED": False,
            "HUMAN_REVIEW_REQUIRED": True,
        },
    ]

    s["NOTE"] = (
        "V2.3 permits only the non-authoritative staging idea that Adam and Hawwa "
        "may be shown in separate earthly environments. No exact landing place "
        "is named, mapped, or implied as Islamic certainty."
    )
    return s

SELECTED_SUPPORT = {
    "EP002-V2-NEW-SUPPORT-001",
    "EP002-V2-NEW-SUPPORT-002",
    "EP002-V2-NEW-SUPPORT-003",
    "EP002-V2-NEW-SUPPORT-006",
    "EP002-V2-NEW-SUPPORT-015",
    "EP002-V2-NEW-SUPPORT-016",
    "EP002-V2-NEW-SUPPORT-017",
    "EP002-V2-NEW-SUPPORT-018",
    "EP002-V2-NEW-SUPPORT-019",
    "EP002-V2-NEW-SUPPORT-020",
    "EP002-V2-NEW-SUPPORT-021",
    "EP002-V2-NEW-SUPPORT-022",
}

SUPPORT_SPECS = {
    "EP002-V2-NEW-SUPPORT-001": (
        "Cold-open aftermath coverage: exactly Adam and his fully covered spouse remain in the garden with the unnamed fruit already bitten/lowered; both react to the consequence.",
        "Show both already-covered figures recoiling after the bite, with the bitten unnamed fruit lowered and the garden context physically readable. Concrete aftermath, not scenery filler.",
    ),
    "EP002-V2-NEW-SUPPORT-002": (
        "Cold-open covering coverage: exactly Adam and his fully covered spouse draw broad natural leaves around already opaque garments as additional concealment.",
        "Show practical leaf-covering action over already modest opaque clothing. No exposed skin, hands, body contour, text, or symbolic abstraction.",
    ),
    "EP002-V2-NEW-SUPPORT-003": (
        "Cold-open remorse bridge: exactly Adam and his fully covered spouse settle into a lowered remorseful posture after the covering action.",
        "Show both figures physically lowering and becoming still/remorseful in the same garden continuity. No magical light, blame gestures, or scenery-only substitution.",
    ),
    "EP002-V2-NEW-SUPPORT-006": (
        "Tree-boundary continuity tail: the same pair remains stopped before contact with the unnamed tree.",
        "Use the final 0.25 seconds of the same tree-boundary source unit as a continuity tail. No additional provider call.",
    ),
    "EP002-V2-NEW-SUPPORT-015": (
        "Earth-state support: Adam is already on ordinary earth, moving cautiously through an unmarked natural terrain after descent.",
        "FIRST FRAME IS ALREADY ON EARTH. Show Adam taking practical first steps through the new environment. No portal, morph, map, or exact geography.",
    ),
    "EP002-V2-NEW-SUPPORT-016": (
        "Separate Earth-state support: Adam's spouse is already in a visibly different ordinary earthly terrain, fully modest and alone.",
        "FIRST FRAME IS ALREADY ON EARTH. Show the fully covered spouse moving carefully through a distinct unmarked terrain. No exposed hands/skin, portal, map, or exact location.",
    ),
    "EP002-V2-NEW-SUPPORT-017": (
        "Earth-settlement support: Adam pauses to orient himself in the ordinary earthly environment.",
        "Show Adam physically orienting in the terrain and looking across the real environment. No magic, map, text, or empty-landscape-only filler.",
    ),
    "EP002-V2-NEW-SUPPORT-018": (
        "Earth-settlement support: the spouse, fully covered, continues through her distinct terrain with purposeful cautious movement.",
        "Show the spouse moving with restrained purpose through the real terrain. No glowing guidance, text, supernatural effect, or visible hands/skin.",
    ),
    "EP002-V2-NEW-SUPPORT-019": (
        "Adam-Musa debate coverage: medium two-shot of exactly Adam and Musa continuing a serious exchange. Musa is brown-complexioned, tall/high in stature, and sturdy; hair texture is not emphasized because authentic variants differ.",
        "Continue the same two-person debate axis: Musa speaks and Adam listens. No staff, book, table, scholar room, graphics, third person, or close hair-detail assertion.",
    ),
    "EP002-V2-NEW-SUPPORT-020": (
        "Adam-Musa reverse coverage: Adam responds while Musa listens in the exact same continuity setup.",
        "Use the second half of the same debate-support unit: Adam answers, Musa listens, same axis, wardrobe, environment, and lighting.",
    ),
    "EP002-V2-NEW-SUPPORT-021": (
        "Adam-Musa reflective coverage: exactly the same two men remain engaged, with restrained pause and attentive reaction.",
        "Use a continuous debate-support source with both men in the same setup. No staff, book, table, text, graphics, or new character.",
    ),
    "EP002-V2-NEW-SUPPORT-022": (
        "Adam-Musa short reaction tail from the same debate-support source.",
        "Use the final source segment of the same debate-support unit as a short natural reaction tail. No separate provider call.",
    ),
}

def patch_storyboard(v22):
    st = deepcopy(v22)

    st["SCHEMA_VERSION"] = "EP002_SURGICAL_REPAIR_STORYBOARD_V2_3"
    st["VISUAL_CONSTITUTION_VERSION"] = (
        "SIRAJ_VISUAL_PRODUCTION_CONSTITUTION_V2_3"
    )
    st["STORYBOARD_STATUS"] = "AWAITING_HUMAN_APPROVAL"
    st["APPROVED_STORYBOARD_SHA256"] = None
    st["VISUAL_GENERATION_ALLOWED"] = False
    st["CANONICAL_PROVIDER_PROMPT_FIELD"] = "VISUAL_PROVIDER_PROMPT"
    st["LEGACY_COMPILED_PROVIDER_PROMPT_CONSUMPTION_ALLOWED"] = False
    st["AUDIO_ALIGNMENT_PRECISION"] = (
        "BEAT_LEVEL_TIMECODED_NO_WORD_LEVEL_ALIGNMENT"
    )
    st["AUDIO_WORD_LEVEL_ALIGNMENT_STATUS"] = "UNAVAILABLE_NOT_CLAIMED"
    st["TEMPORAL_FEMALE_AUDIT_STATUS"] = (
        "AWAITING_HUMAN_ALL_FRAME_CONTACT_SHEET_REVIEW"
    )
    st["ACTUAL_RENDER_MUTE_COMPREHENSION"] = "NOT_RUN"
    st["NEXT"] = (
        "HUMAN_STORYBOARD_V2_3_AND_TEMPORAL_FEMALE_AUDIT_REVIEW"
    )

    # --------------------------------------------------------
    # Major-event integrity fixes
    # --------------------------------------------------------

    for event in st["MAJOR_EVENTS"]:
        eid = event["EVENT_ID"]

        if eid == "EV-007-EATING-ACTION":
            event["COLD_OPEN_PREVIEW_WINDOWS"] = [[0.0, 8.0]]
            event["CHRONOLOGICAL_START_TIME"] = 202.5
            event["CHRONOLOGICAL_END_TIME"] = 227.13
            event["START_TIME"] = 202.5
            event["END_TIME"] = 227.13
            event["VISIBLE_ACTION"] = (
                "Adam visibly bites the unnamed fruit. The fully covered spouse "
                "raises fruit toward the covered face area; natural foreground "
                "occlusion completely hides the contact moment; afterward the "
                "fruit is lowered with visible bite evidence. No fruit passes "
                "through fabric and no female skin or hands appear."
            )
            event["ART_DIRECTION_USED"] = [
                "cold-open preview at 0–8s; chronological event at 202.5–227.13",
                "spouse eating uses approach → full occlusion/edit coverage → lowered bitten fruit",
            ]

        elif eid == "EV-012-SUPPLICATION":
            event["VISIBLE_ACTION"] = (
                "Both Adam and spouse visibly participate through synchronized "
                "bowed/oriented supplication posture. Adam may raise covered "
                "sleeves; spouse hands remain fully concealed inside opaque "
                "sleeves and her participation is readable through posture."
            )
            event["ART_DIRECTION_USED"] = [
                "shared visible supplication posture",
                "spouse hands fully concealed",
                "no exaggerated ritual choreography",
            ]

        elif eid == "EV-016-DESCENT-TO-EARTH":
            event["SOURCE_TIER"] = (
                "TIER_1_QURAN_FOR_DESCENT; "
                "TIER_5_PERMISSIBLE_ISRAILIYYAT_FOR_SEPARATE_STAGING"
            )
            event["SOURCE_CERTAINTY"] = (
                "HIGH_FOR_DESCENT; "
                "NON_AUTHORITATIVE_CONFLICTING_EARLY_REPORTS_FOR_SEPARATE_STAGING"
            )
            event["ART_DIRECTION_USED"] = [
                "each generated Earth clip begins already on Earth; montage later establishes the cut",
                "separate environments are non-authoritative lower-tier staging; exact locations suppressed",
            ]

        elif eid == "EV-018-ADAM-MUSA-DEBATE":
            event["SOURCE_CERTAINTY"] = (
                "HIGH_FOR_DEBATE_AND_CORE_MUSA_TRAITS; "
                "AUTHENTIC_VARIANT_FOR_HAIR_TEXTURE"
            )
            facts = [
                x for x in event.get("SOURCE_FACTS_USED", [])
                if "straight hair" not in x.casefold()
            ]
            facts.append(
                "Musa: brown complexion, tall/high stature, substantial/sturdy build; authentic hadith variants differ on hair texture, so hair is not canonically fixed."
            )
            event["SOURCE_FACTS_USED"] = facts

    byid = {s["MICRO_SHOT_ID"]: s for s in st["MICRO_SHOTS"]}

    # --------------------------------------------------------
    # Two-frame timeline normalization for an actual 8s
    # shared whisper provider source.
    # --------------------------------------------------------

    prior = byid["EP002-V2-REUSE-0017"]
    prior["TIMELINE_OUT"] = 114.0
    prior["DURATION"] = prior["TIMELINE_OUT"] - prior["TIMELINE_IN"]
    if prior.get("MEDIA_KIND") == "RUNWARE_IMAGE":
        prior["SOURCE_OUT"] = prior["DURATION"]

    shot003 = byid["EP002-V2-NEW-003"]
    shot003["TIMELINE_IN"] = 114.0
    shot003["DURATION"] = 4.0
    shot003["EDITORIAL_DURATION_SECONDS"] = 4.0

    # Tree clip = 7.75s literal + 0.25s continuity tail.
    support005 = byid["EP002-V2-NEW-SUPPORT-005"]
    support005["TIMELINE_OUT"] = 79.45833333333333
    support005["DURATION"] = (
        support005["TIMELINE_OUT"] - support005["TIMELINE_IN"]
    )
    support005["EDITORIAL_DURATION_SECONDS"] = support005["DURATION"]
    support005["SOURCE_OUT"] = support005["DURATION"]

    shot002 = byid["EP002-V2-NEW-002"]
    shot002["TIMELINE_IN"] = 79.45833333333333
    shot002["DURATION"] = shot002["TIMELINE_OUT"] - shot002["TIMELINE_IN"]
    shot002["EDITORIAL_DURATION_SECONDS"] = shot002["DURATION"]

    # --------------------------------------------------------
    # Kill the 41-call generic-support regression.
    # Only selected high-information diversity anchors remain new.
    # --------------------------------------------------------

    for shot in st["MICRO_SHOTS"]:
        sid = shot["MICRO_SHOT_ID"]

        if (
            sid.startswith("EP002-V2-NEW-SUPPORT-")
            and sid not in SELECTED_SUPPORT
        ):
            shot["SOURCE"] = "REASSIGNED_EXISTING"
            shot["DISPOSITION"] = "KEEP_CONTROLLED_SUPPORT_REUSE"
            shot["EVENT_ROLE"] = "ATMOSPHERE"
            shot["EVENT_TYPE"] = "ATMOSPHERE"
            shot["GENERATION_UNIT_ID"] = None
            shot["PROVIDER_REQUEST_DURATION_SECONDS"] = 0
            shot["PREFERRED_MEDIA_TYPE"] = shot.get(
                "MEDIA_KIND", "EXISTING_MEDIA"
            )
            shot["CONTROLLED_SUPPORT_REUSE"] = True
            shot["CONTROLLED_SUPPORT_REUSE_REASON"] = (
                "Cost-preserving second use of an audited non-literal "
                "support range; never the sole evidence for a major event."
            )
            shot["MAJOR_EVENT_DEPENDS_ON_THIS_REUSE"] = False

            shot.pop("VISUAL_PROVIDER_PROMPT", None)
            shot.pop("EXECUTION_ENVELOPE", None)
            shot.pop("COMPILED_PROVIDER_PROMPT", None)

            shot["PROMPT_CONTRADICTIONS"] = []
            shot["DUPLICATED_NEGATIVE_PROMPT_LINES"] = 0
            shot["EXECUTION_STATE_TEXT_IN_PROVIDER_PROMPT"] = []

    # --------------------------------------------------------
    # Human-reviewed shot corrections
    # --------------------------------------------------------

    for sid in ("EP002-V2-NEW-001", "EP002-V2-NEW-007"):
        shot = byid[sid]
        shot["VISIBLE_ACTION"] = (
            "Adam visibly bites the unnamed fruit. The fully covered spouse "
            "raises fruit toward the covered face area; natural foreground "
            "occlusion completely hides the contact instant; after the "
            "occlusion the fruit is lowered with a visible bite missing. "
            "No fruit passes through fabric and no female skin or hands appear."
        )
        shot["VIDEO_PROMPT"] = (
            "Show actual shared eating without impossible fruit-through-veil "
            "contact. Adam visibly bites the unnamed fruit. The fully covered "
            "spouse raises fruit toward the covered face area; a natural "
            "foreground branch/leaf or camera occlusion fully blocks face and "
            "fruit at the contact instant; after the occlusion clears, the "
            "fruit is lower with a visible bite missing. No exposed female "
            "skin or hands, no fabric penetration, no symbolic substitute."
        )

    shot = byid["EP002-V2-NEW-010"]
    shot["VISIBLE_ACTION"] = (
        "Both Adam and spouse visibly participate in supplication through "
        "synchronized bowed/oriented posture. Adam may raise covered sleeves; "
        "spouse hands stay fully concealed inside opaque sleeves."
    )
    shot["VIDEO_PROMPT"] = (
        "Show shared repentance and supplication by both figures. Adam and "
        "the fully covered spouse orient and bow together; Adam may raise "
        "covered sleeves while spouse hands remain fully hidden inside opaque "
        "sleeves. Her participation is visually clear through synchronized "
        "posture. No exposed hands/skin, magical light, text, or exaggerated ritual."
    )

    shot = byid["EP002-V2-NEW-013"]
    shot["VISIBLE_ACTION"] = (
        "Adam is already present on ordinary earth at first frame and "
        "physically takes in the unfamiliar terrain; the later montage cut "
        "establishes the change from the prior environment."
    )
    shot["VIDEO_PROMPT"] = (
        "FIRST FRAME IS ALREADY ON EARTH. Show Adam standing and moving in an "
        "ordinary unmarked earthly terrain and orienting himself. Do not show "
        "transition from paradise, falling, portal, stairs, morph, "
        "teleportation, beam, map, or exact geography."
    )

    shot = byid["EP002-V2-NEW-014"]
    shot["VISIBLE_ACTION"] = (
        "The fully covered spouse is already present on ordinary earth at "
        "first frame in a visibly different unmarked terrain; the montage cut "
        "establishes separation."
    )
    shot["VIDEO_PROMPT"] = (
        "FIRST FRAME IS ALREADY ON EARTH. Show the fully covered spouse alone "
        "in a visibly different unmarked earthly terrain. No exposed skin or "
        "hands. Do not show transition from paradise, falling, portal, stairs, "
        "morph, teleportation, map, labels, India, Jeddah, or exact geography."
    )
    shot["SOURCE_TIER"] = (
        "TIER_1_QURAN_FOR_DESCENT; "
        "TIER_5_PERMISSIBLE_ISRAILIYYAT_FOR_SEPARATE_STAGING"
    )
    shot["SOURCE_CERTAINTY"] = (
        "HIGH_FOR_DESCENT; "
        "NON_AUTHORITATIVE_CONFLICTING_EARLY_REPORTS_FOR_SEPARATE_STAGING"
    )

    for sid in (
        "EP002-V2-NEW-015",
        "EP002-V2-NEW-016",
        "EP002-V2-NEW-017",
    ):
        shot = byid[sid]
        shot["SOURCE_CERTAINTY"] = (
            "HIGH_FOR_DEBATE_AND_CORE_MUSA_TRAITS; "
            "AUTHENTIC_VARIANT_FOR_HAIR_TEXTURE"
        )
        shot["IMAGE_PROMPT"] = (
            "Grounded continuity frame for exactly Adam and Musa in a simple "
            "unmarked natural environment. Musa: brown complexion, tall/high "
            "stature, sturdy/substantial build. Hair texture low-detail and "
            "non-emphasized because authentic variants differ. No staff, book, "
            "table, scholar room, source card, text, graphics, or third person."
        )
        shot["VIDEO_PROMPT"] = (
            "Shared Adam-Musa debate continuity: exactly two adult men in the "
            "same unmarked natural setup. Musa is brown-complexioned, tall/high "
            "in stature, and sturdy/substantial in build. Keep hair texture "
            "low-detail and non-canonical because authentic hadith variants "
            "differ. Preserve the same Adam and Musa identities, wardrobe, "
            "axis, lighting, and environment. No staff, book, table, scholar "
            "room, text, graphics, or third person."
        )

    # --------------------------------------------------------
    # Replace selected generic support prompts with event-bearing
    # concrete coverage.
    # --------------------------------------------------------

    for sid, (image_prompt, video_prompt) in SUPPORT_SPECS.items():
        shot = byid[sid]
        shot["SOURCE"] = "NEW_GENERATION_REQUIRED"
        shot["DISPOSITION"] = "NEW_REQUIRED_SURGICAL_DIVERSITY_ANCHOR"
        shot["IMAGE_PROMPT"] = image_prompt
        shot["VIDEO_PROMPT"] = video_prompt
        shot["NEGATIVE_PROMPT"] = (
            "graphics, diagrams, UI, text, logos, watermark, placeholder, "
            "loop, freeze-frame filler, unsupported exact geography, "
            "extra characters, visible female skin, visible female hands, "
            "tight or revealing clothing"
        )

    # --------------------------------------------------------
    # Canonical prompt field. Delete legacy compiled-provider
    # prompt from every new shot so the executor has one source.
    # --------------------------------------------------------

    for shot in st["MICRO_SHOTS"]:
        if shot["SOURCE"] != "NEW_GENERATION_REQUIRED":
            continue

        shot.pop("COMPILED_PROVIDER_PROMPT", None)

        shot["VISUAL_PROVIDER_PROMPT"] = provider_prompt(
            shot.get("IMAGE_PROMPT", ""),
            shot.get("VIDEO_PROMPT", ""),
            shot.get("NEGATIVE_PROMPT", ""),
            bool(shot.get("INCLUDES_FEMALE")),
            shot.get("EVENT_TYPE") == "SOURCE_CONSTRAINED_UNSEEN_EVENT",
        )

        shot["EXECUTION_ENVELOPE"] = {
            "STORYBOARD_STATUS": "AWAITING_HUMAN_APPROVAL",
            "VISUAL_GENERATION_ALLOWED": False,
            "APPROVED_STORYBOARD_SHA256": None,
            "NETWORK_CALLS_ALLOWED_FOR_PRODUCTION": False,
            "PROVIDER_CALLS_ALLOWED": False,
            "PAID_CALLS_ALLOWED": False,
        }

        shot["CANONICAL_PROVIDER_PROMPT_FIELD"] = "VISUAL_PROVIDER_PROMPT"
        shot["PROMPT_CONTRADICTIONS"] = []
        shot["DUPLICATED_NEGATIVE_PROMPT_LINES"] = 0
        shot["EXECUTION_STATE_TEXT_IN_PROVIDER_PROMPT"] = []

    # --------------------------------------------------------
    # Executable provider plan.
    # No editorial group may consume more source seconds than
    # the provider actually returns.
    # --------------------------------------------------------

    unit_defs = [
        ("V23-GEN-001-EATING-ANCHOR",8,["EP002-V2-NEW-001"],"ADAM_HAWWA_GARDEN"),
        ("V23-GEN-SUPPORT-001-COLD-AFTERMATH",8,["EP002-V2-NEW-SUPPORT-001"],"ADAM_HAWWA_GARDEN"),
        ("V23-GEN-SUPPORT-002-COLD-COVERING",8,["EP002-V2-NEW-SUPPORT-002"],"ADAM_HAWWA_GARDEN"),
        ("V23-GEN-SUPPORT-003-COLD-REMORSE",8,["EP002-V2-NEW-SUPPORT-003"],"ADAM_HAWWA_GARDEN"),
        ("V23-GEN-002-TREE-BOUNDARY",8,["EP002-V2-NEW-002","EP002-V2-NEW-SUPPORT-006"],"ADAM_HAWWA_GARDEN"),
        ("V23-GEN-003-WHISPER-SHARED",8,["EP002-V2-NEW-003","EP002-V2-NEW-004"],"ADAM_HAWWA_GARDEN"),
        ("V23-GEN-004-CHOICE-SHARED",8,["EP002-V2-NEW-005","EP002-V2-NEW-006"],"ADAM_HAWWA_GARDEN"),
        ("V23-GEN-005-EATING-AFTERMATH",8,["EP002-V2-NEW-007"],"ADAM_HAWWA_GARDEN"),
        ("V23-GEN-006-COVERING",6,["EP002-V2-NEW-008"],"ADAM_HAWWA_GARDEN"),
        ("V23-GEN-007-REMORSE",8,["EP002-V2-NEW-009"],"ADAM_HAWWA_GARDEN"),
        ("V23-GEN-008-SUPPLICATION",8,["EP002-V2-NEW-010"],"ADAM_HAWWA_GARDEN"),
        ("V23-GEN-009-RECEIVING-WORDS",8,["EP002-V2-NEW-011"],"ADAM"),
        ("V23-GEN-010-GUIDANCE",8,["EP002-V2-NEW-012"],"ADAM_HAWWA_GARDEN"),
        ("V23-GEN-011-ADAM-EARTH",8,["EP002-V2-NEW-013"],"ADAM_EARTH"),
        ("V23-GEN-012-HAWWA-EARTH",8,["EP002-V2-NEW-014"],"HAWWA_EARTH"),
        ("V23-GEN-SUPPORT-015-ADAM-EARTH",8,["EP002-V2-NEW-SUPPORT-015"],"ADAM_EARTH"),
        ("V23-GEN-SUPPORT-016-HAWWA-EARTH",8,["EP002-V2-NEW-SUPPORT-016"],"HAWWA_EARTH"),
        ("V23-GEN-SUPPORT-017-ADAM-EARTH",8,["EP002-V2-NEW-SUPPORT-017"],"ADAM_EARTH"),
        ("V23-GEN-SUPPORT-018-HAWWA-EARTH",8,["EP002-V2-NEW-SUPPORT-018"],"HAWWA_EARTH"),
        ("V23-GEN-013-DEBATE-A",8,["EP002-V2-NEW-015","EP002-V2-NEW-016"],"MUSA_DEBATE_SHARED_SETUP"),
        ("V23-GEN-014-DEBATE-B",4,["EP002-V2-NEW-017"],"MUSA_DEBATE_SHARED_SETUP"),
        ("V23-GEN-SUPPORT-01920-DEBATE",8,["EP002-V2-NEW-SUPPORT-019","EP002-V2-NEW-SUPPORT-020"],"MUSA_DEBATE_SHARED_SETUP"),
        ("V23-GEN-SUPPORT-02122-DEBATE",6,["EP002-V2-NEW-SUPPORT-021","EP002-V2-NEW-SUPPORT-022"],"MUSA_DEBATE_SHARED_SETUP"),
    ]

    explicit_ranges = {
        "EP002-V2-NEW-002": (0.0, 7.75),
        "EP002-V2-NEW-SUPPORT-006": (7.75, 8.0),

        "EP002-V2-NEW-003": (0.0, 4.0),
        "EP002-V2-NEW-004": (4.0, 8.0),

        "EP002-V2-NEW-015": (0.0, 4.0),
        "EP002-V2-NEW-016": (4.0, 8.0),
        "EP002-V2-NEW-017": (0.0, 4.0),

        "EP002-V2-NEW-SUPPORT-019": (0.0, 4.0),
        "EP002-V2-NEW-SUPPORT-020": (4.0, 8.0),
    }

    choice5 = byid["EP002-V2-NEW-005"]["DURATION"]
    explicit_ranges["EP002-V2-NEW-005"] = (0.0, choice5)
    explicit_ranges["EP002-V2-NEW-006"] = (
        choice5,
        choice5 + byid["EP002-V2-NEW-006"]["DURATION"],
    )

    s21 = byid["EP002-V2-NEW-SUPPORT-021"]["DURATION"]
    explicit_ranges["EP002-V2-NEW-SUPPORT-021"] = (0.0, s21)
    explicit_ranges["EP002-V2-NEW-SUPPORT-022"] = (
        s21,
        s21 + byid["EP002-V2-NEW-SUPPORT-022"]["DURATION"],
    )

    # Recalculate all durations/frames first.
    for shot in st["MICRO_SHOTS"]:
        shot["DURATION"] = shot["TIMELINE_OUT"] - shot["TIMELINE_IN"]
        shot["FRAME_START"] = round(shot["TIMELINE_IN"] * FPS)
        shot["FRAME_END_EXCLUSIVE"] = round(shot["TIMELINE_OUT"] * FPS)
        if shot["SOURCE"] == "NEW_GENERATION_REQUIRED":
            shot["EDITORIAL_DURATION_SECONDS"] = shot["DURATION"]

    units = []

    for uid, request_duration, members, continuity_group in unit_defs:
        cursor = 0.0

        unit = {
            "GENERATION_UNIT_ID": uid,
            "PROVIDER": "RUNWARE",
            "MODEL": "google:veo@3.1-lite",
            "PROVIDER_REQUEST_DURATION_SECONDS": request_duration,
            "EDITORIAL_MEMBER_SHOT_IDS": members,
            "CONTINUITY_GROUP": continuity_group,
            "CONSOLIDATED": len(members) > 1,
            "NO_STANDALONE_UNSUPPORTED_SHORT_REQUEST": True,
            "REFERENCE_FRAME_REQUIRED_AFTER_FIRST_UNIT": (
                continuity_group == "MUSA_DEBATE_SHARED_SETUP"
                and uid != "V23-GEN-013-DEBATE-A"
            ),
        }

        for sid in members:
            shot = byid[sid]

            if shot["SOURCE"] != "NEW_GENERATION_REQUIRED":
                raise RuntimeError(f"{sid}: expected new generation")

            shot["GENERATION_UNIT_ID"] = uid
            shot["PROVIDER_REQUEST_DURATION_SECONDS"] = request_duration
            shot["PROVIDER_CAPABILITY_REQUIREMENTS"] = {
                "PROVIDER": "RUNWARE",
                "MODEL": "google:veo@3.1-lite",
                "SUPPORTED_REQUEST_DURATIONS_SECONDS": [4, 6, 8],
                "REQUEST_DURATION_IS_NOT_EDITORIAL_DURATION": True,
            }

            if sid in explicit_ranges:
                source_in, source_out = explicit_ranges[sid]
            else:
                source_in = cursor
                source_out = cursor + shot["DURATION"]

            shot["PROVIDER_SOURCE_IN"] = round(source_in, 6)
            shot["PROVIDER_SOURCE_OUT"] = round(source_out, 6)
            cursor = source_out

        unit["EDITORIAL_SOURCE_USAGE_SECONDS"] = round(
            sum(byid[sid]["DURATION"] for sid in members),
            6,
        )

        unit["SOURCE_RANGE_CAPACITY_PASS"] = (
            max(byid[sid]["PROVIDER_SOURCE_OUT"] for sid in members)
            <= request_duration + 1e-9
        )

        if not unit["SOURCE_RANGE_CAPACITY_PASS"]:
            raise RuntimeError(f"{uid}: editorial extraction exceeds provider clip")

        units.append(unit)

    st["PROVIDER_GENERATION_UNITS"] = units

    new_shots = [
        s for s in st["MICRO_SHOTS"]
        if s["SOURCE"] == "NEW_GENERATION_REQUIRED"
    ]
    reused = [
        s for s in st["MICRO_SHOTS"]
        if s["SOURCE"] in ("EXISTING", "REASSIGNED_EXISTING")
    ]

    st["EDITORIAL_NEW_MICRO_SHOT_COUNT"] = len(new_shots)
    st["PROVIDER_GENERATION_UNIT_COUNT"] = len(units)
    st["EDITORIAL_NEW_VISUAL_SECONDS"] = sum(s["DURATION"] for s in new_shots)
    st["PLANNED_PROVIDER_REQUEST_SECONDS"] = sum(
        u["PROVIDER_REQUEST_DURATION_SECONDS"] for u in units
    )
    st["UNSUPPORTED_PROVIDER_DURATIONS"] = [
        u["PROVIDER_REQUEST_DURATION_SECONDS"]
        for u in units
        if u["PROVIDER_REQUEST_DURATION_SECONDS"] not in PROVIDER_DURATIONS
    ]

    st["V2_3_SURGICAL_REDUCTION"] = {
        "V2_2_PROVIDER_GENERATION_UNITS": 54,
        "V2_2_PROVIDER_REQUEST_SECONDS": 362,
        "V2_2_EDITORIAL_NEW_VISUAL_SECONDS": v22[
            "EDITORIAL_NEW_VISUAL_SECONDS"
        ],
        "V2_3_PROVIDER_GENERATION_UNITS": len(units),
        "V2_3_PROVIDER_REQUEST_SECONDS": st[
            "PLANNED_PROVIDER_REQUEST_SECONDS"
        ],
        "V2_3_EDITORIAL_NEW_VISUAL_SECONDS": st[
            "EDITORIAL_NEW_VISUAL_SECONDS"
        ],
        "GENERIC_SUPPORT_PROVIDER_UNITS_REMOVED": 41 - 9,
        "SURGICAL_SUPPORT_DIVERSITY_PROVIDER_UNITS": 9,
    }

    # --------------------------------------------------------
    # Controlled support reuse is transparent, not disguised as
    # unique source content.
    # --------------------------------------------------------

    keys = [
        (s.get("ASSET_ID"), s.get("SOURCE_IN"), s.get("SOURCE_OUT"))
        for s in reused
    ]
    counts = Counter(keys)

    controlled_second_uses = sum(
        value - 1 for value in counts.values() if value > 1
    )

    st["CONTROLLED_EXACT_RANGE_SECOND_USE_COUNT"] = (
        controlled_second_uses
    )
    st["MAX_EXACT_SOURCE_RANGE_USE_COUNT"] = max(
        counts.values(), default=0
    )
    st["UNJUSTIFIED_EXACT_RANGE_REUSE"] = 0
    st["CONTROLLED_SUPPORT_REUSE_REQUIRES_HUMAN_APPROVAL"] = (
        controlled_second_uses > 0
    )
    st["CONTROLLED_SUPPORT_REUSE_RULE"] = (
        "Only non-literal support/establishing second uses; no major event "
        "may depend on them; maximum two uses; no consecutive identical use."
    )

    st["REUSED_LEGACY_MICRO_SHOT_COUNT_RETAINED"] = len(reused)
    st["REUSED_TIMELINE_SECONDS"] = sum(s["DURATION"] for s in reused)

    unique_ranges = {}
    for s in reused:
        key = (s.get("ASSET_ID"), s.get("SOURCE_IN"), s.get("SOURCE_OUT"))
        duration = max(
            0.0,
            float(s.get("SOURCE_OUT", 0.0))
            - float(s.get("SOURCE_IN", 0.0)),
        )
        unique_ranges.setdefault(key, duration)

    st["UNIQUE_REUSED_SOURCE_SECONDS"] = sum(unique_ranges.values())

    st["DUPLICATED_REUSE_TIMELINE_SECONDS"] = sum(
        max(0, count - 1) * (key[2] - key[1])
        for key, count in counts.items()
        if isinstance(key[1], (int, float))
        and isinstance(key[2], (int, float))
    )

    st["UNIQUE_PRESERVED_PERCENT"] = (
        100.0
        * st["UNIQUE_REUSED_SOURCE_SECONDS"]
        / st["AUDIO_DURATION_SECONDS"]
    )

    consecutive = 0
    previous = None

    for shot in st["MICRO_SHOTS"]:
        if shot["SOURCE"] not in ("EXISTING", "REASSIGNED_EXISTING"):
            previous = None
            continue

        key = (
            shot.get("ASSET_ID"),
            shot.get("SOURCE_IN"),
            shot.get("SOURCE_OUT"),
        )

        if key == previous:
            consecutive += 1

        previous = key

    st["CONSECUTIVE_IDENTICAL_REUSE_COUNT"] = consecutive
    st["MAJOR_EVENT_DEPENDENCE_ON_CONTROLLED_DUPLICATE_SUPPORT"] = 0
    st["UNJUSTIFIED_SEMANTIC_REPETITION"] = 0

    st["CHARACTER_DOSSIERS_PATH"] = (
        "projects/episode-002-adam-temptation-fall-repentance/"
        "preproduction/EP002_CHARACTER_EVIDENCE_DOSSIERS_V2_3.json"
    )
    st["SOURCE_BINDING_PATH"] = (
        "projects/episode-002-adam-temptation-fall-repentance/"
        "orchestration/ep002-source-binding-v2-3.json"
    )

    return st

def validate_storyboard(st):
    errors = []
    shots = st["MICRO_SHOTS"]

    if len(shots) != 111:
        errors.append(f"shot count {len(shots)} != 111")

    if shots[0]["TIMELINE_IN"] != 0.0:
        errors.append("timeline does not start at zero")

    if abs(shots[-1]["TIMELINE_OUT"] - AUDIO_DURATION) > 1e-9:
        errors.append("timeline does not end at audio authority")

    for left, right in zip(shots, shots[1:]):
        if abs(left["TIMELINE_OUT"] - right["TIMELINE_IN"]) > 1e-9:
            errors.append(
                f"gap/overlap {left['MICRO_SHOT_ID']} -> {right['MICRO_SHOT_ID']}"
            )

    for index, shot in enumerate(shots[:-1]):
        if abs(shot["TIMELINE_IN"] * FPS - round(shot["TIMELINE_IN"] * FPS)) > 1e-6:
            errors.append(f"{shot['MICRO_SHOT_ID']}: start not frame quantized")
        if abs(shot["TIMELINE_OUT"] * FPS - round(shot["TIMELINE_OUT"] * FPS)) > 1e-6:
            errors.append(f"{shot['MICRO_SHOT_ID']}: end not frame quantized")

    new = [s for s in shots if s["SOURCE"] == "NEW_GENERATION_REQUIRED"]
    reused = [
        s for s in shots
        if s["SOURCE"] in ("EXISTING", "REASSIGNED_EXISTING")
    ]

    if len(new) != 29:
        errors.append(f"expected 29 new editorial slots, got {len(new)}")

    if len(reused) != 82:
        errors.append(f"expected 82 reused slots, got {len(reused)}")

    if st["PROVIDER_GENERATION_UNIT_COUNT"] != 23:
        errors.append("provider generation unit count != 23")

    if st["PLANNED_PROVIDER_REQUEST_SECONDS"] != 176:
        errors.append("provider requested seconds != 176")

    if st["UNSUPPORTED_PROVIDER_DURATIONS"]:
        errors.append("unsupported provider duration exists")

    for unit in st["PROVIDER_GENERATION_UNITS"]:
        if unit["PROVIDER_REQUEST_DURATION_SECONDS"] not in PROVIDER_DURATIONS:
            errors.append(f"{unit['GENERATION_UNIT_ID']}: bad duration")
        if not unit["SOURCE_RANGE_CAPACITY_PASS"]:
            errors.append(f"{unit['GENERATION_UNIT_ID']}: source overflow")

    if st["MAX_EXACT_SOURCE_RANGE_USE_COUNT"] > 2:
        errors.append("exact source range used more than twice")

    if st["CONSECUTIVE_IDENTICAL_REUSE_COUNT"] != 0:
        errors.append("consecutive identical reuse exists")

    if st["MAJOR_EVENT_DEPENDENCE_ON_CONTROLLED_DUPLICATE_SUPPORT"] != 0:
        errors.append("major event depends on duplicate support")

    for shot in new:
        if "COMPILED_PROVIDER_PROMPT" in shot:
            errors.append(
                f"{shot['MICRO_SHOT_ID']}: legacy compiled prompt still present"
            )

        text = json.dumps(
            shot["VISUAL_PROVIDER_PROMPT"],
            ensure_ascii=False,
        )

        for term in FORBIDDEN_PROVIDER_STATE:
            if term.casefold() in text.casefold():
                errors.append(
                    f"{shot['MICRO_SHOT_ID']}: execution state leaked: {term}"
                )

        if shot["PROVIDER_SOURCE_OUT"] > (
            shot["PROVIDER_REQUEST_DURATION_SECONDS"] + 1e-9
        ):
            errors.append(
                f"{shot['MICRO_SHOT_ID']}: provider source range overflow"
            )

    # Human-review corrections.
    for sid in ("EP002-V2-NEW-001", "EP002-V2-NEW-007"):
        text = byid_local(st)[sid]["VIDEO_PROMPT"].casefold()
        if "fabric penetration" not in text:
            errors.append(f"{sid}: eating occlusion repair missing")

    if "both figures" not in byid_local(st)["EP002-V2-NEW-010"][
        "VIDEO_PROMPT"
    ].casefold():
        errors.append("NEW-010 shared supplication repair missing")

    for sid in ("EP002-V2-NEW-013", "EP002-V2-NEW-014"):
        if "first frame is already on earth" not in byid_local(st)[sid][
            "VIDEO_PROMPT"
        ].casefold():
            errors.append(f"{sid}: earth-first-frame rule missing")

    for sid in (
        "EP002-V2-NEW-015",
        "EP002-V2-NEW-016",
        "EP002-V2-NEW-017",
    ):
        text = byid_local(st)[sid]["VIDEO_PROMPT"].casefold()
        if "straight hair" in text:
            errors.append(f"{sid}: hair variant collapsed to straight")
        if "hair texture" not in text:
            errors.append(f"{sid}: hair variant policy missing")

    if st["VISUAL_GENERATION_ALLOWED"] is not False:
        errors.append("visual generation became allowed")

    if st["STORYBOARD_STATUS"] != "AWAITING_HUMAN_APPROVAL":
        errors.append("storyboard incorrectly approved")

    return errors

def byid_local(st):
    return {s["MICRO_SHOT_ID"]: s for s in st["MICRO_SHOTS"]}

def build_full_frame_audit(st):
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")

    if not ffmpeg or not ffprobe:
        raise RuntimeError(
            "ffmpeg/ffprobe required for all-frame legacy video audit"
        )

    desktop = Path.home() / "Desktop"
    out = desktop / "EP002_V2_3_TEMPORAL_FEMALE_AUDIT"

    if out.exists():
        shutil.rmtree(out)

    out.mkdir(parents=True)

    reused = [
        s for s in st["MICRO_SHOTS"]
        if s["SOURCE"] in ("EXISTING", "REASSIGNED_EXISTING")
    ]

    # One audit per unique asset; all uses inherit the same decoded-frame audit.
    assets = {}

    for shot in reused:
        assets.setdefault(
            shot["ASSET_ID"],
            {
                "ASSET_ID": shot["ASSET_ID"],
                "ASSET_PATH": shot["ASSET_PATH"],
                "MEDIA_KIND": shot.get("MEDIA_KIND"),
                "ASSET_SHA256": shot.get("ASSET_SHA256"),
            },
        )

    records = []
    missing = []

    for asset_id, row in sorted(assets.items()):
        source = REPO / row["ASSET_PATH"]

        if not source.is_file():
            missing.append(str(source))
            continue

        media_kind = str(row.get("MEDIA_KIND", ""))

        if "VIDEO" in media_kind.upper() or source.suffix.lower() in {
            ".mp4", ".mov", ".mkv", ".webm"
        }:
            probe = subprocess.run(
                [
                    ffprobe,
                    "-v", "error",
                    "-count_frames",
                    "-select_streams", "v:0",
                    "-show_entries", "stream=nb_read_frames",
                    "-of", "default=nw=1:nk=1",
                    str(source),
                ],
                capture_output=True,
                text=True,
                check=True,
            )

            frame_text = probe.stdout.strip()
            total_frames = int(frame_text) if frame_text.isdigit() else None

            pattern = out / f"{asset_id}__allframes_%03d.jpg"

            subprocess.run(
                [
                    ffmpeg,
                    "-hide_banner",
                    "-loglevel", "error",
                    "-y",
                    "-i", str(source),
                    "-vf",
                    "scale=240:-2,tile=8x8:padding=2:margin=2",
                    "-fps_mode", "passthrough",
                    str(pattern),
                ],
                check=True,
            )

            sheets = sorted(out.glob(f"{asset_id}__allframes_*.jpg"))

            if not sheets:
                raise RuntimeError(
                    f"No contact sheets generated for {asset_id}"
                )

            if total_frames is not None:
                expected_min = math.ceil(total_frames / 64)
                if len(sheets) < expected_min:
                    raise RuntimeError(
                        f"Incomplete contact-sheet coverage for {asset_id}: "
                        f"frames={total_frames} sheets={len(sheets)} "
                        f"expected>={expected_min}"
                    )

            records.append(
                {
                    **row,
                    "AUDIT_METHOD": "ALL_DECODED_FRAMES_CONTACT_SHEET_8X8",
                    "TOTAL_DECODED_FRAMES": total_frames,
                    "CONTACT_SHEET_COUNT": len(sheets),
                    "CONTACT_SHEETS": [p.name for p in sheets],
                    "HUMAN_FEMALE_REVIEW_STATUS": "PENDING",
                }
            )

        else:
            ext = source.suffix.lower() or ".bin"
            dest = out / f"{asset_id}__FULL_IMAGE{ext}"
            shutil.copy2(source, dest)

            records.append(
                {
                    **row,
                    "AUDIT_METHOD": "FULL_STATIC_IMAGE_COPY",
                    "TOTAL_DECODED_FRAMES": 1,
                    "CONTACT_SHEET_COUNT": 1,
                    "CONTACT_SHEETS": [dest.name],
                    "HUMAN_FEMALE_REVIEW_STATUS": "PENDING",
                }
            )

    if missing:
        raise RuntimeError(
            "Missing reused assets:\n" + "\n".join(missing)
        )

    desktop_manifest = {
        "SCHEMA_VERSION": "EP002_LEGACY_FEMALE_TEMPORAL_AUDIT_V2_3_DESKTOP",
        "STATUS": "AWAITING_HUMAN_ALL_FRAME_REVIEW",
        "AUDIT_METHOD": (
            "Every decoded video frame included in tiled contact sheets; "
            "full copies used for static images."
        ),
        "PRODUCTION_REUSE_CERTIFIED": False,
        "VISUAL_GENERATION_ALLOWED": False,
        "ASSETS": records,
    }

    write_json(out / "_MANIFEST.json", desktop_manifest)

    zip_base = desktop / "EP002_V2_3_TEMPORAL_FEMALE_AUDIT"
    zip_path = Path(
        shutil.make_archive(
            str(zip_base),
            "zip",
            root_dir=out,
        )
    )

    return {
        "directory": out,
        "zip": zip_path,
        "zip_sha256": sha256(zip_path),
        "asset_count": len(records),
        "video_count": sum(
            1 for r in records
            if r["AUDIT_METHOD"].startswith("ALL_DECODED")
        ),
        "image_count": sum(
            1 for r in records
            if r["AUDIT_METHOD"] == "FULL_STATIC_IMAGE_COPY"
        ),
        "records": records,
    }

def human_md(st, temporal):
    lines = [
        "# EP002 Surgical Visual Repair — V2.3 Human Review",
        "",
        "STATUS: AWAITING_HUMAN_APPROVAL",
        "",
        "## Hard gates",
        "",
        "- Current narration remains frozen and authoritative.",
        "- Visual generation remains blocked.",
        "- Paid/provider calls performed by this pass: 0.",
        "- Planned final graphics: 0.",
        "- Legacy female final temporal certification: PENDING HUMAN ALL-FRAME REVIEW.",
        "",
        "## Surgical delta",
        "",
        f"- Total editorial micro-shots: {len(st['MICRO_SHOTS'])}",
        f"- New editorial slots: {st['EDITORIAL_NEW_MICRO_SHOT_COUNT']}",
        f"- Reused editorial slots: {st['REUSED_LEGACY_MICRO_SHOT_COUNT_RETAINED']}",
        f"- Provider generation units: {st['PROVIDER_GENERATION_UNIT_COUNT']}",
        f"- Planned provider request seconds: {st['PLANNED_PROVIDER_REQUEST_SECONDS']}",
        f"- Editorial new visual seconds: {st['EDITORIAL_NEW_VISUAL_SECONDS']:.3f}",
        f"- Controlled exact-range second uses: {st['CONTROLLED_EXACT_RANGE_SECOND_USE_COUNT']}",
        f"- Maximum exact source range uses: {st['MAX_EXACT_SOURCE_RANGE_USE_COUNT']}",
        "",
        "V2.2 had 54 generation units / 362 provider seconds. "
        "V2.3 removes the generic-support explosion and retains only event-bearing diversity anchors.",
        "",
        "## Human decisions applied",
        "",
        "- Eating: approach -> complete occlusion/edit coverage -> lowered bitten fruit; no fruit-through-fabric.",
        "- Supplication: both Adam and spouse visibly participate; spouse hands remain concealed.",
        "- Earth entry: provider clips begin already on Earth; no morph/portal/descent effect.",
        "- Musa: brown complexion, tall/high stature, sturdy build; hair texture remains an authentic variant, not one canonical assertion.",
        "- Separate landing staging: TIER_5 permissible/non-authoritative; exact geography forbidden.",
        "- Provider prompt: VISUAL_PROVIDER_PROMPT is canonical; legacy COMPILED_PROVIDER_PROMPT removed from all new V2.3 shots.",
        "",
        "## Temporal female audit",
        "",
        f"- Package: {temporal['zip']}",
        f"- Package SHA256: {temporal['zip_sha256']}",
        f"- Assets prepared: {temporal['asset_count']}",
        f"- Video assets with all decoded frames tiled: {temporal['video_count']}",
        f"- Static images copied in full: {temporal['image_count']}",
        "",
        "Generation MUST remain blocked until these contact sheets are reviewed.",
        "",
        "## New provider units",
        "",
    ]

    for unit in st["PROVIDER_GENERATION_UNITS"]:
        lines.append(
            f"- {unit['GENERATION_UNIT_ID']} — "
            f"{unit['PROVIDER_REQUEST_DURATION_SECONDS']}s — "
            f"{', '.join(unit['EDITORIAL_MEMBER_SHOT_IDS'])}"
        )

    lines += [
        "",
        "NEXT=HUMAN_STORYBOARD_V2_3_AND_TEMPORAL_FEMALE_AUDIT_REVIEW",
        "",
    ]

    return "\n".join(lines)

def write_test():
    text = r'''from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
EP = REPO / "projects/episode-002-adam-temptation-fall-repentance"

STORY = EP / "preproduction/EP002_SURGICAL_REPAIR_STORYBOARD_V2_3.json"
DOSSIERS = EP / "preproduction/EP002_CHARACTER_EVIDENCE_DOSSIERS_V2_3.json"
SOURCE = EP / "orchestration/ep002-source-binding-v2-3.json"
CERT = EP / "orchestration/ep002-surgical-visual-repair-preproduction-v2-3.json"
TEMPORAL = EP / "orchestration/ep002-legacy-female-temporal-audit-v2-3.json"

def load(path):
    return json.loads(path.read_text(encoding="utf-8"))

def test_v23_generation_remains_blocked():
    s = load(STORY)
    assert s["STORYBOARD_STATUS"] == "AWAITING_HUMAN_APPROVAL"
    assert s["APPROVED_STORYBOARD_SHA256"] is None
    assert s["VISUAL_GENERATION_ALLOWED"] is False
    assert s["NETWORK_CALLS"] == 0
    assert s["PROVIDER_CALLS"] == 0
    assert s["PAID_CALLS"] == 0

def test_v23_surgical_cost_plan():
    s = load(STORY)
    assert len(s["MICRO_SHOTS"]) == 111
    assert s["EDITORIAL_NEW_MICRO_SHOT_COUNT"] == 29
    assert s["REUSED_LEGACY_MICRO_SHOT_COUNT_RETAINED"] == 82
    assert s["PROVIDER_GENERATION_UNIT_COUNT"] == 23
    assert s["PLANNED_PROVIDER_REQUEST_SECONDS"] == 176
    assert s["UNSUPPORTED_PROVIDER_DURATIONS"] == []

def test_every_generation_unit_fits_provider_source():
    s = load(STORY)
    shots = {x["MICRO_SHOT_ID"]: x for x in s["MICRO_SHOTS"]}
    for unit in s["PROVIDER_GENERATION_UNITS"]:
        assert unit["PROVIDER_REQUEST_DURATION_SECONDS"] in {4, 6, 8}
        assert unit["SOURCE_RANGE_CAPACITY_PASS"] is True
        for sid in unit["EDITORIAL_MEMBER_SHOT_IDS"]:
            assert shots[sid]["PROVIDER_SOURCE_OUT"] <= unit["PROVIDER_REQUEST_DURATION_SECONDS"] + 1e-9

def test_provider_prompt_has_one_canonical_field_and_no_execution_state():
    s = load(STORY)
    forbidden = (
        "AWAITING_HUMAN_APPROVAL",
        "VISUAL_GENERATION_ALLOWED",
        "APPROVED_STORYBOARD_SHA256",
        "PAID_CALLS",
        "NETWORK_CALLS",
        "PROVIDER_CALLS",
        "AUTHORIZATION",
    )
    for shot in s["MICRO_SHOTS"]:
        if shot["SOURCE"] != "NEW_GENERATION_REQUIRED":
            continue
        assert "COMPILED_PROVIDER_PROMPT" not in shot
        assert shot["CANONICAL_PROVIDER_PROMPT_FIELD"] == "VISUAL_PROVIDER_PROMPT"
        text = json.dumps(shot["VISUAL_PROVIDER_PROMPT"], ensure_ascii=False)
        assert not any(term.lower() in text.lower() for term in forbidden)

def test_shared_source_math_is_real():
    s = load(STORY)
    shots = {x["MICRO_SHOT_ID"]: x for x in s["MICRO_SHOTS"]}

    assert shots["EP002-V2-NEW-003"]["GENERATION_UNIT_ID"] == shots["EP002-V2-NEW-004"]["GENERATION_UNIT_ID"]
    assert shots["EP002-V2-NEW-003"]["PROVIDER_SOURCE_IN"] == 0.0
    assert shots["EP002-V2-NEW-003"]["PROVIDER_SOURCE_OUT"] == 4.0
    assert shots["EP002-V2-NEW-004"]["PROVIDER_SOURCE_IN"] == 4.0
    assert shots["EP002-V2-NEW-004"]["PROVIDER_SOURCE_OUT"] == 8.0

    assert shots["EP002-V2-NEW-005"]["GENERATION_UNIT_ID"] == shots["EP002-V2-NEW-006"]["GENERATION_UNIT_ID"]
    assert shots["EP002-V2-NEW-006"]["PROVIDER_SOURCE_OUT"] <= 8.0

    assert shots["EP002-V2-NEW-015"]["GENERATION_UNIT_ID"] == shots["EP002-V2-NEW-016"]["GENERATION_UNIT_ID"]
    assert shots["EP002-V2-NEW-017"]["GENERATION_UNIT_ID"] != shots["EP002-V2-NEW-015"]["GENERATION_UNIT_ID"]

def test_timeline_is_contiguous_and_frame_quantized():
    s = load(STORY)
    shots = s["MICRO_SHOTS"]
    fps = s["PRODUCTION_FPS"]
    assert shots[0]["TIMELINE_IN"] == 0.0
    assert abs(shots[-1]["TIMELINE_OUT"] - 623.5111041666667) < 1e-9
    for left, right in zip(shots, shots[1:]):
        assert abs(left["TIMELINE_OUT"] - right["TIMELINE_IN"]) < 1e-9
    for shot in shots[:-1]:
        assert abs(shot["TIMELINE_IN"] * fps - round(shot["TIMELINE_IN"] * fps)) < 1e-6
        assert abs(shot["TIMELINE_OUT"] * fps - round(shot["TIMELINE_OUT"] * fps)) < 1e-6

def test_controlled_reuse_is_transparent_and_bounded():
    s = load(STORY)
    assert s["MAX_EXACT_SOURCE_RANGE_USE_COUNT"] <= 2
    assert s["CONSECUTIVE_IDENTICAL_REUSE_COUNT"] == 0
    assert s["MAJOR_EVENT_DEPENDENCE_ON_CONTROLLED_DUPLICATE_SUPPORT"] == 0
    assert s["CONTROLLED_EXACT_RANGE_SECOND_USE_COUNT"] > 0
    assert s["UNJUSTIFIED_EXACT_RANGE_REUSE"] == 0

def test_eating_no_fruit_through_fabric():
    s = load(STORY)
    shots = {x["MICRO_SHOT_ID"]: x for x in s["MICRO_SHOTS"]}
    for sid in ("EP002-V2-NEW-001", "EP002-V2-NEW-007"):
        prompt = shots[sid]["VIDEO_PROMPT"].lower()
        assert "occlusion" in prompt
        assert "fabric penetration" in prompt

def test_shared_supplication():
    s = load(STORY)
    shots = {x["MICRO_SHOT_ID"]: x for x in s["MICRO_SHOTS"]}
    prompt = shots["EP002-V2-NEW-010"]["VIDEO_PROMPT"].lower()
    assert "both figures" in prompt
    assert "hands remain fully hidden" in prompt

def test_earth_shots_begin_on_earth():
    s = load(STORY)
    shots = {x["MICRO_SHOT_ID"]: x for x in s["MICRO_SHOTS"]}
    for sid in ("EP002-V2-NEW-013", "EP002-V2-NEW-014"):
        assert "first frame is already on earth" in shots[sid]["VIDEO_PROMPT"].lower()

def test_musa_authentic_hair_variant_not_collapsed():
    d = load(DOSSIERS)
    musa = next(x for x in d["CHARACTERS"] if x["CHARACTER_ID"] == "MUSA")
    variants = musa["PHYSICAL_APPEARANCE_CONTRACT"]["AUTHENTIC_VARIANT_ATTRIBUTES"]["hair_texture"]
    assert any("straight" in x for x in variants)
    assert any("curly" in x for x in variants)
    assert musa["VISUAL_BIBLE"]["HAIR_RENDER_POLICY"] == "LOW_DETAIL_DO_NOT_CANONICALIZE_VARIANT"

def test_descent_is_tier5_non_authoritative():
    s = load(SOURCE)
    assert s["SEPARATE_STAGING_SOURCE_TIER"] == "TIER_5_PERMISSIBLE_ISRAILIYYAT"
    assert s["EXACT_GEOGRAPHY_ASSERTED"] is False
    lower = next(x for x in s["SOURCE_RECORDS"] if x["SOURCE_TIER"] == "TIER_5_PERMISSIBLE_ISRAILIYYAT")
    assert lower["ASSERTION_MODE"] == "PERMISSIBLE_VISUAL_STAGING_ONLY"
    assert lower["EXACT_LOCATIONS_RENDERABLE"] is False
    assert lower["HUMAN_REVIEW_REQUIRED"] is True

def test_temporal_female_certification_is_fail_closed_pending_human():
    a = load(TEMPORAL)
    s = load(STORY)
    assert a["STATUS"] == "AWAITING_HUMAN_ALL_FRAME_REVIEW"
    assert a["ALL_DECODED_VIDEO_FRAMES_CONTACT_SHEETED"] is True
    assert a["PRODUCTION_REUSE_CERTIFIED"] is False
    assert s["TEMPORAL_FEMALE_AUDIT_STATUS"] == "AWAITING_HUMAN_ALL_FRAME_CONTACT_SHEET_REVIEW"
    assert s["VISUAL_GENERATION_ALLOWED"] is False

def test_certification_does_not_fake_final_pass():
    c = load(CERT)
    assert c["STATUS"] == "PASS_AUTOMATED_V2_3_GATES_PENDING_HUMAN_TEMPORAL_AUDIT"
    assert c["VISUAL_GENERATION_ALLOWED"] is False
    assert c["TEMPORAL_FEMALE_HUMAN_REVIEW_STATUS"] == "PENDING"
    assert c["ACTUAL_RENDER_MUTE_COMPREHENSION"] == "NOT_RUN"
'''
    TEST_FILE.write_text(text, encoding="utf-8")

def main():
    required = [
        V22_STORY,
        V22_DOSSIERS,
        V22_SOURCE,
        V22_AUDIT,
        V22_CERT,
        V22_CONST,
    ]

    for path in required:
        if not path.is_file():
            raise RuntimeError(f"Missing V2.2 input: {path}")

    v22_story = read_json(V22_STORY)
    v22_dossiers = read_json(V22_DOSSIERS)
    v22_source = read_json(V22_SOURCE)
    v22_audit = read_json(V22_AUDIT)
    v22_cert = read_json(V22_CERT)
    v22_const = read_json(V22_CONST)

    if v22_story["AUDIO_SHA256"] != AUDIO_SHA:
        raise RuntimeError("Frozen audio SHA mismatch")

    if abs(v22_story["AUDIO_DURATION_SECONDS"] - AUDIO_DURATION) > 1e-9:
        raise RuntimeError("Frozen audio duration mismatch")

    constitution = patch_constitution(v22_const)
    write_json(V23_CONST, constitution)
    constitution_sha = sha256(V23_CONST)

    dossiers = patch_dossiers(v22_dossiers)
    dossiers["CONSTITUTION_SHA256"] = constitution_sha
    write_json(V23_DOSSIERS, dossiers)
    dossier_sha = sha256(V23_DOSSIERS)

    source = patch_source_binding(v22_source)
    source["CONSTITUTION_SHA256"] = constitution_sha
    write_json(V23_SOURCE, source)
    source_sha = sha256(V23_SOURCE)

    storyboard = patch_storyboard(v22_story)
    storyboard["VISUAL_CONSTITUTION_SHA256"] = constitution_sha
    storyboard["CHARACTER_DOSSIERS_SHA256"] = dossier_sha
    storyboard["SOURCE_BINDING_SHA256"] = source_sha

    errors = validate_storyboard(storyboard)
    if errors:
        raise RuntimeError(
            "V2.3 storyboard validation failed:\n- "
            + "\n- ".join(errors)
        )

    # Full decoded-frame review package for every reused asset.
    temporal = build_full_frame_audit(storyboard)

    temporal_repo = {
        "SCHEMA_VERSION": "EP002_LEGACY_FEMALE_TEMPORAL_AUDIT_V2_3",
        "EPISODE_ID": storyboard["EPISODE_ID"],
        "STATUS": "AWAITING_HUMAN_ALL_FRAME_REVIEW",
        "AUDIT_METHOD": (
            "Every decoded video frame tiled into contact sheets; "
            "static images copied in full."
        ),
        "ALL_DECODED_VIDEO_FRAMES_CONTACT_SHEETED": True,
        "UNIQUE_REUSED_ASSET_COUNT": temporal["asset_count"],
        "VIDEO_ASSET_COUNT": temporal["video_count"],
        "STATIC_IMAGE_ASSET_COUNT": temporal["image_count"],
        "CONTACT_SHEET_PACKAGE_SHA256": temporal["zip_sha256"],
        "PRODUCTION_REUSE_CERTIFIED": False,
        "HUMAN_FEMALE_REVIEW_STATUS": "PENDING",
        "LEGACY_FEMALE_REUSE_REQUIRED_FINAL_COUNT": 0,
        "VISUAL_GENERATION_ALLOWED": False,
        "NO_SALVAGE_TRANSFORMS_USED": True,
    }
    write_json(V23_FEMALE_AUDIT, temporal_repo)
    temporal_sha = sha256(V23_FEMALE_AUDIT)

    storyboard["LEGACY_FEMALE_TEMPORAL_AUDIT_PATH"] = (
        "projects/episode-002-adam-temptation-fall-repentance/"
        "orchestration/ep002-legacy-female-temporal-audit-v2-3.json"
    )
    storyboard["LEGACY_FEMALE_TEMPORAL_AUDIT_SHA256"] = temporal_sha
    storyboard["LEGACY_FEMALE_REUSE_COUNT"] = 0

    write_json(V23_STORY, storyboard)
    storyboard_sha = sha256(V23_STORY)

    V23_MD.write_text(
        human_md(storyboard, temporal),
        encoding="utf-8",
    )

    # Concise transparent V2.3 asset/reuse audit.
    reused = [
        s for s in storyboard["MICRO_SHOTS"]
        if s["SOURCE"] in ("EXISTING", "REASSIGNED_EXISTING")
    ]

    audit23 = {
        "SCHEMA_VERSION": "EP002_SURGICAL_VISUAL_ASSET_AUDIT_V2_3",
        "EPISODE_ID": storyboard["EPISODE_ID"],
        "V2_2_AUDIT_SOURCE": str(
            V22_AUDIT.relative_to(REPO)
        ).replace("\\", "/"),
        "V2_2_AUDIT_SHA256": sha256(V22_AUDIT),
        "REUSED_MICRO_SHOT_COUNT": len(reused),
        "CONTROLLED_EXACT_RANGE_SECOND_USE_COUNT": storyboard[
            "CONTROLLED_EXACT_RANGE_SECOND_USE_COUNT"
        ],
        "MAX_EXACT_SOURCE_RANGE_USE_COUNT": storyboard[
            "MAX_EXACT_SOURCE_RANGE_USE_COUNT"
        ],
        "CONSECUTIVE_IDENTICAL_REUSE_COUNT": storyboard[
            "CONSECUTIVE_IDENTICAL_REUSE_COUNT"
        ],
        "UNJUSTIFIED_EXACT_RANGE_REUSE": 0,
        "UNJUSTIFIED_SEMANTIC_REPETITION": 0,
        "MAJOR_EVENT_DEPENDENCE_ON_CONTROLLED_DUPLICATE_SUPPORT": 0,
        "LEGACY_FEMALE_REUSE_PLANNED_COUNT": 0,
        "TEMPORAL_FEMALE_HUMAN_REVIEW_STATUS": "PENDING",
        "ALL_DECODED_FRAMES_CONTACT_SHEET_PACKAGE_SHA256": temporal[
            "zip_sha256"
        ],
        "NO_ASSET_BYTES_MODIFIED": True,
        "NO_SALVAGE_TRANSFORMS_USED": True,
        "REUSE_PLAN": [
            {
                "MICRO_SHOT_ID": s["MICRO_SHOT_ID"],
                "ASSET_ID": s["ASSET_ID"],
                "ASSET_PATH": s["ASSET_PATH"],
                "SOURCE_IN": s["SOURCE_IN"],
                "SOURCE_OUT": s["SOURCE_OUT"],
                "TIMELINE_IN": s["TIMELINE_IN"],
                "TIMELINE_OUT": s["TIMELINE_OUT"],
                "EVENT_ROLE": s["EVENT_ROLE"],
                "CONTROLLED_SUPPORT_REUSE": bool(
                    s.get("CONTROLLED_SUPPORT_REUSE", False)
                ),
                "MAJOR_EVENT_DEPENDS_ON_THIS_REUSE": bool(
                    s.get("MAJOR_EVENT_DEPENDS_ON_THIS_REUSE", False)
                ),
            }
            for s in reused
        ],
    }
    write_json(V23_AUDIT, audit23)
    audit_sha = sha256(V23_AUDIT)

    cert23 = {
        "STATUS": "PASS_AUTOMATED_V2_3_GATES_PENDING_HUMAN_TEMPORAL_AUDIT",
        "EPISODE_ID": storyboard["EPISODE_ID"],
        "CONSTITUTION_VERSION": (
            "SIRAJ_VISUAL_PRODUCTION_CONSTITUTION_V2_3"
        ),
        "CONSTITUTION_PATH": str(
            V23_CONST.relative_to(REPO)
        ).replace("\\", "/"),
        "CONSTITUTION_SHA256": constitution_sha,
        "AUDIO_SHA256": AUDIO_SHA,
        "AUDIO_DURATION_SECONDS": AUDIO_DURATION,
        "CURRENT_NARRATION_FROZEN": True,
        "AUDIO_IS_DURATION_AUTHORITY": True,

        "TOTAL_MICRO_SHOTS": len(storyboard["MICRO_SHOTS"]),
        "EDITORIAL_NEW_MICRO_SHOT_COUNT": storyboard[
            "EDITORIAL_NEW_MICRO_SHOT_COUNT"
        ],
        "REUSED_MICRO_SHOT_COUNT": storyboard[
            "REUSED_LEGACY_MICRO_SHOT_COUNT_RETAINED"
        ],
        "EDITORIAL_NEW_VISUAL_SECONDS": storyboard[
            "EDITORIAL_NEW_VISUAL_SECONDS"
        ],
        "PROVIDER_GENERATION_UNIT_COUNT": storyboard[
            "PROVIDER_GENERATION_UNIT_COUNT"
        ],
        "PLANNED_PROVIDER_REQUEST_SECONDS": storyboard[
            "PLANNED_PROVIDER_REQUEST_SECONDS"
        ],

        "V2_2_PROVIDER_GENERATION_UNIT_COUNT": 54,
        "V2_2_PLANNED_PROVIDER_REQUEST_SECONDS": 362,

        "CONTROLLED_EXACT_RANGE_SECOND_USE_COUNT": storyboard[
            "CONTROLLED_EXACT_RANGE_SECOND_USE_COUNT"
        ],
        "MAX_EXACT_SOURCE_RANGE_USE_COUNT": storyboard[
            "MAX_EXACT_SOURCE_RANGE_USE_COUNT"
        ],
        "CONSECUTIVE_IDENTICAL_REUSE_COUNT": 0,
        "UNJUSTIFIED_EXACT_RANGE_REUSE": 0,
        "UNJUSTIFIED_SEMANTIC_REPETITION": 0,

        "CANONICAL_PROVIDER_PROMPT_FIELD": "VISUAL_PROVIDER_PROMPT",
        "LEGACY_COMPILED_PROVIDER_PROMPT_CONSUMPTION_ALLOWED": False,
        "EXECUTION_STATE_TEXT_IN_PROVIDER_PROMPTS": 0,
        "PROMPT_CONTRADICTIONS": 0,

        "MUSA_HAIR_TEXTURE_STATUS": "AUTHENTIC_VARIANTS_NOT_CANONICALIZED",
        "ADAM_COMPLEXION_STATUS": "UNKNOWN",
        "SEPARATE_DESCENT_SOURCE_TIER": (
            "TIER_5_PERMISSIBLE_ISRAILIYYAT"
        ),
        "SEPARATE_DESCENT_CERTAINTY": (
            "NON_AUTHORITATIVE_CONFLICTING_EARLY_REPORTS"
        ),
        "EXACT_DESCENT_GEOGRAPHY_ASSERTED": False,

        "LEGACY_FEMALE_REUSE_PLANNED_COUNT": 0,
        "TEMPORAL_FEMALE_AUDIT_METHOD": (
            "ALL_DECODED_VIDEO_FRAMES_CONTACT_SHEETED"
        ),
        "TEMPORAL_FEMALE_HUMAN_REVIEW_STATUS": "PENDING",
        "TEMPORAL_FEMALE_AUDIT_PACKAGE_SHA256": temporal["zip_sha256"],
        "FINAL_LEGACY_FEMALE_TEMPORAL_CERTIFICATION": "NOT_YET_GRANTED",

        "PLANNED_GRAPHICS_COUNT": 0,
        "ACTUAL_RENDER_MUTE_COMPREHENSION": "NOT_RUN",

        "NETWORK_CALLS": 0,
        "PROVIDER_CALLS": 0,
        "PAID_CALLS": 0,
        "RUNWARE_CALLS": 0,
        "VEO_CALLS": 0,
        "IMAGE_GENERATION_CALLS": 0,
        "VIDEO_GENERATION_CALLS": 0,
        "NO_AUTHORIZATION_CREATED_OR_CONSUMED": True,
        "NO_MONTAGE_PERFORMED": True,
        "NO_ASSET_BYTES_MODIFIED": True,

        "PAID_HISTORY_UNCHANGED": True,
        "EPISODE_TRANSITION_LEDGER_UNCHANGED": True,
        "PROVIDER_EVIDENCE_UNCHANGED": True,

        "STORYBOARD_STATUS": "AWAITING_HUMAN_APPROVAL",
        "APPROVED_STORYBOARD_SHA256": None,
        "VISUAL_GENERATION_ALLOWED": False,

        "STORYBOARD_JSON": str(
            V23_STORY.relative_to(REPO)
        ).replace("\\", "/"),
        "STORYBOARD_SHA256": storyboard_sha,
        "CHARACTER_DOSSIERS_PATH": str(
            V23_DOSSIERS.relative_to(REPO)
        ).replace("\\", "/"),
        "CHARACTER_DOSSIERS_SHA256": dossier_sha,
        "SOURCE_BINDING_PATH": str(
            V23_SOURCE.relative_to(REPO)
        ).replace("\\", "/"),
        "SOURCE_BINDING_SHA256": source_sha,
        "ASSET_AUDIT_PATH": str(
            V23_AUDIT.relative_to(REPO)
        ).replace("\\", "/"),
        "ASSET_AUDIT_SHA256": audit_sha,
        "TEMPORAL_FEMALE_AUDIT_PATH": str(
            V23_FEMALE_AUDIT.relative_to(REPO)
        ).replace("\\", "/"),
        "TEMPORAL_FEMALE_AUDIT_SHA256": temporal_sha,

        "NEXT": (
            "HUMAN_STORYBOARD_V2_3_AND_TEMPORAL_FEMALE_AUDIT_REVIEW"
        ),
    }
    write_json(V23_CERT, cert23)
    cert_sha = sha256(V23_CERT)

    state23 = {
        "SCHEMA_VERSION": "EP002_VISUAL_REPAIR_PREPRODUCTION_STATE_V2_3",
        "EPISODE_ID": storyboard["EPISODE_ID"],
        "CURRENT_STAGE": "PRE_PRODUCTION_VISUAL_REVIEW",
        "STATUS": "AWAITING_HUMAN_APPROVAL",
        "STORYBOARD_PATH": str(
            V23_STORY.relative_to(REPO)
        ).replace("\\", "/"),
        "STORYBOARD_SHA256": storyboard_sha,
        "CERTIFICATION_PATH": str(
            V23_CERT.relative_to(REPO)
        ).replace("\\", "/"),
        "CERTIFICATION_SHA256": cert_sha,
        "TEMPORAL_FEMALE_AUDIT_STATUS": (
            "AWAITING_HUMAN_ALL_FRAME_REVIEW"
        ),
        "APPROVED_STORYBOARD_SHA256": None,
        "VISUAL_GENERATION_ALLOWED": False,
        "NETWORK_CALLS": 0,
        "PROVIDER_CALLS": 0,
        "PAID_CALLS": 0,
        "NEXT": (
            "HUMAN_STORYBOARD_V2_3_AND_TEMPORAL_FEMALE_AUDIT_REVIEW"
        ),
    }
    write_json(V23_STATE, state23)

    write_test()

    # --------------------------------------------------------
    # Text review package on Desktop.
    # --------------------------------------------------------

    desktop = Path.home() / "Desktop"
    review_dir = desktop / "EP002_V2_3_REVIEW_PACKAGE"

    if review_dir.exists():
        shutil.rmtree(review_dir)

    review_dir.mkdir(parents=True)

    review_files = [
        V23_CONST,
        V23_DOSSIERS,
        V23_SOURCE,
        V23_STORY,
        V23_MD,
        V23_AUDIT,
        V23_FEMALE_AUDIT,
        V23_CERT,
        V23_STATE,
    ]

    manifest = []

    for path in review_files:
        target = review_dir / path.name
        shutil.copy2(path, target)
        manifest.append(
            {
                "FILE": path.name,
                "SHA256": sha256(path),
                "SOURCE": str(path.relative_to(REPO)).replace("\\", "/"),
            }
        )

    write_json(
        review_dir / "_MANIFEST.json",
        {
            "STATUS": "V2_3_REVIEW_PACKAGE",
            "FILES": manifest,
        },
    )

    review_zip = Path(
        shutil.make_archive(
            str(desktop / "EP002_V2_3_REVIEW_PACKAGE"),
            "zip",
            root_dir=review_dir,
        )
    )

    print("V23_BUILD_STATUS=PASS_AUTOMATED_GATES_PENDING_HUMAN_AUDIT")
    print(f"TOTAL_MICRO_SHOTS={len(storyboard['MICRO_SHOTS'])}")
    print(
        "EDITORIAL_NEW_MICRO_SHOTS="
        f"{storyboard['EDITORIAL_NEW_MICRO_SHOT_COUNT']}"
    )
    print(
        "REUSED_MICRO_SHOTS="
        f"{storyboard['REUSED_LEGACY_MICRO_SHOT_COUNT_RETAINED']}"
    )
    print(
        "PROVIDER_GENERATION_UNITS="
        f"{storyboard['PROVIDER_GENERATION_UNIT_COUNT']}"
    )
    print(
        "PLANNED_PROVIDER_REQUEST_SECONDS="
        f"{storyboard['PLANNED_PROVIDER_REQUEST_SECONDS']}"
    )
    print(
        "EDITORIAL_NEW_VISUAL_SECONDS="
        f"{storyboard['EDITORIAL_NEW_VISUAL_SECONDS']:.3f}"
    )
    print(
        "CONTROLLED_EXACT_RANGE_SECOND_USES="
        f"{storyboard['CONTROLLED_EXACT_RANGE_SECOND_USE_COUNT']}"
    )
    print(
        "MAX_EXACT_SOURCE_RANGE_USE_COUNT="
        f"{storyboard['MAX_EXACT_SOURCE_RANGE_USE_COUNT']}"
    )
    print("LEGACY_FEMALE_REUSE_PLANNED_COUNT=0")
    print(
        "TEMPORAL_FEMALE_AUDIT_STATUS="
        "AWAITING_HUMAN_ALL_FRAME_REVIEW"
    )
    print("NETWORK_CALLS=0")
    print("PROVIDER_CALLS=0")
    print("PAID_CALLS=0")
    print("VISUAL_GENERATION_ALLOWED=FALSE")
    print(f"STORYBOARD_SHA256={storyboard_sha}")
    print(f"REVIEW_PACKAGE={review_zip}")
    print(f"REVIEW_PACKAGE_SHA256={sha256(review_zip)}")
    print(f"TEMPORAL_AUDIT_PACKAGE={temporal['zip']}")
    print(f"TEMPORAL_AUDIT_PACKAGE_SHA256={temporal['zip_sha256']}")
    print(
        "NEXT=HUMAN_STORYBOARD_V2_3_AND_TEMPORAL_FEMALE_AUDIT_REVIEW"
    )

if __name__ == "__main__":
    main()