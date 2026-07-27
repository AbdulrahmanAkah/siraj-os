"""Verified provider-test intake and precise cinematic budget allocation.

This module is offline-only. It records manual provider observations without
storing credentials or raw provider payloads, derives exact price observations,
quotes explicit frame options, and plans with micro-USD precision. It never
contacts a provider and never authorizes paid execution.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from enum import StrEnum
import json
import re
from typing import Iterable

from src.application.documentary_intelligence import deterministic_id

from .cinematic_compiler import (
    DYNAMIC_BUDGET_PLANNER_SCHEMA_VERSION,
    MOTION_CAPABLE_TREATMENTS,
    CinematicBudgetGuardrails,
    CompiledCinematicEpisode,
    CompiledFrameAssignment,
    DynamicCinematicBudgetPlanner,
    MediaCategory,
    MediaTreatment,
    MotionNeed,
)
from .cinematic_series import (
    GENERATED_VIDEO_HARD_LIMIT_SECONDS,
    CinematicSeriesError,
    CinematicSeriesRuntime,
    CinematicStoryboardPlan,
)
from .models import Storyboard


PROVIDER_MANUAL_TEST_SCHEMA_VERSION = "siraj-provider-manual-test-v1"
VERIFIED_PRICE_CATALOG_SCHEMA_VERSION = "siraj-verified-price-catalog-v1"
PRECISE_MEDIA_OPTION_SCHEMA_VERSION = "siraj-precise-media-option-v1"
PRECISE_BUDGET_PLANNER_SCHEMA_VERSION = "siraj-precise-budget-planner-v1"
LIVE_EXECUTION_STATUS = "BLOCKED_OFFLINE_ONLY"
PRICE_PRECISION_PLACES = 6
PRICE_QUANTUM = Decimal("0.000001")
PRICE_SCALE = 1_000_000
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ProviderTestStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"


class PriceSourceKind(StrEnum):
    MANUAL_PROVIDER_TEST = "manual_provider_test"
    LOCAL_COST_OBSERVATION = "local_cost_observation"
    CONTRACT_QUOTE = "contract_quote"


class BillingBasis(StrEnum):
    PER_REQUEST = "per_request"
    PER_OUTPUT = "per_output"
    PER_SECOND = "per_second"
    PER_MEGAPIXEL = "per_megapixel"
    PER_UNIT = "per_unit"


def _decimal(value: str | int | float | Decimal, *, name: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise CinematicSeriesError(f"{name} must be a valid decimal value.") from exc
    if not result.is_finite():
        raise CinematicSeriesError(f"{name} must be finite.")
    return result


def _money(value: str | int | float | Decimal, *, name: str) -> Decimal:
    result = _decimal(value, name=name)
    if result < 0:
        raise CinematicSeriesError(f"{name} cannot be negative.")
    normalized = result.quantize(PRICE_QUANTUM, rounding=ROUND_HALF_UP)
    if normalized != result:
        raise CinematicSeriesError(
            f"{name} supports at most {PRICE_PRECISION_PLACES} decimal places."
        )
    return normalized


def _positive_units(value: str | int | float | Decimal, *, name: str) -> Decimal:
    result = _decimal(value, name=name)
    if result <= 0:
        raise CinematicSeriesError(f"{name} must be positive.")
    if result.as_tuple().exponent < -6:
        raise CinematicSeriesError(f"{name} supports at most six decimal places.")
    return result


def _usd_text(value: Decimal) -> str:
    rendered = format(value.quantize(PRICE_QUANTUM), "f").rstrip("0").rstrip(".")
    return rendered or "0"


def _to_micro_usd(value: Decimal) -> int:
    return int((value * PRICE_SCALE).to_integral_exact())


def _from_micro_usd(value: int) -> Decimal:
    return (Decimal(value) / PRICE_SCALE).quantize(PRICE_QUANTUM)


def _validate_sha256(value: str, *, name: str) -> None:
    if not _SHA256.fullmatch(value):
        raise CinematicSeriesError(f"{name} must be a lowercase SHA-256 hex digest.")


def _validate_utc(value: str) -> None:
    if not value.endswith("Z"):
        raise CinematicSeriesError("tested_at_utc must use a Z UTC suffix.")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise CinematicSeriesError("tested_at_utc must be valid ISO-8601 UTC.") from exc
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise CinematicSeriesError("tested_at_utc must resolve to UTC.")


@dataclass(frozen=True, slots=True)
class ManualProviderTestRecord:
    test_id: str
    provider_id: str
    model_id: str
    source_kind: PriceSourceKind
    treatment: MediaTreatment
    category: MediaCategory
    billing_basis: BillingBasis
    observed_total_cost_usd: str
    billed_units: str
    generated_output_count: int
    generated_video_seconds: int
    quality_score: int
    reliability_score: int
    latency_ms: int
    request_fingerprint_sha256: str
    response_fingerprint_sha256: str
    tested_at_utc: str
    status: ProviderTestStatus
    notes: str = ""
    credentials_recorded: bool = False
    live_execution_authorized: bool = False

    def validate(self) -> None:
        for value, name in (
            (self.test_id, "test_id"),
            (self.provider_id, "provider_id"),
            (self.model_id, "model_id"),
        ):
            if not value.strip():
                raise CinematicSeriesError(f"{name} must not be blank.")
        _money(self.observed_total_cost_usd, name="observed_total_cost_usd")
        units = _positive_units(self.billed_units, name="billed_units")
        if self.generated_output_count <= 0:
            raise CinematicSeriesError("generated_output_count must be positive.")
        if not 0 <= self.generated_video_seconds <= GENERATED_VIDEO_HARD_LIMIT_SECONDS:
            raise CinematicSeriesError(
                "generated_video_seconds must be between 0 and 300."
            )
        if not 0 <= self.quality_score <= 100:
            raise CinematicSeriesError("quality_score must be between 0 and 100.")
        if not 0 <= self.reliability_score <= 100:
            raise CinematicSeriesError("reliability_score must be between 0 and 100.")
        if self.latency_ms < 0:
            raise CinematicSeriesError("latency_ms cannot be negative.")
        _validate_sha256(
            self.request_fingerprint_sha256,
            name="request_fingerprint_sha256",
        )
        _validate_sha256(
            self.response_fingerprint_sha256,
            name="response_fingerprint_sha256",
        )
        _validate_utc(self.tested_at_utc)
        if self.credentials_recorded:
            raise CinematicSeriesError(
                "Provider credentials or API keys must never be recorded."
            )
        if self.live_execution_authorized:
            raise CinematicSeriesError(
                "A manual test record cannot authorize live provider execution."
            )
        if self.billing_basis is BillingBasis.PER_REQUEST and units != Decimal("1"):
            raise CinematicSeriesError("PER_REQUEST observations must use one billed unit.")
        if self.billing_basis is BillingBasis.PER_OUTPUT:
            if units != units.to_integral_value():
                raise CinematicSeriesError("PER_OUTPUT billed units must be integral.")
            if int(units) != self.generated_output_count:
                raise CinematicSeriesError(
                    "PER_OUTPUT billed units must equal generated_output_count."
                )
        if self.billing_basis is BillingBasis.PER_SECOND:
            if units != units.to_integral_value():
                raise CinematicSeriesError("PER_SECOND billed units must be integral.")
            if int(units) != self.generated_video_seconds:
                raise CinematicSeriesError(
                    "PER_SECOND billed units must equal generated_video_seconds."
                )
        video_treatment = self.treatment in {
            MediaTreatment.GENERATED_VIDEO,
            MediaTreatment.HYBRID_SEQUENCE,
        }
        if video_treatment and self.generated_video_seconds <= 0:
            raise CinematicSeriesError(
                "Generated-video observations require positive video seconds."
            )
        if not video_treatment and self.generated_video_seconds != 0:
            raise CinematicSeriesError(
                "Non-video observations cannot report generated-video seconds."
            )
        if self.treatment is MediaTreatment.GENERATED_IMAGE:
            if self.category is not MediaCategory.IMAGE:
                raise CinematicSeriesError(
                    "Generated-image observations must use the image category."
                )
        if video_treatment and self.category is not MediaCategory.VIDEO:
            raise CinematicSeriesError(
                "Generated-video observations must use the video category."
            )

    @property
    def total_cost(self) -> Decimal:
        return _money(self.observed_total_cost_usd, name="observed_total_cost_usd")

    @property
    def units(self) -> Decimal:
        return _positive_units(self.billed_units, name="billed_units")

    @property
    def unit_price(self) -> Decimal:
        self.validate()
        return (self.total_cost / self.units).quantize(
            PRICE_QUANTUM,
            rounding=ROUND_HALF_UP,
        )

    def to_manifest(self) -> dict[str, object]:
        self.validate()
        return {
            "schema_version": PROVIDER_MANUAL_TEST_SCHEMA_VERSION,
            "test_id": self.test_id,
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "source_kind": self.source_kind.value,
            "treatment": self.treatment.value,
            "category": self.category.value,
            "billing_basis": self.billing_basis.value,
            "observed_total_cost_usd": _usd_text(self.total_cost),
            "billed_units": format(self.units, "f"),
            "derived_unit_price_usd": _usd_text(self.unit_price),
            "generated_output_count": self.generated_output_count,
            "generated_video_seconds": self.generated_video_seconds,
            "quality_score": self.quality_score,
            "reliability_score": self.reliability_score,
            "latency_ms": self.latency_ms,
            "request_fingerprint_sha256": self.request_fingerprint_sha256,
            "response_fingerprint_sha256": self.response_fingerprint_sha256,
            "tested_at_utc": self.tested_at_utc,
            "status": self.status.value,
            "notes": self.notes,
            "credentials_recorded": False,
            "live_execution_authorized": False,
        }


@dataclass(frozen=True, slots=True)
class VerifiedProviderPriceCatalog:
    catalog_id: str
    records: tuple[ManualProviderTestRecord, ...]
    schema_version: str = VERIFIED_PRICE_CATALOG_SCHEMA_VERSION
    live_execution_allowed: bool = False

    @classmethod
    def build(
        cls,
        records: Iterable[ManualProviderTestRecord],
    ) -> "VerifiedProviderPriceCatalog":
        ordered = tuple(records)
        if not ordered:
            raise CinematicSeriesError("A verified price catalog requires records.")
        for item in ordered:
            item.validate()
            if item.status is not ProviderTestStatus.PASS:
                raise CinematicSeriesError(
                    "Failed provider tests cannot enter the verified price catalog."
                )
        if len({item.test_id for item in ordered}) != len(ordered):
            raise CinematicSeriesError("Provider test ids must be unique.")
        canonical = tuple(sorted(ordered, key=lambda item: item.test_id))
        catalog_id = deterministic_id(
            "verified_price_catalog",
            [item.to_manifest() for item in canonical],
        )
        return cls(catalog_id=catalog_id, records=canonical)

    def validate(self) -> None:
        rebuilt = self.build(self.records)
        if rebuilt.catalog_id != self.catalog_id:
            raise CinematicSeriesError("Verified price catalog id is not deterministic.")
        if self.schema_version != VERIFIED_PRICE_CATALOG_SCHEMA_VERSION:
            raise CinematicSeriesError("Unexpected verified price catalog schema.")
        if self.live_execution_allowed:
            raise CinematicSeriesError("A price catalog cannot authorize live execution.")

    def record(self, test_id: str) -> ManualProviderTestRecord:
        self.validate()
        for item in self.records:
            if item.test_id == test_id:
                return item
        raise CinematicSeriesError(f"Unknown verified provider test: {test_id}")

    def to_manifest(self) -> dict[str, object]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "catalog_id": self.catalog_id,
            "live_execution_allowed": False,
            "records": [item.to_manifest() for item in self.records],
        }

    def to_json(self) -> str:
        return json.dumps(
            self.to_manifest(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )


@dataclass(frozen=True, slots=True)
class FrameQuoteSpec:
    quote_id: str
    frame_id: str
    provider_test_id: str
    requested_units: str
    generated_video_seconds: int = 0
    quality_score_override: int | None = None
    reliability_score_override: int | None = None

    def validate(self) -> None:
        for value, name in (
            (self.quote_id, "quote_id"),
            (self.frame_id, "frame_id"),
            (self.provider_test_id, "provider_test_id"),
        ):
            if not value.strip():
                raise CinematicSeriesError(f"{name} must not be blank.")
        _positive_units(self.requested_units, name="requested_units")
        if not 0 <= self.generated_video_seconds <= GENERATED_VIDEO_HARD_LIMIT_SECONDS:
            raise CinematicSeriesError(
                "generated_video_seconds must be between 0 and 300."
            )
        for value, name in (
            (self.quality_score_override, "quality_score_override"),
            (self.reliability_score_override, "reliability_score_override"),
        ):
            if value is not None and not 0 <= value <= 100:
                raise CinematicSeriesError(f"{name} must be between 0 and 100.")

    @property
    def units(self) -> Decimal:
        return _positive_units(self.requested_units, name="requested_units")


@dataclass(frozen=True, slots=True)
class PrecisePricedMediaOption:
    option_id: str
    frame_id: str
    treatment: MediaTreatment
    category: MediaCategory
    estimated_cost_usd: str
    quality_score: int
    reliability_score: int
    generated_video_seconds: int
    provider_id: str
    model_id: str
    price_source_id: str
    billing_basis: BillingBasis
    requested_units: str
    schema_version: str = PRECISE_MEDIA_OPTION_SCHEMA_VERSION
    live_execution_allowed: bool = False

    def validate(self) -> None:
        for value, name in (
            (self.option_id, "option_id"),
            (self.frame_id, "frame_id"),
            (self.provider_id, "provider_id"),
            (self.model_id, "model_id"),
            (self.price_source_id, "price_source_id"),
        ):
            if not value.strip():
                raise CinematicSeriesError(f"{name} must not be blank.")
        _money(self.estimated_cost_usd, name="estimated_cost_usd")
        _positive_units(self.requested_units, name="requested_units")
        if not 0 <= self.quality_score <= 100:
            raise CinematicSeriesError("quality_score must be between 0 and 100.")
        if not 0 <= self.reliability_score <= 100:
            raise CinematicSeriesError("reliability_score must be between 0 and 100.")
        if not 0 <= self.generated_video_seconds <= GENERATED_VIDEO_HARD_LIMIT_SECONDS:
            raise CinematicSeriesError(
                "generated_video_seconds must be between 0 and 300."
            )
        if self.schema_version != PRECISE_MEDIA_OPTION_SCHEMA_VERSION:
            raise CinematicSeriesError("Unexpected precise media option schema.")
        if self.live_execution_allowed:
            raise CinematicSeriesError("A priced option cannot authorize live execution.")
        video_treatment = self.treatment in {
            MediaTreatment.GENERATED_VIDEO,
            MediaTreatment.HYBRID_SEQUENCE,
        }
        if video_treatment and self.generated_video_seconds <= 0:
            raise CinematicSeriesError(
                "Generated-video options require positive video seconds."
            )
        if not video_treatment and self.generated_video_seconds != 0:
            raise CinematicSeriesError(
                "Non-video options cannot allocate generated-video seconds."
            )

    @property
    def cost(self) -> Decimal:
        return _money(self.estimated_cost_usd, name="estimated_cost_usd")

    @property
    def cost_micro_usd(self) -> int:
        return _to_micro_usd(self.cost)


class VerifiedMediaOptionFactory:
    """Quote explicit frame specs from verified manual observations."""

    def quote(
        self,
        compiled: CompiledCinematicEpisode,
        catalog: VerifiedProviderPriceCatalog,
        specs: Iterable[FrameQuoteSpec],
    ) -> tuple[PrecisePricedMediaOption, ...]:
        catalog.validate()
        ordered_specs = tuple(specs)
        if not ordered_specs:
            raise CinematicSeriesError("At least one frame quote spec is required.")
        if len({item.quote_id for item in ordered_specs}) != len(ordered_specs):
            raise CinematicSeriesError("Frame quote ids must be unique.")
        assignments = {item.frame_id: item for item in compiled.assignments}
        options: list[PrecisePricedMediaOption] = []
        for spec in ordered_specs:
            spec.validate()
            assignment = assignments.get(spec.frame_id)
            if assignment is None:
                raise CinematicSeriesError(
                    f"Quote references unknown frame: {spec.frame_id}"
                )
            record = catalog.record(spec.provider_test_id)
            self._validate_quote_semantics(spec, record, assignment)
            exact_cost = (record.unit_price * spec.units).quantize(
                PRICE_QUANTUM,
                rounding=ROUND_HALF_UP,
            )
            quality = (
                record.quality_score
                if spec.quality_score_override is None
                else spec.quality_score_override
            )
            reliability = (
                record.reliability_score
                if spec.reliability_score_override is None
                else spec.reliability_score_override
            )
            option_id = deterministic_id(
                "precise_priced_media_option",
                [
                    spec.quote_id,
                    spec.frame_id,
                    record.test_id,
                    format(spec.units, "f"),
                    spec.generated_video_seconds,
                    _usd_text(exact_cost),
                    quality,
                    reliability,
                ],
            )
            option = PrecisePricedMediaOption(
                option_id=option_id,
                frame_id=spec.frame_id,
                treatment=record.treatment,
                category=record.category,
                estimated_cost_usd=_usd_text(exact_cost),
                quality_score=quality,
                reliability_score=reliability,
                generated_video_seconds=spec.generated_video_seconds,
                provider_id=record.provider_id,
                model_id=record.model_id,
                price_source_id=record.test_id,
                billing_basis=record.billing_basis,
                requested_units=format(spec.units, "f"),
            )
            option.validate()
            options.append(option)
        return tuple(options)

    @staticmethod
    def _validate_quote_semantics(
        spec: FrameQuoteSpec,
        record: ManualProviderTestRecord,
        assignment: CompiledFrameAssignment,
    ) -> None:
        if record.treatment not in assignment.allowed_treatments:
            raise CinematicSeriesError(
                "Verified provider treatment is not allowed for the frame."
            )
        if (
            assignment.motion_need is MotionNeed.REQUIRED
            and record.treatment not in MOTION_CAPABLE_TREATMENTS
        ):
            raise CinematicSeriesError(
                "A motion-required frame needs a motion-capable quote."
            )
        if spec.generated_video_seconds > assignment.maximum_generated_video_seconds:
            raise CinematicSeriesError(
                "Quote exceeds the frame generated-video ceiling."
            )
        if record.billing_basis is BillingBasis.PER_REQUEST:
            if spec.units != Decimal("1"):
                raise CinematicSeriesError("PER_REQUEST quotes must request one unit.")
        if record.billing_basis is BillingBasis.PER_OUTPUT:
            if spec.units != spec.units.to_integral_value():
                raise CinematicSeriesError("PER_OUTPUT quote units must be integral.")
        if record.billing_basis is BillingBasis.PER_SECOND:
            if spec.units != spec.units.to_integral_value():
                raise CinematicSeriesError("PER_SECOND quote units must be integral.")
            if int(spec.units) != spec.generated_video_seconds:
                raise CinematicSeriesError(
                    "PER_SECOND requested units must equal generated_video_seconds."
                )
        video_treatment = record.treatment in {
            MediaTreatment.GENERATED_VIDEO,
            MediaTreatment.HYBRID_SEQUENCE,
        }
        if video_treatment and spec.generated_video_seconds <= 0:
            raise CinematicSeriesError(
                "Generated-video quotes require positive video seconds."
            )
        if not video_treatment and spec.generated_video_seconds != 0:
            raise CinematicSeriesError(
                "Non-video quotes cannot allocate generated-video seconds."
            )


@dataclass(frozen=True, slots=True)
class PreciseFixedProductionCost:
    item_id: str
    category: MediaCategory
    estimated_cost_usd: str
    description: str
    price_source_id: str

    def validate(self) -> None:
        for value, name in (
            (self.item_id, "item_id"),
            (self.description, "description"),
            (self.price_source_id, "price_source_id"),
        ):
            if not value.strip():
                raise CinematicSeriesError(f"{name} must not be blank.")
        _money(self.estimated_cost_usd, name="estimated_cost_usd")

    @property
    def cost(self) -> Decimal:
        return _money(self.estimated_cost_usd, name="estimated_cost_usd")

    @property
    def cost_micro_usd(self) -> int:
        return _to_micro_usd(self.cost)


@dataclass(frozen=True, slots=True)
class PreciseBudgetedCinematicEpisode:
    allocation_id: str
    editorial_compilation_id: str
    final_plan: CinematicStoryboardPlan
    selected_options: tuple[PrecisePricedMediaOption, ...]
    fixed_costs: tuple[PreciseFixedProductionCost, ...]
    category_totals_usd: tuple[tuple[str, str], ...]
    allocated_total_usd: str
    budget_limit_usd: str
    hard_headroom_used: bool
    hard_headroom_justification: str | None
    schema_version: str = PRECISE_BUDGET_PLANNER_SCHEMA_VERSION
    live_execution_allowed: bool = False

    def to_manifest(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "allocation_id": self.allocation_id,
            "editorial_compilation_id": self.editorial_compilation_id,
            "final_plan_id": self.final_plan.plan_id,
            "budget": {
                "allocated_total_usd": self.allocated_total_usd,
                "budget_limit_usd": self.budget_limit_usd,
                "hard_headroom_used": self.hard_headroom_used,
                "hard_headroom_justification": self.hard_headroom_justification,
                "category_totals_usd": dict(self.category_totals_usd),
                "precision_places": PRICE_PRECISION_PLACES,
            },
            "generated_video_seconds": self.final_plan.generated_video_seconds,
            "live_execution_allowed": False,
            "selected_options": [
                {
                    "option_id": item.option_id,
                    "frame_id": item.frame_id,
                    "treatment": item.treatment.value,
                    "category": item.category.value,
                    "estimated_cost_usd": item.estimated_cost_usd,
                    "quality_score": item.quality_score,
                    "reliability_score": item.reliability_score,
                    "generated_video_seconds": item.generated_video_seconds,
                    "provider_id": item.provider_id,
                    "model_id": item.model_id,
                    "price_source_id": item.price_source_id,
                    "billing_basis": item.billing_basis.value,
                    "requested_units": item.requested_units,
                }
                for item in self.selected_options
            ],
            "fixed_costs": [
                {
                    "item_id": item.item_id,
                    "category": item.category.value,
                    "estimated_cost_usd": item.estimated_cost_usd,
                    "description": item.description,
                    "price_source_id": item.price_source_id,
                }
                for item in self.fixed_costs
            ],
        }

    def to_json(self) -> str:
        return json.dumps(
            self.to_manifest(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )


class PreciseDynamicCinematicBudgetPlanner:
    """Optimize verified options with micro-USD precision."""

    def __init__(self, runtime: CinematicSeriesRuntime | None = None) -> None:
        self._runtime = runtime or CinematicSeriesRuntime()

    def plan(
        self,
        storyboard: Storyboard,
        compiled: CompiledCinematicEpisode,
        options: Iterable[PrecisePricedMediaOption],
        *,
        fixed_costs: Iterable[PreciseFixedProductionCost] = (),
        allow_hard_headroom: bool = False,
        hard_headroom_justification: str | None = None,
    ) -> PreciseBudgetedCinematicEpisode:
        ordered_options = tuple(options)
        ordered_fixed = tuple(fixed_costs)
        for item in ordered_options:
            item.validate()
        for item in ordered_fixed:
            item.validate()
        if len({item.option_id for item in ordered_options}) != len(ordered_options):
            raise CinematicSeriesError("Precise media option ids must be unique.")
        if len({item.item_id for item in ordered_fixed}) != len(ordered_fixed):
            raise CinematicSeriesError("Precise fixed cost ids must be unique.")
        if allow_hard_headroom and not (hard_headroom_justification or "").strip():
            raise CinematicSeriesError(
                "Using the USD 45 hard headroom requires explicit justification."
            )
        if not allow_hard_headroom and hard_headroom_justification is not None:
            raise CinematicSeriesError(
                "Headroom justification is invalid when hard headroom is disabled."
            )
        guardrails = compiled.budget
        if not isinstance(guardrails, CinematicBudgetGuardrails):
            raise CinematicSeriesError("Compiled episode has invalid budget guardrails.")
        guardrails.validate()
        budget_limit = _money(
            guardrails.hard_total_usd if allow_hard_headroom else guardrails.target_total_usd,
            name="budget_limit_usd",
        )
        base_cost = sum((item.cost_micro_usd for item in ordered_fixed), 0)
        limit = _to_micro_usd(budget_limit)
        if base_cost > limit:
            raise CinematicSeriesError(
                "Fixed production costs already exceed the selected budget limit."
            )

        option_groups: dict[str, list[PrecisePricedMediaOption]] = {}
        for item in ordered_options:
            option_groups.setdefault(item.frame_id, []).append(item)
        assignment_by_id = {item.frame_id: item for item in compiled.assignments}
        expected_frame_ids = [item.frame_id for item in compiled.assignments]
        extra = sorted(set(option_groups).difference(expected_frame_ids))
        if extra:
            raise CinematicSeriesError(
                f"Precise options reference unknown frames: {extra}"
            )

        eligible_groups: list[tuple[PrecisePricedMediaOption, ...]] = []
        for frame_id in expected_frame_ids:
            assignment = assignment_by_id[frame_id]
            eligible = tuple(
                sorted(
                    (
                        item
                        for item in option_groups.get(frame_id, [])
                        if self._option_is_eligible(assignment, item)
                    ),
                    key=lambda item: item.option_id,
                )
            )
            if not eligible:
                raise CinematicSeriesError(
                    f"No eligible precise option exists for frame {frame_id}."
                )
            eligible_groups.append(eligible)

        states: dict[
            int,
            tuple[int, tuple[str, ...], tuple[PrecisePricedMediaOption, ...]],
        ] = {base_cost: (0, (), ())}
        for assignment, group in zip(
            compiled.assignments,
            eligible_groups,
            strict=True,
        ):
            next_states: dict[
                int,
                tuple[int, tuple[str, ...], tuple[PrecisePricedMediaOption, ...]],
            ] = {}
            for current_cost, (score, ids, chosen) in states.items():
                for option in group:
                    next_cost = current_cost + option.cost_micro_usd
                    if next_cost > limit:
                        continue
                    candidate = (
                        score + DynamicCinematicBudgetPlanner._option_utility(
                            assignment, option
                        ),
                        (*ids, option.option_id),
                        (*chosen, option),
                    )
                    existing = next_states.get(next_cost)
                    if existing is None or self._candidate_better(candidate, existing):
                        next_states[next_cost] = candidate
            states = self._prune_dominated(next_states)
            if not states:
                raise CinematicSeriesError(
                    "No complete precise media plan fits the selected budget limit."
                )

        selected_cost, best = sorted(
            states.items(),
            key=lambda item: (-item[1][0], item[0], item[1][1]),
        )[0]
        selected = best[2]
        video_seconds = sum(item.generated_video_seconds for item in selected)
        if video_seconds > compiled.policy.generated_video_hard_limit_seconds:
            raise CinematicSeriesError(
                "Selected precise plan exceeds the generated-video ceiling."
            )
        selected_by_frame = {item.frame_id: item for item in selected}
        final_directives = tuple(
            replace(
                directive,
                generated_video_seconds=(
                    selected_by_frame[directive.frame_id].generated_video_seconds
                ),
            )
            for directive in compiled.plan.directives
        )
        final_plan = self._runtime.build_plan(
            storyboard,
            compiled.plan.contract,
            final_directives,
        )
        category_totals = self._category_totals(selected, ordered_fixed)
        allocated = _from_micro_usd(selected_cost)
        hard_used = allocated > _money(
            compiled.budget.target_total_usd,
            name="target_total_usd",
        )
        allocation_id = deterministic_id(
            "precise_cinematic_budget_allocation",
            [
                PRECISE_BUDGET_PLANNER_SCHEMA_VERSION,
                DYNAMIC_BUDGET_PLANNER_SCHEMA_VERSION,
                compiled.compilation_id,
                final_plan.plan_id,
                [item.option_id for item in selected],
                [item.item_id for item in ordered_fixed],
                _usd_text(allocated),
                _usd_text(budget_limit),
                hard_headroom_justification,
            ],
        )
        result = PreciseBudgetedCinematicEpisode(
            allocation_id=allocation_id,
            editorial_compilation_id=compiled.compilation_id,
            final_plan=final_plan,
            selected_options=selected,
            fixed_costs=ordered_fixed,
            category_totals_usd=category_totals,
            allocated_total_usd=_usd_text(allocated),
            budget_limit_usd=_usd_text(budget_limit),
            hard_headroom_used=hard_used,
            hard_headroom_justification=(
                hard_headroom_justification if hard_used else None
            ),
        )
        self._validate_result(storyboard, compiled, result)
        return result

    @staticmethod
    def _option_is_eligible(
        assignment: CompiledFrameAssignment,
        option: PrecisePricedMediaOption,
    ) -> bool:
        if option.treatment not in assignment.allowed_treatments:
            return False
        if (
            assignment.motion_need is MotionNeed.REQUIRED
            and option.treatment not in MOTION_CAPABLE_TREATMENTS
        ):
            return False
        if option.generated_video_seconds > assignment.maximum_generated_video_seconds:
            return False
        return True

    @staticmethod
    def _candidate_better(candidate, existing) -> bool:
        if candidate[0] != existing[0]:
            return candidate[0] > existing[0]
        return candidate[1] < existing[1]

    @staticmethod
    def _prune_dominated(states):
        best_score = -1
        pruned = {}
        for cost in sorted(states):
            state = states[cost]
            if state[0] > best_score:
                pruned[cost] = state
                best_score = state[0]
        return pruned

    @staticmethod
    def _category_totals(selected, fixed_costs) -> tuple[tuple[str, str], ...]:
        totals: dict[str, int] = {}
        for item in selected:
            totals[item.category.value] = (
                totals.get(item.category.value, 0) + item.cost_micro_usd
            )
        for item in fixed_costs:
            totals[item.category.value] = (
                totals.get(item.category.value, 0) + item.cost_micro_usd
            )
        return tuple(
            (category, _usd_text(_from_micro_usd(value)))
            for category, value in sorted(totals.items())
        )

    def _validate_result(
        self,
        storyboard: Storyboard,
        compiled: CompiledCinematicEpisode,
        result: PreciseBudgetedCinematicEpisode,
    ) -> None:
        if result.schema_version != PRECISE_BUDGET_PLANNER_SCHEMA_VERSION:
            raise CinematicSeriesError("Unexpected precise budget planner schema.")
        if result.live_execution_allowed:
            raise CinematicSeriesError("Precise planning cannot enable execution.")
        if result.editorial_compilation_id != compiled.compilation_id:
            raise CinematicSeriesError("Precise plan references another compilation.")
        if len(result.selected_options) != storyboard.frame_count:
            raise CinematicSeriesError("Every frame needs one precise option.")
        if [item.frame_id for item in result.selected_options] != [
            item.frame_id for item in storyboard.frames
        ]:
            raise CinematicSeriesError("Precise options must preserve frame order.")
        allocated = _money(result.allocated_total_usd, name="allocated_total_usd")
        limit = _money(result.budget_limit_usd, name="budget_limit_usd")
        if allocated > limit:
            raise CinematicSeriesError("Precise budget result exceeds its limit.")
        if allocated > _money(compiled.budget.hard_total_usd, name="hard_total_usd"):
            raise CinematicSeriesError("Precise result exceeds the hard episode cap.")
        if not self._runtime.validate_plan(storyboard, result.final_plan):
            raise CinematicSeriesError("Precise final cinematic plan is invalid.")


def manual_test_template(provider_id: str = "RUNWARE") -> dict[str, object]:
    """Return a non-executable template for one manually observed provider test."""
    return {
        "schema_version": PROVIDER_MANUAL_TEST_SCHEMA_VERSION,
        "test_id": "REPLACE_WITH_STABLE_TEST_ID",
        "provider_id": provider_id,
        "model_id": "REPLACE_WITH_EXACT_MODEL_ID",
        "source_kind": PriceSourceKind.MANUAL_PROVIDER_TEST.value,
        "treatment": MediaTreatment.GENERATED_IMAGE.value,
        "category": MediaCategory.IMAGE.value,
        "billing_basis": BillingBasis.PER_OUTPUT.value,
        "observed_total_cost_usd": "REPLACE_WITH_EXACT_CHARGED_COST",
        "billed_units": "1",
        "generated_output_count": 1,
        "generated_video_seconds": 0,
        "quality_score": "REVIEW_0_TO_100",
        "reliability_score": "REVIEW_0_TO_100",
        "latency_ms": "REPLACE_WITH_OBSERVED_LATENCY",
        "request_fingerprint_sha256": "SHA256_OF_SANITIZED_REQUEST_WITHOUT_CREDENTIALS",
        "response_fingerprint_sha256": "SHA256_OF_SANITIZED_RESPONSE_OR_OUTPUT_MANIFEST",
        "tested_at_utc": "YYYY-MM-DDTHH:MM:SSZ",
        "status": ProviderTestStatus.PASS.value,
        "notes": "Do not include credentials, authorization headers, or secret material.",
        "credentials_recorded": False,
        "live_execution_authorized": False,
    }
