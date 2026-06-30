from application.services.knowledge_service import KnowledgeService
from domain.entities.entity import Person, Place, Event


def main():
    service = KnowledgeService()
    service.register(Person(name="Muhammad", arabic_name="محمد ﷺ"))
    service.register(Place(name="Makkah", arabic_name="مكة"))
    service.register(Event(name="Battle of Badr", arabic_name="غزوة بدر"))

    print(service.stats())
    for entity in service.all_entities():
        print(entity.to_dict())


if __name__ == "__main__":
    main()