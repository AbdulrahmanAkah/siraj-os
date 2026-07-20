"""Small, Gemini-compatible response models for the bounded Critical-4 run.

The semantic prompt contracts intentionally remain richer for local providers.
Gemini receives only these route-specific schemas because Gemini Structured
Outputs accepts a documented JSON Schema subset rather than arbitrary schemas.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ValidationError


GEMINI_SCHEMA_VERSION = "siraj-gemini-critical-4-schema-v2"
CRITICAL_ROUTES = (
    "PERSON_AND_STATUS",
    "APPOINTMENT_AND_OFFICE",
    "ISNAD",
    "SIRA_POETRY",
)


class GeminiSchemaError(ValueError):
    """A local response schema cannot safely be sent to Gemini."""


class GeminiUnsupportedSchemaKeyword(GeminiSchemaError):
    def __init__(self, keyword: str, path: str):
        super().__init__(f"GEMINI_UNSUPPORTED_SCHEMA_KEYWORD:{keyword}:{path}")
        self.keyword = keyword
        self.path = path


class GeminiResponseSchemaMismatch(GeminiSchemaError):
    """A JSON response parsed but did not satisfy the selected route model."""


class SpanResponse(BaseModel):
    """Provider quote only; Siraj derives internal offsets deterministically."""

    text: str


class EntityResponse(BaseModel):
    id: str
    surface: str
    types: list[str]
    roles: list[str]
    evidence: SpanResponse
    name_boundary_complete: bool
    explicit_proper_name: bool


class StatusResponse(BaseModel):
    person: str
    status: str
    evidence: SpanResponse


class RelationResponse(BaseModel):
    subject: str
    predicate: str
    object: str
    evidence: SpanResponse


class PersonAndStatusResponse(BaseModel):
    route: str
    entities: list[EntityResponse]
    statuses: list[StatusResponse]
    relations: list[RelationResponse]


class AppointmentResponse(BaseModel):
    kind: str
    appointee: str
    appointing_authority: str
    office: str
    jurisdiction: str
    generic_object: str
    evidence: SpanResponse


class AppointmentAndOfficeResponse(BaseModel):
    route: str
    entities: list[EntityResponse]
    appointments: list[AppointmentResponse]


class IsnadResponse(BaseModel):
    narrators: list[str]
    evidence: SpanResponse
    matn_boundary: int | None


class IsnadRouteResponse(BaseModel):
    route: str
    entities: list[EntityResponse]
    isnads: list[IsnadResponse]


class SiraEventResponse(BaseModel):
    type: str
    explicit: bool
    evidence: SpanResponse


class SiraPoetryResponse(BaseModel):
    route: str
    entities: list[EntityResponse]
    events: list[SiraEventResponse]


_MODELS: dict[str, type[BaseModel]] = {
    "PERSON_AND_STATUS": PersonAndStatusResponse,
    "APPOINTMENT_AND_OFFICE": AppointmentAndOfficeResponse,
    "ISNAD": IsnadRouteResponse,
    "SIRA_POETRY": SiraPoetryResponse,
}

_ALLOWED_KEYS = {
    "type", "properties", "required", "items", "enum", "description",
    "title", "nullable", "$defs", "$ref", "anyOf",
}


def route_response_model(route: str) -> type[BaseModel]:
    try:
        return _MODELS[route]
    except KeyError as error:
        raise GeminiSchemaError(f"GEMINI_ROUTE_SCHEMA_NOT_FOUND:{route}") from error


def _resolve_ref(value: str, root: dict[str, Any], path: str) -> dict[str, Any]:
    if not value.startswith("#/$defs/"):
        raise GeminiUnsupportedSchemaKeyword("$ref", path)
    name = value.rsplit("/", 1)[-1]
    target = root.get("$defs", {}).get(name)
    if not isinstance(target, dict):
        raise GeminiSchemaError(f"GEMINI_UNRESOLVED_SCHEMA_REF:{path}")
    return target


def _nullable_any_of(value: list[Any], root: dict[str, Any], path: str) -> dict[str, Any] | None:
    if len(value) != 2 or not all(isinstance(item, dict) for item in value):
        return None
    normal = [item for item in value if item.get("type") != "null"]
    nulls = [item for item in value if item.get("type") == "null"]
    if len(normal) != 1 or len(nulls) != 1:
        return None
    resolved = _sanitize_node(normal[0], root, path + "/anyOf/0")
    resolved["nullable"] = True
    return resolved


def _sanitize_node(value: Any, root: dict[str, Any], path: str) -> Any:
    if isinstance(value, list):
        return [_sanitize_node(item, root, f"{path}/{index}") for index, item in enumerate(value)]
    if not isinstance(value, dict):
        return value
    if "$ref" in value:
        if len(value) != 1:
            raise GeminiUnsupportedSchemaKeyword("$ref-combination", path)
        return _sanitize_node(_resolve_ref(str(value["$ref"]), root, path), root, path)
    if "anyOf" in value:
        nullable = _nullable_any_of(value["anyOf"], root, path)
        if nullable is None or not set(value).issubset({"anyOf", "title", "description"}):
            raise GeminiUnsupportedSchemaKeyword("anyOf", path)
        for key in ("title", "description"):
            if key in value:
                nullable[key] = value[key]
        return nullable
    result: dict[str, Any] = {}
    for key, item in value.items():
        if key not in _ALLOWED_KEYS:
            raise GeminiUnsupportedSchemaKeyword(key, path)
        if key == "$defs":
            continue
        if key == "properties":
            if not isinstance(item, dict):
                raise GeminiSchemaError(f"GEMINI_SCHEMA_PROPERTIES_INVALID:{path}")
            result[key] = {
                str(name): _sanitize_node(child, root, f"{path}/properties/{name}")
                for name, child in sorted(item.items())
            }
        elif key == "items":
            result[key] = _sanitize_node(item, root, f"{path}/items")
        elif key == "type" and isinstance(item, list):
            non_null = [entry for entry in item if entry != "null"]
            if len(non_null) != 1 or len(non_null) + 1 != len(item):
                raise GeminiUnsupportedSchemaKeyword("type", path)
            result["type"] = non_null[0]
            result["nullable"] = True
        else:
            result[key] = _sanitize_node(item, root, f"{path}/{key}")
    return result


def sanitize_schema_for_gemini(schema: dict[str, Any]) -> dict[str, Any]:
    """Return the supported, dereferenced Gemini Schema subset or fail loudly."""

    if not isinstance(schema, dict):
        raise GeminiSchemaError("GEMINI_SCHEMA_NOT_OBJECT")
    sanitized = _sanitize_node(schema, schema, "$")
    if not isinstance(sanitized, dict):
        raise GeminiSchemaError("GEMINI_SANITIZED_SCHEMA_NOT_OBJECT")
    json.dumps(sanitized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sanitized


def gemini_schema_for_route(route: str) -> dict[str, Any]:
    return sanitize_schema_for_gemini(route_response_model(route).model_json_schema())


def parse_route_response(route: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        result = route_response_model(route).model_validate(payload)
    except ValidationError as error:
        raise GeminiResponseSchemaMismatch("GEMINI_RESPONSE_SCHEMA_MISMATCH") from error
    output = result.model_dump(mode="json")
    if output["route"] != route:
        raise GeminiResponseSchemaMismatch("GEMINI_RESPONSE_SCHEMA_MISMATCH")
    return output


def fixture_for_route(route: str) -> dict[str, Any]:
    evidence = {"text": "أ"}
    entity = {
        "id": "m1", "surface": "أ", "types": ["PERSON"], "roles": [],
        "evidence": evidence, "name_boundary_complete": True,
        "explicit_proper_name": True,
    }
    common = {"route": route, "entities": [entity]}
    if route == "PERSON_AND_STATUS":
        return {**common, "statuses": [], "relations": []}
    if route == "APPOINTMENT_AND_OFFICE":
        return {**common, "appointments": []}
    if route == "ISNAD":
        return {**common, "isnads": []}
    if route == "SIRA_POETRY":
        return {**common, "events": []}
    raise GeminiSchemaError(f"GEMINI_ROUTE_SCHEMA_NOT_FOUND:{route}")


def schema_check() -> dict[str, Any]:
    checks = []
    for route in CRITICAL_ROUTES:
        schema = gemini_schema_for_route(route)
        fixture = fixture_for_route(route)
        parsed = parse_route_response(route, fixture)
        checks.append({
            "route": route,
            "status": "PASS",
            "schema": schema,
            "fixture_round_trip": parsed == fixture,
        })
    return {
        "schema_version": GEMINI_SCHEMA_VERSION,
        "network_called": False,
        "status": "PASS",
        "routes": checks,
    }


__all__ = [
    "CRITICAL_ROUTES", "GEMINI_SCHEMA_VERSION", "GeminiResponseSchemaMismatch",
    "GeminiSchemaError", "GeminiUnsupportedSchemaKeyword", "fixture_for_route",
    "gemini_schema_for_route", "parse_route_response", "route_response_model",
    "sanitize_schema_for_gemini", "schema_check",
]
