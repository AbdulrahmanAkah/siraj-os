from application.models.content_specification import ContentSpecification
from application.services.knowledge_context_builder import KnowledgeContextBuilder
from application.services.prompt_builder import PromptBuilder
from application.services.script_structure_builder import ScriptStructureBuilder
from application.services.siraj_engine import SirajEngine
from core.knowledge_asset import KnowledgeAsset
from domain.claims.claim import Claim
from domain.entities.entity import Person
from domain.sources.source import Source

asset = KnowledgeAsset(title="Battle of Badr", description="First major battle")
asset.add_entity(Person(name="Muhammad", arabic_name="محمد ﷺ"))
asset.add_source(Source(title="Sahih Muslim"))
asset.add_claim(Claim(text="The Battle of Badr occurred in the second year after Hijrah."))

outline = SirajEngine().build_outline(asset)
context = KnowledgeContextBuilder().build(outline)
script_structure = ScriptStructureBuilder().build(outline)
specification = ContentSpecification(
    platform="youtube",
    language="ar",
    style="documentary",
    target_audience="general",
    duration_minutes=12,
    tone="professional",
    include_citations=True,
)
prompt = PromptBuilder().build(context, script_structure, specification)
print(prompt.to_dict())
