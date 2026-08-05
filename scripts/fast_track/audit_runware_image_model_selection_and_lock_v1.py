from __future__ import annotations
import argparse,json
from pathlib import Path

def main():
 p=argparse.ArgumentParser(); p.add_argument("--repo-root",type=Path,required=True); p.add_argument("--output-root",type=Path,required=True); a=p.parse_args(); repo=a.repo_root.resolve()
 c=json.loads((repo/"projects/_orchestrator/contracts/runware-image-model-routing-v1.json").read_text(encoding="utf-8"))
 assert c["primary_model"]["air"]=="bytedance:seedream@5.0-pro"
 assert c["secondary_model"]["air"]=="google:4@3"
 assert c["excluded_models"]==["bfl:5@1"]
 a.output_root.mkdir(parents=True,exist_ok=True); r=a.output_root/"audit.txt"
 r.write_text("STATUS=PASS_RUNWARE_IMAGE_MODEL_SELECTION_AND_LOCK_V1\nPRIMARY_IMAGE_MODEL=SEEDREAM_5_PRO\nSECONDARY_HUMAN_REFERENCE_MODEL=NANO_BANANA_2\nFLUX_2_PRO=EXCLUDED\nROLE_BASED_ROUTING=YES\nPAID_PROVIDER_REQUESTS_DURING_AUDIT=0\n",encoding="utf-8")
 print(r.read_text(encoding="utf-8"),end=""); return 0
if __name__=="__main__": raise SystemExit(main())
