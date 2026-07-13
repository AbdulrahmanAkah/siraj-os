import re
import logging
from dataclasses import asdict
from hashlib import sha256

from .canonicalizer import Canonicalizer
from .alias_dictionary import AliasDictionary

from src.domain.knowledge_graph.knowledge_graph import KnowledgeGraph
from src.domain.knowledge_graph.knowledge_node import KnowledgeNode
from src.domain.knowledge_graph.knowledge_edge import KnowledgeEdge

logger = logging.getLogger(__name__)


class GraphBuilder:

    def build(self, extractions):

        if not isinstance(extractions, list):
            extractions = [extractions]

        graph = KnowledgeGraph()
        aliases = AliasDictionary()
        typed_node_types = {
            "PERSON",
            "ORGANIZATION",
            "LOCATION",
            "EVENT",
            "SOURCE",
            "CLAIM",
            "ENTITY",
        }

        def stable_id(prefix, *values):
            identity = "\x00".join(
                Canonicalizer.normalize_text(str(value)) for value in values
            )
            return f"{prefix}_{sha256(identity.encode('utf-8')).hexdigest()[:16]}"

        def add(obj, node_type, node_id):
            data = obj.to_dict() if hasattr(obj, "to_dict") else asdict(obj)
            logger.debug(
                "NODE ADD:\nid=%s\ntype=%s\nname=%s",
                node_id,
                node_type,
                data.get("name") or data.get("title") or data.get("text") or data.get("value", ""),
            )
            graph.add_node(
                KnowledgeNode(
                    id=node_id,
                    type=node_type,
                    data=data,
                )
            )

        def find_existing_identity(identity):
            identities = {
                Canonicalizer.normalize_text(identity),
                Canonicalizer.normalize_text(aliases.resolve(identity)),
            }

            for node in graph.nodes:
                if node.type not in typed_node_types:
                    continue

                node_id = Canonicalizer.normalize_text(node.id)
                if node_id in identities:
                    return node

                data = node.data if isinstance(node.data, dict) else {}
                for key in ("name", "title", "text", "value"):
                    node_name = Canonicalizer.normalize_text(data.get(key, ""))
                    if node_name in identities:
                        return node
                    if Canonicalizer.normalize_text(aliases.resolve(data.get(key, ""))) in identities:
                        return node

            return None

        def resolve_endpoint(identity):
            existing = find_existing_identity(identity)
            return existing.id if existing is not None else identity

        def add_fallback_entity(identity, original):
            existing = find_existing_identity(identity)
            if existing is not None:
                logger.debug(
                    "Skipped ENTITY creation: name=%s matched_existing=%s:%s",
                    original,
                    existing.type,
                    existing.id,
                )
                return existing.id

            resolved = resolve_endpoint(identity)
            if resolved != identity:
                logger.debug(
                    "Skipped ENTITY creation: name=%s matched_existing_id=%s",
                    original,
                    resolved,
                )
                return resolved

            logger.debug(
                "Creating fallback ENTITY: name=%s reason=no_match",
                original,
            )
            logger.debug(
                "NODE ADD:\nid=%s\ntype=ENTITY\nname=%s",
                identity,
                original,
            )
            graph.add_node(
                KnowledgeNode(
                    id=identity,
                    type="ENTITY",
                    data={"name": original},
                )
            )
            return identity

        for extraction_index, extraction in enumerate(extractions):

            for x in extraction.persons:
                metadata = getattr(x, "metadata", {}) or {}
                entity_type = (
                    metadata.get("entity_kind", "PERSON")
                    if isinstance(metadata, dict)
                    else "PERSON"
                )
                add(x, entity_type, Canonicalizer.canonical_name(x.name))

            for x in extraction.events:
                add(x, "EVENT", Canonicalizer.normalize_text(x.name))

            for x in extraction.locations:
                add(x, "LOCATION", Canonicalizer.canonical_name(x.name))

            for i, x in enumerate(extraction.claims):
                node_id = x.claim_id or stable_id("claim", x.text)
                x.claim_id = node_id
                add(x, "CLAIM", node_id)

            for i, x in enumerate(extraction.statistics):
                add(x, "STATISTIC", stable_id("statistic", x.value, x.unit))

            for i, x in enumerate(extraction.timeline):
                add(x, "TIMELINE_EVENT", stable_id("timeline", x.title, x.date))

            for i, x in enumerate(extraction.sources):
                add(x, "SOURCE", x.source_id or f"source_{extraction_index}_{i}")

            for i, x in enumerate(extraction.documents):
                add(x, "DOCUMENT", x.document_id or f"document_{extraction_index}_{i}")

            for i, x in enumerate(extraction.evidence):
                add(x, "EVIDENCE", x.evidence_id or f"evidence_{extraction_index}_{i}")

            for x in extraction.claim_evidence:
                graph.add_edge(
                    KnowledgeEdge(
                        source=x.claim_id,
                        target=x.evidence_id,
                        relation="supported_by",
                        metadata={"confidence": x.confidence, **x.metadata},
                    )
                )

            for x in extraction.evidence:
                graph.add_edge(
                    KnowledgeEdge(
                        source=x.evidence_id,
                        target=x.document_id,
                        relation="located_in",
                    )
                )

            for x in extraction.documents:
                if x.source_id:
                    graph.add_edge(
                        KnowledgeEdge(
                            source=x.document_id,
                            target=x.source_id,
                            relation="originates_from",
                        )
                    )

            for x in extraction.claims:
                for source_id in x.source_ids:
                    graph.add_edge(
                        KnowledgeEdge(
                            source=x.claim_id,
                            target=source_id,
                            relation="attributed_to",
                            metadata={"confidence": x.confidence},
                        )
                    )

            for r in extraction.relationships:
                source = Canonicalizer.normalize_text(r.subject)
                target = Canonicalizer.normalize_text(r.object)
                relation_metadata = {}

                target_date = re.match(r"(.+) in (\d{3,4})$", target)
                if target_date:
                    candidate_target = target_date.group(1).strip()
                    existing_target = find_existing_identity(candidate_target)
                    if existing_target is not None:
                        target = existing_target.id
                        relation_metadata["date"] = target_date.group(2)

                source = add_fallback_entity(source, r.subject)
                target = add_fallback_entity(target, r.object)

                if "date" not in relation_metadata:
                    for node in graph.nodes:
                        if node.type != "TIMELINE_EVENT":
                            continue

                        data = node.data if isinstance(node.data, dict) else {}
                        title = Canonicalizer.normalize_text(data.get("title", ""))
                        if source in title and target in title and data.get("date"):
                            relation_metadata["date"] = data["date"]
                            break

                graph.add_edge(
                    KnowledgeEdge(
                        source=source,
                        target=target,
                        relation=Canonicalizer.normalize_text(r.predicate),
                        metadata=relation_metadata,
                    )
                )

        typed_types = typed_node_types - {"ENTITY"}

        def node_name(node):
            data = node.data if isinstance(node.data, dict) else {}
            return (
                data.get("name")
                or data.get("title")
                or data.get("text")
                or data.get("value")
                or node.id
            )

        def identity_keys(node):
            data = node.data if isinstance(node.data, dict) else {}
            values = [node.id]
            values.extend(data.get(key, "") for key in ("name", "title", "text", "value"))
            keys = set()
            for value in values:
                if not value:
                    continue
                keys.add(Canonicalizer.normalize_text(value))
                keys.add(Canonicalizer.normalize_text(aliases.resolve(value)))
            keys.discard("")
            return keys

        def find_typed_duplicate(entity):
            entity_keys = identity_keys(entity)
            for candidate in graph.nodes:
                if candidate.type not in typed_types:
                    continue
                if entity_keys.intersection(identity_keys(candidate)):
                    return candidate
            return None

        def dump_nodes(label):
            print(label)
            for node in graph.nodes:
                print(f"id={node.id}")
                print(f"type={node.type}")
                print(f"name={node_name(node)}")

        dump_nodes("=== BEFORE CLEANUP ===")
        before_cleanup_count = len(graph.nodes)
        removal_ids = set()

        for node in graph.nodes:
            if node.type != "ENTITY":
                continue
            match = find_typed_duplicate(node)
            if match is None:
                continue

            logger.debug(
                "Removing duplicate ENTITY: %s:%s matched_existing=%s:%s",
                node.type,
                node.id,
                match.type,
                match.id,
            )
            removal_ids.add(id(node))

            for edge in graph.edges:
                if edge.source == node.id:
                    edge.source = match.id
                if edge.target == node.id:
                    edge.target = match.id

            for relationship in graph.relationships:
                if relationship.subject == node.id:
                    relationship.subject = match.id
                if relationship.object == node.id:
                    relationship.object = match.id

        if removal_ids:
            graph.nodes = [node for node in graph.nodes if id(node) not in removal_ids]

        logger.debug(
            "ENTITY cleanup node count: before=%s after=%s",
            before_cleanup_count,
            len(graph.nodes),
        )
        dump_nodes("=== AFTER CLEANUP ===")

        graph.refresh()

        duplicate_entities = [
            node
            for node in graph.nodes
            if node.type == "ENTITY" and find_typed_duplicate(node) is not None
        ]
        assert not duplicate_entities, (
            "GraphBuilder final invariant failed; duplicate ENTITY nodes remain: "
            + ", ".join(node.id for node in duplicate_entities)
        )

        dump_nodes("=== RETURN GRAPH ===")
        return graph


__all__ = ["GraphBuilder"]
