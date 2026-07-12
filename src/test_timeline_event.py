from src.domain.knowledge_objects.timeline_event import TimelineEvent

# Default construction
empty_event = TimelineEvent()
print(empty_event.to_dict())
assert empty_event.title == ""
assert empty_event.description == ""
assert empty_event.date == ""
assert empty_event.location == ""
assert empty_event.confidence == 1.0
assert empty_event.metadata == {}
assert empty_event.to_dict() == {
    "title": "",
    "description": "",
    "date": "",
    "location": "",
    "confidence": 1.0,
    "metadata": {},
}

# Populated construction
event = TimelineEvent(
    title="Battle of Badr",
    description="The first major battle of Islam.",
    date="624-03-13",
    location="Badr",
    confidence=0.95,
    metadata={"source": "historical"},
)
print(event.to_dict())
assert event.title == "Battle of Badr"
assert event.description == "The first major battle of Islam."
assert event.date == "624-03-13"
assert event.location == "Badr"
assert event.confidence == 0.95
assert event.metadata == {"source": "historical"}
assert event.to_dict() == {
    "title": "Battle of Badr",
    "description": "The first major battle of Islam.",
    "date": "624-03-13",
    "location": "Badr",
    "confidence": 0.95,
    "metadata": {"source": "historical"},
}


