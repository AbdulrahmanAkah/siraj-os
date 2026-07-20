"""Read-only Arabic presentation models for the local Pilot-12 workbench."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any


CATEGORY_ORDER = (
    "entities",
    "events",
    "relations",
    "temporal_mentions",
    "isnad",
    "claims_attribution",
    "rejected_elements",
    "warnings",
)

CATEGORY_LABELS = {
    "entities": "الكيانات",
    "events": "الأحداث",
    "relations": "العلاقات",
    "temporal_mentions": "الأزمنة",
    "isnad": "الأسانيد",
    "claims_attribution": "الادعاءات والإسناد",
    "rejected_elements": "العناصر المرفوضة",
    "warnings": "التحذيرات",
}

_TRANSLATIONS = {
    "PERSON": "شخص",
    "PLACE": "مكان",
    "CITY": "مدينة",
    "REGION": "إقليم",
    "STATE": "دولة",
    "DYNASTY": "سلالة حاكمة",
    "GROUP": "جماعة",
    "TRIBE": "قبيلة",
    "SCHOLAR": "عالم",
    "NARRATOR": "راوٍ",
    "CALIPH": "خليفة",
    "RULER": "حاكم",
    "AUTHOR": "مؤلف",
    "WORK": "مؤلَّف",
    "EVENT": "حدث",
    "PERIOD": "فترة زمنية",
    "INSTITUTION": "مؤسسة",
    "OFFICE": "منصب",
    "CONCEPT": "مفهوم",
    "ARRIVAL": "قدوم",
    "APPOINTMENT": "تولية",
    "DISMISSAL": "عزل",
    "DEATH": "وفاة",
    "BIRTH": "ميلاد",
    "FOUNDING": "تأسيس",
    "BATTLE": "قتال",
    "TRAVEL": "سفر",
    "SUCCESSION": "خلافة أو تعاقب",
    "NARRATED_FROM": "روى عن",
    "AUTHORED": "ألّف",
    "SUCCEEDED": "خلف",
    "PRECEDED": "سبق",
    "RULED": "حكم",
    "FOUGHT": "قاتل",
    "FOUNDED": "أسس",
    "LIVED_IN": "أقام في",
    "TRAVELED_TO": "سافر إلى",
    "BORN_IN": "ولد في",
    "DIED_IN": "توفي في",
    "MEMBER_OF": "ينتمي إلى",
    "LED": "قاد",
    "EXPLICIT": "صريحة",
    "INFERRED": "مستنتجة",
    "ARRIVER": "الواصل",
    "APPOINTEE": "المولّى",
    "APPOINTER_UNRESOLVED": "صاحب التولية غير المسمى",
    "SUCCESSOR": "الخلف",
    "LOCATION": "موقع",
    "DESTINATION": "وجهة",
    "ORIGIN": "منشأ",
    "TERRITORY_OR_OFFICE_JURISDICTION": "نطاق حكم أو اختصاص",
    "YEAR": "سنة",
    "MONTH": "شهر",
    "DURATION": "مدة",
    "RELATIVE": "زمن نسبي",
    "APPROXIMATE": "تاريخ تقريبي",
    "HIJRI": "هجري",
    "GREGORIAN": "ميلادي",
    "SOURCE_ASSERTION": "نسبة إلى المصدر",
    "QUOTED": "قول منقول",
    "AUTHORIAL": "كلام المؤلف",
    "AFFIRMATION": "إثبات",
    "NEGATION": "نفي",
    "UNCERTAINTY": "احتمال أو عدم يقين",
    "ACCEPTED_HIGH_CONFIDENCE": "مقبول بثقة عالية",
    "ACCEPTED_WITH_WARNING": "مقبول مع تحذير",
    "HUMAN_REVIEW_REQUIRED": "يحتاج مراجعة",
    "REJECTED_UNSUPPORTED": "مرفوض لعدم كفاية الدليل",
    "EVIDENCE_SPAN_INVALID": "الدليل النصي لا يطابق موضعه",
    "ENTITY_SURFACE_SPAN_MISMATCH": "النص المستخرج لا يطابق موضعه في المصدر",
    "MISSING_EVIDENCE": "لا يوجد دليل نصي كافٍ",
    "UNSUPPORTED_INFERENCE": "استنتاج غير مدعوم بالنص",
    "HEADING_AS_BODY_EVIDENCE": "استُخدم عنوان بوصفه دليلاً من المتن",
}


def arabic_label(value: Any, *, fallback: str = "وصف غير مصنف") -> str:
    """Translate a closed semantic label without exposing technical fallback."""

    if value is None or str(value).strip() == "":
        return fallback
    key = str(value).strip().upper()
    return _TRANSLATIONS.get(key, fallback)


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def _text(value: Any) -> str:
    if isinstance(value, dict):
        for key in (
            "text",
            "exact_surface",
            "surface",
            "name",
            "value",
            "expression",
            "proposition",
        ):
            if value.get(key):
                return str(value[key])
        return ""
    return str(value or "")


def _span_text(item: dict[str, Any]) -> str:
    for key in (
        "evidence",
        "evidence_span",
        "original_text_span",
        "trigger",
        "exact_chain_range",
        "span",
    ):
        value = item.get(key)
        if isinstance(value, dict) and _text(value):
            return _text(value)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def _item_id(item: dict[str, Any]) -> str:
    for key in (
        "mention_id",
        "event_id",
        "event_mention_id",
        "relation_id",
        "temporal_id",
        "chain_id",
        "claim_id",
        "item_id",
        "id",
    ):
        if item.get(key):
            return str(item[key])
    return ""


def _technical(item: dict[str, Any]) -> dict[str, Any]:
    return item


def _status_index(
    reconciliation: dict[str, Any],
    validation: dict[str, Any],
) -> dict[str, tuple[str, list[str]]]:
    issues: dict[str, list[str]] = {}
    for issue in _as_list(validation.get("issues")):
        if isinstance(issue, dict) and issue.get("subject_id"):
            issues.setdefault(str(issue["subject_id"]), []).append(
                str(issue.get("code", ""))
            )
    result: dict[str, tuple[str, list[str]]] = {}
    for item in _as_list(reconciliation.get("items")):
        if not isinstance(item, dict) or not item.get("item_id"):
            continue
        item_id = str(item["item_id"])
        codes = list(map(str, _as_list(item.get("reason_codes"))))
        codes.extend(issues.get(item_id, []))
        result[item_id] = (str(item.get("status", "HUMAN_REVIEW_REQUIRED")), codes)
    return result


def _status_for(
    item: dict[str, Any],
    statuses: dict[str, tuple[str, list[str]]],
    *,
    default: str,
) -> dict[str, Any]:
    status, codes = statuses.get(_item_id(item), (default, []))
    return {
        "code": status,
        "label": arabic_label(status, fallback="يحتاج مراجعة"),
        "reasons": [
            arabic_label(code, fallback="تحتاج هذه النتيجة إلى مراجعة بشرية")
            for code in sorted(set(codes))
        ],
    }


def _entity_card(
    item: dict[str, Any],
    statuses: dict[str, tuple[str, list[str]]],
    default_status: str,
) -> dict[str, Any]:
    types = _as_list(item.get("entity_types") or item.get("entity_type_candidate") or item.get("type"))
    roles = _as_list(item.get("contextual_roles") or item.get("contextual_role"))
    return {
        "kind": "entity",
        "surface": str(item.get("exact_surface") or item.get("normalized_surface_form") or item.get("surface") or "عنصر غير مسمى"),
        "types": [arabic_label(value, fallback="تصنيف مقترح") for value in types],
        "roles": [arabic_label(value, fallback="دور سياقي") for value in roles],
        "evidence": _span_text(item),
        "status": _status_for(item, statuses, default=default_status),
        "technical": _technical(item),
    }


def _participant(value: Any, mention_names: dict[str, str]) -> dict[str, str]:
    if isinstance(value, str):
        return {"name": mention_names.get(value, value), "role": "دور غير محدد"}
    if not isinstance(value, dict):
        return {"name": _text(value) or "غير مسمى", "role": "دور غير محدد"}
    reference = str(value.get("mention_reference") or value.get("mention_id") or "")
    return {
        "name": str(value.get("exact_surface") or value.get("name") or mention_names.get(reference) or reference or "غير مسمى"),
        "role": arabic_label(value.get("role"), fallback="دور غير محدد"),
    }


def _event_card(
    item: dict[str, Any],
    statuses: dict[str, tuple[str, list[str]]],
    default_status: str,
    mention_names: dict[str, str],
) -> dict[str, Any]:
    places = []
    for place in _as_list(item.get("places")):
        if isinstance(place, dict):
            places.append(
                {
                    "name": str(place.get("exact_surface") or place.get("name") or place.get("mention_reference") or "غير مسمى"),
                    "role": arabic_label(place.get("role"), fallback="موقع"),
                }
            )
        else:
            places.append({"name": _text(place), "role": "موقع"})
    institutions = [
        _text(value) for value in _as_list(item.get("institutions") or item.get("offices")) if _text(value)
    ]
    temporal = [
        _text(value) for value in _as_list(item.get("temporal_links") or item.get("temporal_expression")) if _text(value)
    ]
    return {
        "kind": "event",
        "event_type": arabic_label(item.get("event_type") or item.get("type"), fallback="حدث تاريخي محتمل"),
        "evidence": _span_text(item),
        "participants": [_participant(value, mention_names) for value in _as_list(item.get("participants"))],
        "places": places,
        "institutions": institutions,
        "temporal": temporal,
        "status": _status_for(item, statuses, default=default_status),
        "technical": _technical(item),
    }


def _relation_card(
    item: dict[str, Any],
    statuses: dict[str, tuple[str, list[str]]],
    default_status: str,
    mention_names: dict[str, str],
) -> dict[str, Any]:
    subject = str(item.get("subject") or item.get("subject_mention") or "غير مسمى")
    object_ = str(item.get("object") or item.get("object_mention") or "غير مسمى")
    subject = mention_names.get(subject, subject)
    object_ = mention_names.get(object_, object_)
    predicate = item.get("predicate") or item.get("relation_type")
    explicit = item.get("explicit_or_inferred")
    return {
        "kind": "relation",
        "sentence": f"{subject} — {arabic_label(predicate, fallback='صلة تاريخية')} — {object_}",
        "evidence": _span_text(item),
        "explicitness": arabic_label(explicit, fallback="لم يحدد المصدر نوع العلاقة") if explicit else "لم يحدد المصدر نوع العلاقة",
        "status": _status_for(item, statuses, default=default_status),
        "technical": _technical(item),
    }


def _temporal_card(
    item: dict[str, Any],
    statuses: dict[str, tuple[str, list[str]]],
    default_status: str,
) -> dict[str, Any]:
    expression = str(item.get("exact_expression") or item.get("expression") or item.get("temporal_expression") or "عبارة زمنية غير مسماة")
    calendar = item.get("calendar") if item.get("calendar_explicit", bool(item.get("calendar"))) else ""
    return {
        "kind": "temporal",
        "expression": expression,
        "precision": arabic_label(item.get("precision") or item.get("temporal_precision"), fallback="درجة دقة غير محددة"),
        "relative_reference": str(item.get("relative_reference") or ""),
        "calendar": arabic_label(calendar, fallback="") if calendar else "",
        "evidence": _span_text(item),
        "status": _status_for(item, statuses, default=default_status),
        "technical": _technical(item),
    }


def _isnad_card(
    item: dict[str, Any],
    statuses: dict[str, tuple[str, list[str]]],
    default_status: str,
) -> dict[str, Any]:
    narrators = []
    for narrator in _as_list(item.get("ordered_narrators") or item.get("narrators")):
        narrators.append(_text(narrator) or "راوٍ غير مسمى")
    return {
        "kind": "isnad",
        "narrators": narrators,
        "chain_text": _span_text(item),
        "matn_boundary": _text(item.get("matn_boundary") or item.get("matn_range")),
        "ambiguities": [str(value) for value in _as_list(item.get("ambiguous_transitions") or item.get("ambiguities"))],
        "status": _status_for(item, statuses, default=default_status),
        "technical": _technical(item),
    }


def _claim_card(
    item: dict[str, Any],
    statuses: dict[str, tuple[str, list[str]]],
    default_status: str,
) -> dict[str, Any]:
    proposition = str(item.get("proposition") or item.get("normalized_claim") or item.get("original_text") or "ادعاء غير مسمى")
    attribution = item.get("speaker_or_source") or item.get("attribution") or item.get("source_attribution_chain") or ""
    mode = item.get("claim_modality") or item.get("modality") or ""
    quote_type = ""
    if item.get("quoted_or_authorial"):
        quote_type = arabic_label(item.get("quoted_or_authorial"), fallback="نسبة غير محددة")
    return {
        "kind": "claim",
        "proposition": proposition,
        "attribution": _text(attribution),
        "quote_type": quote_type,
        "modality": arabic_label(mode, fallback="درجة إثبات غير محددة") if mode else "",
        "evidence": _span_text(item),
        "status": _status_for(item, statuses, default=default_status),
        "technical": _technical(item),
    }


def _message_card(item: dict[str, Any], *, warning: bool) -> dict[str, Any]:
    codes = _as_list(item.get("reason_codes") or item.get("code"))
    return {
        "kind": "warning" if warning else "rejected",
        "message": "; ".join(
            arabic_label(code, fallback="تحتاج هذه النتيجة إلى مراجعة بشرية")
            for code in codes
        ) or ("تحذير يحتاج مراجعة" if warning else "عنصر مرفوض لعدم كفاية الدليل"),
        "status": {
            "code": item.get("status", "HUMAN_REVIEW_REQUIRED"),
            "label": arabic_label(item.get("status"), fallback="يحتاج مراجعة"),
            "reasons": [],
        },
        "technical": _technical(item),
    }


def _source_collections(source: str, payload: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    if source == "model":
        return {
            "entities": _as_list(payload.get("mentions", {}).get("entities")),
            "events": _as_list(payload.get("events_relations", {}).get("events")),
            "relations": _as_list(payload.get("events_relations", {}).get("relations")),
            "temporal_mentions": _as_list(payload.get("claims_attribution", {}).get("temporals")),
            "isnad": _as_list(payload.get("claims_attribution", {}).get("isnads")),
            "claims_attribution": _as_list(payload.get("claims_attribution", {}).get("claims")),
        }
    if source == "human":
        return {
            "entities": _as_list(payload.get("gold_entities")),
            "events": _as_list(payload.get("gold_events")),
            "relations": _as_list(payload.get("gold_relations")),
            "temporal_mentions": _as_list(payload.get("gold_temporal_mentions")),
            "isnad": _as_list(payload.get("gold_isnad")),
            "claims_attribution": _as_list(payload.get("gold_claims_attribution")),
        }
    return {
        "entities": _as_list(payload.get("entities")),
        "events": _as_list(payload.get("events")),
        "relations": _as_list(payload.get("relations")),
        "temporal_mentions": _as_list(payload.get("temporal_mentions")),
        "isnad": _as_list(payload.get("isnad_chains")),
        "claims_attribution": _as_list(payload.get("claims")),
    }


def build_source_view(
    source: str,
    payload: dict[str, Any],
    *,
    reconciliation: dict[str, Any],
    validation: dict[str, Any],
    rejected: Iterable[dict[str, Any]] = (),
    warnings: Iterable[dict[str, Any]] = (),
) -> dict[str, Any]:
    """Return cards suitable for display; never mutate a storage payload."""

    status_index = _status_index(reconciliation, validation)
    default = "HUMAN_REVIEW_REQUIRED" if source != "reconciled" else "REJECTED_UNSUPPORTED"
    collections = _source_collections("model" if source == "reconciled" else source, payload)
    mention_names = {
        _item_id(item): str(item.get("exact_surface") or item.get("normalized_surface_form") or item.get("surface") or "")
        for item in collections["entities"]
        if _item_id(item)
    }
    builders = {
        "entities": lambda item: _entity_card(item, status_index, default),
        "events": lambda item: _event_card(item, status_index, default, mention_names),
        "relations": lambda item: _relation_card(item, status_index, default, mention_names),
        "temporal_mentions": lambda item: _temporal_card(item, status_index, default),
        "isnad": lambda item: _isnad_card(item, status_index, default),
        "claims_attribution": lambda item: _claim_card(item, status_index, default),
    }
    categories = []
    for key in CATEGORY_ORDER[:6]:
        cards = [builders[key](item) for item in collections[key] if isinstance(item, dict)]
        categories.append(
            {
                "key": key,
                "label": CATEGORY_LABELS[key],
                "empty_message": "لا توجد عناصر مستخرجة في هذه الفئة",
                "items": cards,
            }
        )
    categories.extend(
        [
            {
                "key": "rejected_elements",
                "label": CATEGORY_LABELS["rejected_elements"],
                "empty_message": "لا توجد عناصر مستخرجة في هذه الفئة",
                "items": [_message_card(item, warning=False) for item in rejected if isinstance(item, dict)],
            },
            {
                "key": "warnings",
                "label": CATEGORY_LABELS["warnings"],
                "empty_message": "لا توجد عناصر مستخرجة في هذه الفئة",
                "items": [_message_card(item, warning=True) for item in warnings if isinstance(item, dict)],
            },
        ]
    )
    return {
        "source": source,
        "categories": categories,
        "technical": payload,
    }


def build_presentation_view(
    annotation: dict[str, Any],
    comparison: dict[str, Any],
) -> dict[str, Any]:
    """Build the four explicit, human-readable comparison tabs."""

    baseline = comparison.get("baseline", {})
    model = comparison.get("model_raw", {})
    reconciliation = comparison.get("reconciliation", {})
    validation = comparison.get("validation", {})
    rejected = comparison.get("rejected_elements", {}).get("items", [])
    warnings = comparison.get("warnings", {}).get("items", [])
    return {
        "default_tab": "reconciled",
        "tabs": {
            "baseline": build_source_view(
                "baseline",
                baseline,
                reconciliation=reconciliation,
                validation=validation,
            ),
            "model": build_source_view(
                "model",
                model,
                reconciliation=reconciliation,
                validation=validation,
            ),
            "reconciled": build_source_view(
                "reconciled",
                model,
                reconciliation=reconciliation,
                validation=validation,
                rejected=rejected,
                warnings=warnings,
            ),
            "human": build_source_view(
                "human",
                annotation,
                reconciliation={},
                validation={},
            ),
        },
        "technical": {
            "segment_id": annotation.get("segment_id"),
            "source_id": annotation.get("source_id"),
            "locator": annotation.get("locator"),
            "comparison": comparison,
        },
    }


__all__ = [
    "CATEGORY_LABELS",
    "CATEGORY_ORDER",
    "arabic_label",
    "build_presentation_view",
    "build_source_view",
]
