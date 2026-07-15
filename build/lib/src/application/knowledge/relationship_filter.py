
class RelationshipFilter:

    def apply(self,c):

        if not c.value.get("subject"):
            c.reject("missing_subject")

        if not c.value.get("object"):
            c.reject("missing_object")

        return c


