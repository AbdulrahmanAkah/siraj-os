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
        results.extend(self._find(text,PLACES,"LOCATION"))
        results.extend(self._find(text,ORGANIZATIONS,"ORGANIZATION"))

        return results


    def extract_locations(self,text:str):
        return self._find(text,PLACES,"LOCATION")


    def extract_dates(self,text:str):

        return [
            {
                "value":m.group(),
                "confidence":1.0
            }
            for m in YEAR_PATTERN.finditer(text)
        ]


    def extract_events(self,text:str):

        results=[]

        for line in text.splitlines():

            line=line.strip()

            if not line:
                continue

            if any(word in line.lower() for word in EVENT_WORDS):

                results.append({
                    "value":line,
                    "confidence":0.90
                })

        return results


    def extract_claims(self,text:str):

        results=[]

        for line in text.splitlines():

            line=line.strip()

            if not line:
                continue

            if len(line.split())>=4:

                results.append({
                    "value":line,
                    "confidence":0.80
                })

        return results


    def extract_relationships(self,text:str):

        results=[]

        patterns=[
            (" commanded ","commanded"),
            (" defeated ","defeated"),
            (" led ","led"),
            (" founded ","founded"),
            (" is ","is")
        ]

        for line in text.splitlines():

            sentence=line.strip()

            if not sentence:
                continue

            lower=sentence.lower()

            for token,predicate in patterns:

                if token in lower:

                    left,right=sentence.split(token.strip(),1)

                    results.append({
                        "subject":left.strip(),
                        "predicate":predicate,
                        "object":right.strip(),
                        "confidence":0.90
                    })

                    break

        return results


    def extract_sources(self,text:str):

        results=[]

        for name in ("Wikipedia","Bukhari","Muslim","Quran"):

            if name.lower() in text.lower():

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

