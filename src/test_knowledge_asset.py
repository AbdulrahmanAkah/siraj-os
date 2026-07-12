from src.core.knowledge_asset import KnowledgeAsset

asset = KnowledgeAsset(
    title="Battle of Badr",
    description="First major battle in Islam",
    topic="Islamic History",
)

print(asset.to_dict())

