"""Evidence-bound historical state materialization for legacy tests only."""

from __future__ import annotations

import json
from pathlib import Path

from src.application.artifact_provenance_v1 import sha256_file
from src.application.episode_transition_ledger_v1 import project_state


EPISODE_002 = "episode-002-adam-temptation-fall-repentance"
PROVIDER_EXECUTION_READY_ENTRY_SHA256 = (
    "9d3b6732c28c0c0fb511e409bdf7e0cb6dc3b337d16b3e479cc6eb4f77b6d1d4"
)
UNFINISHED_PROVIDER_RESULTS_RECEIPT_SHA256 = (
    "405599a26f98d421b36a974f294973ceb658a7381a087ca1a4d0ef5186f2adf2"
)
POST_REJECTION_REPLACEMENT_RESULT = (
    "provider-execution-v1/provider-execution-results-v1/"
    "5c34cca2-fd73-54ee-9c96-5e0e677bdab5.json"
)
POST_REJECTION_REPLACEMENT_RESULT_SHA256 = (
    "0e36b564760079a88d5c819287b0b0f70139a452006ddebb09b9ba930dde0aad"
)
TERMINAL_REJECTION_RECONCILIATION_RECEIPT_SHA256 = (
    "18f590116152c43ea1c4587f3177524cdc65a4ee260a33f8c44035b3b91f623d"
)


def _materialize_jsonl_prefix(
    path: Path,
    *,
    identity_field: str,
    identity_value: str,
) -> None:
    """Truncate a clone to one immutable, uniquely identified ledger prefix."""

    lines = path.read_bytes().splitlines(keepends=True)
    rows = [json.loads(line.decode("utf-8-sig")) for line in lines]
    matches = [
        index
        for index, row in enumerate(rows)
        if str(row.get(identity_field) or "") == identity_value
    ]
    if len(matches) != 1:
        raise AssertionError(
            "HISTORICAL_LEDGER_PREFIX_IDENTITY_REQUIRED:"
            + path.as_posix()
            + ":"
            + identity_value
        )
    path.write_bytes(b"".join(lines[: matches[0] + 1]))


def materialize_ep002_provider_execution_ready(
    root: Path,
    *,
    retain_unfinished_provider_session: bool = False,
) -> None:
    """Restore a clone to the real provider-ready append-only history head."""

    orchestration = root / "projects" / EPISODE_002 / "orchestration"
    _materialize_jsonl_prefix(
        orchestration / "episode-transition-ledger-v1.jsonl",
        identity_field="entry_sha256",
        identity_value=PROVIDER_EXECUTION_READY_ENTRY_SHA256,
    )
    projection = project_state(root, EPISODE_002)
    if projection.current_stage != "PROVIDER_EXECUTION" or projection.status != "READY":
        raise AssertionError("HISTORICAL_PROVIDER_EXECUTION_READY_STATE_INVALID")

    if retain_unfinished_provider_session:
        _materialize_jsonl_prefix(
            orchestration
            / "provider-execution-v1"
            / "provider-execution-stage-receipts-v1.jsonl",
            identity_field="receipt_sha256",
            identity_value=UNFINISHED_PROVIDER_RESULTS_RECEIPT_SHA256,
        )


def exclude_ep002_post_rejection_replacement_result(root: Path) -> None:
    """Exclude one verified later replacement result from a historical clone."""

    result = (
        root
        / "projects"
        / EPISODE_002
        / "orchestration"
        / POST_REJECTION_REPLACEMENT_RESULT
    )
    if not result.is_file():
        raise AssertionError("POST_REJECTION_REPLACEMENT_RESULT_REQUIRED")
    if sha256_file(result) != POST_REJECTION_REPLACEMENT_RESULT_SHA256:
        raise AssertionError("POST_REJECTION_REPLACEMENT_RESULT_HASH_MISMATCH")
    result.unlink()

    _materialize_jsonl_prefix(
        root
        / "projects"
        / EPISODE_002
        / "orchestration"
        / "provider-attempt-reconciliation-v1.jsonl",
        identity_field="receipt_sha256",
        identity_value=TERMINAL_REJECTION_RECONCILIATION_RECEIPT_SHA256,
    )
