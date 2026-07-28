from pathlib import Path
import hashlib,json,unittest
P=Path(__file__).resolve().parents[1]/"projects/episode-001-adam/evidence/gap-human-approval-v1.json"
class T(unittest.TestCase):
 def setUp(self): self.d=json.loads(P.read_text(encoding="utf-8-sig"))
 def test_human(self): self.assertTrue(self.d["human_approval"]); self.assertEqual(self.d["approved_by"],"Abdulrahman Akah")
 def test_scope(self): self.assertFalse(self.d["scope"]["opens_evidence_gate"]); self.assertFalse(self.d["scope"]["all_episode_evidence_approved"])
 def test_text(self): self.assertIn("لا تُحذف افتراضيًا",self.d["approval_text"]); self.assertIn("شجرة جميلة جذابة",self.d["approval_text"])
 def test_hash(self): self.assertEqual(self.d["approval_text_sha256"],hashlib.sha256(self.d["approval_text"].encode()).hexdigest())
 def test_events(self): self.assertEqual([x["event_id"] for x in self.d["decisions"]],["EV-ADAM-031","EV-ADAM-071","EV-ADAM-091"])
 def test_blocked(self): self.assertEqual(self.d["live_provider_execution"],"BLOCKED")
if __name__=="__main__": unittest.main()
