
STOP={
"the",
"a",
"an",
"this",
"that",
"these",
"those"
}

class EntityFilter:

    def apply(self,c):

        name=c.value.get("value","")

        if not name:
            c.reject("empty")
            return c

        if name.lower() in STOP:
            c.reject("stopword")
            return c

        if len(name)<2:
            c.reject("tiny")

        return c


