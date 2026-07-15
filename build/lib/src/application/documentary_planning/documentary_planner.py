import re
from hashlib import sha256

from src.application.events.event_engine import EventEngine

from .models import DocumentaryPlan, DocumentarySection


class DocumentaryPlanner:
    """Deterministically turns an historical timeline into documentary sections."""

    _DEFAULT_TITLE = "Historical Documentary"
    _CHAPTER_LIMIT = 3
    _OUTCOME_PATTERN = re.compile(
        r"\b(outcome|legacy|aftermath|consequence|impact|resulted|established|founded)\b",
        re.IGNORECASE,
    )

    def __init__(self, event_engine):
        if not isinstance(event_engine, EventEngine):
            raise TypeError("DocumentaryPlanner requires an EventEngine")
        self.event_engine = event_engine

    def build_documentary_plan(self, timeline=None, title=None):
        timeline = self._timeline(timeline)
        sections = self.build_sections(timeline)
        selected_event_ids = [
            event_id for section in sections for event_id in section.event_ids
        ]
        plan_title = title or self._DEFAULT_TITLE
        plan_key = "\x00".join([plan_title, *selected_event_ids])
        return DocumentaryPlan(
            plan_id=f"plan_{sha256(plan_key.encode('utf-8')).hexdigest()[:16]}",
            title=plan_title,
            sections=sections,
            selected_event_ids=selected_event_ids,
            estimated_runtime=self.estimate_runtime(sections),
        )

    def build_sections(self, timeline=None):
        timeline = self._timeline(timeline)
        events = list(timeline.events)
        if not events:
            return []

        introduction_event = self._select_introduction_event(events)
        remaining = [event for event in events if event.event_id != introduction_event.event_id]
        conclusion_event = self._select_conclusion_event(remaining)
        core_events = [
            event
            for event in remaining
            if conclusion_event is None or event.event_id != conclusion_event.event_id
        ]

        sections = [self._section("introduction", "Introduction", [introduction_event])]
        for index, event_group in enumerate(self._split_chapters(core_events), start=1):
            sections.append(
                self._section(f"chapter_{index}", f"Chapter {index}", event_group)
            )
        if conclusion_event is not None:
            sections.append(self._section("conclusion", "Conclusion", [conclusion_event]))
        return sections

    def rank_sections(self, sections=None, timeline=None):
        sections = self.build_sections(timeline) if sections is None else list(sections)
        return sorted(sections, key=lambda section: (-section.importance, section.section_id))

    def estimate_runtime(self, sections=None, timeline=None):
        sections = self.build_sections(timeline) if sections is None else list(sections)
        return round(sum(section.estimated_duration for section in sections), 2)

    def assign_event(self, event_id, timeline=None):
        for section in self.build_sections(timeline):
            if event_id in section.event_ids:
                return section
        return None

    def get_introduction(self, timeline=None):
        return next(
            (section for section in self.build_sections(timeline) if section.section_id == "introduction"),
            None,
        )

    def get_conclusion(self, timeline=None):
        return next(
            (section for section in self.build_sections(timeline) if section.section_id == "conclusion"),
            None,
        )

    def _timeline(self, timeline):
        return self.event_engine.build_timeline() if timeline is None else timeline

    def _select_introduction_event(self, events):
        return sorted(events, key=lambda event: (-self._event_importance(event), event.event_id))[0]

    def _select_conclusion_event(self, events):
        if not events:
            return None
        return sorted(
            enumerate(events),
            key=lambda item: (
                -int(bool(self._OUTCOME_PATTERN.search(item[1].title))),
                -item[0],
                -self._event_importance(item[1]),
                item[1].event_id,
            ),
        )[0][1]

    def _split_chapters(self, events):
        if not events:
            return []
        chapter_count = min(self._CHAPTER_LIMIT, len(events))
        base_size, remainder = divmod(len(events), chapter_count)
        groups = []
        start = 0
        for index in range(chapter_count):
            size = base_size + (1 if index < remainder else 0)
            groups.append(events[start : start + size])
            start += size
        return groups

    def _section(self, section_id, title, events):
        return DocumentarySection(
            section_id=section_id,
            title=title,
            event_ids=[event.event_id for event in events],
            importance=round(sum(self._event_importance(event) for event in events) / len(events), 3),
            estimated_duration=round(1.0 + len(events) * 0.75, 2),
        )

    @staticmethod
    def _event_importance(event):
        support_strength = min(
            1.0,
            (len(event.claim_ids) + len(event.evidence_ids) + len(event.source_ids)) / 6,
        )
        return round(event.confidence * 0.7 + support_strength * 0.3, 3)


__all__ = ["DocumentaryPlanner"]
