"""Bridge approved editorial episode data into a cinematic storyboard blueprint.

The bridge is deterministic and offline. It preserves event order and trace data,
withholds evidence references until an approved evidence package is explicitly
bound, and delegates narrative/media planning to the cinematic compiler. It does
not call Runware or any other provider.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Iterable, Mapping

from src.application.documentary_intelligence import deterministic_id

from .cinematic_compiler import (
    CinematicCompilationPolicy,
    CinematicSeriesCompiler,
    CompiledCinematicEpisode,
)
from .cinematic_series import (
    RUNWARE_EXECUTION_STATUS,
    CinematicSeriesError,
    EpisodeSeriesContract,
    NarrativeFunction,
)
from .models import Storyboard, StoryboardFrame


EDITORIAL_STORYBOARD_BRIDGE_SCHEMA_VERSION = "siraj-editorial-storyboard-bridge-v1"
EDITORIAL_STORYBOARD_PROFILE_SCHEMA_VERSION = "siraj-editorial-storyboard-profile-v1"
EVIDENCE_GATE_WITHHELD = "WITHHELD_PENDING_APPROVED_EVIDENCE_PACKAGE"
LIVE_EXECUTION_STATUS = "BLOCKED"


@dataclass(frozen=True, slots=True)
class EditorialFrameSpec:
    frame_key: str
    frame_purpose: str
    event_ids: tuple[str, ...] = ()
    editorial_tease_event_ids: tuple[str, ...] = ()

    def validate(self) -> None:
        if not self.frame_key.strip() or not self.frame_purpose.strip():
            raise CinematicSeriesError(
                "Editorial frame key and purpose must not be blank."
            )
        if len(set(self.event_ids)) != len(self.event_ids):
            raise CinematicSeriesError(
                f"Editorial frame {self.frame_key} repeats an event id."
            )
        if len(set(self.editorial_tease_event_ids)) != len(
            self.editorial_tease_event_ids
        ):
            raise CinematicSeriesError(
                f"Editorial frame {self.frame_key} repeats a tease event id."
            )


@dataclass(frozen=True, slots=True)
class EditorialStoryboardProfile:
    profile_id: str
    episode_id: str
    series_contract: EpisodeSeriesContract
    frames: tuple[EditorialFrameSpec, ...]
    schema_version: str = EDITORIAL_STORYBOARD_PROFILE_SCHEMA_VERSION

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object]) -> "EditorialStoryboardProfile":
        if payload.get("schema_version") != EDITORIAL_STORYBOARD_PROFILE_SCHEMA_VERSION:
            raise CinematicSeriesError("Unexpected editorial storyboard profile schema.")

        contract_payload = payload.get("series_contract")
        if not isinstance(contract_payload, Mapping):
            raise CinematicSeriesError("Profile series_contract must be an object.")
        contract = EpisodeSeriesContract(
            series_title=_required_text(contract_payload, "series_title"),
            season_title=_required_text(contract_payload, "season_title"),
            episode_id=_required_text(contract_payload, "episode_id"),
            season_question=_required_text(contract_payload, "season_question"),
            central_question=_required_text(contract_payload, "central_question"),
            emotional_promise=_required_text(contract_payload, "emotional_promise"),
            knowledge_promise=_required_text(contract_payload, "knowledge_promise"),
            next_episode_question=_required_text(
                contract_payload, "next_episode_question"
            ),
            unresolved_thread_from_previous=_optional_text(
                contract_payload.get("unresolved_thread_from_previous")
            ),
        )

        raw_frames = payload.get("frames")
        if not isinstance(raw_frames, list):
            raise CinematicSeriesError("Profile frames must be a list.")
        frames: list[EditorialFrameSpec] = []
        for index, item in enumerate(raw_frames):
            if not isinstance(item, Mapping):
                raise CinematicSeriesError(
                    f"Profile frame {index} must be an object."
                )
            frames.append(
                EditorialFrameSpec(
                    frame_key=_required_text(item, "frame_key"),
                    frame_purpose=_required_text(item, "frame_purpose"),
                    event_ids=_string_tuple(item.get("event_ids", []), "event_ids"),
                    editorial_tease_event_ids=_string_tuple(
                        item.get("editorial_tease_event_ids", []),
                        "editorial_tease_event_ids",
                    ),
                )
            )

        profile = cls(
            profile_id=_required_text(payload, "profile_id"),
            episode_id=_required_text(payload, "episode_id"),
            series_contract=contract,
            frames=tuple(frames),
        )
        profile.validate()
        return profile

    def validate(self) -> None:
        if self.schema_version != EDITORIAL_STORYBOARD_PROFILE_SCHEMA_VERSION:
            raise CinematicSeriesError("Unexpected editorial storyboard profile schema.")
        if not self.profile_id.strip() or not self.episode_id.strip():
            raise CinematicSeriesError("Profile id and episode id must not be blank.")
        if self.series_contract.episode_id != self.episode_id:
            raise CinematicSeriesError(
                "Profile and series contract must reference the same episode."
            )
        self.series_contract.validate()
        if len(self.frames) < 7:
            raise CinematicSeriesError(
                "Editorial profile must contain at least seven frames."
            )
        keys = [frame.frame_key for frame in self.frames]
        if len(set(keys)) != len(keys):
            raise CinematicSeriesError("Editorial frame keys must be unique.")
        for frame in self.frames:
            frame.validate()


@dataclass(frozen=True, slots=True)
class EditorialCinematicBlueprint:
    bridge_id: str
    storyboard: Storyboard
    compiled_episode: CompiledCinematicEpisode
    input_fingerprints: tuple[tuple[str, str], ...]
    source_approval_status: str
    evidence_gate_status: str
    verification_status: str
    frame_event_coverage: tuple[str, ...]
    schema_version: str = EDITORIAL_STORYBOARD_BRIDGE_SCHEMA_VERSION
    live_execution_status: str = LIVE_EXECUTION_STATUS

    def to_manifest(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "bridge_id": self.bridge_id,
            "episode_id": self.compiled_episode.plan.contract.episode_id,
            "source_approval_status": self.source_approval_status,
            "evidence_gate_status": self.evidence_gate_status,
            "verification_status": self.verification_status,
            "live_execution_status": self.live_execution_status,
            "runware_execution_status": (
                self.compiled_episode.plan.runware_execution_status
            ),
            "input_fingerprints": dict(self.input_fingerprints),
            "storyboard": {
                "storyboard_id": self.storyboard.storyboard_id,
                "scene_plan_id": self.storyboard.scene_plan_id,
                "frame_count": self.storyboard.frame_count,
                "validation_state": self.storyboard.validation_state,
                "frames": [
                    {
                        "frame_id": frame.frame_id,
                        "scene_id": frame.scene_id,
                        "frame_purpose": frame.frame_purpose,
                        "referenced_evidence_ids": list(
                            frame.referenced_evidence_ids
                        ),
                        "position": frame.position,
                        "trace_metadata": frame.trace_metadata,
                    }
                    for frame in self.storyboard.frames
                ],
            },
            "frame_event_coverage": list(self.frame_event_coverage),
            "cinematic_compilation": self.compiled_episode.to_manifest(),
        }

    def to_json(self, *, pretty: bool = False) -> str:
        if pretty:
            return json.dumps(
                self.to_manifest(),
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            ) + "\n"
        return json.dumps(
            self.to_manifest(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )


class EditorialStoryboardBridge:
    """Convert episode editorial contracts into an offline cinematic blueprint."""

    REQUIRED_INPUT_PATHS = (
        "contracts/episode-definition-v1.json",
        "contracts/integration-validation-v1.json",
        "contracts/source-package-v1.draft.json",
        "editorial/event-map.json",
        "editorial/human-decisions.json",
    )

    def __init__(self, compiler: CinematicSeriesCompiler | None = None) -> None:
        self._compiler = compiler or CinematicSeriesCompiler()

    def build_from_project(
        self,
        episode_root: Path,
        profile_path: Path,
    ) -> EditorialCinematicBlueprint:
        episode_root = Path(episode_root)
        profile_path = Path(profile_path)
        inputs: dict[str, bytes] = {}
        for relative in self.REQUIRED_INPUT_PATHS:
            path = episode_root / relative
            if not path.is_file():
                raise CinematicSeriesError(f"Missing editorial input: {path}")
            inputs[relative] = path.read_bytes()
        if not profile_path.is_file():
            raise CinematicSeriesError(f"Missing storyboard profile: {profile_path}")
        inputs["cinematic/storyboard-profile-v1.json"] = profile_path.read_bytes()

        parsed = {
            key: _load_json_bytes(value, key)
            for key, value in inputs.items()
        }
        return self.build_from_data(
            episode_definition=_object(parsed["contracts/episode-definition-v1.json"]),
            integration_validation=_object(
                parsed["contracts/integration-validation-v1.json"]
            ),
            source_package=_object(
                parsed["contracts/source-package-v1.draft.json"]
            ),
            event_map=_object_list(parsed["editorial/event-map.json"]),
            human_decisions=_object_list(
                parsed["editorial/human-decisions.json"]
            ),
            profile=EditorialStoryboardProfile.from_mapping(
                _object(parsed["cinematic/storyboard-profile-v1.json"])
            ),
            input_fingerprints={
                key: canonical_text_sha256(value) for key, value in inputs.items()
            },
        )

    def build_from_data(
        self,
        *,
        episode_definition: Mapping[str, object],
        integration_validation: Mapping[str, object],
        source_package: Mapping[str, object],
        event_map: Iterable[Mapping[str, object]],
        human_decisions: Iterable[Mapping[str, object]],
        profile: EditorialStoryboardProfile,
        input_fingerprints: Mapping[str, str] | None = None,
    ) -> EditorialCinematicBlueprint:
        profile.validate()
        events = tuple(event_map)
        decisions = tuple(human_decisions)
        self._validate_contracts(
            episode_definition,
            integration_validation,
            source_package,
            events,
            decisions,
            profile,
        )

        event_by_id = {
            _required_text(event, "event_id"): event for event in events
        }
        required_event_ids = _required_string_list(
            _object(episode_definition.get("historical_scope")),
            "required_event_ids",
        )
        self._validate_profile_event_coverage(profile, required_event_ids, event_by_id)

        source_approval = _required_text(
            _object(episode_definition.get("source_package")),
            "approval_status",
        )
        if source_approval == "APPROVED":
            raise CinematicSeriesError(
                "Approved evidence requires an explicit event-to-evidence binding; "
                "bridge v1 never fabricates evidence ids."
            )

        frames = tuple(
            self._build_frame(index, spec, event_by_id, source_approval)
            for index, spec in enumerate(profile.frames)
        )
        coverage = tuple(
            event_id for spec in profile.frames for event_id in spec.event_ids
        )
        scene_plan_id = deterministic_id(
            "editorial_scene_plan",
            [profile.profile_id, profile.episode_id, coverage],
        )
        storyboard_id = deterministic_id(
            "editorial_storyboard",
            [scene_plan_id, [frame.frame_id for frame in frames]],
        )
        storyboard = Storyboard(
            storyboard_id=storyboard_id,
            scene_plan_id=scene_plan_id,
            frames=list(frames),
            frame_count=len(frames),
            trace_metadata={
                "episode_ids": [profile.episode_id],
                "profile_ids": [profile.profile_id],
                "source_approval_statuses": [source_approval],
                "evidence_gate_statuses": [EVIDENCE_GATE_WITHHELD],
            },
        )
        target_minutes = _required_int(
            episode_definition, "target_duration_minutes"
        )
        compiled = self._compiler.compile(
            storyboard,
            profile.series_contract,
            policy=CinematicCompilationPolicy(
                target_episode_seconds=target_minutes * 60
            ),
        )
        self._validate_compiled_alignment(compiled, profile)

        fingerprints = tuple(sorted((input_fingerprints or {}).items()))
        bridge_id = deterministic_id(
            "editorial_storyboard_bridge",
            [
                EDITORIAL_STORYBOARD_BRIDGE_SCHEMA_VERSION,
                profile.profile_id,
                storyboard.storyboard_id,
                compiled.compilation_id,
                fingerprints,
                coverage,
                source_approval,
            ],
        )
        verification_status = _required_text(
            _object(episode_definition.get("verification", {})),
            "status",
            fallback="deferred",
        )
        blueprint = EditorialCinematicBlueprint(
            bridge_id=bridge_id,
            storyboard=storyboard,
            compiled_episode=compiled,
            input_fingerprints=fingerprints,
            source_approval_status=source_approval,
            evidence_gate_status=EVIDENCE_GATE_WITHHELD,
            verification_status=verification_status,
            frame_event_coverage=coverage,
        )
        self._validate_blueprint(blueprint, required_event_ids)
        return blueprint

    @staticmethod
    def _validate_contracts(
        episode_definition: Mapping[str, object],
        integration_validation: Mapping[str, object],
        source_package: Mapping[str, object],
        events: tuple[Mapping[str, object], ...],
        decisions: tuple[Mapping[str, object], ...],
        profile: EditorialStoryboardProfile,
    ) -> None:
        if episode_definition.get("schema_version") != "siraj-episode-definition-v1":
            raise CinematicSeriesError("Unexpected episode definition schema.")
        episode_id = _required_text(episode_definition, "episode_id")
        if episode_id != profile.episode_id:
            raise CinematicSeriesError("Profile does not match the episode definition.")
        if _required_text(episode_definition, "central_question") != (
            profile.series_contract.central_question
        ):
            raise CinematicSeriesError(
                "Series contract central question must match the episode definition."
            )
        for key, expected in (
            ("minimum_duration_minutes", 18),
            ("target_duration_minutes", 22),
            ("maximum_duration_minutes", 25),
        ):
            if _required_int(episode_definition, key) != expected:
                raise CinematicSeriesError(
                    f"Episode {key} differs from the approved 18/22/25 contract."
                )

        if integration_validation.get("status") != "PASS":
            raise CinematicSeriesError("Editorial integration validation must be PASS.")
        counts = _object(integration_validation.get("counts"))
        expected_counts = {
            "events": 37,
            "human_decisions": 16,
            "research_questions": 32,
            "source_records": 30,
        }
        for key, expected in expected_counts.items():
            if counts.get(key) != expected:
                raise CinematicSeriesError(
                    f"Editorial integration count {key} must equal {expected}."
                )
        if len(events) != 37 or len(decisions) != 16:
            raise CinematicSeriesError(
                "Event map and human decisions must match validated integration counts."
            )
        source_items = source_package.get("source_items")
        research_questions = source_package.get("research_questions")
        if not isinstance(source_items, list) or len(source_items) != 30:
            raise CinematicSeriesError("Source package must contain 30 source items.")
        if not isinstance(research_questions, list) or len(research_questions) != 32:
            raise CinematicSeriesError(
                "Source package must contain 32 research questions."
            )
        approved_decisions = {
            _required_text(item, "decision_id")
            for item in decisions
            if item.get("status") == "approved"
        }
        required_decisions = {
            "HD-GLOBAL-007",
            "HD-GLOBAL-009",
            "HD-GLOBAL-010",
            "HD-ADAM-001",
            "HD-ADAM-002",
        }
        if not required_decisions.issubset(approved_decisions):
            raise CinematicSeriesError(
                "Required approved editorial decisions are missing."
            )

    @staticmethod
    def _validate_profile_event_coverage(
        profile: EditorialStoryboardProfile,
        required_event_ids: list[str],
        event_by_id: Mapping[str, Mapping[str, object]],
    ) -> None:
        if len(event_by_id) != len(required_event_ids):
            raise CinematicSeriesError(
                "Event map ids must be unique and match the episode requirement count."
            )
        if set(event_by_id) != set(required_event_ids):
            raise CinematicSeriesError(
                "Event map does not exactly match required episode event ids."
            )
        ordered_event_ids = [
            _required_text(event, "event_id") for event in event_by_id.values()
        ]
        if ordered_event_ids != required_event_ids:
            raise CinematicSeriesError(
                "Event map must preserve the approved required-event order."
            )
        event_orders = [
            _required_int(event, "order") for event in event_by_id.values()
        ]
        if event_orders != sorted(event_orders) or len(set(event_orders)) != len(event_orders):
            raise CinematicSeriesError(
                "Event map order values must be unique and ascending."
            )
        coverage = [
            event_id for frame in profile.frames for event_id in frame.event_ids
        ]
        if len(coverage) != len(set(coverage)):
            raise CinematicSeriesError(
                "Profile factual event coverage must not repeat event ids."
            )
        if coverage != required_event_ids:
            raise CinematicSeriesError(
                "Profile must cover required event ids exactly in approved order."
            )
        for frame in profile.frames:
            unknown_teases = set(frame.editorial_tease_event_ids).difference(event_by_id)
            if unknown_teases:
                raise CinematicSeriesError(
                    f"Frame {frame.frame_key} teases unknown events: "
                    f"{sorted(unknown_teases)}"
                )

    @staticmethod
    def _build_frame(
        position: int,
        spec: EditorialFrameSpec,
        event_by_id: Mapping[str, Mapping[str, object]],
        source_approval: str,
    ) -> StoryboardFrame:
        selected = [event_by_id[event_id] for event_id in spec.event_ids]
        question_ids = _ordered_unique(
            question_id
            for event in selected
            for question_id in _string_tuple(event.get("question_ids", []), "question_ids")
        )
        event_titles = tuple(_required_text(event, "title") for event in selected)
        sections = _ordered_unique(
            _required_text(event, "section") for event in selected
        )
        verification_statuses = _ordered_unique(
            _required_text(event, "verification_status") for event in selected
        )
        chronology_types = _ordered_unique(
            _required_text(event, "chronology_type") for event in selected
        )
        frame_id = deterministic_id(
            "editorial_frame",
            [position, spec.frame_key, spec.event_ids, spec.editorial_tease_event_ids],
        )
        scene_id = deterministic_id(
            "editorial_scene",
            [position, spec.frame_key, spec.event_ids],
        )
        return StoryboardFrame(
            frame_id=frame_id,
            scene_id=scene_id,
            frame_purpose=spec.frame_purpose,
            referenced_evidence_ids=[],
            position=position,
            trace_metadata={
                "frame_keys": [spec.frame_key],
                "event_ids": list(spec.event_ids),
                "editorial_tease_event_ids": list(spec.editorial_tease_event_ids),
                "question_ids": list(question_ids),
                "event_titles": list(event_titles),
                "sections": list(sections),
                "verification_statuses": list(verification_statuses),
                "chronology_types": list(chronology_types),
                "source_approval_statuses": [source_approval],
                "evidence_gate_statuses": [EVIDENCE_GATE_WITHHELD],
            },
        )

    @staticmethod
    def _validate_compiled_alignment(
        compiled: CompiledCinematicEpisode,
        profile: EditorialStoryboardProfile,
    ) -> None:
        climax_indexes = [
            index
            for index, directive in enumerate(compiled.plan.directives)
            if directive.narrative_function is NarrativeFunction.CLIMAX
        ]
        if climax_indexes != [9]:
            raise CinematicSeriesError(
                "Adam profile must place the compiler climax at frame index 9."
            )
        climax_frame = profile.frames[9]
        expected_climax_events = {"EV-ADAM-052", "EV-ADAM-053", "EV-ADAM-054", "EV-ADAM-055"}
        if not expected_climax_events.issubset(climax_frame.event_ids):
            raise CinematicSeriesError(
                "Adam climax must contain Iblis's refusal, argument, expulsion, "
                "and declared enmity."
            )
        if compiled.plan.generated_video_seconds != 0:
            raise CinematicSeriesError(
                "Editorial bridge cannot pre-allocate generated-video seconds."
            )
        if compiled.plan.runware_execution_status != RUNWARE_EXECUTION_STATUS:
            raise CinematicSeriesError("Runware execution gate changed unexpectedly.")

    @staticmethod
    def _validate_blueprint(
        blueprint: EditorialCinematicBlueprint,
        required_event_ids: list[str],
    ) -> None:
        if blueprint.schema_version != EDITORIAL_STORYBOARD_BRIDGE_SCHEMA_VERSION:
            raise CinematicSeriesError("Unexpected editorial bridge schema.")
        if blueprint.live_execution_status != LIVE_EXECUTION_STATUS:
            raise CinematicSeriesError("Editorial bridge cannot enable live execution.")
        if blueprint.evidence_gate_status != EVIDENCE_GATE_WITHHELD:
            raise CinematicSeriesError("Evidence gate must remain withheld.")
        if list(blueprint.frame_event_coverage) != required_event_ids:
            raise CinematicSeriesError("Blueprint event coverage changed unexpectedly.")
        if blueprint.storyboard.frame_count != 14:
            raise CinematicSeriesError("Adam cinematic profile must produce 14 frames.")
        if any(
            frame.referenced_evidence_ids for frame in blueprint.storyboard.frames
        ):
            raise CinematicSeriesError(
                "Editorial-only blueprint must not expose evidence ids."
            )
        if blueprint.compiled_episode.live_execution_allowed:
            raise CinematicSeriesError("Compiled episode cannot enable live execution.")


def canonical_text_sha256(data: bytes) -> str:
    """Hash canonical UTF-8/LF text independently of Windows checkout endings."""

    text = data.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_blueprint(path: Path, blueprint: EditorialCinematicBlueprint) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(blueprint.to_json(pretty=True))


def _load_json_bytes(data: bytes, name: str) -> object:
    try:
        return json.loads(data.decode("utf-8-sig"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise CinematicSeriesError(f"Invalid JSON input {name}: {error}") from error


def _object(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise CinematicSeriesError("Expected a JSON object.")
    return value


def _object_list(value: object) -> list[Mapping[str, object]]:
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        raise CinematicSeriesError("Expected a list of JSON objects.")
    return list(value)


def _required_text(
    payload: Mapping[str, object],
    key: str,
    *,
    fallback: str | None = None,
) -> str:
    value = payload.get(key, fallback)
    if not isinstance(value, str) or not value.strip():
        raise CinematicSeriesError(f"{key} must be a nonblank string.")
    return value


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise CinematicSeriesError("Optional text must be null or nonblank.")
    return value


def _required_int(payload: Mapping[str, object], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise CinematicSeriesError(f"{key} must be an integer.")
    return value


def _string_tuple(value: object, name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise CinematicSeriesError(f"{name} must be a list of nonblank strings.")
    return tuple(value)


def _required_string_list(payload: Mapping[str, object], key: str) -> list[str]:
    return list(_string_tuple(payload.get(key), key))


def _ordered_unique(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))
