import re

PERSONS={
    "muhammad","abu bakr","umar","uthman","ali"
}

PLACES={
    "makkah","mecca","madinah","medina","badr","uhud"
}

ORGANIZATIONS={
    "muslims",
    "quraysh",
    "muslim army",
}

EVENT_WORDS={
    "battle","war","expedition","siege","migration","treaty"
}

EVENT_ENTITIES={
    "badr",
}

YEAR_PATTERN=re.compile(r"\b\d{3,4}\b")


class RuleEngine:

    def _find(self,text,items,kind):
        results=[]
        lower=text.lower()

        for item in items:
            if item in lower:
                results.append({
                    "kind":kind,
                    "value":item.title(),
                    "confidence":0.95
                })

        return results


    def extract_entities(self,text:str):

        results=[]

        results.extend(self._find(text,PERSONS,"PERSON"))
        results.extend(self._find(text,EVENT_ENTITIES,"EVENT"))
        results.extend(self._find(text,PLACES - EVENT_ENTITIES,"LOCATION"))
        results.extend(self._find(text,ORGANIZATIONS,"ORGANIZATION"))

        return results


    def extract_locations(self,text:str):
        return self._find(text,PLACES,"LOCATION")


    def extract_dates(self,text:str):
        results=[]

        for sentence in re.split(r"(?<=[.!?])\s+|\n+", text):
            sentence=sentence.strip()

            if not sentence:
                continue

            match=YEAR_PATTERN.search(sentence)

            if match:
                results.append({
                    "value":match.group(),
                    "title":sentence.rstrip(".!?"),
                    "confidence":1.0
                })

        return results


    def extract_events(self,text:str):

        results=[]

        for line in re.split(r"(?<=[.!?])\s+|\n+", text):

            line=line.strip()

            if not line:
                continue

            if any(word in line.lower() for word in EVENT_WORDS) or "participated in" in line.lower():

                results.append({
                    "value":line,
                    "confidence":0.90
                })

        return results


    def extract_claims(self,text:str):

        results=[]

        for line in re.split(r"(?<=[.!?])\s+|\n+", text):

            line=line.strip()

            if not line:
                continue

            if len(line.split())>=4 and not line.lower().startswith("the source is "):

                results.append({
                    "value":line,
                    "confidence":0.80
                })

        return results


    def extract_relationships(self,text:str):

        results=[]

        patterns=[
            (" traveled to ","traveled_to"),
            (" participated in ","participated_in"),
            (" opposed ","opposed"),
            (" commanded ","commanded"),
            (" defeated ","defeated"),
            (" led ","led"),
            (" founded ","founded"),
            (" is ","is")
        ]

        for line in re.split(r"(?<=[.!?])\s+|\n+", text):

            sentence=line.strip()

            if not sentence:
                continue

            lower=sentence.lower()

            if re.match(r"^\s*the source is\b", sentence, re.I):
                continue

            for token,predicate in patterns:

                if token in lower:

                    left,right=sentence.lower().split(token.strip(),1)

                    left=sentence[:sentence.lower().find(token.strip())]
                    right=sentence[sentence.lower().find(token.strip()) + len(token.strip()):]

                    subject=left.strip()
                    object_value=right.strip()

                    if predicate == "traveled_to":
                        object_value=re.sub(r"\s+in\s+\d{3,4}$", "", object_value, flags=re.I)

                    object_value=re.sub(r"^the\s+", "", object_value, flags=re.I)

                    results.append({
                        "subject":subject,
                        "predicate":predicate,
                        "object":object_value,
                        "confidence":0.90
                    })

                    break

        return results


    def extract_sources(self,text:str):

        results=[]

        source_match=re.search(r"the source is\s+([^.!?]+)",text,re.I)

        if source_match:
            results.append({
                "name":source_match.group(1).strip(),
                "confidence":1.0
            })

        for name in ("Wikipedia","Bukhari","Muslim","Quran"):

            if name.lower() in text.lower() and not source_match:

                results.append({
                    "name":name,
                    "confidence":0.95
                })

        return results


    def extract_evidence(self,text:str):

        results=[]

        for line in text.splitlines():

            line=line.strip()

            if not line:
                continue

            score=0

            if YEAR_PATTERN.search(line):
                score+=2

            if any(x in line.lower() for x in PERSONS):
                score+=1

            if any(x in line.lower() for x in PLACES):
                score+=1

            results.append({
                "text":line,
                "score":score,
                "confidence":min(1.0,0.50+score*0.15)
            })

        return results

