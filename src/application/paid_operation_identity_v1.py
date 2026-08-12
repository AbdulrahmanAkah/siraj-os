"""Canonical identity contract for immutable paid operation requests.

The provider payload hash and the paid-operation identity are related but not
interchangeable values:

* ``provider_payload_sha256`` fingerprints the exact request body sent to a
  provider.
* ``build_paid_operation_identity`` fingerprints the complete immutable
  operation contract, including the provider body and its execution metadata.

Attempt IDs and ``prior_attempt_id`` are deliberately excluded.  A retry is a
new attempt of the same immutable operation and therefore must bind to the
same operation identity while retaining explicit attempt lineage.
"""

from __future__ import annotations

from typing import Any, Mapping

from src.application.artifact_provenance_v1 import canonical_sha256


SCHEMA_VERSION = "siraj-paid-operation-identity-v1"


def provider_payload_sha256(payload: Mapping[str, Any]) -> str:
    """Return the canonical hash of the exact provider request payload."""

    return canonical_sha256(payload)


def build_paid_operation_identity(
    *,
    episode_id: str,
    stage: str,
    operation_type: str,
    provider: str,
    model: str,
    provider_contract_version: str,
    payload: Mapping[str, Any],
    input_artifact_hashes: Mapping[str, str],
    operation_nonce: str | None,
    authorization_mode: str,
) -> str:
    """Build the single identity used for retry binding.

    This function must be called with the final provider payload, before retry
    authorization is resolved and before any gateway persistence.  It does
    not include human authorization documents or attempt lineage because
    those are guards around the operation, not part of the operation itself.
    """

    material = {
        "schema_version": SCHEMA_VERSION,
        "episode_id": episode_id,
        "stage": stage,
        "operation_type": operation_type,
        "provider": provider,
        "model": model,
        "provider_contract_version": provider_contract_version,
        "payload": payload,
        "input_artifact_hashes": dict(sorted(input_artifact_hashes.items())),
        "operation_nonce": operation_nonce,
        "authorization_mode": authorization_mode,
    }
    return canonical_sha256(material)


def canonical_paid_request_identity(**kwargs: Any) -> str:
    """Descriptive alias for callers that use request terminology."""

    return build_paid_operation_identity(**kwargs)
