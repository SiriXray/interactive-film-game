from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app  # noqa: E402
from tools import build_manifest  # noqa: E402


MANIFEST_PATH = ROOT / "data" / "tianhe-market-gate.story.json"


class TianheMarketGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        app.app.config["TESTING"] = True
        cls.client = app.app.test_client()
        cls.manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        cls.story = cls.manifest["stories"][0]

    def test_manifest_is_valid_and_keeps_q3_s1_choice_contract(self) -> None:
        self.assertEqual([], build_manifest.validate(self.manifest))
        nodes = self.story["nodes"]
        self.assertEqual(12, sum(node["type"] == "cutscene" for node in nodes.values()))
        self.assertEqual(4, sum(node["type"] == "interactive" for node in nodes.values()))
        self.assertEqual(4, sum(node["type"] == "choice" for node in nodes.values()))

    @patch("app.load_jobs", return_value={})
    def test_story_client_payload_uses_local_manifest_assets_without_jobs(self, _: object) -> None:
        payload = app.sanitize_story_for_client(self.story)
        hero = next(character for character in payload["characters"] if character["id"] == "lu-chen")
        self.assertTrue(hero["asset_url"].startswith("/api/story-assets/tianhe-market-gate/character/lu-chen"))
        self.assertEqual("local", hero["production_state"])
        self.assertTrue(payload["nodes"]["tianhe-market-gate-c1-setup"]["poster_url"].startswith("/api/story-assets/tianhe-market-gate/node/"))
        self.assertTrue(payload["nodes"]["tianhe-market-gate-c1-s1"]["avatar_url"].startswith("/api/story-assets/tianhe-market-gate/portrait/lu-chen"))

    def test_live_start_falls_back_to_local_manifest_portrait(self) -> None:
        provider_response = Mock(status_code=201, content=b"{}")
        provider_response.json.return_value = {"live": {"id": "live-local-story"}, "rtc": {"token": "rtc-token"}}
        with patch("app.get_story", return_value=self.story), patch("app.load_jobs", return_value={}), patch(
            "app.file_data_uri", return_value="data:image/png;base64,bG9jYWwtcG9ydHJhaXQ="
        ), patch("app.api_headers", return_value={}), patch("app.requests.post", return_value=provider_response) as post:
            response = self.client.post("/api/live/start", json={"story_id": "tianhe-market-gate", "node_id": "tianhe-market-gate-c1-s1"})
        self.assertEqual(201, response.status_code)
        avatar = post.call_args.kwargs["json"]["avatar"]
        self.assertEqual("data:image/png;base64,bG9jYWwtcG9ydHJhaXQ=", avatar["image_uri"])
        self.assertEqual("陆沉", avatar["name"])

    def test_character_s1_voice_prefers_explicit_s1_voice(self) -> None:
        self.assertEqual("Tina", app.character_s1_voice({"voice": "Qiao", "s1_voice": "Tina"}))
        self.assertEqual("Sohee", app.character_s1_voice({"voice": "Sohee"}))
        self.assertEqual("Qiao", app.character_s1_voice({}))

    @patch("app.load_jobs", return_value={})
    def test_sanitize_story_for_client_prefers_s1_voice_for_interactive_nodes(self, _: object) -> None:
        story = {
            "id": "voice-routing",
            "title": "音色路由测试",
            "characters": [
                {
                    "id": "heroine",
                    "name": "顾清宁",
                    "role": "离婚悬疑女主",
                    "voice": "Qiao",
                    "s1_voice": "Tina",
                    "asset_path": str(MANIFEST_PATH),
                    "s1_portrait_path": str(MANIFEST_PATH),
                }
            ],
            "nodes": {
                "intro": {
                    "type": "interactive",
                    "avatar_character": "heroine",
                    "chapter": "第一章",
                    "title": "第一次连线",
                    "current_goal": "确认使用 Tina 音色",
                    "forbidden": "不要改写正式分支",
                }
            },
        }
        payload = app.sanitize_story_for_client(story)
        self.assertEqual("Tina", payload["nodes"]["intro"]["voice"])

    def test_live_start_uses_explicit_s1_voice_in_avatar_payload(self) -> None:
        story = {
            "id": "voice-routing",
            "title": "音色路由测试",
            "characters": [
                {
                    "id": "heroine",
                    "name": "顾清宁",
                    "role": "离婚悬疑女主",
                    "voice": "Qiao",
                    "s1_voice": "Tina",
                    "asset_path": str(MANIFEST_PATH),
                    "s1_portrait_path": str(MANIFEST_PATH),
                }
            ],
            "nodes": {
                "intro": {
                    "type": "interactive",
                    "avatar_character": "heroine",
                    "chapter": "第一章",
                    "title": "第一次连线",
                    "current_goal": "确认使用 Tina 音色",
                    "forbidden": "不要改写正式分支",
                }
            },
        }
        provider_response = Mock(status_code=201, content=b"{}")
        provider_response.json.return_value = {"live": {"id": "voice-routing-live"}, "rtc": {"token": "rtc-token"}}
        with patch("app.get_story", return_value=story), patch("app.load_jobs", return_value={}), patch(
            "app.file_data_uri", return_value="data:image/png;base64,cG9ydHJhaXQ="
        ), patch("app.api_headers", return_value={}), patch("app.requests.post", return_value=provider_response) as post:
            response = self.client.post("/api/live/start", json={"story_id": "voice-routing", "node_id": "intro"})
        self.assertEqual(201, response.status_code)
        avatar = post.call_args.kwargs["json"]["avatar"]
        self.assertEqual("Tina", avatar["voice"])


if __name__ == "__main__":
    unittest.main()
