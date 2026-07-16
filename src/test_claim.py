from src.domain.knowledge_objects.claim import Claim

claim = Claim(
    text="The Battle of Badr occurred in the second year after Hijrah."
)

print(claim.to_dict())


