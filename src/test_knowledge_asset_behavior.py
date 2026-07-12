from src.core.knowledge_asset import KnowledgeAsset
from src.domain.knowledge_objects.entity import Person
from src.domain.knowledge_objects.source import Source

asset = KnowledgeAsset(title="Battle of Badr")
asset.add_source(Source(title="Sahih Muslim"))
asset.add_entity(Person(name="Muhammad", arabic_name="Ù…Ø­Ù…Ø¯ ï·º"))

print(asset.summary())


