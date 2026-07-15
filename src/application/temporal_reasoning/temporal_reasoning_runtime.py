from hashlib import sha256
import json

from src.application.historical_timeline.models import HistoricalTimeline

from .models import TemporalReasoningPlan, TemporalReasoningResult, TemporalRelation


class TemporalReasoningRuntime:
    def build_temporal_result(self, plan, timeline):
        if not self._valid_inputs(plan, timeline):
            raise ValueError("Invalid temporal reasoning inputs")
        raw = []
        dated = [entry for entry in timeline.entries if self._date_parts(entry.event_date)]
        for index, left in enumerate(dated):
            for right in dated[index + 1 :]:
                raw.extend(self._compare(plan, left, right))
        ordered = sorted(
            {
                (kind, source_id, target_id, source_date, target_date)
                for kind, source_id, target_id, source_date, target_date in raw
            }
        )
        relations = [
            TemporalRelation(
                relation_id=self._id("temporal_relation", list(material)),
                relation_type=material[0],
                source_event_id=material[1],
                target_event_id=material[2],
                source_date=material[3],
                target_date=material[4],
                position=position,
            )
            for position, material in enumerate(ordered)
        ]
        result = TemporalReasoningResult(
            result_id=self._id(
                "temporal_reasoning_result",
                [plan.plan_id, *[item.relation_id for item in relations], "VALID"],
            ),
            plan_id=plan.plan_id,
            relations=relations,
            relation_count=len(relations),
            validation_state="VALID",
        )
        if not self.validate_temporal(plan, timeline, result):
            raise ValueError("Invalid temporal reasoning result")
        return result

    def _compare(self, plan, left, right):
        left_parts = self._date_parts(left.event_date)
        right_parts = self._date_parts(right.event_date)
        relations = []
        if left_parts == right_parts:
            if "OVERLAPS" in plan.allowed_relation_types:
                source_id, target_id = sorted([left.event_id, right.event_id])
                source = left if left.event_id == source_id else right
                target = right if source is left else left
                relations.append(
                    ("OVERLAPS", source_id, target_id, source.event_date, target.event_date)
                )
            return relations
        if self._is_prefix(left_parts, right_parts):
            if "CONTAINS" in plan.allowed_relation_types:
                relations.append(
                    ("CONTAINS", left.event_id, right.event_id, left.event_date, right.event_date)
                )
            return relations
        if self._is_prefix(right_parts, left_parts):
            if "CONTAINS" in plan.allowed_relation_types:
                relations.append(
                    ("CONTAINS", right.event_id, left.event_id, right.event_date, left.event_date)
                )
            return relations
        earlier, later = (left, right) if left_parts < right_parts else (right, left)
        if "BEFORE" in plan.allowed_relation_types:
            relations.append(
                ("BEFORE", earlier.event_id, later.event_id, earlier.event_date, later.event_date)
            )
        if "AFTER" in plan.allowed_relation_types:
            relations.append(
                ("AFTER", later.event_id, earlier.event_id, later.event_date, earlier.event_date)
            )
        return relations

    def validate_temporal(self, plan, timeline, result):
        if not self._valid_inputs(plan, timeline):
            return False
        if not isinstance(result, TemporalReasoningResult):
            return False
        if result.plan_id != plan.plan_id or result.validation_state != "VALID":
            return False
        if result.relation_count != len(result.relations):
            return False
        if [item.position for item in result.relations] != list(range(len(result.relations))):
            return False
        relation_ids = [item.relation_id for item in result.relations]
        if len(relation_ids) != len(set(relation_ids)):
            return False
        event_ids = {entry.event_id for entry in timeline.entries}
        return all(
            item.relation_type in plan.allowed_relation_types
            and item.source_event_id in event_ids
            and item.target_event_id in event_ids
            and item.source_event_id != item.target_event_id
            for item in result.relations
        )

    @staticmethod
    def _date_parts(value):
        if not isinstance(value, str) or not value:
            return ()
        parts = value.split("-")
        if len(parts) not in (1, 2, 3):
            return ()
        if len(parts[0]) != 4 or not all(part.isdigit() for part in parts):
            return ()
        if any(len(part) != 2 for part in parts[1:]):
            return ()
        return tuple(int(part) for part in parts)

    @staticmethod
    def _is_prefix(left, right):
        return len(left) < len(right) and right[: len(left)] == left

    @staticmethod
    def _valid_inputs(plan, timeline):
        return (
            isinstance(plan, TemporalReasoningPlan)
            and bool(plan.plan_id)
            and isinstance(timeline, HistoricalTimeline)
            and timeline.entry_count == len(timeline.entries)
        )

    @staticmethod
    def _id(prefix, material):
        return prefix + "_" + sha256(
            json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:16]


__all__ = ["TemporalReasoningRuntime"]
