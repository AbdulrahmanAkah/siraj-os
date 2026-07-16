from .extraction_result import ExtractionResult
from src.domain.knowledge_objects.person import Person
from src.domain.knowledge_objects.location import Location
from src.domain.knowledge_objects.event import Event
from src.domain.knowledge_objects.claim import Claim
from src.domain.knowledge_objects.relationship import Relationship

from .merge_rules import MergeRules
from .extraction_result import ExtractionResult

class ObjectMerger:

    def merge(self, extraction: ExtractionResult):

        def merge_list(items, checker):
            merged=[]
            for obj in items:
                duplicate=False
                for existing in merged:
                    if checker(obj, existing):
                        duplicate=True
                        break
                if not duplicate:
                    merged.append(obj)
            return merged

        extraction.persons = merge_list(extraction.persons, MergeRules.same_person)
        extraction.locations = merge_list(extraction.locations, MergeRules.same_location)
        extraction.events = merge_list(extraction.events, MergeRules.same_event)
        extraction.claims = merge_list(extraction.claims, MergeRules.same_claim)
        extraction.relationships = merge_list(extraction.relationships, MergeRules.same_relationship)

        return extraction


