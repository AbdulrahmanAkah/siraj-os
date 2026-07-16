from src.application.models.outline import DocumentaryOutline

outline = DocumentaryOutline(
    title="Battle of Badr",
    introduction="Introduction",
    sections=[
        "Background",
        "Preparation",
        "Battle",
        "Aftermath",
    ],
    conclusion="Legacy",
)

print(outline.to_dict())

assert outline.title == "Battle of Badr"
assert len(outline.sections) == 4
assert outline.sections[2] == "Battle"

print("DocumentaryOutline OK")


