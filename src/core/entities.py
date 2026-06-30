from dataclasses import dataclass, field
from typing import Optional
from uuid import uuid4


@dataclass
class Entity:
    name: str
    arabic_name: Optional[str] = None
    entity_type: str = "Entity"
    entity_id: str = field(default_factory=lambda: str(uuid4()))

    def to_dict(self):
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