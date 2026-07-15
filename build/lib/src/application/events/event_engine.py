import re
from hashlib import sha256

from src.application.selection.claim_selector import ClaimSelector

from .models import HistoricalEvent, HistoricalTimeline


class EventEngine:
    """Deterministically builds and orders historical events from selected claims."""

    _DATE_PATTERN = re.compile(r"\b(\d{3,4}-\d{2}-\d{2})\b")
    _YEAR_PATTERN = re.compile(r"\b(\d{3,4})\b")
    _EVENT_PATTERN = re.compile(
        r"\b(battle|war|expedition|siege|migration|treaty)\b",
        re.IGNORECASE,
    )

    def __init__(self, selector):
        if not isinstance(selector, ClaimSelector):
            raise TypeError("EventEngine requires a ClaimSelector")
        self.selector = selector

    def build_event(self, claim_id):
        cluster = self.selector.get_claim_cluster(claim_id)
        if cluster is None:
            return None

        claim_ids = sorted(cluster.claim_ids)
        scored_claims = [
            (self.selector.evaluate_claim(item), self.selector.get_claim(item))
            for item in claim_ids
        ]
        scored_claims = [item for item in scored_claims if item[0] and item[1]]
        if not scored_claims:
            return None

        title_claim = sorted(
            scored_claims,
            key=lambda item: (
                -int(self._is_explicit_event(item[1])),
                -item[0].score,
                item[1].id,
            ),
        )[0][1]
        source_ids = set(cluster.source_ids)
        document_ids = set(cluster.document_ids)
        evidence_ids = set(cluster.evidence_ids)
        selection_scores = []
        support_scores = []
        contradiction_count = 0
        temporal_values = []

        for item_id in claim_ids:
            score = self.selector.evaluate_claim(item_id)
            support = self.selector.get_support_profile(item_id)
            provenance = self.selector.get_claim_provenance(item_id)
            claim = self.selector.get_claim(item_id)
            selection_scores.append(score.score)
            support_scores.append(support.confidence_score)
            contradiction_count += len(self.selector.get_claim_contradictions(item_id))
            evidence_ids.update(node.id for node in provenance["evidence"])
            document_ids.update(node.id for node in provenance["documents"])
            source_ids.update(node.id for node in provenance["sources"])
            temporal_values.extend(self._temporal_values(claim))

        date = min(item[1] for item in temporal_values if item[0] == "date") if any(
            item[0] == "date" for item in temporal_values
        ) else None
        year = int(date.split("-", 1)[0]) if date else min(
            (int(item[1]) for item in temporal_values if item[0] == "year"),
            default=None,
        )
        confidence = round(
            max(
                0.0,
                min(
                    1.0,
                    sum(selection_scores) / len(selection_scores) * 0.65
                    + sum(support_scores) / len(support_scores) * 0.35
                    - min(contradiction_count, 2) * 0.10,
                ),
            ),
            3,
        )
        event_key = "\x00".join(claim_ids)
        return HistoricalEvent(
            event_id=f"event_{sha256(event_key.encode('utf-8')).hexdigest()[:16]}",
            title=self._claim_text(title_claim),
            claim_ids=claim_ids,
            source_ids=sorted(source_ids),
            document_ids=sorted(document_ids),
            evidence_ids=sorted(evidence_ids),
            confidence=confidence,
            year=year,
            date=date,
        )

    def build_events(self, limit=50):
        events = {}
        for score in self.selector.select_top_claims(limit):
            event = self.build_event(score.claim_id)
            if event is not None:
                events[event.event_id] = event
        return list(events.values())

    def rank_events(self, events=None):
        events = self.build_events() if events is None else list(events)
        return sorted(events, key=lambda event: (-event.confidence, event.event_id))

    def build_timeline(self, events=None):
        events = self.build_events() if events is None else list(events)
        placed = [event for event in events if event.date or event.year is not None]
        unplaced = [event for event in events if event.date is None and event.year is None]
        placed = sorted(placed, key=self._timeline_key)
        unplaced = sorted(unplaced, key=lambda event: event.event_id)
        timeline_key = "\x00".join(event.event_id for event in placed + unplaced)
        return HistoricalTimeline(
            timeline_id=f"timeline_{sha256(timeline_key.encode('utf-8')).hexdigest()[:16]}",
            events=placed + unplaced,
            ordered_event_ids=[event.event_id for event in placed],
            unplaced_event_ids=[event.event_id for event in unplaced],
        )

    def get_unplaced_events(self, events=None):
        events = self.build_events() if events is None else list(events)
        return sorted(
            [event for event in events if event.date is None and event.year is None],
            key=lambda event: event.event_id,
        )

    def _temporal_values(self, claim):
        data = claim.data if isinstance(claim.data, dict) else {}
        metadata = data.get("metadata", {}) if isinstance(data.get("metadata", {}), dict) else {}
        values = [str(data.get("date", "")), str(metadata.get("date", "")), self._claim_text(claim)]
        temporal_values = []
        for value in values:
            temporal_values.extend(("date", item) for item in self._DATE_PATTERN.findall(value))
            temporal_values.extend(("year", item) for item in self._YEAR_PATTERN.findall(value))
        return temporal_values

    def _timeline_key(self, event):
        if event.date:
            return (int(event.date.split("-", 1)[0]), 0, event.date, event.event_id)
        return (event.year, 1, "", event.event_id)

    def _is_explicit_event(self, claim):
        return bool(self._EVENT_PATTERN.search(self._claim_text(claim)))

    @staticmethod
    def _claim_text(claim):
        data = claim.data if isinstance(claim.data, dict) else {}
        return data.get("text", "")


__all__ = ["EventEngine"]
