
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from src.application.knowledge.extraction_pipeline import ExtractionPipeline

text="""
Battle of Badr happened in 624 CE.
Muhammad commanded Muslim Army.
Muslims defeated Quraysh.
Badr is southwest of Madinah.
Wikipedia states the battle changed history.
"""

pipeline=ExtractionPipeline()
objects=pipeline.run(text)

print("="*70)

for o in objects:
    print(type(o).__name__)
    print(o.metadata)

print("="*70)
print("OBJECTS:",len(objects))


