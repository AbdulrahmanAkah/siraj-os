from hashlib import sha256

from src.application.narrative_architecture.narrative_architect import NarrativeArchitect

from .models import ScriptSegment, ScriptStructure


class ScriptArchitect:
    """Deterministically turns narrative beats into script-structure segments."""

    _SEGMENT_TYPES = {
        "SETUP": "OPENING_HOOK",
        "CONTEXT": "BACKGROUND",
        "ESCALATION": "DEVELOPMENT",
        "TURNING_POINT": "REVEAL",
        "CLIMAX": "CLIMAX",
        "AFTERMATH": "RESOLUTION",
        "LEGACY": "EPILOGUE",
    }
    _PURPOSES = {
        "OPENING_HOOK": "Establish the documentary's opening focus.",
        "BACKGROUND": "Provide essential historical context.",
        "DEVELOPMENT": "Develop the central historical progression.",
        "REVEAL": "Reveal the narrative turn.",
        "CLIMAX": "Present the documentary's decisive moment.",
        "RESOLUTION": "Resolve the immediate historical outcome.",
        "EPILOGUE": "Connect the outcome to its continuing legacy.",
    }
    _BASE_DURATIONS = {
        "OPENING_HOOK": 1.0,
        "BACKGROUND": 1.25,
        "DEVELOPMENT": 1.5,
        "REVEAL": 1.25,
        "CLIMAX": 2.0,
        "RESOLUTION": 1.25,
        "EPILOGUE": 1.0,
    }
    _COMPLEXITY_ADJUSTMENT = {"LOW": 0.0, "MEDIUM": 0.25, "HIGH": 0.5}

    def __init__(self, narrative_architect):
        if not isinstance(narrative_architect, NarrativeArchitect):
            raise TypeError("ScriptArchitect requires a NarrativeArchitect")
        self.narrative_architect = narrative_architect
        self._architectures_by_id = {}

    def build_script_structure(self, narrative_architecture=None):
        narrative_architecture = self._architecture(narrative_architecture)
        self._architectures_by_id[narrative_architecture.architecture_id] = (
            narrative_architecture
        )
        segments = self.generate_segments(narrative_architecture)
        structure_key = "\x00".join(
            [narrative_architecture.architecture_id, *(segment.segment_id for segment in segments)]
        )
        return ScriptStructure(
            structure_id=(
                f"script_structure_{sha256(structure_key.encode('utf-8')).hexdigest()[:16]}"
            ),
            narrative_architecture_id=narrative_architecture.architecture_id,
            segments=segments,
            estimated_runtime=self.estimate_runtime(narrative_architecture, segments),
            segment_count=len(segments),
        )

    def generate_segments(self, narrative_architecture=None):
        narrative_architecture = self._architecture(narrative_architecture)
        assignments = self.assign_segment_types(narrative_architecture)
        segments = []
        for position, beat in enumerate(
            sorted(
                narrative_architecture.beats,
                key=lambda item: (item.position, item.beat_id),
            )
        ):
            segment_type = assignments[beat.beat_id]
            segments.append(
                ScriptSegment(
                    segment_id=self._segment_id(
                        narrative_architecture.architecture_id,
                        beat.beat_id,
                        segment_type,
                    ),
                    beat_id=beat.beat_id,
                    segment_type=segment_type,
                    purpose=self._PURPOSES[segment_type],
                    estimated_duration=self._segment_duration(
                        segment_type,
                        len(beat.event_ids),
                        narrative_architecture.estimated_complexity,
                    ),
                    position=position,
                )
            )
        return segments

    def assign_segment_types(self, narrative_architecture=None):
        narrative_architecture = self._architecture(narrative_architecture)
        return {
            beat.beat_id: self._SEGMENT_TYPES[beat.beat_type]
            for beat in narrative_architecture.beats
        }

    def estimate_runtime(self, narrative_architecture=None, segments=None):
        narrative_architecture = self._architecture(narrative_architecture)
        segments = (
            self.generate_segments(narrative_architecture)
            if segments is None
            else list(segments)
        )
        return round(sum(segment.estimated_duration for segment in segments), 2)

    def validate_structure(self, script_structure, narrative_architecture=None):
        if script_structure is None or not script_structure.segments:
            return False
        narrative_architecture = (
            narrative_architecture
            or self._architectures_by_id.get(
                script_structure.narrative_architecture_id
            )
            or self._architecture(None)
        )
        segments = script_structure.segments
        segment_ids = [segment.segment_id for segment in segments]
        if len(segment_ids) != len(set(segment_ids)):
            return False
        if sum(segment.segment_type == "OPENING_HOOK" for segment in segments) != 1:
            return False
        if sum(segment.segment_type == "CLIMAX" for segment in segments) != 1:
            return False
        if not any(
            segment.segment_type in {"RESOLUTION", "EPILOGUE"}
            for segment in segments
        ):
            return False
        if [segment.position for segment in segments] != list(range(len(segments))):
            return False
        if segments != sorted(segments, key=lambda item: (item.position, item.segment_id)):
            return False
        beat_ids = {beat.beat_id for beat in narrative_architecture.beats}
        segment_beat_ids = [segment.beat_id for segment in segments]
        return (
            len(segment_beat_ids) == len(set(segment_beat_ids))
            and set(segment_beat_ids) == beat_ids
        )

    def _architecture(self, narrative_architecture):
        return (
            self.narrative_architect.build_narrative_architecture()
            if narrative_architecture is None
            else narrative_architecture
        )

    @classmethod
    def _segment_duration(cls, segment_type, event_count, complexity):
        return round(
            cls._BASE_DURATIONS[segment_type]
            + min(event_count, 3) * 0.2
            + cls._COMPLEXITY_ADJUSTMENT.get(complexity, 0.0),
            2,
        )

    @staticmethod
    def _segment_id(architecture_id, beat_id, segment_type):
        key = "\x00".join([architecture_id, beat_id, segment_type])
        return f"segment_{sha256(key.encode('utf-8')).hexdigest()[:16]}"


__all__ = ["ScriptArchitect"]
