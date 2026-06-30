from core.entities import Person, Place, Event
from core.knowledge_engine import KnowledgeEngine

engine = KnowledgeEngine()

engine.register(Person(name="Muhammad", arabic_name="محمد ﷺ"))
engine.register(Place(name="Makkah", arabic_name="مكة"))
engine.register(Event(name="Battle of Badr", arabic_name="غزوة بدر"))

print(engine.stats())

for entity in engine.all_entities():
    print(entity.to_dict())