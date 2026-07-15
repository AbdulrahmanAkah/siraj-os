from hashlib import sha256

from src.application.documentary_planning.documentary_planner import DocumentaryPlanner

from .models import NarrativeArc, NarrativeArchitecture, NarrativeBeat


class NarrativeArchitect:
    """Deterministically maps documentary-plan sections to narrative beats and arcs."""

    _INTRODUCTION_ID = "introduction"
    _CONCLUSION_ID = "conclusion"
    _END_TYPES = {"AFTERMATH", "LEGACY"}

    def __init__(self, documentary_planner):
        if not isinstance(documentary_planner, DocumentaryPlanner):
            raise TypeError("NarrativeArchitect requires a DocumentaryPlanner")
        self.documentary_planner = documentary_planner
        self._plans_by_id = {}

    def build_narrative_architecture(self, documentary_plan=None):
        documentary_plan = self._plan(documentary_plan)
        self._plans_by_id[documentary_plan.plan_id] = documentary_plan
        beats = self.generate_beats(documentary_plan)
        arcs = self.build_arcs(beats)
        architecture_key = "\x00".join(
            [documentary_plan.plan_id, *(beat.beat_id for beat in beats)]
        )
        return NarrativeArchitecture(
            architecture_id=(
                f"architecture_{sha256(architecture_key.encode('utf-8')).hexdigest()[:16]}"
            ),
            documentary_plan_id=documentary_plan.plan_id,
            beats=beats,
            arcs=arcs,
            estimated_complexity=self.estimate_complexity(documentary_plan, beats),
        )

    def generate_beats(self, documentary_plan=None):
        documentary_plan = self._plan(documentary_plan)
        assignments = self.assign_beat_types(documentary_plan)
        beats = []
        position = 0
        for section in documentary_plan.sections:
            for beat_type in assignments.get(section.section_id, []):
                beats.append(
                    NarrativeBeat(
                        beat_id=self._beat_id(
                            documentary_plan.plan_id,
                            section.section_id,
                            beat_type,
                        ),
                        title=f"{section.title}: {beat_type.replace('_', ' ').title()}",
                        section_id=section.section_id,
                        event_ids=list(section.event_ids),
                        beat_type=beat_type,
                        importance=section.importance,
                        position=position,
                    )
                )
                position += 1
        return beats

    def assign_beat_types(self, documentary_plan=None):
        documentary_plan = self._plan(documentary_plan)
        end_section_id = (
            self._CONCLUSION_ID
            if any(
                section.section_id == self._CONCLUSION_ID
                for section in documentary_plan.sections
            )
            else documentary_plan.sections[-1].section_id
        )
        middle_sections = [
            section
            for section in documentary_plan.sections
            if section.section_id not in {self._INTRODUCTION_ID, end_section_id}
        ]
        climax_section_id = (
            sorted(
                middle_sections,
                key=lambda section: (-section.importance, section.section_id),
            )[0].section_id
            if middle_sections
            else self._INTRODUCTION_ID
        )
        assignments = {}
        for section in documentary_plan.sections:
            types = []
            if section.section_id == self._INTRODUCTION_ID:
                types.extend(["SETUP", "CONTEXT"])
            if section.section_id == climax_section_id:
                types.append("CLIMAX")
            elif (
                section.section_id not in {self._INTRODUCTION_ID, end_section_id}
            ):
                types.append(
                    "ESCALATION"
                    if section.section_id < climax_section_id
                    else "TURNING_POINT"
                )
            if section.section_id == end_section_id:
                types.extend(["AFTERMATH", "LEGACY"])
            assignments[section.section_id] = types
        return assignments

    def build_arcs(self, beats=None, documentary_plan=None):
        beats = (
            self.generate_beats(documentary_plan)
            if beats is None
            else list(beats)
        )
        groups = {
            "Beginning": [beat for beat in beats if beat.beat_type in {"SETUP", "CONTEXT"}],
            "Middle": [
                beat
                for beat in beats
                if beat.beat_type not in {"SETUP", "CONTEXT", *self._END_TYPES}
            ],
            "End": [beat for beat in beats if beat.beat_type in self._END_TYPES],
        }
        return [
            self._arc(title, group)
            for title, group in groups.items()
            if group
        ]

    def estimate_complexity(self, documentary_plan=None, beats=None):
        documentary_plan = self._plan(documentary_plan)
        beats = self.generate_beats(documentary_plan) if beats is None else list(beats)
        score = (
            len(documentary_plan.sections)
            + len(documentary_plan.selected_event_ids)
            + len(beats)
        )
        if score <= 7:
            return "LOW"
        if score <= 14:
            return "MEDIUM"
        return "HIGH"

    def validate_structure(self, architecture, documentary_plan=None):
        if architecture is None or not architecture.beats:
            return False
        documentary_plan = (
            documentary_plan
            or self._plans_by_id.get(architecture.documentary_plan_id)
            or self._plan(None)
        )
        sections_by_id = {
            section.section_id: section for section in documentary_plan.sections
        }
        beat_ids = [beat.beat_id for beat in architecture.beats]
        if len(beat_ids) != len(set(beat_ids)):
            return False
        if sum(beat.beat_type == "CLIMAX" for beat in architecture.beats) != 1:
            return False
        if not any(beat.beat_type == "SETUP" for beat in architecture.beats):
            return False
        if not any(beat.beat_type in self._END_TYPES for beat in architecture.beats):
            return False
        if any(beat.section_id not in sections_by_id for beat in architecture.beats):
            return False

        represented_events = {
            event_id for beat in architecture.beats for event_id in beat.event_ids
        }
        selected_events = set(documentary_plan.selected_event_ids)
        return (
            selected_events.issubset(represented_events)
            and represented_events.issubset(selected_events)
        )

    def _plan(self, documentary_plan):
        return (
            self.documentary_planner.build_documentary_plan()
            if documentary_plan is None
            else documentary_plan
        )

    @staticmethod
    def _beat_id(plan_id, section_id, beat_type):
        key = "\x00".join([plan_id, section_id, beat_type])
        return f"beat_{sha256(key.encode('utf-8')).hexdigest()[:16]}"

    @staticmethod
    def _arc(title, beats):
        key = "\x00".join([title, *(beat.beat_id for beat in beats)])
        return NarrativeArc(
            arc_id=f"arc_{sha256(key.encode('utf-8')).hexdigest()[:16]}",
            title=title,
            beat_ids=[beat.beat_id for beat in beats],
            importance=round(
                sum(beat.importance for beat in beats) / len(beats),
                3,
            ),
        )


__all__ = ["NarrativeArchitect"]
