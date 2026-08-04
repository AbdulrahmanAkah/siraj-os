from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EPISODE = ROOT / "projects" / "episode-001-adam"


class AdamVisualSafetyPolicyV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = json.loads(
            (EPISODE / "cinematic" / "visual-safety-policy-v2.json").read_text(
                encoding="utf-8-sig"
            )
        )
        cls.evidence = json.loads(
            (EPISODE / "evidence" / "visual-safety-human-direction-v2.json").read_text(
                encoding="utf-8-sig"
            )
        )
        cls.binding = json.loads(
            (EPISODE / "contracts" / "visual-safety-policy-binding-v2.json").read_text(
                encoding="utf-8-sig"
            )
        )
        cls.rules = {item["rule_id"]: item for item in cls.policy["rules"]}

    def test_exact_human_direction_hash(self):
        phrase = self.evidence["exact_human_direction_ar"]
        self.assertEqual(
            hashlib.sha256(phrase.encode("utf-8")).hexdigest(),
            self.evidence["exact_human_direction_sha256"],
        )

    def test_no_tabarruj_is_blocking(self):
        self.assertEqual(
            self.rules["NO_TABARRUJ_FOR_WOMEN"]["severity"],
            "BLOCKING",
        )

    def test_hair_is_always_blocked(self):
        self.assertEqual(
            self.rules["WOMEN_HAIR_MUST_REMAIN_COVERED"]["severity"],
            "BLOCKING",
        )
        self.assertIn(
            "الشعر",
            self.rules["WOMEN_LIMITED_EXPOSURE_NECESSITY_ONLY"]["forbidden"],
        )

    def test_hands_feet_and_partial_face_are_narrow_allowances(self):
        self.assertEqual(
            set(
                self.rules["WOMEN_LIMITED_EXPOSURE_NECESSITY_ONLY"][
                    "allowed_only_when_necessary"
                ]
            ),
            {"الكفان", "القدمان", "جزء محدود غير مكتمل من ملامح الوجه"},
        )

    def test_complete_identifiable_face_is_blocked_for_every_character(self):
        rule = self.rules["NO_COMPLETE_IDENTIFIABLE_FACE_FOR_ANY_CHARACTER"]
        self.assertEqual(rule["severity"], "BLOCKING")
        self.assertIn("كل شخصية بشرية", rule["applies_to"])
        self.assertIn("وجه أمامي كامل", rule["rejection"])

    def test_adam_pre_descent_skin_and_face_constraints(self):
        rule = self.rules["ADAM_DEPICTION_CONSTRAINTS"]
        self.assertEqual(
            rule["pre_descent_skin_tone"],
            "DARK_SKIN_CLEARLY_VISIBLE_WHEN_SKIN_IS_SHOWN",
        )
        self.assertEqual(rule["face_rule"], "NO_COMPLETE_IDENTIFIABLE_FACE")

    def test_policy_supersedes_old_zero_skin_interpretation(self):
        legacy = self.binding["legacy_rule_resolution"]
        self.assertIn(
            "HANDS_AND_FEET_ALLOWED_WHEN_NECESSARY",
            legacy["preliminary_policy_zero_female_skin"],
        )

    def test_final_visual_approval_remains_false(self):
        self.assertFalse(self.policy["master_visual_approval"])
        self.assertFalse(self.policy["final_master_visual_approval"])
        self.assertFalse(self.binding["master_visual_approval"])
        self.assertFalse(self.binding["final_master_visual_approval"])


if __name__ == "__main__":
    unittest.main()
