from hashlib import sha256
import json


CANONICAL_CREATED_AT = "1970-01-01T00:00:00Z"


def deterministic_id(prefix, material):
    payload = json.dumps(
        material,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return prefix + "_" + sha256(payload).hexdigest()[:16]


def stable_unique(values):
    return sorted(set(values))


def canonical_trace(
    *,
    source_ids=(),
    evidence_ids=(),
    claim_ids=(),
    event_ids=(),
    reasoning_ids=(),
):
    return {
        "source_ids": stable_unique(source_ids),
        "evidence_ids": stable_unique(evidence_ids),
        "claim_ids": stable_unique(claim_ids),
        "event_ids": stable_unique(event_ids),
        "reasoning_ids": stable_unique(reasoning_ids),
    }


__all__ = [
    "CANONICAL_CREATED_AT",
    "canonical_trace",
    "deterministic_id",
    "stable_unique",
]
