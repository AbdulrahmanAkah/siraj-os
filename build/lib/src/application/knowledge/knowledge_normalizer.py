
class KnowledgeNormalizer:

    MAP={

        "mecca":"Makkah",
        "makkah":"Makkah",
        "medina":"Madinah",
        "madinah":"Madinah",
        "qur'an":"Quran",
        "quran":"Quran"

    }

    def extract(self,data):

        if not isinstance(data,list):
            return []

        out=[]

        for item in data:

            if isinstance(item,dict):

                item=item.copy()

                for k,v in item.items():

                    if isinstance(v,str):

                        item[k]=self.MAP.get(v.lower(),v)

            out.append(item)

        return out


