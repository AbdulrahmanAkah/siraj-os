
class KnowledgeQualityEngine:

    TRUSTED_SOURCES = {

        "quran": 1.00,
        "sahih bukhari": 1.00,
        "sahih muslim": 1.00,
        "bukhari": 1.00,
        "muslim": 1.00,
        "ibn kathir": 0.94,
        "wikipedia": 0.50,

    }

    def _process_object(self, obj):

        md = getattr(obj, "metadata", {}) or {}

        score = float(md.get("confidence", 0.50))

        source = str(md.get("source", "")).lower()

        for trusted_source, trusted_score in self.TRUSTED_SOURCES.items():

            if trusted_source in source:

                score = (score + trusted_score) / 2

                md["trusted_source"] = True

                break

        md["knowledge_score"] = round(score, 3)

        if score >= 0.90:
            md["quality"] = "HIGH"

        elif score >= 0.75:
            md["quality"] = "MEDIUM"

        else:
            md["quality"] = "LOW"

        obj.metadata = md

        return obj

    def process(self, extraction):

        collections = [

            extraction.persons,
            extraction.locations,
            extraction.events,
            extraction.claims,
            extraction.relationships,
            extraction.statistics,
            extraction.timeline,
            extraction.sources,

        ]

        for collection in collections:

            for obj in collection:

                self._process_object(obj)

        return extraction


