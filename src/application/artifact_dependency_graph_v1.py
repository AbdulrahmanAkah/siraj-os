from __future__ import annotations

import hashlib
import json
from collections import deque
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping


class DependencyGraphError(RuntimeError):
    pass


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_sha256(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_scope_dependency_graph(
    episode_id: str,
    proposal: Mapping[str, Any],
) -> dict[str, Any]:
    events = proposal.get("events")
    if not isinstance(events, list) or not events:
        raise DependencyGraphError("EVENTS_REQUIRED_FOR_DEPENDENCY_GRAPH")

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, str]] = []

    def add_node(node_id: str, kind: str, source_id: str | None = None) -> None:
        nodes.append(
            {
                "node_id": node_id,
                "kind": kind,
                "source_id": source_id,
                "status": "PLANNED",
                "version": 1,
                "artifact_path_relative": None,
                "artifact_sha256": None,
                "invalidated_at_utc": None,
                "invalidation_reason": None,
            }
        )

    def add_edge(parent: str, child: str) -> None:
        edges.append({"from": parent, "to": child})

    scope_id = f"{episode_id}:SCOPE"
    final_id = f"{episode_id}:FINAL_MASTER"
    add_node(scope_id, "TOPIC_SCOPE", str(proposal.get("slug_en", "")))

    for event in events:
        if not isinstance(event, Mapping):
            raise DependencyGraphError("INVALID_EVENT_IN_PROPOSAL")
        event_id = str(event.get("event_id", ""))
        if not event_id:
            raise DependencyGraphError("EVENT_ID_REQUIRED")
        event_node = f"{episode_id}:EVENT:{event_id}"
        evidence_node = f"{episode_id}:EVIDENCE:{event_id}"
        script_node = f"{episode_id}:SCRIPT:{event_id}"
        shot_plan_node = f"{episode_id}:SHOT_PLAN:{event_id}"
        tts_node = f"{episode_id}:TTS:{event_id}"
        sfx_node = f"{episode_id}:SFX:{event_id}"
        timeline_node = f"{episode_id}:TIMELINE:{event_id}"

        add_node(event_node, "EVENT", event_id)
        add_node(evidence_node, "EVIDENCE_PACKAGE", event_id)
        add_node(script_node, "SCRIPT_SEGMENT", event_id)
        add_node(shot_plan_node, "SHOT_PLAN", event_id)
        add_node(tts_node, "TTS_SEGMENT", event_id)
        add_node(sfx_node, "SFX_SEGMENT", event_id)
        add_node(timeline_node, "TIMELINE_RANGE", event_id)

        add_edge(scope_id, event_node)
        add_edge(event_node, evidence_node)
        add_edge(evidence_node, script_node)
        add_edge(script_node, shot_plan_node)
        add_edge(script_node, tts_node)
        add_edge(shot_plan_node, sfx_node)
        add_edge(shot_plan_node, timeline_node)
        add_edge(tts_node, timeline_node)
        add_edge(sfx_node, timeline_node)
        add_edge(timeline_node, final_id)

    add_node(final_id, "FINAL_MASTER", episode_id)
    graph = {
        "schema_version": "siraj-artifact-dependency-graph-v1",
        "episode_id": episode_id,
        "status": "ACTIVE",
        "created_at_utc": _now_utc(),
        "updated_at_utc": _now_utc(),
        "nodes": nodes,
        "edges": edges,
        "partial_rebuild_policy": {
            "regenerate_only_invalidated_nodes_and_downstream_dependents": True,
            "preserve_unaffected_paid_assets": True,
            "final_master_may_be_reexported_without_regenerating_valid_assets": True,
        },
    }
    graph["graph_sha256"] = canonical_sha256(graph)
    return graph


def _node_index(graph: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    nodes = graph.get("nodes")
    if not isinstance(nodes, list):
        raise DependencyGraphError("GRAPH_NODES_REQUIRED")
    index: dict[str, dict[str, Any]] = {}
    for node in nodes:
        if not isinstance(node, dict):
            raise DependencyGraphError("INVALID_GRAPH_NODE")
        node_id = str(node.get("node_id", ""))
        if not node_id or node_id in index:
            raise DependencyGraphError("INVALID_OR_DUPLICATE_NODE_ID")
        index[node_id] = node
    return index


def _children(graph: Mapping[str, Any]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    edges = graph.get("edges")
    if not isinstance(edges, list):
        raise DependencyGraphError("GRAPH_EDGES_REQUIRED")
    for edge in edges:
        if not isinstance(edge, Mapping):
            raise DependencyGraphError("INVALID_GRAPH_EDGE")
        parent = str(edge.get("from", ""))
        child = str(edge.get("to", ""))
        if not parent or not child:
            raise DependencyGraphError("GRAPH_EDGE_ENDPOINT_REQUIRED")
        result.setdefault(parent, set()).add(child)
    return result


def downstream_nodes(
    graph: Mapping[str, Any],
    changed_node_ids: Iterable[str],
) -> tuple[str, ...]:
    index = _node_index(graph)
    children = _children(graph)
    queue: deque[str] = deque()
    visited: set[str] = set()
    for node_id in changed_node_ids:
        value = str(node_id)
        if value not in index:
            raise DependencyGraphError(f"UNKNOWN_CHANGED_NODE:{value}")
        queue.append(value)
    while queue:
        current = queue.popleft()
        if current in visited:
            continue
        visited.add(current)
        for child in sorted(children.get(current, set())):
            queue.append(child)
    return tuple(sorted(visited))


def invalidate_nodes(
    graph: dict[str, Any],
    changed_node_ids: Iterable[str],
    reason: str,
) -> dict[str, Any]:
    invalidated = downstream_nodes(graph, changed_node_ids)
    index = _node_index(graph)
    timestamp = _now_utc()
    for node_id in invalidated:
        node = index[node_id]
        node["status"] = "INVALIDATED_REBUILD_REQUIRED"
        node["invalidated_at_utc"] = timestamp
        node["invalidation_reason"] = reason.strip() or "USER_REQUESTED_CHANGE"
    graph["updated_at_utc"] = timestamp
    graph["last_invalidation"] = {
        "changed_node_ids": sorted(str(item) for item in changed_node_ids),
        "invalidated_node_ids": list(invalidated),
        "reason": reason.strip() or "USER_REQUESTED_CHANGE",
        "created_at_utc": timestamp,
    }
    graph.pop("graph_sha256", None)
    graph["graph_sha256"] = canonical_sha256(graph)
    return graph


def rebuild_plan(graph: Mapping[str, Any]) -> dict[str, Any]:
    nodes = _node_index(graph)
    invalidated = [
        node_id
        for node_id, node in nodes.items()
        if node.get("status") == "INVALIDATED_REBUILD_REQUIRED"
    ]
    kinds: dict[str, int] = {}
    for node_id in invalidated:
        kind = str(nodes[node_id].get("kind", "UNKNOWN"))
        kinds[kind] = kinds.get(kind, 0) + 1
    return {
        "schema_version": "siraj-partial-rebuild-plan-v1",
        "episode_id": graph.get("episode_id"),
        "status": "REBUILD_REQUIRED" if invalidated else "NO_REBUILD_REQUIRED",
        "invalidated_node_ids": sorted(invalidated),
        "invalidated_kind_counts": dict(sorted(kinds.items())),
        "preserve_other_nodes": True,
        "regenerate_entire_episode": False,
        "created_at_utc": _now_utc(),
    }
