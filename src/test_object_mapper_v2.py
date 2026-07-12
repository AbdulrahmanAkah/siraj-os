
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))

from src.application.knowledge.object_mapper import ObjectMapper

items=[

{"type":"PERSON","value":"Muhammad"},

{"type":"PLACE","value":"Madinah"},

{"type":"EVENT","value":"Battle of Badr"},

{"type":"CLAIM","value":"Muhammad commanded the army."},

{"type":"RELATIONSHIP",
"subject":"Muhammad",
"predicate":"commanded",
"object":"Muslim army"}

]

mapper=ObjectMapper()

objects=mapper.map(items)

print("="*60)

for obj in objects:
    print(type(obj).__name__)
    print(obj)

print("="*60)
print("TOTAL:",len(objects))


