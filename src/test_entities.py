from core.entities import Person, Place, Event
from core.repositories.entity_repository import EntityRepository

repo = EntityRepository()

repo.add(Person(name="Muhammad", arabic_name="محمد ﷺ"))
repo.add(Place(name="Makkah", arabic_name="مكة"))
repo.add(Event(name="Battle of Badr", arabic_name="غزوة بدر"))

print(f"Entities: {repo.count()}")

for entity in repo.all():
    print(entity.to_dict())