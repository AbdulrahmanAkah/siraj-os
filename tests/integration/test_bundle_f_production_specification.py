from src.application.documentary_production import DocumentaryProductionRuntime
from src.application.production_contracts import frames_to_milliseconds,milliseconds_to_frames,display_timecode
def test_bundle_f_integer_time_and_deterministic_production_package():
 runtime=DocumentaryProductionRuntime();spec=runtime.specification("production",["scene-b","scene-a"],"ar",20000);first=runtime.build_all(spec,[('scene-b',' Text  B ',['e2']),('scene-a','Text A',['e1'])]);second=runtime.build_all(spec,[('scene-a','Text A',['e1']),('scene-b',' Text  B ',['e2'])])
 assert first[-1]==second[-1] and first[-1].status=="BLOCKED"
 assert frames_to_milliseconds(25)==1000 and milliseconds_to_frames(1000)==25 and display_timecode(0)=="00:00:00.000"
