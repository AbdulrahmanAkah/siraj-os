"""Local, versioned cost authority for SIRAJ pre-spend planning.

The registry intentionally permits explicit ``UNPRICED`` records.  An
unknown price is never converted to zero and never authorizes a paid request.
This module performs no network lookup and creates no provider attempt.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_UP
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.application.artifact_provenance_v1 import canonical_sha256
from src.application.siraj_cinematic_media_mix_policy_v2 import validate_true_video_coverage


REGISTRY_SCHEMA_VERSION = "siraj-media-pricing-registry-v2"
REGISTRY_RELATIVE_PATH = Path("projects/_series/siraj-media-pricing-registry-v2.json")


class CostAuthorityError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class PriceRecord:
    provider: str
    model: str
    media_kind: str
    status: str
    billing_unit: str
    unit_price: float | None
    currency: str | None
    registry_version: str
    source: str
    effective_at_utc: str
    valid_until_utc: str | None = None
    notes: str | None = None
    source_url: str | None = None
    retrieved_at_utc: str | None = None
    variants: tuple[dict[str, Any], ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class CostAssessment:
    pricing_status: str
    priced_requests: int
    unpriced_requests: int
    estimated_total_cost: float | None
    maximum_bound: float | None
    currency: str | None
    provider_subtotals: dict[str, float | None]
    media_type_subtotals: dict[str, float | None]
    unknown_cost_components: tuple[dict[str, Any], ...]
    registry_version: str
    provider_execution_allowed: bool

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["unknown_cost_components"] = [dict(item) for item in self.unknown_cost_components]
        return value


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _record_is_stale(record: PriceRecord) -> bool:
    if not record.valid_until_utc:
        return False
    try:
        expiry = datetime.fromisoformat(record.valid_until_utc.replace("Z", "+00:00"))
    except ValueError:
        return True
    return datetime.now(timezone.utc) > expiry


def _record_from_mapping(value: Mapping[str, Any]) -> PriceRecord:
    required = ("provider", "model", "media_kind", "status", "billing_unit", "registry_version", "source")
    if any(not str(value.get(key) or "").strip() for key in required):
        raise CostAuthorityError("PRICING_RECORD_REQUIRED_FIELDS_MISSING")
    price = value.get("unit_price")
    if price is not None and (not isinstance(price, (int, float)) or isinstance(price, bool) or float(price) < 0):
        raise CostAuthorityError("PRICING_UNIT_PRICE_INVALID")
    status = str(value["status"]).upper()
    if status not in {"PRICED", "UNPRICED", "LOCAL_ZERO"}:
        raise CostAuthorityError("PRICING_RECORD_STATUS_INVALID:" + status)
    if status == "PRICED" and (price is None or not str(value.get("currency") or "").strip()):
        raise CostAuthorityError("PRICED_RECORD_REQUIRES_PRICE_AND_CURRENCY")
    if status != "PRICED" and price is not None:
        raise CostAuthorityError("UNPRICED_RECORD_CANNOT_HAVE_PRICE")
    return PriceRecord(
        provider=str(value["provider"]),
        model=str(value["model"]),
        media_kind=str(value["media_kind"]),
        status=status,
        billing_unit=str(value["billing_unit"]),
        unit_price=float(price) if price is not None else None,
        currency=str(value.get("currency")) if value.get("currency") else None,
        registry_version=str(value["registry_version"]),
        source=str(value["source"]),
        effective_at_utc=str(value.get("effective_at_utc") or ""),
        valid_until_utc=str(value.get("valid_until_utc")) if value.get("valid_until_utc") else None,
        notes=str(value.get("notes")) if value.get("notes") else None,
        source_url=str(value.get("source_url")) if value.get("source_url") else None,
        retrieved_at_utc=str(value.get("retrieved_at_utc")) if value.get("retrieved_at_utc") else None,
        variants=tuple(dict(item) for item in value.get("variants", []) if isinstance(item, Mapping)),
    )


def load_pricing_registry(path: Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict) or value.get("schema_version") != REGISTRY_SCHEMA_VERSION:
        raise CostAuthorityError("PRICING_REGISTRY_SCHEMA_INVALID")
    if not isinstance(value.get("entries"), list):
        raise CostAuthorityError("PRICING_REGISTRY_ENTRIES_REQUIRED")
    registry_version = str(value.get("registry_version") or "")
    if not registry_version:
        raise CostAuthorityError("PRICING_REGISTRY_VERSION_REQUIRED")
    records = [_record_from_mapping(item) for item in value["entries"] if isinstance(item, Mapping)]
    if len(records) != len(value["entries"]):
        raise CostAuthorityError("PRICING_REGISTRY_ENTRY_INVALID")
    value["_records"] = records
    return value


def _record_key(provider: str, model: str, media_kind: str) -> tuple[str, str, str]:
    return provider.upper(), model, media_kind.upper()


def find_price_record(registry: Mapping[str, Any], *, provider: str, model: str, media_kind: str) -> PriceRecord | None:
    records = registry.get("_records")
    if not isinstance(records, list):
        records = [_record_from_mapping(item) for item in registry.get("entries", []) if isinstance(item, Mapping)]
    wanted = _record_key(provider, model, media_kind)
    for record in records:
        if _record_key(record.provider, record.model, record.media_kind) == wanted:
            return record
    return None


def _unit_quantity(unit: Mapping[str, Any], billing_unit: str) -> float:
    normalized = billing_unit.lower()
    if normalized in {"per_image", "image", "request", "per_request", "fixed_duration_request"}:
        return 1.0
    if normalized in {"per_generated_video_second", "video_second", "second"}:
        return float(unit.get("requested_seconds") or unit.get("provider_requested_seconds") or unit.get("requested_duration_seconds") or 0.0)
    if normalized in {"per_token", "token"}:
        return float(unit.get("token_count") or 0.0)
    raise CostAuthorityError("PRICING_BILLING_UNIT_UNSUPPORTED:" + billing_unit)


def _variant_matches(variant: Mapping[str, Any], unit: Mapping[str, Any]) -> bool:
    """Match a provider pricing tier without guessing a missing dimension."""

    requested_variant = str(unit.get("pricing_variant") or "").strip()
    if requested_variant and str(variant.get("id") or "") == requested_variant:
        return True
    resolution = str(unit.get("resolution") or "").strip().lower()
    if resolution and str(variant.get("resolution") or "").strip().lower() == resolution:
        audio = unit.get("generate_audio")
        if "generate_audio" not in variant or audio is None or bool(variant.get("generate_audio")) == bool(audio):
            return True
    width = unit.get("width")
    height = unit.get("height")
    if isinstance(width, int) and isinstance(height, int):
        dimensions = variant.get("dimensions")
        if isinstance(dimensions, list) and [width, height] in dimensions:
            return True
        pixels = width * height
        min_pixels = variant.get("min_pixels")
        max_pixels = variant.get("max_pixels")
        if min_pixels is not None and pixels < int(min_pixels):
            return False
        if max_pixels is not None and pixels > int(max_pixels):
            return False
        if min_pixels is not None or max_pixels is not None:
            return True
    return False


def resolve_price_variant(record: PriceRecord, unit: Mapping[str, Any]) -> Mapping[str, Any] | None:
    """Resolve the exact price tier for a planned request.

    A priced record with unresolved dimensions is deliberately treated as
    unknown; the estimator must never silently select the cheapest tier.
    """

    if not record.variants:
        return {
            "id": "base",
            "billing_unit": record.billing_unit,
            "unit_price": record.unit_price,
            "currency": record.currency,
        }
    for variant in record.variants:
        if _variant_matches(variant, unit):
            return variant
    return None


def assess_cost(
    units: Sequence[Mapping[str, Any]],
    registry: Mapping[str, Any],
) -> CostAssessment:
    """Assess all planned paid units without reaching a provider."""

    records = registry.get("_records")
    if not isinstance(records, list):
        records = [_record_from_mapping(item) for item in registry.get("entries", []) if isinstance(item, Mapping)]
    registry_version = str(registry.get("registry_version") or "")
    if not registry_version:
        raise CostAuthorityError("PRICING_REGISTRY_VERSION_REQUIRED")
    priced = 0
    unpriced = 0
    total = 0.0
    currency: str | None = None
    provider_subtotals: dict[str, float | None] = {}
    media_subtotals: dict[str, float | None] = {}
    unknown: list[dict[str, Any]] = []
    for unit in units:
        media_kind = str(unit.get("media_kind") or "")
        if media_kind == "LOCAL_GRAPHICS" or str(unit.get("provider") or "").upper() == "LOCAL":
            provider_subtotals.setdefault("LOCAL", 0.0)
            media_subtotals.setdefault(media_kind or "LOCAL", 0.0)
            continue
        provider = str(unit.get("provider") or "")
        model = str(unit.get("model") or "")
        record = find_price_record(registry, provider=provider, model=model, media_kind=media_kind)
        if (
            record is None
            or record.status != "PRICED"
            or record.registry_version != registry_version
            or _record_is_stale(record)
        ):
            unpriced += 1
            provider_subtotals[provider] = None
            media_subtotals[media_kind] = None
            unknown.append(
                {
                    "unit_id": unit.get("unit_id"),
                    "provider": provider,
                    "model": model,
                    "media_kind": media_kind,
                    "pricing_data_required": "provider/model/media-type billing unit and currency price",
                    "reason": "NO_AUTHORITATIVE_LOCAL_PRICE" if record is None else "PRICE_RECORD_UNPRICED_OR_STALE",
                }
            )
            continue
        variant = resolve_price_variant(record, unit)
        if variant is None:
            unpriced += 1
            provider_subtotals[provider] = None
            media_subtotals[media_kind] = None
            unknown.append(
                {
                    "unit_id": unit.get("unit_id"),
                    "provider": provider,
                    "model": model,
                    "media_kind": media_kind,
                    "pricing_data_required": "exact provider pricing variant (resolution/duration/input tier)",
                    "reason": "PRICING_VARIANT_UNRESOLVED",
                }
            )
            continue
        billing_unit = str(variant.get("billing_unit") or record.billing_unit)
        unit_price = variant.get("unit_price", record.unit_price)
        variant_currency = variant.get("currency", record.currency)
        if unit_price is None or not str(variant_currency or "").strip():
            unpriced += 1
            provider_subtotals[provider] = None
            media_subtotals[media_kind] = None
            unknown.append(
                {
                    "unit_id": unit.get("unit_id"),
                    "provider": provider,
                    "model": model,
                    "media_kind": media_kind,
                    "pricing_data_required": "variant unit price and currency",
                    "reason": "PRICING_VARIANT_UNPRICED",
                }
            )
            continue
        quantity = _unit_quantity(unit, billing_unit)
        amount_decimal = Decimal(str(unit_price)) * Decimal(str(quantity))
        amount = float(amount_decimal.quantize(Decimal("0.00000001"), rounding=ROUND_UP))
        priced += 1
        total += amount
        if currency is None:
            currency = str(variant_currency)
        elif currency != str(variant_currency):
            raise CostAuthorityError("PRICING_CURRENCY_MISMATCH")
        provider_subtotals[provider] = round(float(provider_subtotals.get(provider) or 0.0) + amount, 8)
        media_subtotals[media_kind] = round(float(media_subtotals.get(media_kind) or 0.0) + amount, 8)
    status = "COMPLETE" if unpriced == 0 else ("UNKNOWN" if priced == 0 else "PARTIAL")
    return CostAssessment(
        pricing_status=status,
        priced_requests=priced,
        unpriced_requests=unpriced,
        estimated_total_cost=float(Decimal(str(total)).quantize(Decimal("0.00000001"), rounding=ROUND_UP)) if unpriced == 0 else None,
        maximum_bound=float(Decimal(str(total)).quantize(Decimal("0.00000001"), rounding=ROUND_UP)) if unpriced == 0 else None,
        currency=currency if unpriced == 0 else None,
        provider_subtotals=provider_subtotals,
        media_type_subtotals=media_subtotals,
        unknown_cost_components=tuple(unknown),
        registry_version=registry_version,
        provider_execution_allowed=unpriced == 0,
    )


def canonical_registry_template(repo_root: Path | None = None) -> dict[str, Any]:
    """Return the checked-in registry, or a safe no-price bootstrap template.

    The checked-in versioned registry is the planning authority.  The
    no-price fallback remains useful for isolated fixtures and deliberately
    cannot authorize execution; it is not a second production price source.
    """

    root = Path(repo_root or Path.cwd()).resolve()
    registry_path = root / REGISTRY_RELATIVE_PATH
    if registry_path.is_file():
        loaded = load_pricing_registry(registry_path)
        loaded.pop("_records", None)
        return loaded

    now = _now_utc()
    entries = []
    for provider, model, media_kind in (
        ("RUNWARE", "google:veo@3.1-lite", "RUNWARE_VIDEO"),
        ("RUNWARE", "bytedance:seedream@5.0-pro", "RUNWARE_IMAGE"),
        ("RUNWARE", "google:4@3", "RUNWARE_IMAGE"),
    ):
        entries.append(
            PriceRecord(
                provider=provider,
                model=model,
                media_kind=media_kind,
                status="UNPRICED",
                billing_unit="UNKNOWN_UNTIL_AUTHORITATIVE_SOURCE",
                unit_price=None,
                currency=None,
                registry_version="v2-local-authority-2026-08-09",
                source="NO_AUTHORITATIVE_LOCAL_PRICE",
                effective_at_utc=now,
                notes="Do not infer zero or substitute another model; provider execution remains blocked.",
            )
        )
    return {
        "schema_version": REGISTRY_SCHEMA_VERSION,
        "registry_version": "v2-local-authority-2026-08-09",
        "generated_at_utc": now,
        "currency_policy": "EXPLICIT_CURRENCY_REQUIRED",
        "unknown_price_policy": "UNKNOWN_PRICING_BLOCKS_EXECUTION",
        "entries": [entry.as_dict() for entry in entries],
    }


def require_complete_pricing_for_provider_execution(
    repo_root: Path,
    episode_id: str,
    *,
    preflight_result_path: Path | None = None,
) -> dict[str, Any]:
    """Fail closed before any provider adapter can be reached.

    This read-only guard is intentionally usable by legacy adapters as a
    compatibility brake.  It does not create authorization, locks, attempts,
    or network traffic.
    """

    path = preflight_result_path or (
        Path(repo_root).resolve()
        / "projects"
        / episode_id
        / "orchestration"
        / "media-cost-preflight-v1.json"
    )
    if not path.is_file():
        raise CostAuthorityError("PREFLIGHT_RESULT_REQUIRED_BEFORE_PROVIDER_EXECUTION")
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, Mapping) or payload.get("episode_id") != episode_id:
        raise CostAuthorityError("PREFLIGHT_RESULT_EPISODE_INVALID")
    expected = canonical_sha256({key: value for key, value in payload.items() if key != "result_sha256"})
    if payload.get("result_sha256") != expected:
        raise CostAuthorityError("PREFLIGHT_RESULT_HASH_INVALID")
    summary = payload.get("summary")
    authoritative = payload.get("authoritative_state")
    if not isinstance(summary, Mapping) or not isinstance(authoritative, Mapping):
        raise CostAuthorityError("PREFLIGHT_RESULT_AUTHORITY_INVALID")
    coverage = validate_true_video_coverage(
        float(authoritative.get("duration_seconds") or 0.0),
        float(summary.get("generated_video_seconds") or 0.0),
    )
    if coverage.status != "PASS":
        raise CostAuthorityError(coverage.reason or coverage.status)
    cost_status = str(payload.get("cost_status") or "UNKNOWN").upper()
    envelope = payload.get("cost_envelope_usd")
    if not cost_status.startswith("KNOWN") or not isinstance(envelope, Mapping) or not isinstance(envelope.get("upper_bound"), (int, float)):
        raise CostAuthorityError("UNKNOWN_PRICING_BLOCKS_EXECUTION")
    return {
        "status": "PASS",
        "episode_id": episode_id,
        "preflight_result_path": str(path),
        "result_sha256": payload.get("result_sha256"),
        "coverage": coverage.as_dict(),
        "cost_status": cost_status,
        "cost_envelope": dict(envelope),
        "provider_execution_allowed": True,
    }
