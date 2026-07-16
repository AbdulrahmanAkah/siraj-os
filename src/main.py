from src.application.services.knowledge_service import KnowledgeService
from src.domain.knowledge_objects.entity import Person, Place, Event


def main():
    service = KnowledgeService()
    service.register(Person(name="Muhammad", arabic_name="Ù…Ø­Ù…Ø¯ ï·º"))
    service.register(Place(name="Makkah", arabic_name="Ù…ÙƒØ©"))
    service.register(Event(name="Battle of Badr", arabic_name="ØºØ²ÙˆØ© Ø¨Ø¯Ø±"))

    print(service.stats())
    for entity in service.all_entities():
        print(entity.to_dict())


if __name__ == "__main__":
    main()

