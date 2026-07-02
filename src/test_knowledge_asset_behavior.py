from core.knowledge_asset import KnowledgeAsset
from domain.entities.entity import Person
from domain.sources.source import Source

asset = KnowledgeAsset(title="Battle of Badr")
asset.add_source(Source(title="Sahih Muslim"))
asset.add_entity(Person(name="Muhammad", arabic_name="محمد ﷺ"))

print(asset.summary())
