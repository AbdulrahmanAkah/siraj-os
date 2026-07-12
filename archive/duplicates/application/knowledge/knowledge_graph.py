from dataclasses import dataclass, field
from typing import Any

@dataclass
class KnowledgeGraph:

    persons: dict[str, Any] = field(default_factory=dict)
    locations: dict[str, Any] = field(default_factory=dict)
    events: dict[str, Any] = field(default_factory=dict)
    claims: dict[str, Any] = field(default_factory=dict)

    relationships: list[Any] = field(default_factory=list)
    edges: list[dict] = field(default_factory=list)

    def add_node(self, category: str, key: str, node: Any):
        getattr(self, category)[key] = node

    def add_edge(self, source: str, predicate: str, target: str):
        self.edges.append({
            "source": source,
            "predicate": predicate,
            "target": target
        })

    def find_node(self, category: str, key: str):
        return getattr(self, category).get(key)

    def neighbors(self, key: str):
        return [
            e for e in self.edges
            if e["source"] == key or e["target"] == key
        ]

    def export_dict(self):
        return {
            "persons": self.persons,
            "locations": self.locations,
            "events": self.events,
            "claims": self.claims,
            "relationships": self.relationships,
            "edges": self.edges,
        }


