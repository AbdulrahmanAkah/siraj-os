from application.models.content_specification import ContentSpecification
from application.services.generation_service import GenerationService
from application.services.knowledge_context_builder import KnowledgeContextBuilder
from application.services.knowledge_organizer import KnowledgeOrganizer
from application.services.narrative_planner import NarrativePlanner
from application.services.prompt_builder import PromptBuilder
from application.services.siraj_engine import SirajEngine
from core.knowledge_asset import KnowledgeAsset
from domain.claims.claim import Claim
from domain.entities.entity import Person
from domain.sources.source import Source
from infrastructure.llm.mock_llm_provider import MockLLMProvider
from domain.relationships.relationship import Relationship

asset = KnowledgeAsset(title="Battle of Badr", description="First major battle")
asset.add_entity(Person(name="Muhammad", arabic_name="محمد ﷺ"))
asset.add_source(Source(title="Sahih Muslim"))
asset.add_claim(Claim(text="The Battle of Badr occurred in the second year after Hijrah."))
asset.add_relationship(
    Relationship(subject="Muhammad", predicate="participated_in", object="Battle of Badr")
)

outline = SirajEngine().build_outline(asset)
context = KnowledgeContextBuilder().build(outline)
organized = KnowledgeOrganizer().build(context, relationships=asset.relationships)
plan = NarrativePlanner().build(organized)
specification = ContentSpecification(
    platform="youtube",
    language="ar",
    style="documentary",
    target_audience="general",
    duration_minutes=12,
    tone="professional",
    include_citations=True,
)
prompt = PromptBuilder().build(plan, specification)
provider = MockLLMProvider()
service = GenerationService(provider)
script = service.generate(prompt)
print(script.to_dict())
