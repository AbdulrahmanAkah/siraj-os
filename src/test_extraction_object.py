from src.application.models.extraction_object import ExtractionObject
from src.domain.knowledge_objects.knowledge_object_type import KnowledgeObjectType


default_object = ExtractionObject()

print(default_object.to_dict())

assert default_object.object_type == KnowledgeObjectType.EVENT
assert default_object.value == {}
assert default_object.confidence == 1.0
assert default_object.metadata == {}

assert default_object.to_dict() == {
    "object_type": KnowledgeObjectType.EVENT.value,
    "value": {},
    "confidence": 1.0,
    "metadata": {},
}


custom_object = ExtractionObject(
    object_type=KnowledgeObjectType.PERSON,
    value={"name": "Muhammad"},
    confidence=0.85,
    metadata={"source": "unit-test"},
)

print(custom_object.to_dict())

assert custom_object.object_type == KnowledgeObjectType.PERSON
assert custom_object.value == {"name": "Muhammad"}
assert custom_object.confidence == 0.85
assert custom_object.metadata == {"source": "unit-test"}

assert custom_object.to_dict() == {
    "object_type": KnowledgeObjectType.PERSON.value,
    "value": {"name": "Muhammad"},
    "confidence": 0.85,
    "metadata": {"source": "unit-test"},
}

print("ExtractionObject OK")


