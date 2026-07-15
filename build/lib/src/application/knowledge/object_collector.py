from src.application.knowledge.extraction_result import ExtractionResult

from src.domain.knowledge_objects.person import Person
from src.domain.knowledge_objects.location import Location
from src.domain.knowledge_objects.event import Event
from src.domain.knowledge_objects.claim import Claim
from src.domain.knowledge_objects.relationship import Relationship


class ObjectCollector:

    def collect(self, objects):

        extraction = ExtractionResult()

        for obj in objects:

            print("[COLLECT]", type(obj), obj.__class__.__name__)

            if isinstance(obj, Person):
                extraction.persons.append(obj)

            elif isinstance(obj, Location):
                extraction.locations.append(obj)

            elif isinstance(obj, Event):
                extraction.events.append(obj)

            elif isinstance(obj, Claim):
                extraction.claims.append(obj)

            elif isinstance(obj, Relationship):
                extraction.relationships.append(obj)

        print(
            "[SUMMARY]",
            "Persons =", len(extraction.persons),
            "Locations =", len(extraction.locations),
            "Events =", len(extraction.events),
            "Claims =", len(extraction.claims),
            "Relationships =", len(extraction.relationships)
        )

        return extraction

