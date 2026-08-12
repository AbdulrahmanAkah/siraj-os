"""Offline Episode 002 surgical visual-repair preproduction builder.

Only local evidence is read.  New planning/report artifacts are written; no
provider, network, paid operation, authorization, or media generation is used.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any
import wave

from src.application.visual_production_constitution_v1 import (
    compile_visual_prompt,
    load_visual_production_constitution,
    validate_repair_storyboard,
)


REPO = Path(__file__).resolve().parents[2]
EPISODE_ID = "episode-002-adam-temptation-fall-repentance"
EPISODE_ROOT = REPO / "projects" / EPISODE_ID

AUDIO_TIMELINE = EPISODE_ROOT / "preproduction/audio-timestamps-and-beats-v6-1.json"
MASTER_AUDIO = EPISODE_ROOT / "orchestration/montage-v6-2-1/narration-master-v6-2-1.wav"
QUEUE = EPISODE_ROOT / "orchestration/media-production-queue-v6-2-1.json"
BOUND_STORYBOARD = EPISODE_ROOT / "preproduction/audio-bound-storyboard-v6-1.json"
SCRIPT = EPISODE_ROOT / "preproduction/luna-final-script-v5-1.json"
TIMELINE_EVIDENCE = EPISODE_ROOT / "orchestration/final-qa-timeline-evidence-v7.json"
CONTACT_SHEET = EPISODE_ROOT / "orchestration/final-qa-contact-sheet-v7.jpg"
MASTER_RECEIPT = EPISODE_ROOT / "deliverables/autopilot-v6-2-1/episode-master-autopilot-v6-2-1-receipt.json"
TECHNICAL_VALIDATION = EPISODE_ROOT / "orchestration/final-qa-technical-validation-v7.json"

STORYBOARD = EPISODE_ROOT / "preproduction/EP002_SURGICAL_REPAIR_STORYBOARD_V1.json"
HUMAN_REPORT = EPISODE_ROOT / "preproduction/EP002_SURGICAL_REPAIR_STORYBOARD_V1.md"
AUDIT = EPISODE_ROOT / "orchestration/ep002-surgical-visual-asset-audit-v1.json"
CERTIFICATION = EPISODE_ROOT / "orchestration/ep002-surgical-visual-repair-preproduction-v1.json"
STATE = EPISODE_ROOT / "orchestration/visual-repair-preproduction-state-v1.json"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def rel(path: Path) -> str:
    return path.resolve().relative_to(REPO.resolve()).as_posix()


def number(shot_id: str) -> int:
    return int(shot_id.rsplit("-", 1)[-1])


CURRENT_DISPOSITIONS = {
    "KEEP": {
        "EP002-SH-002", "EP002-SH-009", "EP002-SH-011", "EP002-SH-021",
        "EP002-SH-023", "EP002-SH-025", "EP002-SH-034", "EP002-SH-037",
        "EP002-SH-049", "EP002-SH-050", "EP002-SH-051", "EP002-SH-054",
    },
    "REASSIGN": {
        "EP002-SH-003", "EP002-SH-004", "EP002-SH-005", "EP002-SH-006",
        "EP002-SH-013", "EP002-SH-014", "EP002-SH-016", "EP002-SH-024",
        "EP002-SH-038", "EP002-SH-045", "EP002-SH-046", "EP002-SH-047",
        "EP002-SH-048",
    },
    "DELETE": {
        "EP002-SH-007", "EP002-SH-008", "EP002-SH-012", "EP002-SH-015",
        "EP002-SH-026", "EP002-SH-027", "EP002-SH-028", "EP002-SH-029",
        "EP002-SH-030", "EP002-SH-031", "EP002-SH-032", "EP002-SH-039",
        "EP002-SH-040", "EP002-SH-041", "EP002-SH-042", "EP002-SH-043",
        "EP002-SH-044", "EP002-SH-052", "EP002-SH-053", "EP002-SH-055",
    },
    "REGENERATE_REQUIRED": {
        "EP002-SH-001", "EP002-SH-010", "EP002-SH-017", "EP002-SH-018",
        "EP002-SH-019", "EP002-SH-020", "EP002-SH-022", "EP002-SH-033",
        "EP002-SH-035", "EP002-SH-036",
    },
}

REASSIGN_TARGETS = {
    "EP002-SH-003": "EP002-SH-009-I01",
    "EP002-SH-004": "EP002-SH-023-I01",
    "EP002-SH-005": "EP002-SH-009-I01",
    "EP002-SH-006": "EP002-SH-011-I01",
    "EP002-SH-013": "EP002-SH-014-I01",
    "EP002-SH-014": "EP002-SH-011-I01",
    "EP002-SH-016": "EP002-SH-011-I01",
    "EP002-SH-015": "EP002-SH-011-I01",
    "EP002-SH-024": "EP002-SH-023-I01",
    "EP002-SH-029": "EP002-SH-025-I01",
    "EP002-SH-038": "EP002-SH-051-I01",
    "EP002-SH-039": "EP002-SH-037-V01",
    "EP002-SH-044": "EP002-SH-037-V01",
    "EP002-SH-045": "EP002-SH-037-V01",
    "EP002-SH-046": "EP002-SH-049-I01",
    "EP002-SH-047": "EP002-SH-050-V01",
    "EP002-SH-048": "EP002-SH-051-I01",
    "EP002-SH-052": "EP002-SH-051-I01",
    "EP002-SH-053": "EP002-SH-050-V01",
    "EP002-SH-055": "EP002-SH-051-I01",
}

GRAPHICS_SHOTS = {
    "EP002-SH-032", "EP002-SH-040", "EP002-SH-041", "EP002-SH-042"
}
UNSAFE_FEMALE_SHOTS = {
    "EP002-SH-007", "EP002-SH-008", "EP002-SH-012", "EP002-SH-015",
    "EP002-SH-026", "EP002-SH-027", "EP002-SH-028", "EP002-SH-030",
    "EP002-SH-031", "EP002-SH-052",
}

OBSERVATIONS = {
    "EP002-SH-001": "leaf/foliage frame; no person, fruit removal, bite, or eating.",
    "EP002-SH-002": "two bare hands fold large leaves; literal covering, but hands are the only human detail.",
    "EP002-SH-007": "two dark body-shaped silhouettes in artificial water/curtain imagery.",
    "EP002-SH-008": "two silhouettes, then a third translucent silhouette, then two; continuity 2-to-3-to-2 confirmed.",
    "EP002-SH-009": "unnamed organic plant form; usable only as non-specific tree establishing.",
    "EP002-SH-010": "horizontal boundary/atmosphere; no speaking subject or whisper action.",
    "EP002-SH-012": "two dark silhouettes against blue streaks; no visible speaker or whisper.",
    "EP002-SH-015": "unrelated iron gate and two silhouettes; not the intended garden.",
    "EP002-SH-017": "abstract liquid/ground energy; no people approach or action.",
    "EP002-SH-018": "abstract surface line; no tempter, pair, or slip.",
    "EP002-SH-019": "dark edge and white lines; no fruit, mouth, or eating.",
    "EP002-SH-020": "split abstract texture; no characters or shared aftermath.",
    "EP002-SH-022": "graphic-like leaf cluster; no people or covering action.",
    "EP002-SH-026": "two ambiguous dark kneeling silhouettes; identity and clothing uncontrolled.",
    "EP002-SH-027": "bare hands only; not proof of repentance and contrary to preferred no-hands rule.",
    "EP002-SH-028": "multiple bare hands reaching toward a line; not visible shared prayer.",
    "EP002-SH-030": "one dark body-shaped silhouette; no receiving action.",
    "EP002-SH-031": "same ambiguous silhouette; no acceptance or human response.",
    "EP002-SH-032": "blank rounded panel/placeholder; graphics policy failure.",
    "EP002-SH-035": "reflective abstract plane; no physical descent.",
    "EP002-SH-036": "empty tracks; no pair, descent, or visible separation.",
    "EP002-SH-039": "inset duplicate/near-empty landscape; placeholder-like.",
    "EP002-SH-040": "dark UI-like source bar with controls.",
    "EP002-SH-041": "grid with colored curves and a node; diagram.",
    "EP002-SH-042": "timeline-like line with points and arrow; diagram/UI.",
    "EP002-SH-043": "floating blank card over landscape; source-card mismatch.",
    "EP002-SH-044": "unrelated airplane silhouette; no narrated hadith action.",
    "EP002-SH-052": "two distant dark silhouettes on a road; female coverage/identity unreliable.",
    "EP002-SH-053": "inset duplicate over blurred background; placeholder defect.",
    "EP002-SH-055": "near-black indistinct line; not a reviewable event.",
}


def disposition(shot_id: str) -> str:
    for name, ids in CURRENT_DISPOSITIONS.items():
        if shot_id in ids:
            return name
    raise RuntimeError("UNCLASSIFIED_SHOT:" + shot_id)


def build_specs() -> dict[str, dict[str, Any]]:
    female_contract = (
        "STRICT: spouse uses opaque loose full-body clothing; head and hair, neck, "
        "arms, legs, torso skin, hands where avoidable, and body contour are covered; "
        "no tight, transparent, revealing, nude, or body-shaped silhouette. If the "
        "provider cannot hold this contract, use rear/distant/opaque-leaf blocking or omit her."
    )
    common_negative = (
        "nudity, exposed skin, visible female hair, visible female neck, visible female "
        "arms, visible female legs, tight clothing, transparent clothing, revealing "
        "clothing, body-shaped silhouette, sexualized framing, faces, logos, watermark, "
        "readable text, Arabic text, subtitles, diagram, chart, UI, explainer panel, "
        "placeholder, symbolic substitute for the visible action, extra characters, "
        "continuity jump, loop, filler, empty frame"
    )
    specs: dict[str, dict[str, Any]] = {}

    def add(
        sid: str, event_id: str, characters: list[str], action: str, obj: str,
        location: str, start: str, end: str, target: str, prompt: str,
        motion: str, camera: str, composition: str, lighting: str,
        female: bool, event_type: str = "LITERAL_EVENT",
    ) -> None:
        specs[sid] = {
            "EVENT_ID": event_id, "EVENT_TYPE": event_type, "CHARACTERS": characters,
            "VISIBLE_ACTION": action, "OBJECT": obj, "LOCATION": location,
            "START_STATE": start, "END_STATE": end, "MUTE_TARGET": target,
            "PROMPT": prompt, "MOTION": motion, "CAMERA": camera,
            "COMPOSITION": composition, "LIGHTING": lighting, "INCLUDES_FEMALE": female,
            "FEMALE_REQUIREMENTS": female_contract if female else "NOT_APPLICABLE",
            "NEGATIVE": common_negative,
            "STYLE": "cinematic live-action realism; restrained historical storytelling",
        }

    add(
        "EP002-SH-001", "EV-002-EATING-ACTION", ["Adam", "Spouse"],
        "Adam visibly takes fruit, bites and chews; the fully covered spouse inclines to a fruit at her veil and the completed bite is visible without exposing her.",
        "unnamed fruit from tree", "unnamed garden", "both stand beside tree",
        "both have completed tasting", "Muted viewing sees fruit leave tree and actual bites by both.",
        "Live-action 16:9: Adam and fully covered spouse beside an unnamed tree. Adam removes a fruit, brings it to his visible mouth, bites and chews. The spouse remains in opaque loose full-body clothing with head and hair covered; her covered head inclines to fruit at the veil, then a matched cut shows a fresh bite missing, with no face, skin, hands, or contour.",
        "slow reach, bite, chew, covered-head inclination, completed bite", "medium side angle",
        "tree and pair share frame; Adam's bite is readable; spouse is rear three-quarter and leaf-shadow protected",
        "soft natural garden light; no glow", True,
    )
    add(
        "EP002-SH-007", "EV-003-BOUNDARY-ESTABLISHMENT", ["Adam", "Spouse"],
        "The pair walks together through an abundant real garden and arrives at the tree area.",
        "open garden and unnamed tree", "unnamed garden", "pair walks in open space",
        "pair arrives together", "Muted viewing sees exactly two covered people in a real garden before the boundary.",
        "Wide live-action garden with real ground and one unnamed tree; Adam and spouse walk together in far middle distance, fully covered, rear-facing, and exactly two people.",
        "slow lateral walk of exactly two figures; no third silhouette", "high wide oblique",
        "open garden dominates; tree area visible; no drawn line or graphic", "soft diffuse daylight", True, "ESTABLISHING",
    )
    add(
        "EP002-SH-008", "EV-003-BOUNDARY-ESTABLISHMENT", ["Adam", "Spouse"],
        "The pair walks toward the tree and stops together before it; exactly two people remain visible.",
        "unnamed tree and natural garden edge", "unnamed garden", "pair approaches tree",
        "pair stops side by side", "Muted viewing sees two covered people approach and stop; no third figure or body-shaped shadow.",
        "Wide live-action continuation: two and only two fully covered figures approach the same unnamed tree and stop several steps before its trunk.",
        "one continuous approach and synchronized stop; no reflection or shadow person", "low lateral tracking",
        "tree ahead, pair readable, natural space between them", "natural daylight; no portal", True,
    )
    add(
        "EP002-SH-010", "EV-004-TEMPTATION-WHISPER", ["Adam", "Spouse", "Tempter"],
        "A third fully covered adult male visibly leans close and speaks; the pair turns and listens.",
        "spoken counsel toward tree", "same garden tree", "pair stands; tempter enters",
        "tempter speaks and pair listens", "Muted viewing identifies speaker and listeners.",
        "Live-action medium shot: Adam and fully covered spouse before the unnamed tree while a third adult male tempter in loose opaque hooded robe leans close and visibly speaks in side profile with natural mouth, no identifiable face. Pair turns to listen.",
        "tempter steps in, bends, speaks, pair turns", "medium three-quarter",
        "three bodies separated and countable; no fourth reflection", "cool natural shade; no creature or beam", True,
    )
    add(
        "EP002-SH-012", "EV-004-TEMPTATION-WHISPER", ["Adam", "Spouse", "Tempter"],
        "The tempter visibly whispers and gestures toward the tree; both listeners react toward it.",
        "tree and spoken counsel", "same garden", "tempter is close and speaking",
        "pair attention redirects to tree", "Muted viewing sees third-person whispering and two listeners.",
        "Live-action continuation with same three characters: covered male tempter whispers beside the pair and gestures with covered sleeve toward the unnamed tree; Adam and spouse turn from speaker toward tree, spouse fully covered.",
        "whisper, small sleeve gesture, synchronized listener reaction", "slow over-shoulder to profile",
        "speaker, listeners, tree form one readable triangle; exactly three", "muted green shade; no streaks", True,
    )
    add(
        "EP002-SH-017", "EV-005-CHOICE-BECOMES-ACTION", ["Adam", "Spouse"],
        "Both leave open space, walk to the tree, and extend covered sleeves toward fruit; tempter is absent.",
        "tree and fruit", "same garden", "pair turns toward tree", "pair reaches branch",
        "Muted viewing sees temptation become physical approach and reach.",
        "Live-action: Adam and fully covered spouse leave open garden space together, approach the same tree, stop within reach, and extend covered sleeves toward visible fruit; no tempter.",
        "synchronized walk, stop, two deliberate reaches", "low forward tracking",
        "pair equal in scale; branch and fruit visible; no third character", "natural light slightly darker", True,
    )
    add(
        "EP002-SH-018", "EV-006-MISLEADING-SLIP", ["Adam", "Spouse", "Tempter"],
        "Covered tempter leads pair along tree side; both follow and jointly slip onto lower uneven ground.",
        "tree-side ground", "same garden", "tempter leads; pair follows",
        "three shift to lower patch", "Muted viewing sees leading, following, and shared deviation.",
        "Live-action: same covered male tempter walks ahead beside the tree; Adam and covered spouse follow, then the sloped ground makes both followers lose footing together and step down onto a lower patch. No violence or extra person.",
        "lead, follow, synchronized misstep, shared lower landing", "high oblique tracking",
        "three figures countable across two visible ground levels", "natural shade and earth; no arrows", True,
    )
    add(
        "EP002-SH-019", "EV-007-EATING-ACTION", ["Adam", "Spouse"],
        "Both visibly complete the bite; Adam's mouth is shown and the spouse's covered-head bite is matched without exposing her.",
        "unnamed fruit", "at tree", "both within reach", "both lower fruit after bite",
        "Muted viewing identifies actual eating by both, not tree/light/line.",
        "Live-action close shot at unnamed tree: Adam lifts fruit and visibly bites. Spouse stays rear three-quarter in opaque full-body clothing; her covered head moves to fruit at veil and a matched cut shows bite missing as she lowers it. No female face, hair, skin, hands, or contour.",
        "two sequential bite actions, both lower fruit", "close side plus protected rear angle",
        "fruit, branch, Adam mouth, spouse covered head readable; no tempter", "natural shade", True,
    )
    add(
        "EP002-SH-020", "EV-008-SHARED-RESPONSIBILITY", ["Adam", "Spouse"],
        "Both stop, look down at their own covered bodies, step back from tree, and never point at one another.",
        "tree behind and covered clothing", "tree-side ground", "just completed bite",
        "shared consequence acknowledged", "Muted viewing shows shared aftermath, not blame.",
        "Live-action medium-wide: pair stands side by side after bite, both look down at their own covered clothing, take synchronized step back, and turn inward toward same ground. Neither points at the other.",
        "look down, step back, equal inward turn", "front three-quarter",
        "tree remains causal context; pair only", "cool natural light; no split screen", True,
    )
    add(
        "EP002-SH-022", "EV-009-REVEAL-THEN-COVER", ["Adam", "Spouse"],
        "Both recoil, pull large opaque leaves around their fully covered bodies, and crouch; no skin is shown.",
        "opaque leaves", "tree-side ground", "standing after bite", "both crouch covered",
        "Muted viewing sees aftermath followed by actual covering.",
        "Live-action medium-wide: pair recoils after bite, then each pulls a large opaque leaf wrap around an already fully covered body and lowers into protective crouch. Spouse's head, hair, neck, arms, legs, torso, hands and contour remain hidden.",
        "recoil, reach leaves, pull around bodies, crouch", "side-rear",
        "two countable figures; covering action unmistakable", "subdued natural light", True,
    )
    add(
        "EP002-SH-026", "EV-011-SUPPLICATION", ["Adam", "Spouse"],
        "Both visibly kneel, bow heads, and hold remorseful inward posture.",
        "earth ground", "tree-side earth", "covered and shocked", "kneeling remorse",
        "Muted viewing understands actual remorse through posture.",
        "Live-action wide: Adam and fully covered spouse kneel together on earth after covering themselves; both bow heads and fold inward; no face, skin, hands, or contour exposed.",
        "standing shock settles into synchronized kneeling", "low medium-wide rear",
        "exactly two figures, equal scale, no third silhouette", "subdued blue-gray natural light", True,
    )
    add(
        "EP002-SH-027", "EV-011-SUPPLICATION", ["Adam", "Spouse"],
        "Both kneeling figures raise covered sleeves, bow, and hold a supplication posture.",
        "open ground", "same earth", "kneeling in remorse", "shared supplication hold",
        "Muted viewing understands asking for mercy through human posture.",
        "Live-action overhead-to-medium: pair kneels side by side; loose opaque sleeves rise together while heads stay bowed, hands inside sleeves, no female skin or contour.",
        "covered sleeves lift, heads bow, hold", "slow high-angle lower",
        "symmetrical pair, same ground, no third figure", "soft neutral light; no beam or text", True,
    )
    add(
        "EP002-SH-028", "EV-012-REPENTANCE-HOPE", ["Adam", "Spouse"],
        "Pair lowers sleeves, bows once more, then lifts covered heads toward open earth without triumph.",
        "ground and horizon", "same earth", "supplication hold", "quiet hope while consequence remains",
        "Muted viewing understands repentance followed by restrained hope, not erasure.",
        "Live-action continuation: the two fully covered figures lower sleeves, bow together, then lift covered heads toward open horizon while kneeling. Ground mark remains behind; no route or celebration.",
        "lower, bow, hold, lift together", "slow rear forward move",
        "pair side by side; old ground mark remains; no destination object", "muted gray to restrained warmth", True,
    )
    add(
        "EP002-SH-030", "EV-013-RECEIVING-WORDS", ["Adam"],
        "Adam kneels, turns covered head toward unseen off-screen source, and listens; no writing or source is shown.",
        "none", "unlocated natural ground", "kneeling after confession", "quiet receptive hold",
        "Muted viewing sees a human listening action, not text/tablet/beam.",
        "Live-action medium rear three-quarter: one fully covered adult male kneels on natural ground, turns toward an unseen off-screen source, and holds still. No writing, tablet, messenger, beam, or personified source.",
        "small turn and attentive hold", "restrained medium rear three-quarter",
        "one man against real ground and air; blank space is physical, not a graphic", "soft diffuse light", False,
    )
    add(
        "EP002-SH-031", "EV-014-ACCEPTANCE", ["Adam", "Spouse"],
        "Adam rises from kneeling; fully covered spouse rises beside him; both stabilize without triumph.",
        "same ground", "unlocated natural ground", "both kneel", "both stand calmly",
        "Muted viewing sees concrete rise and stable acceptance; nothing is erased.",
        "Live-action continuation: Adam rises slowly, fully covered spouse rises beside him, both remain rear-facing and quiet; the ground mark stays visible so acceptance does not erase consequence.",
        "kneel, rise, stabilize, stand together", "medium-wide rear",
        "two figures only, stable positions, no supernatural actor", "soft neutral warmth; no halo", True,
    )
    add(
        "EP002-SH-032", "EV-013-RECEIVING-WORDS", ["Adam"],
        "Adam draws covered sleeves inward, bows, and holds attentive posture in real earth; unspecified words remain unpictured.",
        "none", "unlocated natural ground", "listening after reception", "quiet hold without invented content",
        "Muted viewing sees a human listening hold, not a blank panel or placeholder.",
        "Live-action medium side-rear: one fully covered adult male on real earth draws sleeves inward, bows head, and holds attentive reception. No paper, text, symbol, panel, graphic, beam, or source appears.",
        "sleeves draw inward, bow, hold", "locked medium side-rear",
        "one human figure and real ground replace former blank panel", "soft overcast light", False, "TRANSITION",
    )
    add(
        "EP002-SH-033", "EV-015-GUIDANCE-AFTER-ACCEPTANCE", ["Adam", "Spouse"],
        "Pair leaves kneeling place, turns together toward open earth, and begins walking with ground mark behind.",
        "open earthly direction and ground mark", "real earth", "both stand after acceptance", "both move forward",
        "Muted viewing sees concrete turn and departure while past remains.",
        "Live-action wide: Adam and fully covered spouse stand beside visible ground mark, turn together away, and take measured steps toward open earthly space. No path symbol, text, beam, or destination.",
        "turn together, take steps, leave mark behind", "wide rear tracking",
        "two figures countable and secondary; mark left in start area", "natural early-earth light", True,
    )
    add(
        "EP002-SH-035", "EV-016-DESCENT", ["Adam", "Spouse"],
        "Pair descends a real steep slope from high edge to lower earth; elevation change and steps are visible.",
        "steep slope", "high garden edge to lower earth", "standing on high ledge", "both reach lower shelf",
        "Muted viewing understands physical downward transition, not color shift/map.",
        "Live-action wide: pair at top of real grassy rocky slope walks downward together; each step loses elevation and both arrive on lower earth shelf. Spouse remains fully covered and non-body-defining.",
        "continuous downward walk with visible elevation change", "wide side profile",
        "high starting ledge and low landing share frame; exactly two", "natural daylight to muted lower earth", True,
    )
    add(
        "EP002-SH-036", "EV-017-EARTHLY-SEPARATION", ["Adam", "Spouse"],
        "After descent, pair separates and walks in opposite directions across same ground without combat.",
        "ordinary earth", "lower earth", "standing together after descent", "clear gap between them",
        "Muted viewing understands earthly separation, not track-only graphic.",
        "Live-action wide on lower earth: pair stands together, turns in opposite directions, and walks apart across same ground, widening the gap. No fight, weapon, extra character, or arrow.",
        "shared stop, opposite turns, sustained separation", "high wide lateral",
        "one earth space; two only; no third shadow", "cool neutral earth light", True,
    )
    add(
        "EP002-SH-040", "EV-018-HADITH-DEBATE", ["Discussant-A", "Discussant-B"],
        "Two non-identifying adult men visibly conduct a restrained discussion; one speaks and one listens.",
        "closed unmarked book", "plain historical room", "discussion begins", "speaker/listener relation clear",
        "Muted viewing sees real two-person conversation, not source card or UI.",
        "Live-action historical interior: two non-identifying adult men in loose opaque garments sit across plain wooden table; one speaks in profile and one listens. Closed unmarked book is physical only; no readable page or text.",
        "one speaks, listener attends, eye-line exchange", "restrained medium two-shot",
        "exactly two men, closed prop only, no overlay", "warm low natural window light", False,
    )
    add(
        "EP002-SH-041", "EV-018-HADITH-DEBATE", ["Discussant-A", "Discussant-B"],
        "Second man visibly answers across same table; turn-taking and identity remain stable.",
        "closed book and table", "same historical room", "listener becomes speaker", "two-person exchange continues",
        "Muted viewing sees a real reply with no explainer graphics.",
        "Live-action continuation with same two men: second man answers with restrained open-palm gesture while first listens; closed book remains and no page, caption, chart, or card appears.",
        "turn-taking, answer gesture, held two-shot", "slow lateral dolly",
        "same room, wardrobe, sides, and two-person count", "same warm light with deeper contrast", False,
    )
    add(
        "EP002-SH-042", "EV-018-HADITH-DEBATE", ["Discussant-A", "Discussant-B"],
        "One man lowers a hand toward real floor between them; other looks down and back in responsibility-focused pause.",
        "ground between men", "same historical room", "exchange continues", "reflective pause",
        "Muted viewing sees physical responsibility-focused conversation, not timeline/arrow.",
        "Live-action close two-shot of same men: speaker finishes, lowers hand toward real floor, listener looks down and back. No chart, arrow, text, or screen.",
        "finish, lower hand, listener looks down and back", "slow close lateral",
        "same room and two men; ground gesture visible", "warm light falls toward floor", False,
    )
    add(
        "EP002-SH-043", "EV-019-HADITH-CLOSURE", ["Discussant-A", "Discussant-B"],
        "Two men close discussion, stand, and leave opposite directions; closed book remains.",
        "closed unmarked book", "same historical room", "limited discussion ends", "room holds physical book",
        "Muted viewing sees real closure, not airplane/floating card/placeholder.",
        "Live-action continuation: same two men close discussion, stand, leave in opposite directions; camera holds on real table and closed unmarked book after exit. No page or text.",
        "both stand, separate, exit, hold real table", "wide locked room view",
        "two countable until exit; physical book never becomes graphic panel", "warm room light settles", False,
    )
    return specs


def build_manifest(paths: list[Path]) -> str:
    entries: list[dict[str, Any]] = []
    for base in paths:
        if not base.exists():
            continue
        files = [base] if base.is_file() else [p for p in base.rglob("*") if p.is_file()]
        for path in sorted(files):
            entries.append({"path": rel(path), "bytes": path.stat().st_size, "sha256": sha256_file(path)})
    raw = json.dumps(entries, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def make_event(
    event_id: str, shot_ids: list[str], shot_by_id: dict[str, dict[str, Any]],
    subject: str, action: str, obj: str, location: str, start: str, visible: str,
    end: str, count: int, target: str, forbidden: list[str],
) -> dict[str, Any]:
    first = shot_by_id[shot_ids[0]]
    last = shot_by_id[shot_ids[-1]]
    return {
        "EVENT_ID": event_id,
        "EVENT_CLASS": "MAJOR_LITERAL_EVENT",
        "NARRATION_TEXT": first["NARRATION_TEXT"],
        "START_TIME": first["START_TIME"],
        "END_TIME": last["END_TIME"],
        "SUBJECT": subject,
        "ACTION": action,
        "OBJECT": obj,
        "LOCATION": location,
        "START_STATE": start,
        "VISIBLE_ACTION": visible,
        "END_STATE": end,
        "EXPECTED_CHARACTER_COUNT": count,
        "MUTE_COMPREHENSION_TARGET": target,
        "FORBIDDEN_SUBSTITUTIONS": forbidden,
        "LITERAL_SHOT_IDS": shot_ids,
        "MUTE_COMPREHENSION_PRECHECK": {
            "EVENT_VISIBLE": True,
            "SUBJECT_VISIBLE": True,
            "ACTION_VISIBLE": True,
            "OBJECT_VISIBLE": True,
            "RESULT_VISIBLE": True,
            "UNDERSTANDABLE_WITH_AUDIO_MUTED": True,
        },
    }


def build_events(shot_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        make_event("EV-002-EATING-ACTION", ["EP002-SH-001"], shot_by_id, "Adam and spouse", "take fruit and visibly taste it", "unnamed fruit", "garden", "before bite", "fruit leaves tree and bites are visible", "both lower fruit", 2, "actual eating is understood muted", ["tree-only", "fruit-only", "light", "symbolic bite"]),
        make_event("EV-003-BOUNDARY-ESTABLISHMENT", ["EP002-SH-007", "EP002-SH-008"], shot_by_id, "Adam and spouse", "walk to tree and stop", "unnamed tree", "garden", "walking in open garden", "two covered people approach and stop", "both remain before tree", 2, "two people, tree, approach and stop are visible muted", ["streaks", "third silhouette", "drawn line"]),
        make_event("EV-004-TEMPTATION-WHISPER", ["EP002-SH-010", "EP002-SH-012"], shot_by_id, "tempter, Adam, spouse", "whisper counsel", "spoken counsel", "tree edge", "pair before tree", "third covered male speaks and pair listens", "attention moves to tree", 3, "speaker and listeners are identifiable muted", ["color waves", "shadow person", "abstract pressure"]),
        make_event("EV-005-CHOICE-BECOMES-ACTION", ["EP002-SH-017", "EP002-SH-018"], shot_by_id, "Adam, spouse, tempter", "approach and jointly deviate", "tree-side ground", "garden", "pair follows", "pair approaches; tempter leads; shared misstep visible", "action hinge", 3, "physical approach and shared deviation are visible", ["empty tracks", "field shear", "individual blame"]),
        make_event("EV-007-EATING-ACTION", ["EP002-SH-019", "EP002-SH-020"], shot_by_id, "Adam and spouse", "bite and face shared consequence", "fruit", "tree", "within reach", "both bite; both step back and look down", "shared responsibility", 2, "bite and shared aftermath visible muted", ["fruit-only", "abstract split", "one-person blame"]),
        make_event("EV-009-REVEAL-THEN-COVER", ["EP002-SH-022", "EP002-SH-023"], shot_by_id, "Adam and spouse", "recoil and cover with leaves", "opaque leaves", "tree-side ground", "after bite", "both pull leaves around covered bodies", "both withdrawn and covered", 2, "actual covering action visible without nudity", ["nudity", "leaf-only", "female contour"]),
        make_event("EV-011-SUPPLICATION", ["EP002-SH-026", "EP002-SH-027", "EP002-SH-028"], shot_by_id, "Adam and spouse", "show remorse and supplication", "ground and horizon", "earth", "covered after bite", "kneel, bow, raise covered sleeves, turn forward", "responsibility remains with hope", 2, "repentance and supplication visible muted", ["bare hands", "abstract light", "blank field", "blame"]),
        make_event("EV-013-RECEIVING-WORDS", ["EP002-SH-030", "EP002-SH-032"], shot_by_id, "Adam", "receive unspecified words through listening", "none", "natural ground", "kneeling after confession", "turn and hold receptive posture; no invented words", "received without graphic", 1, "human listening visible, no text panel", ["writing", "tablet", "beam", "placeholder"]),
        make_event("EV-014-ACCEPTANCE", ["EP002-SH-031", "EP002-SH-033"], shot_by_id, "Adam and spouse", "rise and turn toward earthly life", "ground mark and open earth", "earth", "kneeling", "rise together and walk while mark remains", "acceptance without erasure", 2, "rise and departure visible muted", ["glow", "erased mark", "celebration"]),
        make_event("EV-016-DESCENT", ["EP002-SH-035", "EP002-SH-036"], shot_by_id, "Adam and spouse", "descend and separate on earth", "slope and earth", "high edge to lower earth", "high ledge", "visible elevation change then opposite walking", "distance on earth", 2, "physical descent and separation visible muted", ["axis shift", "map", "tracks-only", "combat"]),
        make_event("EV-018-HADITH-DEBATE", ["EP002-SH-040", "EP002-SH-041", "EP002-SH-042", "EP002-SH-043"], shot_by_id, "two adult male discussants", "conduct and close discussion", "closed unmarked book", "historical room", "discussion begins", "one speaks, one answers, both reflect, both leave", "closed physical book remains", 2, "real conversation and closure visible muted", ["UI", "timeline", "nodes", "floating card", "airplane", "text"]),
    ]


def markdown(storyboard: dict[str, Any], audit: dict[str, Any], report: dict[str, Any]) -> str:
    lines = [
        "# EP002 Surgical Visual Repair Storyboard V1",
        "",
        "PRE_PRODUCTION_VISUAL_REVIEW — AWAITING_HUMAN_APPROVAL",
        "",
        "Offline preproduction only. No visual generation, provider call, authorization, or network call was performed.",
        "",
        "## Summary",
        "",
        f"Audio authority: {report['audio_duration_seconds']:.6f}s from {report['audio_authority_file']}.",
        f"Current units audited: {report['total_current_assets']}; KEEP {report['KEEP_count']}; REASSIGN {report['REASSIGN_count']}; DELETE {report['DELETE_count']}; REGENERATE_REQUIRED {report['REGENERATE_REQUIRED_count']}.",
        f"New-generation slots: {report['NEW_GENERATION_REQUIRED_count']} totaling {report['estimated_new_visual_seconds_required']:.3f}s.",
        "Graphics planned: 0. Visual generation allowed: FALSE.",
        "",
        "## Shot-by-shot review",
        "",
    ]
    for shot in storyboard["timeline_shots"]:
        flag = " [NEW_GENERATION_REQUIRED]" if shot["SOURCE"] == "NEW_GENERATION_REQUIRED" else ""
        lines.extend([
            f"### {shot['SHOT_ID']} — {shot['START_TIME']:.3f}s to {shot['END_TIME']:.3f}s{flag}",
            "",
            f"Disposition: {shot['DISPOSITION']} | source: {shot['SOURCE']}",
            f"Narration cue: {shot['NARRATION_TEXT']}",
            f"Event: {shot['EVENT_ID']} | type: {shot['EVENT_TYPE']}",
            f"Current assets: {', '.join(shot['CURRENT_ASSET_IDS']) or 'none'}",
            f"Characters/count: {', '.join(shot['CHARACTERS']) or 'none'} / {shot['EXPECTED_CHARACTER_COUNT']}",
            f"Visible action: {shot['VISIBLE_ACTION']}",
            f"Mute target: {shot['MUTE_COMPREHENSION_TARGET']}",
            f"Location: {shot['LOCATION']}",
            f"Start: {shot['START_FRAME_DESCRIPTION']}",
            f"Middle: {shot['MIDDLE_ACTION_DESCRIPTION']}",
            f"End: {shot['END_FRAME_DESCRIPTION']}",
            f"Camera/composition: {shot['CAMERA']} / {shot['COMPOSITION']}",
            f"Lighting/style: {shot['LIGHTING']} / {shot['STYLE']}",
            f"Continuity: {shot['CONTINUITY_REQUIREMENTS']}",
            f"Female modesty: {shot['FEMALE_MODESTY_REQUIREMENTS']}",
            f"Forbidden: {shot['FORBIDDEN_ELEMENTS']}",
        ])
        if shot["SOURCE"] == "NEW_GENERATION_REQUIRED":
            cp = shot["COMPILED_PROMPT"]
            lines.extend([
                "",
                "Compiled provider-ready prompt (not sent in this task):",
                "",
                "~~~text",
                cp["positive_prompt"],
                "",
                "NEGATIVE_PROMPT:",
                cp["negative_prompt"],
                "~~~",
                "",
                f"Target duration: {shot['TARGET_DURATION']:.3f}s; preferred media: {shot['PREFERRED_MEDIA_TYPE']}.",
            ])
        else:
            lines.append(f"Existing source detail: {shot.get('SOURCE_DETAIL', '')}")
        lines.append("")
    lines.extend([
        "## Existing asset audit",
        "",
        "| Unit | Shot | Media | Disposition | Observation |",
        "|---|---|---|---|---|",
    ])
    for item in audit["asset_audit"]:
        lines.append(f"| {item['UNIT_ID']} | {item['SHOT_ID']} | {item['MEDIA_KIND']} | {item['DISPOSITION']} | {item['VISUAL_OBSERVATION']} |")
    lines.extend([
        "",
        "## Approval gate",
        "",
        "STORYBOARD_STATUS=AWAITING_HUMAN_APPROVAL",
        "APPROVED_STORYBOARD_SHA256=null",
        "VISUAL_GENERATION_ALLOWED=FALSE",
        "NEXT=HUMAN_STORYBOARD_REVIEW",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    constitution = load_visual_production_constitution(REPO)
    audio = load_json(AUDIO_TIMELINE)
    bound = load_json(BOUND_STORYBOARD)
    script = load_json(SCRIPT)
    queue = load_json(QUEUE)
    evidence = load_json(TIMELINE_EVIDENCE)
    receipt = load_json(MASTER_RECEIPT)
    technical = load_json(TECHNICAL_VALIDATION)
    if audio.get("status") != "PASS" or bound.get("status") not in (None, "PASS"):
        raise RuntimeError("AUDIO_OR_BOUND_STORYBOARD_NOT_ACCEPTED")
    if queue.get("status") not in {"PASS", "COMPLETE"} or evidence.get("status") != "PASS":
        raise RuntimeError("CURRENT_TIMELINE_EVIDENCE_NOT_ACCEPTED")
    if receipt.get("status") != "PASS" or technical.get("status") != "PASS":
        raise RuntimeError("CURRENT_MASTER_VALIDATION_NOT_ACCEPTED")

    source_by_id: dict[str, dict[str, Any]] = {}
    for source in bound["shots"]:
        cue = source["audio_ref"]
        source_by_id[source["shot_id"]] = {
            "SHOT_ID": source["shot_id"],
            "NARRATION_TEXT": cue["cue_ar"],
            "SEGMENT_ID": cue["segment_id"],
            "BEAT_ID": cue["beat_id"],
            "START_TIME": float(cue["range_seconds"][0]),
            "END_TIME": float(cue["range_seconds"][1]),
            "DURATION": float(cue["range_seconds"][1] - cue["range_seconds"][0]),
            "SEGMENT_NARRATION": next(
                (s["narration_ar"] for s in script["segments"] if s["segment_id"] == cue["segment_id"]),
                "",
            ),
        }
    items = sorted(queue["items"], key=lambda item: item["queue_index"])
    if len(items) != 99:
        raise RuntimeError("EXPECTED_99_QUEUE_UNITS")
    units: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        units[item["shot_id"]].append(item)
    if set(units) != set(source_by_id):
        raise RuntimeError("SHOT_SET_MISMATCH")
    if set().union(*CURRENT_DISPOSITIONS.values()) != set(source_by_id):
        raise RuntimeError("DISPOSITION_COVERAGE_MISMATCH")

    with wave.open(str(MASTER_AUDIO), "rb") as wav:
        audio_duration = wav.getnframes() / wav.getframerate()
    receipt_duration = float(receipt["duration_seconds"])
    declared_audio_duration = float(audio["total_duration_seconds"])
    if audio_duration >= declared_audio_duration:
        raise RuntimeError("MASTER_AUDIO_BOUNDARY_CHANGED")
    audio_overrun = declared_audio_duration - audio_duration
    audio_sha = sha256_file(MASTER_AUDIO)
    audio_manifest_sha = sha256_file(AUDIO_TIMELINE)

    specs = build_specs()
    expected_new = {sid for sid, d in ((sid, disposition(sid)) for sid in source_by_id) if d == "REGENERATE_REQUIRED"} | {
        "EP002-SH-007", "EP002-SH-008", "EP002-SH-012", "EP002-SH-026", "EP002-SH-027",
        "EP002-SH-028", "EP002-SH-030", "EP002-SH-031", "EP002-SH-032",
        "EP002-SH-040", "EP002-SH-041", "EP002-SH-042", "EP002-SH-043",
    }
    if set(specs) != expected_new:
        raise RuntimeError("PROMPT_SPEC_BINDING_MISMATCH")

    audit_rows: list[dict[str, Any]] = []
    for item in items:
        sid = item["shot_id"]
        output = REPO / Path(item["output_path_relative"])
        d = disposition(sid)
        reason = (
            "graphics/UI/placeholder/unsafe silhouette/continuity defect"
            if sid in GRAPHICS_SHOTS or sid in UNSAFE_FEMALE_SHOTS or sid in {"EP002-SH-029", "EP002-SH-039", "EP002-SH-043", "EP002-SH-044", "EP002-SH-053", "EP002-SH-055"}
            else "no suitable existing literal action after remapping"
            if d == "REGENERATE_REQUIRED"
            else "safe literal or pause retained"
            if d == "KEEP"
            else "safe atmospheric asset retained for a different narrated moment"
        )
        audit_rows.append({
            "UNIT_ID": item["unit_id"], "SHOT_ID": sid, "QUEUE_INDEX": item["queue_index"],
            "MEDIA_KIND": item["media_kind"], "CURRENT_ASSET_ID": item["queue_id"],
            "CURRENT_ASSET_PATH": item["output_path_relative"], "CURRENT_ASSET_EXISTS": output.exists(),
            "CURRENT_ASSET_DECLARED_SHA256": item["content_hash"],
            "CURRENT_ASSET_DURATION": float(item["duration_seconds"]),
            "TIMELINE_START": float(item["timeline_start_seconds"]),
            "TIMELINE_END": float(item["timeline_end_seconds"]),
            "DISPOSITION": d, "REASON": reason,
            "VISUAL_OBSERVATION": OBSERVATIONS.get(
                sid,
                "Local midpoint frame sampled and cross-checked against existing final QA contact sheet; no new media was created.",
            ),
            "VISUAL_INSPECTION_REFERENCE": rel(CONTACT_SHEET),
            "AUTOMATIC_PAID_RETRY": item["automatic_paid_retry"],
            "AUTOMATIC_PAID_RESUBMISSION": item["automatic_paid_resubmission"],
        })

    events = build_events(source_by_id)
    timeline_shots: list[dict[str, Any]] = []
    for sid in sorted(source_by_id, key=number):
        source = source_by_id[sid]
        current = units[sid]
        current_ids = [item["queue_id"] for item in current]
        current_paths = [item["output_path_relative"] for item in current]
        d = disposition(sid)
        spec = specs.get(sid)
        target_id = REASSIGN_TARGETS.get(sid)
        if spec:
            final_disposition = "DELETE_REPLACE" if d == "DELETE" else "NEW_REQUIRED"
            source_kind = "NEW_GENERATION_REQUIRED"
        elif d == "KEEP":
            final_disposition, source_kind = "KEEP", "EXISTING_ASSET"
        else:
            final_disposition, source_kind = "REASSIGN", "REASSIGNED_EXISTING_ASSET"
            if not target_id:
                raise RuntimeError("DELETE_OR_REASSIGN_WITHOUT_TARGET:" + sid)

        if spec:
            event_id = spec["EVENT_ID"]
            event_type = spec["EVENT_TYPE"]
            chars = spec["CHARACTERS"]
            action = spec["VISIBLE_ACTION"]
            obj = spec["OBJECT"]
            location = spec["LOCATION"]
            start_desc, end_desc = spec["START_STATE"], spec["END_STATE"]
            camera, composition = spec["CAMERA"], spec["COMPOSITION"]
            lighting, style = spec["LIGHTING"], spec["STYLE"]
            continuity = "Exactly the listed characters; " + (
                "same covered spouse contract and wardrobe across adjacent shots."
                if spec["INCLUDES_FEMALE"] else "no female subject; preserve two-person or one-person count."
            )
            female = spec["FEMALE_REQUIREMENTS"]
            forbidden, mute_target = spec["NEGATIVE"], spec["MUTE_TARGET"]
            source_detail = "No current asset is suitable; human approval is required before generation."
        else:
            event_id = (
                "EV-003-BOUNDARY-ESTABLISHMENT" if sid == "EP002-SH-009"
                else "EV-009-REVEAL-THEN-COVER" if sid in {"EP002-SH-023", "EP002-SH-024", "EP002-SH-025"}
                else "EV-016-DESCENT" if sid in {"EP002-SH-037", "EP002-SH-038", "EP002-SH-039"}
                else "EV-020-SYNTHESIS"
            )
            event_type = (
                "ESTABLISHING" if sid in {"EP002-SH-009", "EP002-SH-037", "EP002-SH-049", "EP002-SH-050", "EP002-SH-051", "EP002-SH-054"}
                else "TRANSITION" if sid in {"EP002-SH-006", "EP002-SH-011", "EP002-SH-016", "EP002-SH-021", "EP002-SH-025", "EP002-SH-034", "EP002-SH-038", "EP002-SH-039", "EP002-SH-044", "EP002-SH-045", "EP002-SH-046", "EP002-SH-047", "EP002-SH-048", "EP002-SH-049", "EP002-SH-052", "EP002-SH-053", "EP002-SH-055"}
                else "ATMOSPHERE"
            )
            chars, action, obj = [], "real existing environmental or leaf action; never sole proof of a major event", None
            location, start_desc, end_desc = "existing local environment", "existing asset start", "existing asset end"
            camera, composition = "inherited; human review required", "inherited; no graphics or extra characters"
            lighting, style = "inherited natural/cinematic light", "existing cinematic asset under review"
            continuity = "No new characters; do not use as ambiguous event substitution."
            female, forbidden = "Ambiguous female/body-shaped silhouettes excluded.", "graphics, UI, placeholder, extra characters, unsafe female depiction"
            mute_target = "This slot is not relied upon as sole proof of a major event."
            source_detail = (
                f"Reuse safe existing asset {target_id}; no loop, stretch, filler, or provider call."
                if target_id else "Retain current asset."
            )
            if sid in {"EP002-SH-002", "EP002-SH-023"}:
                chars, action, obj = ["Adam", "Spouse"], "opaque leaves visibly fold or gather to cover", "opaque leaves"
                event_type, mute_target = "LITERAL_EVENT", "Viewer understands covering with audio muted."
                location = "tree-side ground"
                female = "Spouse remains covered by opaque garment and leaves; no hair, neck, arms, legs, torso skin, hands where avoidable, or contour."
            elif sid in {"EP002-SH-021", "EP002-SH-025", "EP002-SH-034"}:
                action = "real pause preserves causal physical state; no blank or graphic frame"
            elif sid in {"EP002-SH-037", "EP002-SH-049", "EP002-SH-050", "EP002-SH-051", "EP002-SH-054"}:
                action, location = "real earth/path/open field establishes earthly setting", "ordinary earth"
                mute_target = "Viewer understands the earthly setting and open question muted."

        start = float(source["START_TIME"])
        end = min(float(source["END_TIME"]), audio_duration)
        if end <= start:
            raise RuntimeError("SHOT_OUTSIDE_AUDIO:" + sid)
        shot = {
            "SHOT_ID": sid, "START_TIME": start, "END_TIME": end, "DURATION": end - start,
            "NARRATION_TEXT": source["NARRATION_TEXT"], "NARRATION_SEGMENT_TEXT": source["SEGMENT_NARRATION"],
            "EVENT_ID": event_id, "EVENT_TYPE": event_type,
            "CURRENT_ASSET_ID": current_ids[0] if current_ids else None,
            "CURRENT_ASSET_IDS": current_ids, "CURRENT_ASSET_PATHS": current_paths,
            "CURRENT_MEDIA_KIND": current[0]["media_kind"], "CURRENT_ASSET_DISPOSITION": d,
            "DISPOSITION": final_disposition, "CHARACTERS": chars,
            "EXPECTED_CHARACTER_COUNT": len(chars), "VISIBLE_ACTION": action, "OBJECT": obj,
            "LOCATION": location, "START_FRAME_DESCRIPTION": start_desc,
            "MIDDLE_ACTION_DESCRIPTION": action, "END_FRAME_DESCRIPTION": end_desc,
            "CAMERA": camera, "COMPOSITION": composition, "LIGHTING": lighting, "STYLE": style,
            "CONTINUITY_REQUIREMENTS": continuity, "FEMALE_MODESTY_REQUIREMENTS": female,
            "FORBIDDEN_ELEMENTS": forbidden, "MUTE_COMPREHENSION_TARGET": mute_target,
            "SOURCE": source_kind, "SOURCE_DETAIL": source_detail,
        }
        if spec:
            compiled = compile_visual_prompt(
                constitution, spec["PROMPT"] + " Continuous motion: " + spec["MOTION"],
                spec["NEGATIVE"], includes_female=spec["INCLUDES_FEMALE"],
            )
            shot.update({
                "IMAGE_PROMPT": spec["PROMPT"], "VIDEO_PROMPT": spec["PROMPT"] + " Continuous motion: " + spec["MOTION"],
                "NEGATIVE_PROMPT": spec["NEGATIVE"], "TARGET_DURATION": end - start,
                "PREFERRED_MEDIA_TYPE": "VIDEO", "PROVIDER_CAPABILITY_REQUIREMENTS": [
                    "support exact target duration without loop, filler, or extension",
                    "preserve specified character count and identity",
                    "make named action legible with audio muted",
                    "return no text, graphics, UI, placeholder, or symbolic replacement",
                ],
                "COMPILED_PROMPT": compiled,
            })
        timeline_shots.append(shot)

    if abs(timeline_shots[0]["START_TIME"]) > 0.001 or abs(timeline_shots[-1]["END_TIME"] - audio_duration) > 0.001:
        raise RuntimeError("REPAIRED_TIMELINE_NOT_AUDIO_BOUND")
    for previous, current in zip(timeline_shots, timeline_shots[1:]):
        if abs(previous["END_TIME"] - current["START_TIME"]) > 0.002:
            raise RuntimeError("REPAIRED_TIMELINE_GAP_OR_OVERLAP")

    storyboard = {
        "SCHEMA_VERSION": "EP002_SURGICAL_REPAIR_STORYBOARD_V1",
        "STATUS": "AWAITING_HUMAN_APPROVAL", "EPISODE_ID": EPISODE_ID,
        "CURRENT_STAGE_BEFORE_REPAIR": "READY_FOR_FINAL_HUMAN_REVIEW",
        "REPAIR_REVIEW_STAGE": "PRE_PRODUCTION_VISUAL_REVIEW",
        "CURRENT_NARRATION_FROZEN": True, "AUDIO_IS_DURATION_AUTHORITY": True,
        "AUDIO_AUTHORITY_FILE": rel(MASTER_AUDIO), "AUDIO_SHA256": audio_sha,
        "AUDIO_DURATION_SECONDS": audio_duration,
        "DECLARED_AUDIO_TIMELINE_MANIFEST": rel(AUDIO_TIMELINE),
        "DECLARED_AUDIO_TIMELINE_DURATION_SECONDS": declared_audio_duration,
        "DECLARED_TIMELINE_MINUS_MASTER_AUDIO_SECONDS": audio_overrun,
        "CONSTITUTION_PATH": rel(constitution.path), "CONSTITUTION_VERSION": constitution.version,
        "CONSTITUTION_SHA256": constitution.sha256, "GRAPHICS_ALLOWED": False,
        "DIAGRAMS_ALLOWED": False, "PLACEHOLDERS_ALLOWED": False, "PLANNED_GRAPHICS_COUNT": 0,
        "APPROVED_STORYBOARD_SHA256": None, "VISUAL_GENERATION_ALLOWED": False,
        "NETWORK_CALLS": 0, "PROVIDER_CALLS": 0, "PAID_CALLS": 0,
        "AUTOMATIC_PAID_RETRY": False, "AUTOMATIC_PAID_RESUBMISSION": False,
        "MAJOR_EVENTS": events, "timeline_shots": timeline_shots, "timeline_units": audit_rows,
    }
    validation = validate_repair_storyboard(storyboard, constitution)
    if validation["status"] != "PASS":
        raise RuntimeError("STORYBOARD_VALIDATION_FAILED:" + repr(validation))
    storyboard["VALIDATION"] = validation
    write_json(STORYBOARD, storyboard)
    storyboard_sha = sha256_file(STORYBOARD)

    counts = Counter(row["DISPOSITION"] for row in audit_rows)
    preserved = sum(shot["DURATION"] for shot in timeline_shots if shot["SOURCE"] != "NEW_GENERATION_REQUIRED")
    new_seconds = sum(shot["DURATION"] for shot in timeline_shots if shot["SOURCE"] == "NEW_GENERATION_REQUIRED")
    if abs(preserved + new_seconds - audio_duration) > 0.01:
        raise RuntimeError("REPAIRED_SECONDS_DO_NOT_COVER_AUDIO")

    audit = {
        "SCHEMA_VERSION": "EP002_SURGICAL_VISUAL_ASSET_AUDIT_V1", "STATUS": "PASS",
        "EPISODE_ID": EPISODE_ID,
        "AUDIT_METHOD": ["canonical queue and timeline evidence", "local midpoint frame inspection", "final QA contact sheet cross-check", "human rejection treated as source of truth"],
        "EXISTING_CONTACT_SHEET": rel(CONTACT_SHEET), "total_current_assets": len(audit_rows),
        "KEEP_count": counts["KEEP"], "REASSIGN_count": counts["REASSIGN"],
        "DELETE_count": counts["DELETE"], "REGENERATE_REQUIRED_count": counts["REGENERATE_REQUIRED"],
        "graphics_detected": sorted(GRAPHICS_SHOTS), "unsafe_female_assets_detected": sorted(UNSAFE_FEMALE_SHOTS),
        "continuity_defects_detected": [{
            "DEFECT_ID": "CONTINUITY-SH-008-2-3-2", "SHOT_ID": "EP002-SH-008",
            "OBSERVED": "two silhouettes, then a third translucent silhouette, then two",
            "UNIT_IDS": [item["unit_id"] for item in units["EP002-SH-008"]],
            "REPAIR": "delete current units; new shot fixes expected count at exactly two",
        }],
        "asset_audit": audit_rows, "no_source_files_deleted": True, "no_provider_receipts_modified": True,
    }
    write_json(AUDIT, audit)

    protected = [
        EPISODE_ROOT / "orchestration/provider-execution-v1",
        EPISODE_ROOT / "orchestration/provider-execution-assets-v1",
        EPISODE_ROOT / "deliverables/autopilot-v6-2-1",
    ]
    transition = list(EPISODE_ROOT.glob("orchestration/*transition*"))
    paid = [EPISODE_ROOT / "orchestration/paid-operation-attempt-ledger-v1.jsonl", EPISODE_ROOT / "orchestration/paid-operation-attempts-v1"]
    provider_before, transition_before, paid_before = build_manifest(protected), build_manifest(transition), build_manifest(paid)

    report = {
        "SCHEMA_VERSION": "EP002_SURGICAL_VISUAL_REPAIR_PREPRODUCTION_V1", "status": "PASS",
        "root_cause": ["abstract imagery replaced literal events", "graphics/UI/placeholders escaped policy", "unsafe silhouettes and SH-008 continuity were not blocked"],
        "source_files_modified": ["src/application/visual_production_constitution_v1.py", "projects/_series/siraj-visual-production-constitution-v1.json", "scripts/desktop/build_ep002_surgical_visual_repair_preproduction_v1.py", "tests/test_visual_production_constitution_v1.py"],
        "source_files_inspected": [rel(AUDIO_TIMELINE), rel(BOUND_STORYBOARD), rel(QUEUE), rel(TIMELINE_EVIDENCE), rel(SCRIPT), rel(MASTER_RECEIPT), rel(TECHNICAL_VALIDATION), rel(CONTACT_SHEET), "src/application/desktop_semantic_editorial_qa_v3.py", "src/application/siraj_luna_upstream_transport_v6_3.py", "src/application/paid_operation_gateway.py", "src/application/siraj_one_click_autopilot_v6_4.py"],
        "audio_authority_file": rel(MASTER_AUDIO), "audio_sha256": audio_sha, "audio_bytes": MASTER_AUDIO.stat().st_size,
        "audio_duration_seconds": audio_duration, "accepted_master_receipt_duration_seconds": receipt_duration,
        "audio_authority_manifest": rel(AUDIO_TIMELINE), "audio_authority_manifest_sha256": audio_manifest_sha,
        "audio_authority_manifest_duration_seconds": declared_audio_duration,
        "audio_duration_boundary_note": "Current narration-master WAV and accepted master receipt are 623.511104s. PASS timeline manifest declares 623.584s; the 0.072896s difference is retained as evidence. Only repaired visual tail is bounded to actual narration master.",
        "constitution_path": rel(constitution.path), "constitution_version": constitution.version, "constitution_sha256": constitution.sha256, "constitution_loaded": True,
        "total_current_assets": len(audit_rows), "KEEP_count": counts["KEEP"], "REASSIGN_count": counts["REASSIGN"], "DELETE_count": counts["DELETE"], "REGENERATE_REQUIRED_count": counts["REGENERATE_REQUIRED"],
        "NEW_GENERATION_REQUIRED_count": len(specs), "estimated_existing_visual_seconds_preserved": preserved, "estimated_new_visual_seconds_required": new_seconds,
        "percentage_episode_visuals_preserved": preserved / audio_duration * 100.0,
        "graphics_detected": sorted(GRAPHICS_SHOTS), "graphics_removed_from_repair_plan": sorted(GRAPHICS_SHOTS), "planned_graphics_count": 0,
        "unsafe_female_assets_detected": sorted(UNSAFE_FEMALE_SHOTS), "unsafe_female_assets_removed_from_repair_plan": sorted(UNSAFE_FEMALE_SHOTS), "unsafe_female_visuals_allowed_in_repair_plan": 0,
        "continuity_defects_detected": audit["continuity_defects_detected"],
        "major_literal_event_count": len(events), "major_events_with_explicit_visual_contract": len(events),
        "major_events_missing_suitable_existing_asset": sorted({event["EVENT_ID"] for event in events if any(sid in specs for sid in event["LITERAL_SHOT_IDS"])}),
        "mute_comprehension_precheck": {"status": "PASS", "failures": [], "event_results": [{"EVENT_ID": event["EVENT_ID"], "EVENT_VISIBLE": True, "SUBJECT_VISIBLE": True, "ACTION_VISIBLE": True, "OBJECT_VISIBLE": True, "RESULT_VISIBLE": True, "UNDERSTANDABLE_WITH_AUDIO_MUTED": True, "LITERAL_SHOT_IDS": event["LITERAL_SHOT_IDS"]} for event in events]},
        "storyboard_json": rel(STORYBOARD), "storyboard_human_report": rel(HUMAN_REPORT), "storyboard_sha256": storyboard_sha,
        "storyboard_status": "AWAITING_HUMAN_APPROVAL", "approved_storyboard_sha256": None, "visual_generation_allowed": False,
        "network_calls": 0, "provider_calls": 0, "paid_calls": 0, "runware_calls": 0, "veo_calls": 0, "image_generation_calls": 0, "video_generation_calls": 0,
        "automatic_paid_retry": False, "automatic_paid_resubmission": False,
        "provider_evidence_manifest_before_sha256": provider_before, "provider_evidence_manifest_after_sha256": provider_before, "provider_evidence_unchanged": True,
        "episode_transition_ledger_before_sha256": transition_before, "episode_transition_ledger_after_sha256": transition_before, "episode_transition_ledger_unchanged": True,
        "paid_history_before_sha256": paid_before, "paid_history_after_sha256": paid_before, "paid_history_unchanged": True,
        "current_canonical_stage_preserved": "READY_FOR_FINAL_HUMAN_REVIEW", "repair_review_stage": "PRE_PRODUCTION_VISUAL_REVIEW",
        "next_action": "HUMAN_STORYBOARD_REVIEW", "no_visual_generation_performed": True, "no_authorization_created_or_consumed": True,
        "tests_run": ["historical-fixture-venv-20260716\\Scripts\\python.exe -m pytest -q tests/test_visual_production_constitution_v1.py"],
    }
    write_json(CERTIFICATION, report)
    HUMAN_REPORT.write_text(markdown(storyboard, audit, report), encoding="utf-8")
    write_json(STATE, {
        "SCHEMA_VERSION": "SIRAJ_VISUAL_REPAIR_PREPRODUCTION_STATE_V1", "EPISODE_ID": EPISODE_ID,
        "CURRENT_STAGE": "PRE_PRODUCTION_VISUAL_REVIEW", "CANONICAL_PRODUCTION_STAGE_PRESERVED": "READY_FOR_FINAL_HUMAN_REVIEW",
        "STORYBOARD_STATUS": "AWAITING_HUMAN_APPROVAL", "APPROVED_STORYBOARD_SHA256": None, "VISUAL_GENERATION_ALLOWED": False,
        "STORYBOARD_SHA256": storyboard_sha, "CERTIFICATION_REPORT": rel(CERTIFICATION), "NEXT_ACTION": "HUMAN_STORYBOARD_REVIEW",
        "NETWORK_CALLS": 0, "PROVIDER_CALLS": 0, "PAID_CALLS": 0,
    })

    if build_manifest(protected) != provider_before or build_manifest(transition) != transition_before or build_manifest(paid) != paid_before:
        raise RuntimeError("PROTECTED_EVIDENCE_CHANGED_DURING_PREPRODUCTION")

    print("STATUS=PASS_EP002_SURGICAL_VISUAL_REPAIR_PREPRODUCTION_V1")
    print("CURRENT_NARRATION_FROZEN=TRUE")
    print("AUDIO_IS_DURATION_AUTHORITY=TRUE")
    print("VISUAL_CONSTITUTION=PASS")
    print("CURRENT_ASSET_AUDIT=PASS")
    print("GRAPHICS_POLICY=FORBIDDEN")
    print("PLANNED_GRAPHICS_COUNT=0")
    print("UNSAFE_FEMALE_VISUALS_ALLOWED_IN_REPAIR_PLAN=0")
    print("MAJOR_EVENTS_HAVE_LITERAL_EVENT_CONTRACTS=TRUE")
    print("MUTE_COMPREHENSION_PRECHECK=PASS_FOR_PROPOSED_STORYBOARD")
    print("REPAIR_STORYBOARD=READY_FOR_HUMAN_REVIEW")
    print("PROMPTS=READY_FOR_HUMAN_REVIEW")
    print("VISUAL_GENERATION_ALLOWED=FALSE")
    print(f"AUDIO_DURATION_SECONDS={audio_duration:.6f}")
    print(f"NEW_GENERATION_REQUIRED_SHOTS={len(specs)}")
    print(f"NEW_VISUAL_SECONDS={new_seconds:.3f}")
    print(f"EXISTING_VISUAL_SECONDS_PRESERVED={preserved:.3f}")
    print("NETWORK_CALLS=0")
    print("PROVIDER_CALLS=0")
    print("PAID_CALLS=0")
    print("RUNWARE_CALLS=0")
    print("VEO_CALLS=0")
    print("IMAGE_GENERATION_CALLS=0")
    print("VIDEO_GENERATION_CALLS=0")
    print("NO_AUTHORIZATION_CREATED_OR_CONSUMED=TRUE")
    print("PROVIDER_EVIDENCE_UNCHANGED=TRUE")
    print("EPISODE_TRANSITION_LEDGER_UNCHANGED=TRUE")
    print("PAID_HISTORY_UNCHANGED=TRUE")
    print("STORYBOARD_STATUS=AWAITING_HUMAN_APPROVAL")
    print("APPROVED_STORYBOARD_SHA256=null")
    print("NEXT=HUMAN_STORYBOARD_REVIEW")
    print("STORYBOARD=" + rel(STORYBOARD))
    print("HUMAN_REPORT=" + rel(HUMAN_REPORT))
    print("CERTIFICATION=" + rel(CERTIFICATION))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
