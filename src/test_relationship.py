from src.domain.knowledge_objects.entity import Person
from src.domain.knowledge_objects.relationship import Relationship

relationship = Relationship(
    subject="Muhammad",
    predicate="participated_in",
    object="Battle of Badr",
)
print(relationship.to_dict())


