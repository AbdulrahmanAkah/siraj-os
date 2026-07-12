from abc import ABC, abstractmethod


class EntityRepository(ABC):

    @abstractmethod
    def save(self, entity):
        pass

    @abstractmethod
    def find(self, entity_id):
        pass
