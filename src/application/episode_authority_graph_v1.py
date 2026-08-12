"""Versioned authority/dependency graph for post-TTS episode artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from src.application.artifact_provenance_v1 import artifact_reference, canonical_sha256


SCHEMA_VERSION = "siraj-episode-authority-graph-v1"
AUTHORITY_ORDER = (
    "FINAL_TTS_AUDIO",
    "AUDIO_TIMELINE",
    "AUDIO_BOUND_STORYBOARD",
    "CREATIVE_OVERLAY",
    "PROVIDER_PLAN",
)


class EpisodeAuthorityGraphError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class AuthorityNode:
    name: str
    artifact_path: Path
    schema_version: str
    depends_on: tuple[str, ...]
    dependency_hashes: Mapping[str, str]

    def reference(self, repo_root: Path) -> dict[str, object]:
        value = artifact_reference(self.artifact_path, base=repo_root)
        value.update({
            "authority_name": self.name,
            "schema_version": self.schema_version,
            "depends_on": list(self.depends_on),
            "dependency_hashes": dict(self.dependency_hashes),
        })
        return value


def validate_graph(nodes: Sequence[AuthorityNode], repo_root: Path) -> dict[str, object]:
    names = [node.name for node in nodes]
    if names != list(AUTHORITY_ORDER):
        raise EpisodeAuthorityGraphError("AUTHORITY_ORDER_INVALID")
    known: dict[str, str] = {}
    references = []
    for node in nodes:
        if not node.artifact_path.is_file():
            raise EpisodeAuthorityGraphError("AUTHORITY_ARTIFACT_MISSING:" + node.name)
        for dependency in node.depends_on:
            if dependency not in known:
                raise EpisodeAuthorityGraphError("AUTHORITY_DEPENDENCY_NOT_PRIOR:" + dependency)
            if node.dependency_hashes.get(dependency) != known[dependency]:
                raise EpisodeAuthorityGraphError("AUTHORITY_DEPENDENCY_HASH_MISMATCH:" + node.name)
        reference = node.reference(repo_root)
        known[node.name] = str(reference["sha256"])
        references.append(reference)
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "PASS",
        "nodes": references,
        "graph_sha256": canonical_sha256(references),
        "structural_rebuild_requires_explicit_proposal": True,
    }


def structural_rebuild_proposal(
    *, episode_id: str, reason: str, current_graph_sha256: str,
    affected_authorities: Sequence[str],
) -> dict[str, object]:
    if not reason.strip() or not affected_authorities:
        raise EpisodeAuthorityGraphError("STRUCTURAL_REBUILD_REASON_AND_SCOPE_REQUIRED")
    return {
        "schema_version": "siraj-structural-rebuild-proposal-v1",
        "status": "PROPOSED_NOT_AUTHORIZED",
        "episode_id": episode_id,
        "reason": reason,
        "current_graph_sha256": current_graph_sha256,
        "affected_authorities": list(affected_authorities),
        "automatic_execution": False,
        "explicit_human_approval_required": True,
    }
