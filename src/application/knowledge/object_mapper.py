
from src.domain.knowledge_objects.person import Person
from src.domain.knowledge_objects.location import Location
from src.domain.knowledge_objects.event import Event
from src.domain.knowledge_objects.claim import Claim
from src.domain.knowledge_objects.relationship import Relationship

class ObjectMapper:

    def map(self,c):

        meta=dict(c.metadata)
        meta["confidence"]=c.confidence
        meta["source"]=c.source
        meta["source_reference"]=c.source_reference

        if hasattr(c,"knowledge_score"):
            meta["knowledge_score"]=c.knowledge_score

        if hasattr(c,"quality"):
            meta["quality"]=c.quality

        if c.kind=="PERSON":
            return Person(
                name=c.value,
                aliases=[],
                description="",
                metadata=meta,
                source_reference=c.source_reference
            )

        if c.kind=="ORGANIZATION":
            return Person(
                name=c.value,
                aliases=[],
                description="",
                metadata=meta,
                source_reference=c.source_reference
            )

        if c.kind=="LOCATION":
            return Location(
                name=c.value,
             description=meta.get("original_text", ""), 
               metadata=meta,
                source_reference=c.source_reference
            )

        if c.kind=="EVENT":
            return Event(
                name=c.value,
                description="",
                metadata=meta,
                source_reference=c.source_reference
            )

        if c.kind=="CLAIM":
            return Claim(
                text=c.value,
                metadata=meta,
                source_reference=c.source_reference
            )

        if c.kind=="RELATIONSHIP":
            print(type(c.value))
            print("SUBJECT VALUE:", c.value.get("subject"))
            print("VALUE BEFORE CREATE:", repr(c.value))
            obj = Relationship(
                subject=c.value.get("subject",""),
                predicate=c.value.get("predicate",""),
                object=c.value.get("object",""),
                metadata=meta,
                source_reference=c.source_reference
            )
            print("OBJECT ID:", id(obj))
            print("AFTER CREATE:", repr(obj))
            print("REL MAP:", repr(c.value), "->", repr(obj.subject), repr(obj.predicate), repr(obj.object))
            print("RELATIONSHIP TYPE:", type(obj))
            return obj

            #
        return None


