
class ClaimFilter:

    def apply(self,c):

        t=c.value.get("value","")

        if len(t.split())<4:
            c.reject("too_short")

        if "?" in t:
            c.reject("question")

        return c


