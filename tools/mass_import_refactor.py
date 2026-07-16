from pathlib import Path

REPLACEMENTS = {

    "from application.": "from src.application.",
    "import application.": "import src.application.",

    "from core.": "from src.core.",
    "import core.": "import src.core.",

    "from infrastructure.": "from src.infrastructure.",
    "import infrastructure.": "import src.infrastructure.",

    "from domain.": "from src.domain.",
    "import domain.": "import src.domain.",

}

count = 0

for file in Path("src").rglob("*.py"):

    text = file.read_text(encoding="utf8")

    original = text

    for old,new in REPLACEMENTS.items():
        text=text.replace(old,new)

    if text!=original:
        file.write_text(text,encoding="utf8")
        count+=1
        print(file)

print()
print("FILES UPDATED:",count)