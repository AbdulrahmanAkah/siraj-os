from src.application.models.documentary.script import Script

script = Script(
    title="Battle of Badr",
    introduction="A short introduction to the battle.",
    body="The main content of the documentary script.",
    conclusion="A closing summary.",
    citations=["Sahih Muslim", "Ibn Hisham"],
    language="ar",
    metadata={"source": "test"},
)

print(script.to_dict())


