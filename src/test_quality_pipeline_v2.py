
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))

from src.application.knowledge.extraction_pipeline import ExtractionPipeline

text="""
Battle of Badr happened in 624 CE.
Muhammad commanded Muslim Army.
Muslims defeated Quraysh.
Badr is southwest of Madinah.
Wikipedia states the battle changed history.
"""

pipe=ExtractionPipeline()
objs=pipe.run(text)

print("="*70)

for o in objs:
    print(type(o).__name__,getattr(o,"confidence",None),o)

print("="*70)
print("TOTAL:",len(objs))


