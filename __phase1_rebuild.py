from pathlib import Path

root=Path("src/application/knowledge")

entity_code=r'''
from .base_extractor import BaseExtractor
from .candidate_models import Candidate
from .rule_engine import RuleEngine

class EntityExtractor(BaseExtractor):

    def __init__(self):
        self.rules=RuleEngine()

    def extract(self,text:str):

        candidates=[]

        for item in self.rules.extract_entities(text):

            candidates.append(
                Candidate(
                    kind=item["type"],
                    value=item["value"],
                    source="entity_extractor",
                    metadata={
                        "extractor":"entity_extractor",
                        "rule":"entity"
                    }
                )
            )

        return candidates
'''

location_code=r'''
from .base_extractor import BaseExtractor
from .candidate_models import Candidate
from .rule_engine import RuleEngine

class LocationExtractor(BaseExtractor):

    def __init__(self):
        self.rules=RuleEngine()

    def extract(self,text:str):

        candidates=[]

        for item in self.rules.extract_locations(text):

            candidates.append(
                Candidate(
                    kind="PLACE",
                    value=item["value"],
                    source="location_extractor",
                    metadata={
                        "extractor":"location_extractor",
                        "rule":"location"
                    }
                )
            )

        return candidates
'''

(root/"entity_extractor.py").write_text(entity_code,encoding="utf8")
(root/"location_extractor.py").write_text(location_code,encoding="utf8")

print("="*70)
print("ENTITY + LOCATION EXTRACTORS REBUILT")
print("="*70)
