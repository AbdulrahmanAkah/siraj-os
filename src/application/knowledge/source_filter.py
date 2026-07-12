
GOOD={

"wikipedia",
"britannica",
"quran",
"sahih muslim",
"sahih bukhari",
"tabari",
"ibn hisham",
"ibn ishaq"

}

BAD={

"muslim",
"people",
"army",
"history"

}

class SourceFilter:

    def apply(self,c):

        n=c.value.get("name","").lower()

        if n in BAD:
            c.reject("false_source")
            return c

        if n not in GOOD:
            c.lower(0.20)

        return c


