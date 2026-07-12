
from .alias_dictionary import AliasDictionary


class RelationshipResolver:

    def __init__(self):

        self.aliases = AliasDictionary()


    def resolve(self, graph):

        for relation in graph.relationships:
            print("BEFORE:", repr(relation.subject), repr(relation.object))

            relation.subject = self.aliases.resolve(relation.subject)
            relation.object = self.aliases.resolve(relation.object)
            print("AFTER :", repr(relation.subject), repr(relation.object))

        return graph


