"""Integrated research and production policy for historical documentary episodes.

The module is deterministic and offline. It never approves evidence, downloads
media, grades hadith, or executes providers. It builds review-oriented manifests
from tracked contracts and local review artifacts.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping

POLICY_BUNDLE_SCHEMA = "siraj-research-production-policy-bundle-v1"
TARGETED_REVIEW_PACK_SCHEMA = "siraj-targeted-evidence-review-pack-v1"
FILLER_PLAN_SCHEMA = "siraj-cinematic-filler-plan-v1"
RECITATION_CUE_PLAN_SCHEMA = "siraj-quran-recitation-cue-plan-v1"
POLICY_STATUS = "APPROVED"
REVIEW_STATUS = "HUMAN_EXTRACTION_AND_VERIFICATION_PENDING"
EVIDENCE_GATE_STATUS = "WITHHELD_PENDING_APPROVED_EVIDENCE_PACKAGE"
AUTOMATIC_APPROVAL_STATUS = "FORBIDDEN"
LIVE_EXECUTION_STATUS = "BLOCKED"
MUSIC_POLICY = "PROHIBITED_GLOBALLY"
RECITATION_AUDIO_MODE = "QURAN_ONLY_EXCLUSIVE_AUDIO"
RIGHTS_STATUS = "UNVERIFIED_REQUIRES_PUBLICATION_BASIS"

_SECRET_KEYS = {
    "api_key", "apikey", "token", "secret", "password", "authorization",
    "cookie", "credential", "credentials", "private_key",
}
_ABSOLUTE_WINDOWS = re.compile(r"^[A-Za-z]:[\\/]")
_EVENT_ID = re.compile(r"^EV-ADAM-\d{3}$")

GAP_EVENTS = (
    "EV-ADAM-031",
    "EV-ADAM-071",
    "EV-ADAM-091",
)
EDITORIAL_EVENT = "EV-ADAM-099"

SEARCH_TERMS: dict[str, tuple[str, ...]] = {
    "EV-ADAM-031": (
        "عطاس", "عطس", "الحمد لله", "يرحمك ربك", "أول حركة",
        "نفخ الروح", "بلغت الروح", "تكلم آدم",
    ),
    "EV-ADAM-071": (
        "حواء", "زوج آدم", "زوجة آدم", "ضلع", "خلقت المرأة",
        "نوم آدم", "سكن إليها",
    ),
    "EV-ADAM-091": (
        "الشجرة", "شجرة الخلد", "الحنطة", "الكرم", "العنب",
        "التين", "السنبلة", "نوع الشجرة",
    ),
}

QUESTION_IDS = {
    "EV-ADAM-031": ("RQ-ADAM-013", "RQ-ADAM-031"),
    "EV-ADAM-071": ("RQ-ADAM-025", "RQ-ADAM-026", "RQ-ADAM-027"),
    "EV-ADAM-091": ("RQ-ADAM-029", "RQ-ADAM-030"),
}

RECITATION_CANDIDATES = (
    {
        "cue_key": "before-adam",
        "frame_position": 2,
        "references": (
            {"surah": "هود", "verses": "7"},
            {"surah": "الحجر", "verses": "26-27"},
        ),
    },
    {
        "cue_key": "creation-announcement",
        "frame_position": 3,
        "references": ({"surah": "البقرة", "verses": "30"},),
    },
    {
        "cue_key": "formation-of-adam",
        "frame_position": 4,
        "references": (
            {"surah": "الحجر", "verses": "26-29"},
            {"surah": "ص", "verses": "71-72"},
        ),
    },
    {
        "cue_key": "knowledge-and-honor",
        "frame_position": 6,
        "references": ({"surah": "البقرة", "verses": "31-33"},),
    },
    {
        "cue_key": "command-and-prostration",
        "frame_position": 7,
        "references": (
            {"surah": "البقرة", "verses": "34"},
            {"surah": "الأعراف", "verses": "11-12"},
        ),
    },
    {
        "cue_key": "iblis-refusal-climax",
        "frame_position": 9,
        "references": (
            {"surah": "الأعراف", "verses": "12-18"},
            {"surah": "الحجر", "verses": "33-43"},
            {"surah": "ص", "verses": "76-85"},
        ),
    },
    {
        "cue_key": "covenant",
        "frame_position": 10,
        "references": ({"surah": "الأعراف", "verses": "172"},),
    },
    {
        "cue_key": "paradise-and-prohibition",
        "frame_position": 12,
        "references": (
            {"surah": "البقرة", "verses": "35"},
            {"surah": "الأعراف", "verses": "19"},
        ),
    },
)

FILLER_BY_FRAME_KEY: dict[str, tuple[str, ...]] = {
    "symbolic-cold-open": (
        "cosmic_scale_without_creation_sequence_claim",
        "darkness_light_and_dust_symbolism",
    ),
    "central-question": (
        "manuscript_ink_and_earth_texture",
        "abstract_question_visualization",
    ),
    "before-adam": (
        "water_sky_and_vastness_symbolism",
        "nonliteral_cosmic_ambience",
    ),
    "creation-announcement": (
        "earth_landscape_without_location_claim",
        "soil_and_horizon_transition",
    ),
    "formation-of-adam": (
        "macro_clay_earth_and_water_textures",
        "nonhuman_abstract_formation_symbolism",
    ),
    "beginning-of-life": (
        "wind_over_land_and_leaf_movement",
        "breath_like_light_without_depicting_adam",
    ),
    "knowledge-and-honor": (
        "ink_letters_objects_and_order_symbolism",
        "light_revealing_names_without_unseen_depiction",
    ),
    "command-to-prostrate": (
        "vast_empty_space_and_light_transition",
        "obedience_symbolism_without_angels",
    ),
    "angels-prostrate": (
        "light_bowing_motion_abstract_only",
        "empty_space_and_ordered_light_patterns",
    ),
    "iblis-refusal-climax": (
        "fire_and_clay_contrast_without_depicting_iblis",
        "storm_shadow_and_fall_symbolism",
    ),
    "covenant-withheld": (
        "generational_light_streams_abstract_only",
        "humanity_horizon_without_unseen_reconstruction",
    ),
    "spouse-and-garden": (
        "paired_natural_forms_without_human_depiction",
        "garden_beauty_as_conceptual_approximation",
    ),
    "tree-prohibition": (
        "lush_garden_with_unidentified_distant_tree",
        "warning_and_boundary_symbolism",
    ),
    "next-episode-promise": (
        "leaf_shadow_and_whisper_like_motion",
        "unseen_temptation_symbolism_without_entity",
    ),
}


class ProductionPolicyError(ValueError):
    pass


def canonical_json_bytes(payload: object) -> bytes:
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def canonical_json_sha256(payload: object) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _relative(repo_root: Path, path: Path) -> str:
    resolved_root = repo_root.resolve()
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(resolved_root).as_posix()
    except ValueError as error:
        raise ProductionPolicyError(f"Path escaped repository: {path}") from error
    if _ABSOLUTE_WINDOWS.match(relative) or relative.startswith("/"):
        raise ProductionPolicyError("Absolute path leaked into manifest.")
    return relative


def _walk_values(value: Any, *, key: str = "") -> Iterable[tuple[str, Any]]:
    if isinstance(value, Mapping):
        for child_key, child in value.items():
            child_key_text = str(child_key)
            if child_key_text.lower() in _SECRET_KEYS:
                continue
            yield from _walk_values(child, key=child_key_text)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_values(child, key=key)
    else:
        yield key, value


def _text_candidates(value: Any) -> list[str]:
    result: list[str] = []
    for key, item in _walk_values(value):
        if isinstance(item, str) and len(item.strip()) >= 3:
            if key.lower() not in _SECRET_KEYS:
                result.append(item.strip())
    return result


def _record_locator(record: Mapping[str, Any], line_number: int) -> dict[str, object]:
    locator: dict[str, object] = {"record_number": line_number}
    for key in (
        "page", "page_number", "page_index", "volume", "part", "section",
        "heading", "window_id", "report_id", "candidate_id", "source_id",
        "start_page", "end_page", "line_start", "line_end",
    ):
        value = record.get(key)
        if isinstance(value, (str, int, float, bool)) and value not in ("", None):
            locator[key] = value
    return locator


def _preview(texts: list[str], terms: tuple[str, ...]) -> str:
    joined = " | ".join(texts)
    if not joined:
        return ""
    lower = joined.casefold()
    positions = [lower.find(term.casefold()) for term in terms]
    positions = [pos for pos in positions if pos >= 0]
    start = max(0, (min(positions) if positions else 0) - 100)
    snippet = joined[start : start + 420]
    return snippet.replace("\r", " ").replace("\n", " ").strip()


@dataclass(frozen=True, slots=True)
class CandidateRecord:
    event_id: str
    relative_path: str
    record_number: int
    source_ids: tuple[str, ...]
    matched_terms: tuple[str, ...]
    locator: tuple[tuple[str, object], ...]
    preview: str
    record_sha256: str

    def to_manifest(self) -> dict[str, object]:
        return {
            "event_id": self.event_id,
            "relative_path": self.relative_path,
            "record_number": self.record_number,
            "source_ids": list(self.source_ids),
            "matched_terms": list(self.matched_terms),
            "locator": dict(self.locator),
            "preview": self.preview,
            "record_sha256": self.record_sha256,
            "status": "AUTOMATED_PREFILTER_NOT_EVIDENCE",
        }


class AdamResearchProductionBuilder:
    """Build policies, targeted review pack, filler plan, and recitation cues."""

    def __init__(self, repo_root: Path, policy_root: Path | None = None) -> None:
        self.repo_root = Path(repo_root)
        self.policy_root = Path(policy_root) if policy_root is not None else self.repo_root

    def build_all(self) -> dict[str, object]:
        policy_bundle = self._load_and_validate_policies()
        recovered = self._load_required(
            "projects/episode-001-adam/evidence/"
            "recovered-evidence-knowledge-v1.json"
        )
        gap_docket = self._load_required(
            "projects/episode-001-adam/evidence/"
            "evidence-gap-closure-docket-v1.json"
        )
        blueprint = self._load_required(
            "projects/episode-001-adam/cinematic/"
            "editorial-cinematic-blueprint-v1.json"
        )
        event_map = self._load_required(
            "projects/episode-001-adam/editorial/event-map.json"
        )
        source_package = self._load_required(
            "projects/episode-001-adam/contracts/"
            "source-package-v1.draft.json"
        )

        validate_recovered_inputs(recovered, gap_docket, event_map)
        review_pack = self._build_review_pack(
            recovered, gap_docket, event_map, source_package
        )
        filler_plan = self._build_filler_plan(blueprint, policy_bundle)
        recitation_plan = self._build_recitation_plan(blueprint, policy_bundle)
        prompts = build_notebooklm_prompts(review_pack)
        return {
            "policy_bundle": policy_bundle,
            "review_pack": review_pack,
            "filler_plan": filler_plan,
            "recitation_plan": recitation_plan,
            "notebooklm_prompts": prompts,
        }

    def _load_required(self, relative: str) -> Any:
        path = self.repo_root / relative
        if not path.is_file():
            raise ProductionPolicyError(f"Missing required input: {relative}")
        return _load_json(path)

    def _load_and_validate_policies(self) -> dict[str, object]:
        paths = (
            "config/temporary_hadith_verification_policy_v1.json",
            "config/cinematic_filler_policy_v1.json",
            "config/quran_recitation_audio_policy_v1.json",
        )
        items = []
        for path in paths:
            policy_path = self.policy_root / path
            if not policy_path.is_file():
                raise ProductionPolicyError(f"Missing policy input: {path}")
            items.append(_load_json(policy_path))
        bundle = {
            "schema_version": POLICY_BUNDLE_SCHEMA,
            "status": POLICY_STATUS,
            "policies": items,
            "input_fingerprints": {
                path: hashlib.sha256(
                    (self.policy_root / path).read_bytes()
                ).hexdigest()
                for path in paths
            },
        }
        validate_policy_bundle(bundle)
        return bundle

    def _build_review_pack(
        self,
        recovered: Mapping[str, Any],
        gap_docket: Mapping[str, Any],
        event_map: Any,
        source_package: Mapping[str, Any],
    ) -> dict[str, object]:
        events = {
            item["event_id"]: item
            for item in event_map
            if isinstance(item, Mapping) and isinstance(item.get("event_id"), str)
        }
        review_artifacts = recovered.get("review_artifacts", [])
        if not isinstance(review_artifacts, list):
            raise ProductionPolicyError("Recovered review_artifacts must be a list.")

        candidates: dict[str, list[CandidateRecord]] = {
            event_id: [] for event_id in GAP_EVENTS
        }
        scanned_paths: list[str] = []
        missing_paths: list[str] = []
        for item in review_artifacts:
            if not isinstance(item, Mapping):
                continue
            artifact = item.get("artifact")
            if not isinstance(artifact, Mapping):
                continue
            relative = artifact.get("relative_path")
            if not isinstance(relative, str) or not relative:
                continue
            path = self.repo_root / relative
            if not path.is_file():
                missing_paths.append(relative)
                continue
            scanned_paths.append(relative)
            for candidate in self._scan_file(path, relative):
                candidates[candidate.event_id].append(candidate)

        source_items = source_package.get("source_items", [])
        source_by_id = {
            item.get("source_id"): item
            for item in source_items
            if isinstance(item, Mapping) and isinstance(item.get("source_id"), str)
        }

        dossiers: list[dict[str, object]] = []
        for event_id in GAP_EVENTS:
            event = events[event_id]
            event_candidates = sorted(
                candidates[event_id],
                key=lambda item: (
                    item.relative_path,
                    item.record_number,
                    item.record_sha256,
                ),
            )
            source_ids = sorted(
                {
                    source_id
                    for item in event_candidates
                    for source_id in item.source_ids
                }
            )
            dossiers.append(
                {
                    "event_id": event_id,
                    "event_title": event.get("title", ""),
                    "section": event.get("section", ""),
                    "verification_status": event.get("verification_status", ""),
                    "question_ids": list(QUESTION_IDS[event_id]),
                    "search_terms": list(SEARCH_TERMS[event_id]),
                    "candidate_record_count": len(event_candidates),
                    "candidate_source_ids": source_ids,
                    "candidate_source_titles": [
                        {
                            "source_id": source_id,
                            "title": source_by_id.get(source_id, {}).get(
                                "title", ""
                            ),
                            "source_type": source_by_id.get(source_id, {}).get(
                                "source_type", ""
                            ),
                        }
                        for source_id in source_ids
                    ],
                    "candidates": [
                        candidate.to_manifest()
                        for candidate in event_candidates[:80]
                    ],
                    "candidate_limit_applied": len(event_candidates) > 80,
                    "required_human_work": [
                        "extract_exact_text_from_original_file",
                        "verify_locator_and_attribution",
                        "preserve_surrounding_context",
                        "separate_author_statement_from_quoted_report",
                        "record_isnad_when_present",
                        "verify_hadith_grade_via_authorized_reference",
                        "compare_conflicting_reports",
                        "choose_disposition_without_automatic_approval",
                    ],
                    "allowed_dispositions": [
                        "include_assertive",
                        "include_qualified",
                        "omit_unverified",
                    ],
                    "default_disposition": None,
                }
            )

        pack = {
            "schema_version": TARGETED_REVIEW_PACK_SCHEMA,
            "pack_id": "",
            "episode_id": "episode-001-adam",
            "status": REVIEW_STATUS,
            "evidence_gate_status": EVIDENCE_GATE_STATUS,
            "automatic_evidence_approval": AUTOMATIC_APPROVAL_STATUS,
            "live_provider_execution": LIVE_EXECUTION_STATUS,
            "extraction_method": {
                "primary": "ASSISTANT_MANUAL_EXTRACTION_AND_VERIFICATION",
                "parallel_helper": "NOTEBOOKLM_FOR_BULK_LOCATOR_DISCOVERY",
                "notebooklm_may_approve": False,
                "notebooklm_may_grade_hadith": False,
                "automated_prefilter_is_evidence": False,
            },
            "temporary_hadith_verification": {
                "authority": "DORAR_AL_SUNNIYYAH",
                "status": "TEMPORARILY_ALLOWED",
                "exact_scholar_attribution_required": True,
                "exact_source_attribution_required": True,
                "automatic_grading_forbidden": True,
                "human_verification_required": True,
                "original_source_crosscheck_preferred": True,
            },
            "scanned_review_artifact_count": len(sorted(set(scanned_paths))),
            "missing_review_artifact_count": len(sorted(set(missing_paths))),
            "missing_review_artifacts": sorted(set(missing_paths)),
            "events": dossiers,
            "editorial_event": {
                "event_id": EDITORIAL_EVENT,
                "disposition_recommendation": "editorial_only",
                "binding": False,
            },
            "raw_source_files_modified": False,
        }
        pack["pack_id"] = "targeted_review_pack_" + canonical_json_sha256(
            {k: v for k, v in pack.items() if k != "pack_id"}
        )[:16]
        validate_targeted_review_pack(pack)
        return pack

    def _scan_file(
        self, path: Path, relative: str
    ) -> Iterable[CandidateRecord]:
        suffix = path.suffix.lower()
        if suffix not in {".json", ".jsonl"}:
            return ()
        records: list[tuple[int, Any]] = []
        if suffix == ".jsonl":
            with path.open("r", encoding="utf-8-sig", errors="strict") as stream:
                for line_number, line in enumerate(stream, start=1):
                    if not line.strip():
                        continue
                    try:
                        records.append((line_number, json.loads(line)))
                    except json.JSONDecodeError:
                        continue
        else:
            payload = _load_json(path)
            if isinstance(payload, list):
                records = list(enumerate(payload, start=1))
            elif isinstance(payload, Mapping):
                candidate_lists = [
                    value for value in payload.values() if isinstance(value, list)
                ]
                if candidate_lists:
                    for values in candidate_lists:
                        records.extend(enumerate(values, start=1))
                else:
                    records = [(1, payload)]

        output: list[CandidateRecord] = []
        for line_number, record in records:
            if not isinstance(record, Mapping):
                continue
            texts = _text_candidates(record)
            searchable = "\n".join(texts).casefold()
            if not searchable:
                continue
            source_ids = sorted(
                {
                    value
                    for key, value in _walk_values(record)
                    if key == "source_id"
                    and isinstance(value, str)
                    and value.startswith("SRC-")
                }
            )
            encoded = canonical_json_bytes(record)
            for event_id, terms in SEARCH_TERMS.items():
                matched = tuple(
                    term for term in terms if term.casefold() in searchable
                )
                if not matched:
                    continue
                output.append(
                    CandidateRecord(
                        event_id=event_id,
                        relative_path=relative,
                        record_number=line_number,
                        source_ids=tuple(source_ids),
                        matched_terms=matched,
                        locator=tuple(
                            sorted(_record_locator(record, line_number).items())
                        ),
                        preview=_preview(texts, matched),
                        record_sha256=hashlib.sha256(encoded).hexdigest(),
                    )
                )
        return output

    def _build_filler_plan(
        self,
        blueprint: Mapping[str, Any],
        policy_bundle: Mapping[str, Any],
    ) -> dict[str, object]:
        frames = blueprint.get("storyboard", {}).get("frames", [])
        if not isinstance(frames, list) or len(frames) != 14:
            raise ProductionPolicyError("Adam blueprint must contain 14 frames.")
        items: list[dict[str, object]] = []
        for frame in frames:
            trace = frame.get("trace_metadata", {})
            keys = trace.get("frame_keys", [])
            if not isinstance(keys, list) or len(keys) != 1:
                raise ProductionPolicyError("Each frame must have one frame key.")
            key = keys[0]
            suggestions = FILLER_BY_FRAME_KEY.get(key)
            if suggestions is None:
                raise ProductionPolicyError(f"No filler plan for frame key: {key}")
            items.append(
                {
                    "frame_id": frame.get("frame_id"),
                    "position": frame.get("position"),
                    "frame_key": key,
                    "event_ids": trace.get("event_ids", []),
                    "filler_suggestions": list(suggestions),
                    "classification": "SYMBOLIC_CINEMATIC_FILLER",
                    "historical_assertion": False,
                    "geographical_assertion": False,
                    "chronological_assertion": False,
                    "identity_assertion": False,
                    "true_form_assertion": False,
                    "specific_person_judgment": False,
                    "symbolic_only": True,
                    "requires_period_context_validation": key not in {
                        "symbolic-cold-open", "central-question"
                    },
                }
            )
        plan = {
            "schema_version": FILLER_PLAN_SCHEMA,
            "plan_id": "",
            "episode_id": "episode-001-adam",
            "status": "HUMAN_REVIEW_PENDING",
            "music_policy": MUSIC_POLICY,
            "evidence_gate_status": EVIDENCE_GATE_STATUS,
            "general_allowed_contextual_fillers": [
                "battle_preparations_when_battle_context_is_verified",
                "travel_preparations_when_travel_context_is_verified",
                "social_conditions_when_period_context_is_verified",
                "daily_life_ambience_without_event_specific_assertion",
                "environmental_and_material_transitions",
                "conceptual_afterlife_approximation",
            ],
            "general_guardrails": [
                "must_not_change_historical_event",
                "must_not_contradict_selected_evidence",
                "must_not_invent_named_person_action_or_dialogue",
                "must_not_assert_unverified_location_or_chronology",
                "must_not_depict_allah_prophets_or_embodied_angels",
                "must_not_claim_true_form_of_unseen_realm",
                "doctrinal_narration_must_be_evidence_bound",
                "must_not_assign_specific_person_to_paradise_or_hell",
            ],
            "afterlife_visualization": {
                "paradise": {
                    "allowed": True,
                    "purpose": "conceptual_approximation_of_extreme_beauty_and_desirability",
                    "true_form_claim": False,
                },
                "hell": {
                    "allowed": True,
                    "purpose": "conceptual_approximation_of_extreme_punishment_and_warning",
                    "true_form_claim": False,
                    "duration_or_person_specific_judgment_from_visuals": False,
                },
            },
            "frames": items,
        }
        plan["plan_id"] = "cinematic_filler_plan_" + canonical_json_sha256(
            {k: v for k, v in plan.items() if k != "plan_id"}
        )[:16]
        validate_filler_plan(plan)
        return plan

    def _build_recitation_plan(
        self,
        blueprint: Mapping[str, Any],
        policy_bundle: Mapping[str, Any],
    ) -> dict[str, object]:
        frames = blueprint.get("storyboard", {}).get("frames", [])
        by_position = {
            frame.get("position"): frame
            for frame in frames
            if isinstance(frame, Mapping)
        }
        cues: list[dict[str, object]] = []
        for candidate in RECITATION_CANDIDATES:
            frame = by_position.get(candidate["frame_position"])
            if frame is None:
                raise ProductionPolicyError(
                    f"Missing frame position {candidate['frame_position']}"
                )
            cues.append(
                {
                    "cue_key": candidate["cue_key"],
                    "frame_id": frame.get("frame_id"),
                    "frame_position": candidate["frame_position"],
                    "candidate_references": [
                        dict(item) for item in candidate["references"]
                    ],
                    "selection_status": "CANDIDATE_NOT_SELECTED",
                    "recording_status": "NOT_ACQUIRED",
                    "reciter": "مشاري راشد العفاسي",
                    "preferred_recording_contexts": [
                        "قيام الليل",
                        "التراويح",
                        "الصلاة الجهرية",
                    ],
                    "preferred_recording_period": {
                        "start_year": 1998,
                        "end_year": 2010,
                    },
                    "audio_mode": RECITATION_AUDIO_MODE,
                    "narrator_muted": True,
                    "ambience_muted": True,
                    "sound_effects_muted": True,
                    "music_present": False,
                    "verse_boundary_verification_required": True,
                    "recitation_verification_required": True,
                    "rights_status": RIGHTS_STATUS,
                    "publication_allowed": False,
                }
            )
        plan = {
            "schema_version": RECITATION_CUE_PLAN_SCHEMA,
            "plan_id": "",
            "episode_id": "episode-001-adam",
            "status": "CANDIDATE_SELECTION_PENDING",
            "preferred_reciter": "مشاري راشد العفاسي",
            "preferred_period": {"start_year": 1998, "end_year": 2010},
            "preferred_context_priority": [
                "قيام الليل",
                "التراويح",
                "الصلاة الجهرية",
                "تسجيل استديو عند عدم توفر المناسب",
            ],
            "music_policy": MUSIC_POLICY,
            "recitation_audio_mode": RECITATION_AUDIO_MODE,
            "rights_policy": {
                "user_expectation_of_reusability_recorded": True,
                "rights_assumed_clear": False,
                "publication_basis_required": True,
                "status": RIGHTS_STATUS,
            },
            "cues": cues,
        }
        plan["plan_id"] = "quran_recitation_cue_plan_" + canonical_json_sha256(
            {k: v for k, v in plan.items() if k != "plan_id"}
        )[:16]
        validate_recitation_plan(plan)
        return plan


def validate_recovered_inputs(
    recovered: Mapping[str, Any],
    gap_docket: Mapping[str, Any],
    event_map: Any,
) -> None:
    if recovered.get("schema_version") != "siraj-recovered-evidence-knowledge-v1":
        raise ProductionPolicyError("Unexpected recovered knowledge schema.")
    if recovered.get("evidence_gate_status") != EVIDENCE_GATE_STATUS:
        raise ProductionPolicyError("Recovered knowledge gate changed.")
    if recovered.get("automatic_evidence_approval") != AUTOMATIC_APPROVAL_STATUS:
        raise ProductionPolicyError("Recovered knowledge allowed automation.")
    if recovered.get("uncovered_event_ids") != [
        *GAP_EVENTS,
        EDITORIAL_EVENT,
    ]:
        raise ProductionPolicyError("Unexpected uncovered event set.")
    if gap_docket.get("schema_version") != "siraj-evidence-gap-closure-docket-v1":
        raise ProductionPolicyError("Unexpected gap docket schema.")
    if not isinstance(event_map, list):
        raise ProductionPolicyError("Event map must be a list.")
    ids = [
        item.get("event_id")
        for item in event_map
        if isinstance(item, Mapping)
    ]
    if any(event_id not in ids for event_id in (*GAP_EVENTS, EDITORIAL_EVENT)):
        raise ProductionPolicyError("Gap event missing from event map.")


def validate_policy_bundle(bundle: Mapping[str, Any]) -> None:
    if bundle.get("schema_version") != POLICY_BUNDLE_SCHEMA:
        raise ProductionPolicyError("Unexpected policy bundle schema.")
    if bundle.get("status") != POLICY_STATUS:
        raise ProductionPolicyError("Policy bundle must be approved.")
    policies = bundle.get("policies")
    if not isinstance(policies, list) or len(policies) != 3:
        raise ProductionPolicyError("Policy bundle must contain three policies.")
    by_schema = {
        item.get("schema_version"): item
        for item in policies
        if isinstance(item, Mapping)
    }
    hadith = by_schema.get("siraj-temporary-hadith-verification-policy-v1")
    filler = by_schema.get("siraj-cinematic-filler-policy-v1")
    recitation = by_schema.get("siraj-quran-recitation-audio-policy-v1")
    if not all((hadith, filler, recitation)):
        raise ProductionPolicyError("Required production policies are missing.")
    if hadith.get("automatic_hadith_grading") != "FORBIDDEN":
        raise ProductionPolicyError("Automatic hadith grading must be forbidden.")
    if hadith.get("dorar_status") != "TEMPORARILY_ALLOWED":
        raise ProductionPolicyError("Dorar temporary status is missing.")
    if filler.get("music_policy") != MUSIC_POLICY:
        raise ProductionPolicyError("Music prohibition changed.")
    if recitation.get("audio_mode") != RECITATION_AUDIO_MODE:
        raise ProductionPolicyError("Quran recitation must be exclusive audio.")
    if recitation.get("music_policy") != MUSIC_POLICY:
        raise ProductionPolicyError("Music prohibition changed.")
    if recitation.get("rights_status") != RIGHTS_STATUS:
        raise ProductionPolicyError("Recitation rights status must remain unverified.")


def validate_targeted_review_pack(pack: Mapping[str, Any]) -> None:
    if pack.get("schema_version") != TARGETED_REVIEW_PACK_SCHEMA:
        raise ProductionPolicyError("Unexpected targeted review schema.")
    if pack.get("status") != REVIEW_STATUS:
        raise ProductionPolicyError("Targeted review pack must remain pending.")
    if pack.get("evidence_gate_status") != EVIDENCE_GATE_STATUS:
        raise ProductionPolicyError("Targeted review pack opened evidence gate.")
    if pack.get("automatic_evidence_approval") != AUTOMATIC_APPROVAL_STATUS:
        raise ProductionPolicyError("Targeted review pack allowed auto approval.")
    events = pack.get("events")
    if not isinstance(events, list) or [
        item.get("event_id") for item in events
    ] != list(GAP_EVENTS):
        raise ProductionPolicyError("Targeted review pack must contain three gaps.")
    if any(item.get("default_disposition") is not None for item in events):
        raise ProductionPolicyError("Factual gap received a default decision.")
    if any(
        candidate.get("status") != "AUTOMATED_PREFILTER_NOT_EVIDENCE"
        for item in events
        for candidate in item.get("candidates", [])
    ):
        raise ProductionPolicyError("Candidate prefilter became evidence.")


def validate_filler_plan(plan: Mapping[str, Any]) -> None:
    if plan.get("schema_version") != FILLER_PLAN_SCHEMA:
        raise ProductionPolicyError("Unexpected filler plan schema.")
    if plan.get("music_policy") != MUSIC_POLICY:
        raise ProductionPolicyError("Music must remain prohibited.")
    frames = plan.get("frames")
    if not isinstance(frames, list) or len(frames) != 14:
        raise ProductionPolicyError("Adam filler plan must cover 14 frames.")
    for frame in frames:
        if frame.get("classification") != "SYMBOLIC_CINEMATIC_FILLER":
            raise ProductionPolicyError("Filler classification changed.")
        for key in (
            "historical_assertion",
            "geographical_assertion",
            "chronological_assertion",
            "identity_assertion",
            "true_form_assertion",
            "specific_person_judgment",
        ):
            if frame.get(key) is not False:
                raise ProductionPolicyError(f"Filler assertion must be false: {key}")
        if frame.get("symbolic_only") is not True:
            raise ProductionPolicyError("Filler must be symbolic.")


def validate_recitation_plan(plan: Mapping[str, Any]) -> None:
    if plan.get("schema_version") != RECITATION_CUE_PLAN_SCHEMA:
        raise ProductionPolicyError("Unexpected recitation cue schema.")
    if plan.get("preferred_reciter") != "مشاري راشد العفاسي":
        raise ProductionPolicyError("Preferred reciter changed.")
    if plan.get("music_policy") != MUSIC_POLICY:
        raise ProductionPolicyError("Music must remain prohibited.")
    if plan.get("recitation_audio_mode") != RECITATION_AUDIO_MODE:
        raise ProductionPolicyError("Recitation must be Quran-only audio.")
    rights = plan.get("rights_policy")
    if not isinstance(rights, Mapping) or rights.get("rights_assumed_clear") is not False:
        raise ProductionPolicyError("Rights cannot be assumed clear.")
    cues = plan.get("cues")
    if not isinstance(cues, list) or not cues:
        raise ProductionPolicyError("Recitation cue candidates are missing.")
    for cue in cues:
        if cue.get("narrator_muted") is not True:
            raise ProductionPolicyError("Narrator must be muted during recitation.")
        if cue.get("ambience_muted") is not True:
            raise ProductionPolicyError("Ambience must be muted during recitation.")
        if cue.get("sound_effects_muted") is not True:
            raise ProductionPolicyError("Effects must be muted during recitation.")
        if cue.get("music_present") is not False:
            raise ProductionPolicyError("Music is forbidden.")
        if cue.get("publication_allowed") is not False:
            raise ProductionPolicyError("Uncleared recitation cannot be published.")


def build_notebooklm_prompts(review_pack: Mapping[str, Any]) -> str:
    validate_targeted_review_pack(review_pack)
    lines = [
        "# حزمة تعليمات NotebookLM — فجوات أدلة حلقة آدم",
        "",
        "## قواعد إلزامية مشتركة",
        "",
        "1. لا تلخص من الذاكرة ولا تستخدم معرفة خارج الملفات المرفوعة.",
        "2. أعد النص العربي المطابق حرفيًا مع سياق كافٍ قبله وبعده.",
        "3. اذكر اسم المصدر والجزء والصفحة والباب أو رقم السجل بدقة.",
        "4. افصل كلام المؤلف عن النص المنقول وعن الإسناد.",
        "5. لا تصحح حديثًا ولا تضعفه من عندك، ولا تعتبر تكرار الخبر تصحيحًا له.",
        "6. عند وجود حكم حديثي، انقل اسم العالم والكتاب ونص الحكم كما هو.",
        "7. اعرض الروايات المتعارضة منفصلة ولا تدمجها.",
        "8. لا تتخذ قرار الإدراج النهائي؛ أعد مادة مراجعة فقط.",
        "",
    ]
    for event in review_pack["events"]:
        lines.extend(
            [
                f"## {event['event_id']} — {event['event_title']}",
                "",
                f"الأسئلة المرتبطة: {', '.join(event['question_ids'])}",
                "",
                "ابحث عن الألفاظ والمفاهيم التالية:",
                "",
                *[f"- {term}" for term in event["search_terms"]],
                "",
                "أعد جدولًا لكل موضع يحتوي على:",
                "",
                "- النص الحرفي.",
                "- 150–300 كلمة من السياق عند الحاجة.",
                "- المصدر والجزء والصفحة والباب.",
                "- القائل الأصلي أو صاحب الرواية.",
                "- الإسناد كاملًا إن وجد.",
                "- الحكم المنقول واسم صاحبه ومصدره إن وجد.",
                "- هل النص جازم أم تفسيري أم تاريخي أم إسرائيلي أم ضعيف.",
                "- أوجه التعارض أو الاختلاف مع المواضع الأخرى.",
                "- أي نقص يمنع الاعتماد.",
                "",
            ]
        )
    lines.extend(
        [
            "## شكل التسليم",
            "",
            "سلّم ملفًا منفصلًا لكل حدث، ولا تخلط الأحداث الثلاثة.",
            "الحالة النهائية لكل نتيجة: CANDIDATE_FOR_ASSISTANT_VERIFICATION.",
            "",
        ]
    )
    return "\n".join(lines)


def write_outputs(
    output_root: Path,
    built: Mapping[str, object],
) -> dict[str, Path]:
    output_root = Path(output_root)
    paths = {
        "review_pack": output_root
        / "projects/episode-001-adam/evidence/targeted-review-pack-v1.json",
        "notebooklm_prompts": output_root
        / "projects/episode-001-adam/evidence/notebooklm-extraction-prompts-v1.md",
        "filler_plan": output_root
        / "projects/episode-001-adam/cinematic/filler-plan-v1.json",
        "recitation_plan": output_root
        / "projects/episode-001-adam/audio/quran-recitation-cue-plan-v1.json",
    }
    for key, path in paths.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        if key == "notebooklm_prompts":
            text = str(built[key]).replace("\r\n", "\n").replace("\r", "\n")
            if not text.endswith("\n"):
                text += "\n"
            path.write_text(text, encoding="utf-8", newline="\n")
        else:
            path.write_bytes(canonical_json_bytes(built[key]))
    return paths
