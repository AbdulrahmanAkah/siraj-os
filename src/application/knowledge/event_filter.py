
BAD_PREFIX=(
"wikipedia",
"according to",
"states",
"reports",
"claims",
"said",
"says",
"believes",
"mentions"
)

GOOD=(
"battle",
"war",
"siege",
"migration",
"treaty",
"conference",
"earthquake",
"revolution",
"expedition"
)

class EventFilter:

    def apply(self,c):

        text=c.value.get("value","").lower()

        if text.startswith(BAD_PREFIX):
            c.reject("report_sentence")
            return c

        if not any(k in text for k in GOOD):
            c.reject("not_event")
            return c

        c.boost(0.25)

        return c


