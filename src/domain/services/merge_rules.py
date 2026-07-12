from .entity_resolver import EntityResolver

class MergeRules:

    @staticmethod
    def same_person(a,b):
        return EntityResolver.same(a.name,b.name)

    @staticmethod
    def same_location(a,b):
        return EntityResolver.same(a.name,b.name)

    @staticmethod
    def same_event(a,b):
        return EntityResolver.same(a.name,b.name)

    @staticmethod
    def same_claim(a,b):
        return EntityResolver.same(a.text,b.text)

    @staticmethod
    def same_relationship(a,b):
        return (
            EntityResolver.same(a.subject,b.subject)
            and
            EntityResolver.same(a.predicate,b.predicate)
            and
            EntityResolver.same(a.object,b.object)
        )


