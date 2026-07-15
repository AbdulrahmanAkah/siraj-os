
class KnowledgeValidator:

    def extract(self,data):

        if not isinstance(data,list):
            return []

        seen=set()
        out=[]

        for item in data:

            key=str(item)

            if key in seen:
                continue

            seen.add(key)

            if isinstance(item,dict) and item:
                out.append(item)

        return out


