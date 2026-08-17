from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools import build_rednote_story_bundle  # noqa: E402


class RednoteStoryBundleTests(unittest.TestCase):
    def test_generated_bundle_is_valid(self) -> None:
        manifest = json.loads((ROOT / "data" / "story.json").read_text(encoding="utf-8"))
        self.assertEqual([], build_rednote_story_bundle.validate(manifest))
        self.assertEqual(3, len(manifest["stories"]))

    def test_every_episode_has_q3_s1_and_formal_choice(self) -> None:
        manifest = json.loads((ROOT / "data" / "story.json").read_text(encoding="utf-8"))
        for story in manifest["stories"]:
            nodes = story["nodes"]
            self.assertEqual(6, sum(node["type"] == "cutscene" for node in nodes.values()) // 3)
            self.assertEqual(6, sum(node["type"] == "interactive" for node in nodes.values()))
            self.assertEqual(6, sum(node["type"] == "choice" for node in nodes.values()))
            self.assertTrue(all(len(node["options"]) == 2 for node in nodes.values() if node["type"] == "choice"))


if __name__ == "__main__":
    unittest.main()
