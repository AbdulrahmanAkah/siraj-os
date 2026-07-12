from dataclasses import dataclass, field
from typing import Dict
from uuid import uuid4


@dataclass
class Entity:

    entity_id: str = field(default_factory=lambda: str(uuid4()))
    entity_type: str = "Entity"
    name: str = ""
    arabic_name: str = ""

    def to_dict(self) -> Dict[str, object]:
        return {
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "name": self.name,
            "arabic_name": self.arabic_name,
        }


@dataclass
class Person(Entity):
    entity_type: str = "Person"


@dataclass
class Place(Entity):
    entity_type: str = "Place"


@dataclass
class Event(Entity):
    entity_type: str = "Event"


__all__ = [
    "Entity",
    "Person",
    "Place",
    "Event",
]
