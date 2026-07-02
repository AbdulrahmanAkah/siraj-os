from domain.entities.entity import Person
from domain.relationships.relationship import Relationship

relationship = Relationship(
    subject="Muhammad",
    predicate="participated_in",
    object="Battle of Badr",
)
print(relationship.to_dict())
