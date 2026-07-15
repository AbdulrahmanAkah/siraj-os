from dataclasses import asdict, is_dataclass
from hashlib import sha256
import json

CANONICAL_TIMESTAMP = "1970-01-01T00:00:00Z"

def _normalise(value):
    if is_dataclass(value):
        return _normalise(asdict(value))
    if isinstance(value, dict):
        return {str(key): _normalise(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, (list, tuple)):
        return [_normalise(item) for item in value]
    if isinstance(value, set):
        return sorted((_normalise(item) for item in value), key=lambda item: repr(item))
    return value

def canonical_payload(value):
    return json.dumps(_normalise(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)

def integrity_hash(value):
    return sha256(canonical_payload(value).encode("utf-8")).hexdigest()

def deterministic_id(prefix, material):
    return prefix + "_" + integrity_hash(material)[:16]

def stable_unique(values):
    return sorted(set(values))

def canonical_trace(**values):
    return {key: stable_unique(value) for key, value in sorted(values.items())}

def canonical_version_metadata(subject_id, version="v1"):
    return {"subject_id": subject_id, "version": version, "schema": "operations-v1"}
