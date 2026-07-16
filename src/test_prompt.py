from src.application.models.prompt import Prompt

prompt = Prompt(
    system_prompt="You are an expert documentary writer.",
    user_prompt="Generate a documentary script about the Battle of Badr.",
    language="ar",
    target_model="",
)

print(prompt.to_dict())


