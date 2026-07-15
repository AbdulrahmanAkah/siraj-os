from hashlib import sha256
import json

from src.application.claim_extraction.claim_extraction_runtime import (
    ClaimExtractionRuntime,
)
from src.application.claim_extraction.models import ClaimExtractionResult
from src.application.entity_extraction.entity_extraction_runtime import (
    EntityExtractionRuntime,
)
from src.application.entity_extraction.models import EntityExtractionResult

from .models import (
    EventCandidate,
    EventEvidence,
    EventExtractionPlan,
    EventExtractionResult,
    EventRecord,
)


class EventExtractionRuntime:
    """Extracts deterministic events from claims and canonical entities."""

    STRATEGIES = (
        "METADATA_EVENT",
        "CLAIM_PATTERN_EVENT",
        "ENTITY_DERIVED_EVENT",
    )
    EVENT_TYPES = (
        "CREATION_EVENT",
        "PUBLICATION_EVENT",
        "ORGANIZATION_EVENT",
        "LOCATION_EVENT",
        "DATE_EVENT",
    )
    METADATA_FIELDS = {
        "publication_date": ("PUBLICATION_EVENT", "Publication on", True),
        "published_at": ("PUBLICATION_EVENT", "Publication on", True),
        "created_at": ("CREATION_EVENT", "Creation on", True),
        "organization": ("ORGANIZATION_EVENT", "Organization:", False),
        "location": ("LOCATION_EVENT", "Location:", False),
    }

    def __init__(self, claim_extraction_runtime, entity_extraction_runtime):
        if not isinstance(claim_extraction_runtime, ClaimExtractionRuntime):
            raise TypeError(
                "EventExtractionRuntime requires a ClaimExtractionRuntime"
            )
        if not isinstance(entity_extraction_runtime, EntityExtractionRuntime):
            raise TypeError(
                "EventExtractionRuntime requires an EntityExtractionRuntime"
            )
        self.claim_extraction_runtime = claim_extraction_runtime
        self.entity_extraction_runtime = entity_extraction_runtime

    def execute_event_extraction(
        self,
        plan,
        claim_extraction_result,
        entity_extraction_result,
    ):
        self.validate_runtime_inputs_or_raise(
            plan,
            claim_extraction_result,
            entity_extraction_result,
        )
        candidates = self.generate_candidates(
            plan,
            claim_extraction_result,
            entity_extraction_result,
        )
        events = self.build_event_records(candidates)
        events = events[: plan.event_limit]
        result = self.build_extraction_result(plan, candidates, events)
        if not self.validate_extraction(
            plan,
            claim_extraction_result,
            entity_extraction_result,
            result,
        ):
            raise ValueError("Invalid event extraction result")
        return result

    def extract_events(self, plan, claim_extraction_result, entity_extraction_result):
        return self.execute_event_extraction(
            plan,
            claim_extraction_result,
            entity_extraction_result,
        )

    def generate_candidates(
        self,
        plan,
        claim_extraction_result,
        entity_extraction_result,
    ):
        candidates = []
        candidates_by_text = {}
        for candidate in claim_extraction_result.candidates:
            candidates_by_text.setdefault(candidate.claim_text, set()).add(
                candidate.extraction_strategy
            )
        for claim in sorted(
            claim_extraction_result.claims,
            key=lambda item: item.claim_id,
        ):
            source_strategies = candidates_by_text.get(claim.claim_text, set())
            for strategy in plan.extraction_strategies:
                event_data = self._event_for_claim(
                    claim.claim_text,
                    strategy,
                    source_strategies,
                )
                if event_data is None:
                    continue
                event_type, event_title, event_date = event_data
                candidates.append(
                    self._candidate_from_claim(
                        claim.claim_id,
                        event_type,
                        event_title,
                        event_date,
                        strategy,
                    )
                )
        for entity in sorted(
            entity_extraction_result.entities,
            key=lambda item: item.entity_id,
        ):
            if "ENTITY_DERIVED_EVENT" not in plan.extraction_strategies:
                continue
            event_data = self._event_for_entity(entity.entity_name, entity.entity_type)
            if event_data is None:
                continue
            event_type, event_title, event_date = event_data
            candidates.append(
                self._candidate_from_entity(
                    entity.entity_id,
                    entity.source_claim_ids,
                    event_type,
                    event_title,
                    event_date,
                )
            )
        return candidates

    def generate_event_candidates(
        self,
        plan,
        claim_extraction_result,
        entity_extraction_result,
    ):
        return self.generate_candidates(
            plan,
            claim_extraction_result,
            entity_extraction_result,
        )

    def build_event_records(self, candidates):
        grouped = {}
        for candidate in candidates:
            key = (candidate.event_type, candidate.event_title, candidate.event_date)
            grouped.setdefault(key, []).append(candidate)
        events = []
        for (event_type, event_title, event_date), event_candidates in grouped.items():
            claim_ids = sorted(
                {
                    claim_id
                    for candidate in event_candidates
                    for claim_id in candidate.source_claim_ids
                }
            )
            entity_ids = sorted(
                {
                    entity_id
                    for candidate in event_candidates
                    for entity_id in candidate.source_entity_ids
                }
            )
            supporting_text = event_title
            evidence = [
                self.generate_evidence(
                    supporting_text,
                    claim_ids,
                    entity_ids,
                )
            ]
            events.append(
                EventRecord(
                    event_id=self._event_id(
                        event_type,
                        event_title,
                        event_date,
                        claim_ids,
                        entity_ids,
                    ),
                    event_type=event_type,
                    event_title=event_title,
                    event_date=event_date,
                    source_claim_ids=claim_ids,
                    source_entity_ids=entity_ids,
                    evidence=evidence,
                )
            )
        return sorted(events, key=lambda event: event.event_id)

    def generate_evidence(self, supporting_text, claim_ids, entity_ids):
        if not supporting_text or not (claim_ids or entity_ids):
            raise ValueError("Event evidence requires text and a source reference")
        material = "\x00".join(
            [supporting_text, *sorted(claim_ids), "\x00", *sorted(entity_ids)]
        )
        return EventEvidence(
            evidence_id=(
                f"event_evidence_"
                f"{sha256(material.encode('utf-8')).hexdigest()[:16]}"
            ),
            supporting_text=supporting_text,
            claim_ids=sorted(set(claim_ids)),
            entity_ids=sorted(set(entity_ids)),
        )

    def build_extraction_result(self, plan, candidates, events):
        material = {
            "plan_id": plan.plan_id,
            "candidate_ids": [candidate.candidate_id for candidate in candidates],
            "event_ids": [event.event_id for event in events],
        }
        result_id = (
            f"event_extraction_result_"
            f"{sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode('utf-8')).hexdigest()[:16]}"
        )
        return EventExtractionResult(
            result_id=result_id,
            plan_id=plan.plan_id,
            candidates=list(candidates),
            events=list(events),
            candidate_count=len(candidates),
            event_count=len(events),
        )

    def validate_extraction(
        self,
        plan,
        claim_extraction_result,
        entity_extraction_result,
        extraction_result,
    ):
        if not self._validate_plan(plan):
            return False
        if not self._validate_claim_result(plan, claim_extraction_result):
            return False
        if not self._validate_entity_result(plan, entity_extraction_result):
            return False
        if not isinstance(extraction_result, EventExtractionResult):
            return False
        if extraction_result.plan_id != plan.plan_id:
            return False
        if extraction_result.candidate_count != len(extraction_result.candidates):
            return False
        if extraction_result.event_count != len(extraction_result.events):
            return False
        if extraction_result.event_count > plan.event_limit:
            return False
        claim_ids = {claim.claim_id for claim in claim_extraction_result.claims}
        entity_ids = {entity.entity_id for entity in entity_extraction_result.entities}
        candidate_ids = [candidate.candidate_id for candidate in extraction_result.candidates]
        if len(candidate_ids) != len(set(candidate_ids)):
            return False
        if any(
            not candidate.event_title.strip()
            or candidate.event_type not in self.EVENT_TYPES
            or not (candidate.source_claim_ids or candidate.source_entity_ids)
            or any(claim_id not in claim_ids for claim_id in candidate.source_claim_ids)
            or any(entity_id not in entity_ids for entity_id in candidate.source_entity_ids)
            for candidate in extraction_result.candidates
        ):
            return False
        event_ids = [event.event_id for event in extraction_result.events]
        event_keys = [
            (event.event_type, event.event_title, event.event_date)
            for event in extraction_result.events
        ]
        if len(event_ids) != len(set(event_ids)) or len(event_keys) != len(set(event_keys)):
            return False
        if any(
            not event.event_title.strip()
            or event.event_type not in self.EVENT_TYPES
            or not (event.source_claim_ids or event.source_entity_ids)
            or event.source_claim_ids != sorted(set(event.source_claim_ids))
            or event.source_entity_ids != sorted(set(event.source_entity_ids))
            or any(claim_id not in claim_ids for claim_id in event.source_claim_ids)
            or any(entity_id not in entity_ids for entity_id in event.source_entity_ids)
            or not event.evidence
            or event.event_id
            != self._event_id(
                event.event_type,
                event.event_title,
                event.event_date,
                event.source_claim_ids,
                event.source_entity_ids,
            )
            or any(
                not evidence.supporting_text.strip()
                or not (evidence.claim_ids or evidence.entity_ids)
                or evidence.claim_ids != sorted(set(evidence.claim_ids))
                or evidence.entity_ids != sorted(set(evidence.entity_ids))
                or any(claim_id not in claim_ids for claim_id in evidence.claim_ids)
                or any(entity_id not in entity_ids for entity_id in evidence.entity_ids)
                or evidence.evidence_id
                != self._evidence_id(
                    evidence.supporting_text,
                    evidence.claim_ids,
                    evidence.entity_ids,
                )
                for evidence in event.evidence
            )
            for event in extraction_result.events
        ):
            return False
        return True

    def validate_runtime_inputs_or_raise(
        self,
        plan,
        claim_extraction_result,
        entity_extraction_result,
    ):
        if not self._validate_plan(plan):
            raise ValueError("Invalid event extraction plan")
        if not self._validate_claim_result(plan, claim_extraction_result):
            raise ValueError("Invalid claim extraction result")
        if not self._validate_entity_result(plan, entity_extraction_result):
            raise ValueError("Invalid entity extraction result")

    @classmethod
    def _event_for_claim(cls, claim_text, strategy, source_strategies):
        if strategy == "METADATA_EVENT":
            if "STRUCTURED_METADATA" not in source_strategies:
                return None
            if " is " not in claim_text:
                return None
            field, value = claim_text.split(" is ", 1)
            field = field.strip().lower().replace(" ", "_")
            value = value.strip()
            metadata_event = cls.METADATA_FIELDS.get(field)
            if metadata_event is None or not value:
                return None
            event_type, prefix, has_date = metadata_event
            return event_type, f"{prefix} {value}", value if has_date else None
        if strategy == "CLAIM_PATTERN_EVENT":
            for prefix, event_type, title_prefix, has_date in (
                ("Published on ", "PUBLICATION_EVENT", "Publication on", True),
                ("Created on ", "CREATION_EVENT", "Creation on", True),
                ("Organized on ", "ORGANIZATION_EVENT", "Organization:", False),
                ("Located in ", "LOCATION_EVENT", "Location:", False),
                ("Dated on ", "DATE_EVENT", "Date:", True),
            ):
                if claim_text.startswith(prefix):
                    value = claim_text[len(prefix):].strip()
                    if value:
                        return event_type, f"{title_prefix} {value}", value if has_date else None
        return None

    @staticmethod
    def _event_for_entity(entity_name, entity_type):
        mapping = {
            "DATE": ("DATE_EVENT", "Date:", entity_name),
            "ORGANIZATION": ("ORGANIZATION_EVENT", "Organization:", None),
            "LOCATION": ("LOCATION_EVENT", "Location:", None),
        }
        event_data = mapping.get(entity_type)
        if event_data is None:
            return None
        event_type, prefix, event_date = event_data
        return event_type, f"{prefix} {entity_name}", event_date

    @staticmethod
    def _candidate_from_claim(claim_id, event_type, event_title, event_date, strategy):
        candidate_id = EventExtractionRuntime._candidate_id(
            event_type,
            event_title,
            event_date,
            [claim_id],
            [],
            strategy,
        )
        return EventCandidate(
            candidate_id=candidate_id,
            event_type=event_type,
            event_title=event_title,
            event_date=event_date,
            source_claim_ids=[claim_id],
            extraction_strategy=strategy,
        )

    @staticmethod
    def _candidate_from_entity(entity_id, claim_ids, event_type, event_title, event_date):
        candidate_id = EventExtractionRuntime._candidate_id(
            event_type,
            event_title,
            event_date,
            claim_ids,
            [entity_id],
            "ENTITY_DERIVED_EVENT",
        )
        return EventCandidate(
            candidate_id=candidate_id,
            event_type=event_type,
            event_title=event_title,
            event_date=event_date,
            source_claim_ids=sorted(set(claim_ids)),
            source_entity_ids=[entity_id],
            extraction_strategy="ENTITY_DERIVED_EVENT",
        )

    def _validate_plan(self, plan):
        return (
            isinstance(plan, EventExtractionPlan)
            and bool(plan.plan_id)
            and bool(plan.claim_extraction_result_id)
            and bool(plan.entity_extraction_result_id)
            and isinstance(plan.extraction_strategies, list)
            and bool(plan.extraction_strategies)
            and len(plan.extraction_strategies) == len(set(plan.extraction_strategies))
            and all(strategy in self.STRATEGIES for strategy in plan.extraction_strategies)
            and isinstance(plan.event_limit, int)
            and not isinstance(plan.event_limit, bool)
            and plan.event_limit > 0
        )

    @staticmethod
    def _validate_claim_result(plan, result):
        return (
            isinstance(result, ClaimExtractionResult)
            and plan.claim_extraction_result_id == result.result_id
            and result.claim_count == len(result.claims)
            and result.candidate_count == len(result.candidates)
            and len({claim.claim_id for claim in result.claims}) == len(result.claims)
        )

    @staticmethod
    def _validate_entity_result(plan, result):
        return (
            isinstance(result, EntityExtractionResult)
            and plan.entity_extraction_result_id == result.result_id
            and result.entity_count == len(result.entities)
            and result.candidate_count == len(result.candidates)
            and len({entity.entity_id for entity in result.entities}) == len(result.entities)
        )

    @staticmethod
    def _candidate_id(event_type, event_title, event_date, claim_ids, entity_ids, strategy):
        material = "\x00".join(
            [event_type, event_title, event_date or "", *sorted(claim_ids), "\x00", *sorted(entity_ids), strategy]
        )
        return f"event_candidate_{sha256(material.encode('utf-8')).hexdigest()[:16]}"

    @staticmethod
    def _event_id(event_type, event_title, event_date, claim_ids, entity_ids):
        material = "\x00".join(
            [event_type, event_title, event_date or "", *sorted(claim_ids), "\x00", *sorted(entity_ids)]
        )
        return f"event_{sha256(material.encode('utf-8')).hexdigest()[:16]}"

    @staticmethod
    def _evidence_id(supporting_text, claim_ids, entity_ids):
        material = "\x00".join(
            [supporting_text, *sorted(claim_ids), "\x00", *sorted(entity_ids)]
        )
        return f"event_evidence_{sha256(material.encode('utf-8')).hexdigest()[:16]}"


__all__ = ["EventExtractionRuntime"]
