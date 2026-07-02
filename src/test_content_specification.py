from application.models.content_specification import ContentSpecification

spec = ContentSpecification(
    platform="youtube",
    language="ar",
    style="documentary",
    target_audience="general",
    duration_minutes=12,
    tone="professional",
    include_citations=True,
)

print(spec.to_dict())
