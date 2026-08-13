"""EP002 V2.4 reviewed visual-repair paid execution.

This is a dedicated repair boundary for the exact human-approved V2.4
storyboard.  It is intentionally separate from the historical Episode 002
provider plan, and it never treats a CLI mapping as Desktop authorization.

Paid submissions:
- require an in-memory capability issued for one Desktop UI session;
- are bound to the exact V2.4 storyboard and approval receipt;
- are first-attempt only;
- stop on the first failed/unknown/unresolved unit;
- never retry or resubmit automatically;
- never start montage or QA automatically.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
import base64
import hashlib
import json
import shutil
import subprocess
import threading
import uuid
import zipfile

from src.application.artifact_provenance_v1 import (
    append_jsonl,
    canonical_sha256,
    sha256_file,
    utc_now,
)
from src.application.desktop_provider_execution_v1 import (
    CanonicalRunwarePaidGateway,
    _provider_api_key,
)
from src.application.paid_operation_gateway import PaidOperationRequest
from src.application.provider_model_contracts import (
    CONTRACT_VERSION as PROVIDER_CONTRACT_VERSION,
    validate_runware_task,
)
from src.application.siraj_episode_master_authorization_v6_6 import (
    master_authorization_active,
    master_authorization_reference,
)


EPISODE_ID = "episode-002-adam-temptation-fall-repentance"
STAGE = "EP002_V24_REPAIR_PROVIDER_EXECUTION"
DESKTOP_SOURCE = "DESKTOP_UI"

STORYBOARD_REL = Path(
    "projects/episode-002-adam-temptation-fall-repentance/"
    "preproduction/EP002_SURGICAL_REPAIR_STORYBOARD_V2_4.json"
)
APPROVAL_REL = Path(
    "projects/episode-002-adam-temptation-fall-repentance/"
    "orchestration/ep002-v2-4-final-human-approval-v1.json"
)
CERTIFICATION_REL = Path(
    "projects/episode-002-adam-temptation-fall-repentance/"
    "orchestration/ep002-surgical-visual-repair-preproduction-v2-4.json"
)
FEMALE_REVIEW_REL = Path(
    "projects/episode-002-adam-temptation-fall-repentance/"
    "orchestration/ep002-legacy-female-temporal-human-review-v2-4.json"
)
DOSSIERS_REL = Path(
    "projects/episode-002-adam-temptation-fall-repentance/"
    "preproduction/EP002_CHARACTER_EVIDENCE_DOSSIERS_V2_4.json"
)
SOURCE_BINDING_REL = Path(
    "projects/episode-002-adam-temptation-fall-repentance/"
    "orchestration/ep002-source-binding-v2-4.json"
)
CONSTITUTION_REL = Path(
    "projects/_series/siraj-visual-production-constitution-v2-4.json"
)
PRICING_REL = Path(
    "projects/_series/siraj-media-pricing-registry-v2.json"
)
EXECUTION_ROOT_REL = Path(
    "projects/episode-002-adam-temptation-fall-repentance/"
    "orchestration/ep002-v2-4-repair-provider-execution-v1"
)
LEDGER_NAME = "attempt-ledger-v1.jsonl"
STATE_NAME = "state-v1.json"
REFERENCE_DIR_NAME = "reference-frames-v1"
REVIEW_DIR_NAME = "render-conformance-review-v1"

EXPECTED_STORYBOARD_SHA256 = (
    "a01f945615bbd18409745607b98fba87bba39c71ffa99bc2019cc0462c9faef8"
)
EXPECTED_PLAN_SHA256 = (
    "3ea9b8d751fd7f75433128e031c462e1837f633c4df99317660ebacf7234c152"
)
EXPECTED_CERTIFICATION_SHA256 = "f123f4cf62cc7ec4dccfcbabd741277c0e8fcdb748da5462804c7142ee5d6f63"
EXPECTED_FEMALE_REVIEW_SHA256 = "575a43abd2121072cc65eab26fd4f8ea2eeb2eed0ea72aa3a194e9d8084b94dd"
EXPECTED_DOSSIERS_SHA256 = "87e773ec7f7fc261eca1a2a3fc4f83df203f6c68fc6907d9446cb27315174589"
EXPECTED_SOURCE_BINDING_SHA256 = "b4fe69bc3c72e46c3c8062887bae3582a0c59c0019fa4c170db0c1470d381a00"
EXPECTED_CONSTITUTION_SHA256 = "5faa996be8ec9e4d18eb309d09bf4c561532829077997feb5d0320abfa8a7cfd"
EXPECTED_UNIT_COUNT = 27
EXPECTED_PROVIDER_SECONDS = 208
UNIT_PRICE_USD = 0.05
EXPECTED_COST_USD = 10.40
MAXIMUM_COST_USD = 12.00
MODEL = "google:veo@3.1-lite"

ATTEMPT_NAMESPACE = uuid.UUID("29164a96-eafb-4767-b169-b3ca4d15c22a")

_FORBIDDEN_PROMPT_TERMS = (
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


class EP002V24RepairExecutionError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class V24ProviderUnit:
    ordinal: int
    unit_id: str
    model: str
    duration_seconds: int
    continuity_group: str
    reference_frame_required: bool
    member_shot_ids: tuple[str, ...]
    positive_prompt: str
    seed: int
    expected_cost_usd: float

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class V24ExecutionPreview:
    status: str
    storyboard_sha256: str
    provider_plan_sha256: str
    planned_units: int
    completed_units: int
    remaining_units: int
    provider_seconds: int
    expected_cost_usd: float
    maximum_cost_usd: float
    unresolved_unit_ids: tuple[str, ...]
    review_package_path: str | None
    execution_allowed: bool

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class V24ExecutionOutcome:
    status: str
    completed_units: int
    skipped_completed_units: int
    planned_units: int
    expected_total_cost_usd: float
    maximum_cost_usd: float
    review_package_path: str | None
    next_stage: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class _DesktopCapability:
    __slots__ = ("token",)

    def __init__(self) -> None:
        self.token = uuid.uuid4().hex


def _repo_path(repo: Path, rel: Path) -> Path:
    return (repo / rel).resolve()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EP002V24RepairExecutionError("JSON_UNREADABLE:" + str(path)) from exc
    if not isinstance(value, dict):
        raise EP002V24RepairExecutionError("JSON_OBJECT_REQUIRED:" + str(path))
    return value


def _write_json_atomic(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(
        json.dumps(dict(value), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temp.replace(path)


def _runtime_uuid4(plan_sha256: str, unit_id: str) -> str:
    material = hashlib.sha256(
        (plan_sha256 + "\0" + unit_id).encode("utf-8")
    ).digest()[:16]
    raw = bytearray(material)
    raw[6] = (raw[6] & 0x0F) | 0x40
    raw[8] = (raw[8] & 0x3F) | 0x80
    return str(uuid.UUID(bytes=bytes(raw)))


def _stable_seed(continuity_group: str) -> int:
    digest = hashlib.sha256(
        ("SIRAJ_EP002_V24:" + continuity_group).encode("utf-8")
    ).hexdigest()
    return int(digest[:8], 16)


def _clean_prompt_text(value: str) -> str:
    return re_sub_whitespace(value)


def re_sub_whitespace(value: str) -> str:
    # Preserve line boundaries used to communicate time-segment progression,
    # but normalize accidental horizontal whitespace.
    lines = []
    for raw in str(value or "").replace("\r", "").split("\n"):
        line = " ".join(raw.strip().split())
        if line:
            lines.append(line)
    return "\n".join(lines)


def _provider_prompt_for_unit(
    unit: Mapping[str, Any],
    shots: Mapping[str, Mapping[str, Any]],
) -> str:
    duration = int(unit["PROVIDER_REQUEST_DURATION_SECONDS"])
    parts: list[str] = []
    for shot_id in unit["EDITORIAL_MEMBER_SHOT_IDS"]:
        shot = shots.get(str(shot_id))
        if not isinstance(shot, Mapping):
            raise EP002V24RepairExecutionError(
                "PLAN_MEMBER_SHOT_MISSING:" + str(shot_id)
            )
        bundle = shot.get("VISUAL_PROVIDER_PROMPT")
        if not isinstance(bundle, Mapping):
            raise EP002V24RepairExecutionError(
                "CANONICAL_VISUAL_PROVIDER_PROMPT_MISSING:" + str(shot_id)
            )
        text = _clean_prompt_text(str(bundle.get("positive_video") or ""))
        if not text:
            raise EP002V24RepairExecutionError(
                "POSITIVE_VIDEO_PROMPT_EMPTY:" + str(shot_id)
            )
        start = float(shot.get("PROVIDER_SOURCE_IN", 0.0))
        end = float(shot.get("PROVIDER_SOURCE_OUT", duration))
        if start < -1e-9 or end <= start or end > duration + 1e-9:
            raise EP002V24RepairExecutionError(
                "PROVIDER_SOURCE_RANGE_INVALID:" + str(shot_id)
            )
        parts.append(f"TIME SEGMENT {start:.3f}-{end:.3f}s: {text}")

    prefix = (
        f"Create one continuous {duration}-second cinematic shot for the "
        "approved SIRAJ Episode 002 storyboard. Follow the time-ordered visual "
        "directions exactly. Preserve character identity, wardrobe, environment, "
        "screen direction, lighting logic, anatomy, and physical continuity "
        "within this generation unit. Every action must be visually explicit "
        "and narratively meaningful. No filler, no generic scenery substitution, "
        "no symbolic replacement, no extra characters, no text, no graphics, "
        "no captions, no logos, no watermark. Use natural human motion, stable "
        "faces and anatomy, physically plausible object interaction, cinematic "
        "composition, and no morphing or warping."
    )
    prompt = prefix + "\n" + "\n".join(parts)
    prompt = _clean_prompt_text(prompt)
    if len(prompt) > 3000:
        raise EP002V24RepairExecutionError(
            f"PROVIDER_PROMPT_TOO_LONG:{unit['GENERATION_UNIT_ID']}:{len(prompt)}"
        )
    lowered = prompt.casefold()
    leaked = [
        term for term in _FORBIDDEN_PROMPT_TERMS
        if term.casefold() in lowered
    ]
    if leaked:
        raise EP002V24RepairExecutionError(
            "EXECUTION_STATE_LEAKED_IN_PROVIDER_PROMPT:"
            + str(unit["GENERATION_UNIT_ID"])
            + ":"
            + ",".join(leaked)
        )
    return prompt


def build_approved_provider_plan(
    storyboard: Mapping[str, Any],
) -> tuple[list[V24ProviderUnit], str]:
    if storyboard.get("EPISODE_ID") != EPISODE_ID:
        raise EP002V24RepairExecutionError("V24_EPISODE_ID_MISMATCH")
    if storyboard.get("STORYBOARD_STATUS") != "AWAITING_HUMAN_APPROVAL":
        raise EP002V24RepairExecutionError(
            "V24_PREAPPROVAL_ARTIFACT_STATUS_CHANGED"
        )
    if storyboard.get("APPROVED_STORYBOARD_SHA256") is not None:
        raise EP002V24RepairExecutionError(
            "V24_PREAPPROVAL_ARTIFACT_HASH_FIELD_CHANGED"
        )
    if storyboard.get("VISUAL_GENERATION_ALLOWED") is not False:
        raise EP002V24RepairExecutionError(
            "V24_PREAPPROVAL_VISUAL_GENERATION_FLAG_CHANGED"
        )
    if storyboard.get("PLANNED_GRAPHICS_COUNT") != 0:
        raise EP002V24RepairExecutionError("V24_GRAPHICS_MUST_EQUAL_ZERO")
    if storyboard.get("LEGACY_FEMALE_REUSE_COUNT") != 0:
        raise EP002V24RepairExecutionError(
            "V24_LEGACY_FEMALE_REUSE_MUST_EQUAL_ZERO"
        )
    if storyboard.get("CANONICAL_PROVIDER_PROMPT_FIELD") != "VISUAL_PROVIDER_PROMPT":
        raise EP002V24RepairExecutionError(
            "V24_CANONICAL_PROVIDER_PROMPT_FIELD_INVALID"
        )
    if storyboard.get("LEGACY_COMPILED_PROVIDER_PROMPT_CONSUMPTION_ALLOWED") is not False:
        raise EP002V24RepairExecutionError(
            "V24_LEGACY_COMPILED_PROMPT_MUST_BE_BLOCKED"
        )
    if storyboard.get("PLANNED_COST_WITHIN_CAP") is not True:
        raise EP002V24RepairExecutionError("V24_COST_WITHIN_CAP_REQUIRED")
    if abs(float(storyboard.get("PLANNED_COST_CAP_USD") or -1.0) - MAXIMUM_COST_USD) > 1e-9:
        raise EP002V24RepairExecutionError("V24_COST_CAP_MISMATCH")
    if abs(float(storyboard.get("PLANNED_VEO_720P_COST_USD") or -1.0) - EXPECTED_COST_USD) > 1e-9:
        raise EP002V24RepairExecutionError("V24_PLANNED_COST_MISMATCH")
    if int(storyboard.get("PROVIDER_GENERATION_UNIT_COUNT") or 0) != EXPECTED_UNIT_COUNT:
        raise EP002V24RepairExecutionError("V24_PROVIDER_UNIT_COUNT_MISMATCH")
    if int(float(storyboard.get("PLANNED_PROVIDER_REQUEST_SECONDS") or 0)) != EXPECTED_PROVIDER_SECONDS:
        raise EP002V24RepairExecutionError("V24_PROVIDER_SECONDS_MISMATCH")
    if storyboard.get("LEGACY_FEMALE_TEMPORAL_AUDIT_STATUS") not in (
        "HUMAN_REVIEW_PASS_ALL_REUSED_ASSETS",
        None,
    ):
        # V2.4 stores the human result in its dedicated artifact and
        # certification fields; an unexpected explicit value is fail-closed.
        raise EP002V24RepairExecutionError(
            "V24_LEGACY_FEMALE_TEMPORAL_STATUS_UNEXPECTED"
        )

    raw_shots = storyboard.get("MICRO_SHOTS")
    raw_units = storyboard.get("PROVIDER_GENERATION_UNITS")
    if not isinstance(raw_shots, list) or not isinstance(raw_units, list):
        raise EP002V24RepairExecutionError("V24_STORYBOARD_PLAN_ARRAYS_REQUIRED")
    shots = {
        str(item.get("MICRO_SHOT_ID")): item
        for item in raw_shots
        if isinstance(item, Mapping)
    }

    units: list[V24ProviderUnit] = []
    seen_ids: set[str] = set()
    previous_debate_seen = False
    for ordinal, raw in enumerate(raw_units, 1):
        if not isinstance(raw, Mapping):
            raise EP002V24RepairExecutionError("V24_PROVIDER_UNIT_OBJECT_REQUIRED")
        unit_id = str(raw.get("GENERATION_UNIT_ID") or "")
        if not unit_id or unit_id in seen_ids:
            raise EP002V24RepairExecutionError(
                "V24_PROVIDER_UNIT_ID_INVALID:" + unit_id
            )
        seen_ids.add(unit_id)
        if str(raw.get("PROVIDER") or "") != "RUNWARE":
            raise EP002V24RepairExecutionError("V24_PROVIDER_MUST_BE_RUNWARE:" + unit_id)
        if str(raw.get("MODEL") or "") != MODEL:
            raise EP002V24RepairExecutionError("V24_MODEL_MISMATCH:" + unit_id)
        duration = int(raw.get("PROVIDER_REQUEST_DURATION_SECONDS") or 0)
        if duration not in {4, 6, 8}:
            raise EP002V24RepairExecutionError("V24_DURATION_INVALID:" + unit_id)
        if raw.get("SOURCE_RANGE_CAPACITY_PASS") is not True:
            raise EP002V24RepairExecutionError(
                "V24_SOURCE_RANGE_CAPACITY_NOT_PASS:" + unit_id
            )
        members = raw.get("EDITORIAL_MEMBER_SHOT_IDS")
        if not isinstance(members, list) or not members:
            raise EP002V24RepairExecutionError(
                "V24_UNIT_MEMBERS_REQUIRED:" + unit_id
            )
        group = str(raw.get("CONTINUITY_GROUP") or "")
        reference_required = bool(
            raw.get("REFERENCE_FRAME_REQUIRED_AFTER_FIRST_UNIT")
        )
        if group == "MUSA_DEBATE_SHARED_SETUP":
            if reference_required and not previous_debate_seen:
                raise EP002V24RepairExecutionError(
                    "V24_REFERENCE_CHAIN_START_INVALID:" + unit_id
                )
            previous_debate_seen = True
        elif reference_required:
            raise EP002V24RepairExecutionError(
                "V24_UNPLANNED_REFERENCE_FRAME_REQUIREMENT:" + unit_id
            )

        prompt = _provider_prompt_for_unit(raw, shots)
        unit = V24ProviderUnit(
            ordinal=ordinal,
            unit_id=unit_id,
            model=MODEL,
            duration_seconds=duration,
            continuity_group=group,
            reference_frame_required=reference_required,
            member_shot_ids=tuple(str(x) for x in members),
            positive_prompt=prompt,
            seed=_stable_seed(group),
            expected_cost_usd=round(duration * UNIT_PRICE_USD, 8),
        )
        units.append(unit)

    semantic_plan = [unit.as_dict() for unit in units]
    plan_sha = canonical_sha256(semantic_plan)
    if len(units) != EXPECTED_UNIT_COUNT:
        raise EP002V24RepairExecutionError("V24_UNIT_COUNT_INVALID")
    if sum(unit.duration_seconds for unit in units) != EXPECTED_PROVIDER_SECONDS:
        raise EP002V24RepairExecutionError("V24_PROVIDER_SECONDS_INVALID")
    if abs(sum(unit.expected_cost_usd for unit in units) - EXPECTED_COST_USD) > 1e-9:
        raise EP002V24RepairExecutionError("V24_COST_TOTAL_INVALID")
    if plan_sha != EXPECTED_PLAN_SHA256:
        raise EP002V24RepairExecutionError(
            "V24_PROVIDER_PLAN_HASH_MISMATCH:" + plan_sha
        )
    return units, plan_sha



def _validate_release_evidence(repo: Path, storyboard: Mapping[str, Any]) -> None:
    files = {
        "certification": (CERTIFICATION_REL, EXPECTED_CERTIFICATION_SHA256),
        "female_review": (FEMALE_REVIEW_REL, EXPECTED_FEMALE_REVIEW_SHA256),
        "dossiers": (DOSSIERS_REL, EXPECTED_DOSSIERS_SHA256),
        "source_binding": (SOURCE_BINDING_REL, EXPECTED_SOURCE_BINDING_SHA256),
        "constitution": (CONSTITUTION_REL, EXPECTED_CONSTITUTION_SHA256),
    }
    loaded: dict[str, dict[str, Any]] = {}
    for label, (rel, expected_sha) in files.items():
        path = _repo_path(repo, rel)
        if not path.is_file() or sha256_file(path) != expected_sha:
            raise EP002V24RepairExecutionError(
                "V24_RELEASE_EVIDENCE_HASH_MISMATCH:" + label
            )
        loaded[label] = _read_json(path)

    female = loaded["female_review"]
    if (
        female.get("STATUS") != "PASS_HUMAN_ALL_FRAME_REVIEW"
        or female.get("ASSETS_REVIEWED") != 40
        or female.get("VIDEO_ASSETS_REVIEWED") != 29
        or female.get("STATIC_IMAGES_REVIEWED") != 11
        or female.get("TOTAL_DECODED_VIDEO_FRAMES_REVIEWED") != 4811
        or female.get("CONTACT_SHEETS_REVIEWED") != 92
        or female.get("LEGACY_FEMALE_REUSE_COUNT") != 0
        or female.get("SALVAGE_TRANSFORM_USED") is not False
    ):
        raise EP002V24RepairExecutionError(
            "V24_LEGACY_FEMALE_HUMAN_REVIEW_INVALID"
        )

    cert = loaded["certification"]
    if (
        cert.get("STATUS")
        != "PASS_AUTOMATED_V2_4_GATES_AWAITING_FINAL_HUMAN_STORYBOARD_APPROVAL"
        or cert.get("LEGACY_FEMALE_TEMPORAL_HUMAN_REVIEW") != "PASS"
        or cert.get("LEGACY_FEMALE_REUSE_COUNT") != 0
        or cert.get("PLANNED_GRAPHICS_COUNT") != 0
        or cert.get("GENERIC_LEGACY_TAIL_AFTER_479_583_SECONDS") != 0
        or cert.get("NETWORK_CALLS") != 0
        or cert.get("PROVIDER_CALLS") != 0
        or cert.get("PAID_CALLS") != 0
        or cert.get("NO_MONTAGE_PERFORMED") is not True
        or cert.get("ACTUAL_RENDER_MUTE_COMPREHENSION") != "NOT_RUN"
        or abs(float(cert.get("PLANNED_VEO_720P_COST_USD") or -1) - EXPECTED_COST_USD) > 1e-9
        or abs(float(cert.get("PLANNED_COST_CAP_USD") or -1) - MAXIMUM_COST_USD) > 1e-9
    ):
        raise EP002V24RepairExecutionError(
            "V24_PREPRODUCTION_CERTIFICATION_INVALID"
        )

    constitution = loaded["constitution"]
    graphics = constitution.get("GRAPHICS_POLICY")
    if (
        constitution.get("STATUS") != "ACTIVE"
        or constitution.get("FAIL_CLOSED") is not True
        or constitution.get("STORYBOARD_HUMAN_APPROVAL_REQUIRED_BEFORE_VISUAL_GENERATION") is not True
        or not isinstance(graphics, Mapping)
        or graphics.get("GRAPHICS_ALLOWED") is not False
        or graphics.get("PLACEHOLDER_VISUALS_ALLOWED") is not False
    ):
        raise EP002V24RepairExecutionError(
            "V24_CONSTITUTION_RELEASE_GATE_INVALID"
        )

    if (
        storyboard.get("VISUAL_CONSTITUTION_SHA256")
        != EXPECTED_CONSTITUTION_SHA256
        or storyboard.get("CHARACTER_DOSSIERS_SHA256")
        != EXPECTED_DOSSIERS_SHA256
        or storyboard.get("SOURCE_BINDING_SHA256")
        != EXPECTED_SOURCE_BINDING_SHA256
        or storyboard.get("LEGACY_FEMALE_TEMPORAL_AUDIT_SHA256")
        != EXPECTED_FEMALE_REVIEW_SHA256
    ):
        raise EP002V24RepairExecutionError(
            "V24_STORYBOARD_RELEASE_EVIDENCE_BINDING_INVALID"
        )

    dossiers = loaded["dossiers"]
    if (
        dossiers.get("STATUS")
        != "PASS_SOURCE_FACTS_AND_ART_DIRECTION_SEPARATED"
        or dossiers.get("UNKNOWN_ATTRIBUTES_REMAIN_UNKNOWN") is not True
    ):
        raise EP002V24RepairExecutionError("V24_CHARACTER_DOSSIERS_INVALID")

    source = loaded["source_binding"]
    if (
        source.get("SEPARATE_STAGING_SOURCE_TIER")
        != "TIER_5_PERMISSIBLE_ISRAILIYYAT"
        or source.get("EXACT_GEOGRAPHY_ASSERTED") is not False
        or source.get("SEPARATE_STAGING_HUMAN_REVIEW_REQUIRED") is not True
    ):
        raise EP002V24RepairExecutionError("V24_SOURCE_BINDING_INVALID")



def _validate_local_pricing_registry(repo: Path) -> None:
    path = _repo_path(repo, PRICING_REL)
    if not path.is_file():
        raise EP002V24RepairExecutionError("V24_PRICING_REGISTRY_MISSING")
    registry = _read_json(path)
    if registry.get("source_policy") != "OFFICIAL_PROVIDER_DOCUMENTATION_ONLY":
        raise EP002V24RepairExecutionError("V24_PRICING_SOURCE_POLICY_INVALID")
    entries = registry.get("entries")
    if not isinstance(entries, list):
        raise EP002V24RepairExecutionError("V24_PRICING_ENTRIES_REQUIRED")
    matching = [
        row
        for row in entries
        if isinstance(row, Mapping)
        and row.get("provider") == "RUNWARE"
        and row.get("model") == MODEL
        and row.get("media_kind") == "RUNWARE_VIDEO"
        and row.get("status") == "PRICED"
    ]
    if len(matching) != 1:
        raise EP002V24RepairExecutionError("V24_PRICING_ENTRY_UNIQUE_REQUIRED")
    row = matching[0]
    variants = row.get("variants")
    if not isinstance(variants, list):
        raise EP002V24RepairExecutionError("V24_PRICING_VARIANTS_REQUIRED")
    variant = next(
        (
            item
            for item in variants
            if isinstance(item, Mapping)
            and item.get("id") == "720p_no_audio"
        ),
        None,
    )
    if (
        not isinstance(variant, Mapping)
        or float(variant.get("unit_price") or -1.0) != UNIT_PRICE_USD
        or variant.get("currency") != "USD"
        or row.get("billing_unit") != "per_generated_video_second"
    ):
        raise EP002V24RepairExecutionError("V24_720P_PRICE_BINDING_INVALID")


def _approval_receipt(repo: Path) -> dict[str, Any]:
    path = _repo_path(repo, APPROVAL_REL)
    if not path.is_file():
        raise EP002V24RepairExecutionError("V24_FINAL_HUMAN_APPROVAL_RECEIPT_REQUIRED")
    value = _read_json(path)
    signature = str(value.get("approval_sha256") or "")
    unsigned = {k: v for k, v in value.items() if k != "approval_sha256"}
    required = {
        "schema_version": "siraj-ep002-v24-final-human-approval-v1",
        "status": "ACTIVE",
        "episode_id": EPISODE_ID,
        "storyboard_sha256": EXPECTED_STORYBOARD_SHA256,
        "provider_plan_sha256": EXPECTED_PLAN_SHA256,
        "provider_generation_units": EXPECTED_UNIT_COUNT,
        "provider_request_seconds": EXPECTED_PROVIDER_SECONDS,
        "planned_cost_usd": EXPECTED_COST_USD,
        "maximum_cost_usd": MAXIMUM_COST_USD,
        "scope": "V24_INITIAL_FIRST_ATTEMPTS_ONLY",
        "automatic_paid_retry": False,
        "automatic_paid_resubmission": False,
        "publishing": "HUMAN_ONLY",
        "montage_after_generation": "HUMAN_RENDER_CONFORMANCE_REVIEW_REQUIRED",
    }
    for key, expected in required.items():
        if value.get(key) != expected:
            raise EP002V24RepairExecutionError(
                "V24_FINAL_APPROVAL_BINDING_INVALID:" + key
            )
    if signature != canonical_sha256(unsigned):
        raise EP002V24RepairExecutionError("V24_FINAL_APPROVAL_SIGNATURE_INVALID")
    if str(value.get("confirmation_text") or "").strip() != "أعتمد Storyboard V2.4 النهائي":
        raise EP002V24RepairExecutionError("V24_APPROVAL_CONFIRMATION_TEXT_INVALID")
    return value


def _ledger_path(repo: Path) -> Path:
    return _repo_path(repo, EXECUTION_ROOT_REL) / LEDGER_NAME


def _state_path(repo: Path) -> Path:
    return _repo_path(repo, EXECUTION_ROOT_REL) / STATE_NAME


def _read_events(repo: Path) -> list[dict[str, Any]]:
    path = _ledger_path(repo)
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise EP002V24RepairExecutionError("V24_LEDGER_ROW_OBJECT_REQUIRED")
        stored = str(value.get("receipt_sha256") or "")
        unsigned = {k: v for k, v in value.items() if k != "receipt_sha256"}
        if stored != canonical_sha256(unsigned):
            raise EP002V24RepairExecutionError("V24_LEDGER_RECEIPT_HASH_INVALID")
        if value.get("storyboard_sha256") != EXPECTED_STORYBOARD_SHA256:
            raise EP002V24RepairExecutionError("V24_LEDGER_STORYBOARD_BINDING_INVALID")
        if value.get("provider_plan_sha256") != EXPECTED_PLAN_SHA256:
            raise EP002V24RepairExecutionError("V24_LEDGER_PLAN_BINDING_INVALID")
        rows.append(value)
    return rows


def _append_event(repo: Path, payload: Mapping[str, Any]) -> dict[str, Any]:
    value = {
        "schema_version": "siraj-ep002-v24-repair-attempt-ledger-v1",
        "event_id": str(uuid.uuid4()),
        "episode_id": EPISODE_ID,
        "stage": STAGE,
        "storyboard_sha256": EXPECTED_STORYBOARD_SHA256,
        "provider_plan_sha256": EXPECTED_PLAN_SHA256,
        "timestamp_utc": utc_now(),
        "automatic_paid_retry": False,
        "automatic_paid_resubmission": False,
        **dict(payload),
    }
    value["receipt_sha256"] = canonical_sha256(value)
    path = _ledger_path(repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    append_jsonl(path, value)
    return value


def _completed_units(repo: Path, units: Sequence[V24ProviderUnit]) -> dict[str, dict[str, Any]]:
    events = _read_events(repo)
    known = {unit.unit_id: unit for unit in units}
    completes: dict[str, list[dict[str, Any]]] = {key: [] for key in known}
    intents: dict[str, list[dict[str, Any]]] = {key: [] for key in known}
    stage_level_statuses = {"ALL_FIRST_ATTEMPTS_COMPLETE"}
    for row in events:
        status = str(row.get("status") or "")
        unit_id = str(row.get("unit_id") or "")
        if status in stage_level_statuses:
            if unit_id:
                raise EP002V24RepairExecutionError(
                    "V24_STAGE_EVENT_MUST_NOT_BIND_UNIT:"
                    + status
                    + ":"
                    + unit_id
                )
            continue
        if unit_id not in known:
            raise EP002V24RepairExecutionError(
                "V24_LEDGER_UNKNOWN_UNIT:" + unit_id
            )
        if status == "INTENT_PERSISTED":
            intents[unit_id].append(row)
        elif status == "COMPLETE":
            completes[unit_id].append(row)

    if any(
        str(row.get("status") or "") == "COST_DRIFT_HUMAN_REACK_REQUIRED"
        for row in events
    ):
        raise EP002V24RepairExecutionError(
            "V24_COST_DRIFT_REQUIRES_HUMAN_REACK"
        )

    result: dict[str, dict[str, Any]] = {}
    for unit_id, unit in known.items():
        complete_rows = completes[unit_id]
        intent_rows = intents[unit_id]
        if len(complete_rows) > 1:
            raise EP002V24RepairExecutionError(
                "V24_MULTIPLE_DURABLE_COMPLETIONS:" + unit_id
            )
        if complete_rows:
            row = complete_rows[0]
            asset_raw = Path(str(row.get("asset_path") or ""))
            asset = asset_raw if asset_raw.is_absolute() else repo / asset_raw
            asset = asset.resolve()
            try:
                asset.relative_to(repo)
            except ValueError as exc:
                raise EP002V24RepairExecutionError(
                    "V24_COMPLETED_ASSET_OUTSIDE_REPO:" + unit_id
                ) from exc
            if not asset.is_file():
                raise EP002V24RepairExecutionError(
                    "V24_COMPLETED_ASSET_MISSING:" + unit_id
                )
            if sha256_file(asset) != str(row.get("asset_sha256") or ""):
                raise EP002V24RepairExecutionError(
                    "V24_COMPLETED_ASSET_HASH_MISMATCH:" + unit_id
                )
            if int(row.get("duration_seconds") or 0) != unit.duration_seconds:
                raise EP002V24RepairExecutionError(
                    "V24_COMPLETED_DURATION_BINDING_MISMATCH:" + unit_id
                )
            result[unit_id] = row
            continue
        if intent_rows:
            # Any intent without a durable completion may have crossed the
            # network boundary.  Never infer non-submission and never resubmit.
            raise EP002V24RepairExecutionError(
                "V24_UNRESOLVED_ATTEMPT_REQUIRES_FORENSIC_RECONCILIATION:"
                + unit_id
            )
    return result


def _technical_tools() -> tuple[str, str]:
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise EP002V24RepairExecutionError("FFMPEG_AND_FFPROBE_REQUIRED_BEFORE_SPEND")
    return ffmpeg, ffprobe


def _technical_validate_video(
    asset: Path,
    *,
    requested_seconds: int,
) -> dict[str, Any]:
    _, ffprobe = _technical_tools()
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,codec_name,avg_frame_rate",
            "-show_entries",
            "format=duration,size",
            "-of",
            "json",
            str(asset),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    value = json.loads(result.stdout)
    streams = value.get("streams")
    fmt = value.get("format")
    if not isinstance(streams, list) or len(streams) != 1 or not isinstance(fmt, Mapping):
        raise EP002V24RepairExecutionError("V24_VIDEO_FFPROBE_SCHEMA_INVALID")
    stream = streams[0]
    width = int(stream.get("width") or 0)
    height = int(stream.get("height") or 0)
    duration = float(fmt.get("duration") or 0.0)
    size = int(fmt.get("size") or 0)
    if (width, height) != (1280, 720):
        raise EP002V24RepairExecutionError(
            f"V24_VIDEO_DIMENSIONS_INVALID:{width}x{height}"
        )
    if duration < requested_seconds - 0.35 or duration > requested_seconds + 1.25:
        raise EP002V24RepairExecutionError(
            f"V24_VIDEO_DURATION_INVALID:{duration}:{requested_seconds}"
        )
    if size <= 1024:
        raise EP002V24RepairExecutionError("V24_VIDEO_FILE_TOO_SMALL")
    return {
        "width": width,
        "height": height,
        "duration_seconds": duration,
        "size_bytes": size,
        "codec_name": stream.get("codec_name"),
        "avg_frame_rate": stream.get("avg_frame_rate"),
    }


def _extract_last_frame(repo: Path, unit_id: str, asset: Path) -> tuple[Path, str]:
    ffmpeg, _ = _technical_tools()
    root = _repo_path(repo, EXECUTION_ROOT_REL) / REFERENCE_DIR_NAME
    root.mkdir(parents=True, exist_ok=True)
    output = root / (unit_id + "__last-frame.jpg")
    temp = output.with_suffix(".tmp.jpg")
    subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-sseof",
            "-0.12",
            "-i",
            str(asset),
            "-frames:v",
            "1",
            "-q:v",
            "2",
            str(temp),
        ],
        check=True,
    )
    if not temp.is_file() or temp.stat().st_size <= 512:
        raise EP002V24RepairExecutionError(
            "V24_REFERENCE_FRAME_EXTRACTION_FAILED:" + unit_id
        )
    digest = sha256_file(temp)
    if output.is_file():
        if sha256_file(output) != digest:
            raise EP002V24RepairExecutionError(
                "V24_REFERENCE_FRAME_HASH_CONFLICT:" + unit_id
            )
        temp.unlink()
    else:
        temp.replace(output)
    return output, sha256_file(output)


def _data_uri(path: Path) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def _task_for_unit(
    unit: V24ProviderUnit,
    *,
    plan_sha256: str,
    reference_frame: Path | None,
) -> dict[str, Any]:
    task: dict[str, Any] = {
        "taskType": "videoInference",
        "taskUUID": _runtime_uuid4(plan_sha256, unit.unit_id),
        "model": unit.model,
        "positivePrompt": unit.positive_prompt,
        "duration": unit.duration_seconds,
        "seed": unit.seed,
        "numberResults": 1,
        "deliveryMethod": "async",
        "includeCost": True,
        "providerSettings": {
            "google": {
                "generateAudio": False,
                # EP002's already-certified regional runtime policy requires
                # allow_adult.  Prompt constraints still forbid extra people.
                "personGeneration": "allow_adult",
            }
        },
    }
    if reference_frame is None:
        task["width"] = 1280
        task["height"] = 720
    else:
        task["resolution"] = "720p"
        task["inputs"] = {
            "frameImages": [
                {
                    "image": _data_uri(reference_frame),
                    "frame": "first",
                }
            ]
        }
    validated = validate_runware_task(task, require_uuid_v4=True)
    return dict(validated.payload)


def _relative(repo: Path, path: Path) -> str:
    return str(path.resolve().relative_to(repo.resolve())).replace("\\", "/")


def _write_state(repo: Path, payload: Mapping[str, Any]) -> None:
    value = {
        "schema_version": "siraj-ep002-v24-repair-provider-state-v1",
        "episode_id": EPISODE_ID,
        "stage": STAGE,
        "storyboard_sha256": EXPECTED_STORYBOARD_SHA256,
        "provider_plan_sha256": EXPECTED_PLAN_SHA256,
        "automatic_paid_retry": False,
        "automatic_paid_resubmission": False,
        **dict(payload),
    }
    _write_json_atomic(_state_path(repo), value)


def _build_render_review_package(
    repo: Path,
    units: Sequence[V24ProviderUnit],
    completed: Mapping[str, Mapping[str, Any]],
) -> Path:
    ffmpeg, ffprobe = _technical_tools()
    root = _repo_path(repo, EXECUTION_ROOT_REL) / REVIEW_DIR_NAME
    if root.exists():
        # Derived review evidence only. Paid assets and provider receipts live
        # elsewhere and are never deleted or rewritten here.
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)

    manifest_rows: list[dict[str, Any]] = []
    total_decoded_frames = 0
    total_contact_sheets = 0

    for unit in units:
        row = completed[unit.unit_id]
        raw = Path(str(row["asset_path"]))
        asset = raw if raw.is_absolute() else repo / raw
        asset = asset.resolve()

        frame_probe = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-count_frames",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=nb_read_frames",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(asset),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        try:
            decoded_frames = int(frame_probe.stdout.strip())
        except ValueError as exc:
            raise EP002V24RepairExecutionError(
                "V24_REVIEW_DECODED_FRAME_COUNT_INVALID:" + unit.unit_id
            ) from exc
        if decoded_frames <= 0:
            raise EP002V24RepairExecutionError(
                "V24_REVIEW_DECODED_FRAME_COUNT_ZERO:" + unit.unit_id
            )

        pattern = root / (unit.unit_id + "__sheet_%03d.jpg")
        vf = "scale=320:-2,tile=8x8:padding=2:margin=2"
        subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(asset),
                "-vf",
                vf,
                "-fps_mode",
                "passthrough",
                str(pattern),
            ],
            check=True,
        )

        sheets = sorted(root.glob(unit.unit_id + "__sheet_*.jpg"))
        if not sheets:
            raise EP002V24RepairExecutionError(
                "V24_ALL_FRAME_REVIEW_SHEETS_MISSING:" + unit.unit_id
            )

        # Each 8x8 sheet can contain at most 64 decoded frames. The lower
        # bound accounts only for a partially-filled final sheet. This proves
        # the sheet inventory is sufficient to cover the complete decode.
        if not (
            (len(sheets) - 1) * 64 < decoded_frames
            and len(sheets) * 64 >= decoded_frames
        ):
            raise EP002V24RepairExecutionError(
                "V24_ALL_FRAME_REVIEW_COVERAGE_INVALID:"
                + unit.unit_id
                + f":frames={decoded_frames}:sheets={len(sheets)}"
            )

        total_decoded_frames += decoded_frames
        total_contact_sheets += len(sheets)
        manifest_rows.append(
            {
                "ordinal": unit.ordinal,
                "unit_id": unit.unit_id,
                "member_shot_ids": list(unit.member_shot_ids),
                "continuity_group": unit.continuity_group,
                "asset_path": _relative(repo, asset),
                "asset_sha256": sha256_file(asset),
                "review_mode": "ALL_DECODED_FRAMES_CONTACT_SHEET_8X8",
                "decoded_frames_reviewable": decoded_frames,
                "contact_sheet_count": len(sheets),
                "contact_sheets": [
                    {
                        "name": sheet.name,
                        "sha256": sha256_file(sheet),
                    }
                    for sheet in sheets
                ],
                "expected_cost_usd": unit.expected_cost_usd,
                "human_semantic_conformance": "PENDING",
                "human_female_modesty_conformance": "PENDING",
                "human_literal_event_conformance": "PENDING",
                "human_continuity_conformance": "PENDING",
            }
        )

    manifest = {
        "schema_version": "siraj-ep002-v24-render-conformance-review-v2",
        "status": "AWAITING_HUMAN_RENDER_CONFORMANCE_REVIEW",
        "episode_id": EPISODE_ID,
        "storyboard_sha256": EXPECTED_STORYBOARD_SHA256,
        "provider_plan_sha256": EXPECTED_PLAN_SHA256,
        "unit_count": len(units),
        "provider_seconds": sum(x.duration_seconds for x in units),
        "planned_cost_usd": EXPECTED_COST_USD,
        "review_mode": "ALL_DECODED_FRAMES_CONTACT_SHEET_8X8",
        "total_decoded_frames_reviewable": total_decoded_frames,
        "total_contact_sheets": total_contact_sheets,
        "graphics_count": 0,
        "legacy_female_reuse_count": 0,
        "actual_render_mute_comprehension": "NOT_RUN",
        "montage_allowed": False,
        "qa_allowed": False,
        "provider_retry_allowed": False,
        "units": manifest_rows,
        "next": "HUMAN_V24_RENDER_CONFORMANCE_REVIEW_BEFORE_MONTAGE",
    }
    manifest_path = root / "_MANIFEST.json"
    _write_json_atomic(manifest_path, manifest)

    desktop = Path.home() / "Desktop"
    zip_path = desktop / "EP002_V2_4_RENDER_CONFORMANCE_REVIEW.zip"
    temp_zip = zip_path.with_suffix(".tmp.zip")
    if temp_zip.exists():
        temp_zip.unlink()
    with zipfile.ZipFile(temp_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(root.iterdir()):
            if path.is_file():
                archive.write(path, arcname=path.name)
    temp_zip.replace(zip_path)
    return zip_path




def _validate_local_environment() -> None:
    _provider_api_key()
    _technical_tools()


class EP002V24DesktopRepairExecutionService:
    """One-session Desktop-only executor for the approved V2.4 first attempts."""

    def __init__(
        self,
        repo_root: Path,
        *,
        gateway: Any | None = None,
        technical_validator: Callable[..., Mapping[str, Any]] | None = None,
        reference_extractor: Callable[..., tuple[Path, str]] | None = None,
        environment_validator: Callable[[], None] | None = None,
        review_builder: Callable[..., Path] | None = None,
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.gateway = gateway or CanonicalRunwarePaidGateway()
        self.technical_validator = technical_validator or _technical_validate_video
        self.reference_extractor = reference_extractor or _extract_last_frame
        self.environment_validator = environment_validator or _validate_local_environment
        self.review_builder = review_builder or _build_render_review_package
        self._pending_capability: _DesktopCapability | None = None
        self._active = False
        self._lock = threading.Lock()

    def _load(self) -> tuple[dict[str, Any], list[V24ProviderUnit], str, dict[str, Any]]:
        storyboard_path = _repo_path(self.repo_root, STORYBOARD_REL)
        if not storyboard_path.is_file():
            raise EP002V24RepairExecutionError("V24_STORYBOARD_MISSING")
        if sha256_file(storyboard_path) != EXPECTED_STORYBOARD_SHA256:
            raise EP002V24RepairExecutionError("V24_STORYBOARD_HASH_MISMATCH")
        storyboard = _read_json(storyboard_path)
        _validate_release_evidence(self.repo_root, storyboard)
        _validate_local_pricing_registry(self.repo_root)
        units, plan_sha = build_approved_provider_plan(storyboard)
        approval = _approval_receipt(self.repo_root)
        if plan_sha != str(approval.get("provider_plan_sha256") or ""):
            raise EP002V24RepairExecutionError("V24_APPROVAL_PLAN_HASH_MISMATCH")
        if not master_authorization_active(self.repo_root, EPISODE_ID):
            raise EP002V24RepairExecutionError("EPISODE_MASTER_AUTHORIZATION_NOT_ACTIVE")
        # Resolve credentials and local video tools BEFORE any intent is
        # persisted, so missing local prerequisites cannot create ambiguity.
        self.environment_validator()
        return storyboard, units, plan_sha, approval

    def inspect(self) -> V24ExecutionPreview:
        _, units, plan_sha, _ = self._load()
        review_package = Path.home() / "Desktop" / "EP002_V2_4_RENDER_CONFORMANCE_REVIEW.zip"
        unresolved: tuple[str, ...] = ()
        completed: dict[str, dict[str, Any]] = {}
        try:
            completed = _completed_units(self.repo_root, units)
        except EP002V24RepairExecutionError as exc:
            prefix = "V24_UNRESOLVED_ATTEMPT_REQUIRES_FORENSIC_RECONCILIATION:"
            if str(exc).startswith(prefix):
                unresolved = (str(exc)[len(prefix):],)
            elif str(exc) == "V24_COST_DRIFT_REQUIRES_HUMAN_REACK":
                unresolved = ("COST_DRIFT_HUMAN_REACK_REQUIRED",)
            else:
                raise
        remaining = len(units) - len(completed)
        allowed = not unresolved and remaining > 0
        status = (
            "READY_FOR_EXPLICIT_DESKTOP_START"
            if allowed
            else "ALREADY_COMPLETED"
            if remaining == 0 and not unresolved
            else "BLOCKED_RECONCILIATION_REQUIRED"
        )
        return V24ExecutionPreview(
            status=status,
            storyboard_sha256=EXPECTED_STORYBOARD_SHA256,
            provider_plan_sha256=plan_sha,
            planned_units=len(units),
            completed_units=len(completed),
            remaining_units=remaining,
            provider_seconds=sum(x.duration_seconds for x in units),
            expected_cost_usd=EXPECTED_COST_USD,
            maximum_cost_usd=MAXIMUM_COST_USD,
            unresolved_unit_ids=unresolved,
            review_package_path=str(review_package) if review_package.is_file() else None,
            execution_allowed=allowed,
        )

    def issue_desktop_capability(self, *, source: str) -> _DesktopCapability:
        if source != DESKTOP_SOURCE:
            raise EP002V24RepairExecutionError("V24_DESKTOP_UI_SOURCE_REQUIRED")
        preview = self.inspect()
        if not preview.execution_allowed:
            raise EP002V24RepairExecutionError(
                "V24_EXECUTION_NOT_ALLOWED:" + preview.status
            )
        capability = _DesktopCapability()
        self._pending_capability = capability
        return capability

    def execute(
        self,
        capability: _DesktopCapability,
        *,
        source: str,
        progress_callback: Callable[[Mapping[str, Any]], None] | None = None,
    ) -> V24ExecutionOutcome:
        if source != DESKTOP_SOURCE:
            raise EP002V24RepairExecutionError("V24_DESKTOP_UI_SOURCE_REQUIRED")
        if capability is not self._pending_capability:
            raise EP002V24RepairExecutionError("V24_DESKTOP_EXECUTION_CONTEXT_REQUIRED")
        # Capability is one-shot even if local execution later fails.
        self._pending_capability = None
        with self._lock:
            if self._active:
                raise EP002V24RepairExecutionError("V24_DUPLICATE_EXECUTION_BLOCKED")
            self._active = True
        try:
            return self._execute_once(progress_callback=progress_callback)
        finally:
            with self._lock:
                self._active = False

    def _execute_once(
        self,
        *,
        progress_callback: Callable[[Mapping[str, Any]], None] | None,
    ) -> V24ExecutionOutcome:
        _, units, plan_sha, approval = self._load()
        completed = _completed_units(self.repo_root, units)
        skipped = len(completed)

        planned_total = sum(unit.expected_cost_usd for unit in units)
        if abs(planned_total - EXPECTED_COST_USD) > 1e-9:
            raise EP002V24RepairExecutionError("V24_COST_TOTAL_CHANGED")
        if planned_total > MAXIMUM_COST_USD + 1e-9:
            raise EP002V24RepairExecutionError("V24_COST_CAP_EXCEEDED")

        master_ref = master_authorization_reference(self.repo_root, EPISODE_ID)
        cumulative_exposure = sum(
            unit.expected_cost_usd
            for unit in units
            if unit.unit_id in completed
        )

        _write_state(
            self.repo_root,
            {
                "status": "RUNNING_FIRST_ATTEMPTS",
                "planned_units": len(units),
                "completed_units": len(completed),
                "maximum_cost_usd": MAXIMUM_COST_USD,
                "planned_cost_usd": EXPECTED_COST_USD,
                "montage_allowed": False,
            },
        )

        previous_completed_by_group: dict[str, tuple[V24ProviderUnit, Mapping[str, Any]]] = {}
        for unit in units:
            if unit.unit_id in completed:
                previous_completed_by_group[unit.continuity_group] = (
                    unit,
                    completed[unit.unit_id],
                )
                continue

            # Re-read after every unit. A concurrent or stale process cannot
            # quietly introduce a second attempt.
            current_completed = _completed_units(self.repo_root, units)
            if unit.unit_id in current_completed:
                completed = current_completed
                previous_completed_by_group[unit.continuity_group] = (
                    unit,
                    completed[unit.unit_id],
                )
                continue

            reference_path: Path | None = None
            reference_sha: str | None = None
            if unit.reference_frame_required:
                prior = previous_completed_by_group.get(unit.continuity_group)
                if prior is None:
                    raise EP002V24RepairExecutionError(
                        "V24_REQUIRED_CONTINUITY_REFERENCE_NOT_AVAILABLE:"
                        + unit.unit_id
                    )
                prior_unit, prior_row = prior
                raw = Path(str(prior_row.get("asset_path") or ""))
                prior_asset = raw if raw.is_absolute() else self.repo_root / raw
                reference_path, reference_sha = self.reference_extractor(
                    self.repo_root,
                    prior_unit.unit_id,
                    prior_asset.resolve(),
                )

            task = _task_for_unit(
                unit,
                plan_sha256=plan_sha,
                reference_frame=reference_path,
            )
            validated = validate_runware_task(task, require_uuid_v4=True)
            runtime_payload = dict(validated.payload)

            next_exposure = cumulative_exposure + unit.expected_cost_usd
            if next_exposure > MAXIMUM_COST_USD + 1e-9:
                raise EP002V24RepairExecutionError(
                    "V24_COST_CAP_EXCEEDED_BEFORE_SUBMISSION:" + unit.unit_id
                )

            attempt_id = str(
                uuid.uuid5(
                    ATTEMPT_NAMESPACE,
                    EXPECTED_PLAN_SHA256 + ":" + unit.unit_id,
                )
            )
            request = PaidOperationRequest(
                repo_root=self.repo_root,
                episode_id=EPISODE_ID,
                stage=STAGE,
                operation_type="RUNWARE_VIDEO_INFERENCE",
                provider="RUNWARE",
                model=unit.model,
                provider_contract_version=PROVIDER_CONTRACT_VERSION,
                payload=runtime_payload,
                input_artifact_hashes={
                    "v24_storyboard": EXPECTED_STORYBOARD_SHA256,
                    "v24_provider_plan": EXPECTED_PLAN_SHA256,
                    "v24_approval_receipt": str(approval["approval_sha256"]),
                    **(
                        {"continuity_reference_frame": str(reference_sha)}
                        if reference_sha
                        else {}
                    ),
                },
                master_authorization_reference=master_ref,
                authorization_mode="EPISODE_MASTER",
                operation_nonce="EP002_V24_FIRST_ATTEMPT:" + unit.unit_id,
                attempt_id=attempt_id,
            )

            _append_event(
                self.repo_root,
                {
                    "status": "INTENT_PERSISTED",
                    "unit_id": unit.unit_id,
                    "ordinal": unit.ordinal,
                    "attempt_id": attempt_id,
                    "duration_seconds": unit.duration_seconds,
                    "expected_cost_usd": unit.expected_cost_usd,
                    "maximum_cost_usd": MAXIMUM_COST_USD,
                    "runtime_payload_sha256": request.payload_sha256,
                    "reference_frame_sha256": reference_sha,
                    "authorization_scope": "V24_INITIAL_FIRST_ATTEMPTS_ONLY",
                },
            )

            if progress_callback:
                progress_callback(
                    {
                        "stage": STAGE,
                        "status": "SUBMITTING_FIRST_ATTEMPT",
                        "unit_id": unit.unit_id,
                        "ordinal": unit.ordinal,
                        "planned_units": len(units),
                        "completed_units": len(completed),
                        "expected_cost_usd": unit.expected_cost_usd,
                        "planned_total_cost_usd": EXPECTED_COST_USD,
                        "maximum_cost_usd": MAXIMUM_COST_USD,
                    }
                )

            try:
                gateway_result = self.gateway.submit(
                    request=request,
                    unit={
                        "unit_id": unit.unit_id,
                        "request_id": unit.unit_id,
                        "media_kind": "RUNWARE_VIDEO",
                        "provider": "RUNWARE",
                        "model": unit.model,
                    },
                    attempt_id=attempt_id,
                )
            except Exception as exc:
                _append_event(
                    self.repo_root,
                    {
                        "status": "FAILED_OR_UNKNOWN_STOPPED",
                        "unit_id": unit.unit_id,
                        "ordinal": unit.ordinal,
                        "attempt_id": attempt_id,
                        "error": str(exc),
                        "next_action": "FORENSIC_RECONCILIATION_BEFORE_ANY_RESUBMISSION",
                    },
                )
                _write_state(
                    self.repo_root,
                    {
                        "status": "STOPPED_FIRST_FAILURE_OR_UNKNOWN",
                        "blocked_unit_id": unit.unit_id,
                        "error": str(exc),
                        "automatic_paid_retry": False,
                        "automatic_paid_resubmission": False,
                        "montage_allowed": False,
                    },
                )
                raise EP002V24RepairExecutionError(
                    "V24_PROVIDER_ATTEMPT_STOPPED_NO_RETRY:"
                    + unit.unit_id
                    + ":"
                    + str(exc)
                ) from exc

            if not isinstance(gateway_result, Mapping):
                _append_event(
                    self.repo_root,
                    {
                        "status": "FAILED_OR_UNKNOWN_STOPPED",
                        "unit_id": unit.unit_id,
                        "ordinal": unit.ordinal,
                        "attempt_id": attempt_id,
                        "error": "PROVIDER_GATEWAY_RESULT_OBJECT_REQUIRED",
                        "next_action": "FORENSIC_RECONCILIATION_BEFORE_ANY_RESUBMISSION",
                    },
                )
                raise EP002V24RepairExecutionError(
                    "V24_PROVIDER_RESULT_INVALID_NO_RETRY:" + unit.unit_id
                )

            status = str(gateway_result.get("status") or "").upper()
            if status != "COMPLETE":
                _append_event(
                    self.repo_root,
                    {
                        "status": "FAILED_OR_UNKNOWN_STOPPED",
                        "unit_id": unit.unit_id,
                        "ordinal": unit.ordinal,
                        "attempt_id": attempt_id,
                        "provider_status": status or "UNKNOWN",
                        "provider_operation_id": gateway_result.get(
                            "provider_operation_id"
                        ),
                        "error": gateway_result.get("error"),
                        "next_action": "FORENSIC_RECONCILIATION_BEFORE_ANY_RESUBMISSION",
                    },
                )
                _write_state(
                    self.repo_root,
                    {
                        "status": "STOPPED_FIRST_FAILURE_OR_UNKNOWN",
                        "blocked_unit_id": unit.unit_id,
                        "provider_status": status or "UNKNOWN",
                        "automatic_paid_retry": False,
                        "automatic_paid_resubmission": False,
                        "montage_allowed": False,
                    },
                )
                raise EP002V24RepairExecutionError(
                    "V24_PROVIDER_FIRST_ATTEMPT_NOT_COMPLETE_NO_RETRY:"
                    + unit.unit_id
                    + ":"
                    + (status or "UNKNOWN")
                )

            asset_value = str(gateway_result.get("asset_path") or "")
            asset_sha = str(gateway_result.get("asset_sha256") or "")
            if not asset_value or not asset_sha:
                raise EP002V24RepairExecutionError(
                    "V24_COMPLETE_RESULT_ASSET_EVIDENCE_MISSING:" + unit.unit_id
                )
            raw_asset = Path(asset_value)
            asset = raw_asset if raw_asset.is_absolute() else self.repo_root / raw_asset
            asset = asset.resolve()
            if not asset.is_file() or sha256_file(asset) != asset_sha:
                raise EP002V24RepairExecutionError(
                    "V24_COMPLETE_ASSET_HASH_INVALID:" + unit.unit_id
                )

            technical = dict(
                self.technical_validator(
                    asset,
                    requested_seconds=unit.duration_seconds,
                )
            )
            actual_cost = gateway_result.get("actual_cost_usd")
            if isinstance(actual_cost, (int, float)) and not isinstance(actual_cost, bool):
                actual_cost_value: float | None = float(actual_cost)
            else:
                actual_cost_value = None

            complete_row = _append_event(
                self.repo_root,
                {
                    "status": "COMPLETE",
                    "unit_id": unit.unit_id,
                    "ordinal": unit.ordinal,
                    "attempt_id": attempt_id,
                    "duration_seconds": unit.duration_seconds,
                    "expected_cost_usd": unit.expected_cost_usd,
                    "actual_cost_usd": actual_cost_value,
                    "provider_operation_id": gateway_result.get(
                        "provider_operation_id"
                    ),
                    "asset_path": _relative(self.repo_root, asset),
                    "asset_sha256": asset_sha,
                    "runtime_payload_sha256": request.payload_sha256,
                    "reference_frame_sha256": reference_sha,
                    "technical_validation": technical,
                    "render_semantic_conformance": "PENDING_HUMAN_REVIEW",
                },
            )
            completed[unit.unit_id] = complete_row
            previous_completed_by_group[unit.continuity_group] = (
                unit,
                complete_row,
            )
            cumulative_exposure = next_exposure

            if (
                actual_cost_value is not None
                and actual_cost_value > unit.expected_cost_usd + 0.01
            ):
                _append_event(
                    self.repo_root,
                    {
                        "status": "COST_DRIFT_HUMAN_REACK_REQUIRED",
                        "unit_id": unit.unit_id,
                        "ordinal": unit.ordinal,
                        "expected_cost_usd": unit.expected_cost_usd,
                        "actual_cost_usd": actual_cost_value,
                        "maximum_cost_usd": MAXIMUM_COST_USD,
                        "next_action": "HUMAN_COST_REACK_REQUIRED_BEFORE_ANY_FURTHER_UNIT",
                    },
                )
                _write_state(
                    self.repo_root,
                    {
                        "status": "STOPPED_COST_DRIFT_HUMAN_REACK_REQUIRED",
                        "last_completed_unit": unit.unit_id,
                        "expected_cost_usd": unit.expected_cost_usd,
                        "actual_cost_usd": actual_cost_value,
                        "maximum_cost_usd": MAXIMUM_COST_USD,
                        "montage_allowed": False,
                    },
                )
                raise EP002V24RepairExecutionError(
                    "V24_COST_DRIFT_REQUIRES_HUMAN_REACK"
                )

            _write_state(
                self.repo_root,
                {
                    "status": "RUNNING_FIRST_ATTEMPTS",
                    "planned_units": len(units),
                    "completed_units": len(completed),
                    "last_completed_unit": unit.unit_id,
                    "planned_exposure_usd": round(cumulative_exposure, 8),
                    "maximum_cost_usd": MAXIMUM_COST_USD,
                    "montage_allowed": False,
                },
            )
            if progress_callback:
                progress_callback(
                    {
                        "stage": STAGE,
                        "status": "UNIT_COMPLETE",
                        "unit_id": unit.unit_id,
                        "ordinal": unit.ordinal,
                        "planned_units": len(units),
                        "completed_units": len(completed),
                        "planned_exposure_usd": round(cumulative_exposure, 8),
                        "maximum_cost_usd": MAXIMUM_COST_USD,
                    }
                )

        completed = _completed_units(self.repo_root, units)
        if len(completed) != len(units):
            raise EP002V24RepairExecutionError("V24_NOT_ALL_UNITS_DURABLY_COMPLETE")

        review_package = self.review_builder(
            self.repo_root,
            units,
            completed,
        )
        _append_event(
            self.repo_root,
            {
                "status": "ALL_FIRST_ATTEMPTS_COMPLETE",
                "completed_units": len(completed),
                "planned_units": len(units),
                "planned_cost_usd": EXPECTED_COST_USD,
                "maximum_cost_usd": MAXIMUM_COST_USD,
                "review_package_path": str(review_package),
                "review_package_sha256": sha256_file(review_package),
                "next_action": "HUMAN_V24_RENDER_CONFORMANCE_REVIEW_BEFORE_MONTAGE",
            },
        )
        _write_state(
            self.repo_root,
            {
                "status": "AWAITING_HUMAN_RENDER_CONFORMANCE_REVIEW",
                "completed_units": len(completed),
                "planned_units": len(units),
                "planned_cost_usd": EXPECTED_COST_USD,
                "maximum_cost_usd": MAXIMUM_COST_USD,
                "review_package_path": str(review_package),
                "review_package_sha256": sha256_file(review_package),
                "montage_allowed": False,
                "qa_allowed": False,
                "actual_render_mute_comprehension": "NOT_RUN",
                "next": "HUMAN_V24_RENDER_CONFORMANCE_REVIEW_BEFORE_MONTAGE",
            },
        )
        return V24ExecutionOutcome(
            status="AWAITING_HUMAN_RENDER_CONFORMANCE_REVIEW",
            completed_units=len(completed),
            skipped_completed_units=skipped,
            planned_units=len(units),
            expected_total_cost_usd=EXPECTED_COST_USD,
            maximum_cost_usd=MAXIMUM_COST_USD,
            review_package_path=str(review_package),
            next_stage="HUMAN_V24_RENDER_CONFORMANCE_REVIEW_BEFORE_MONTAGE",
        )


__all__ = [
    "DESKTOP_SOURCE",
    "EPISODE_ID",
    "EXPECTED_COST_USD",
    "EXPECTED_PLAN_SHA256",
    "EXPECTED_STORYBOARD_SHA256",
    "EXPECTED_UNIT_COUNT",
    "MAXIMUM_COST_USD",
    "EP002V24DesktopRepairExecutionService",
    "EP002V24RepairExecutionError",
    "V24ExecutionOutcome",
    "V24ExecutionPreview",
    "V24ProviderUnit",
    "build_approved_provider_plan",
]
