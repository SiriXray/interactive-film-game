from __future__ import annotations

import sys
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app  # noqa: E402
from tools import build_manifest  # noqa: E402


class InteractiveFilmAppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        app.app.config["TESTING"] = True
        cls.client = app.app.test_client()

    def test_manifest_graph_is_valid(self) -> None:
        manifest = app.load_stories()
        self.assertEqual(2, manifest["manifest_version"])
        self.assertEqual([], build_manifest.validate(manifest))
        story_ids = [story["id"] for story in manifest["stories"]]
        self.assertIn("family-classmates-rewind", story_ids)
        self.assertGreaterEqual(len(manifest["stories"]), 9)

    def test_all_manifest_nodes_are_reachable_from_each_story_start(self) -> None:
        for story in app.load_stories()["stories"]:
            visited: set[str] = set()
            queue = [story["start"]]
            while queue:
                node_id = queue.pop()
                if node_id in visited:
                    continue
                visited.add(node_id)
                node = story["nodes"][node_id]
                if node["type"] in {"cutscene", "interactive"}:
                    queue.append(node["next"])
                elif node["type"] == "choice":
                    queue.extend(option["next"] for option in node["options"])
            self.assertEqual(set(story["nodes"]), visited, story["id"])

    def test_every_cutscene_is_fifteen_seconds_from_three_q3_clips(self) -> None:
        for story in app.load_stories()["stories"]:
            for node in story["nodes"].values():
                if node["type"] != "cutscene":
                    continue
                plan = node["render_plan"]
                self.assertEqual(15, plan["target_seconds"])
                self.assertEqual(3, len(plan["clips"]))
                self.assertEqual(15, sum(clip["duration"] for clip in plan["clips"]))
                self.assertTrue({clip["model"] for clip in plan["clips"]}.issubset(app.ALLOWED_VIDEO_MODELS))

    def test_manifest_counts_match_the_fmv_and_s1_production_contract(self) -> None:
        stories = app.load_stories()["stories"]
        nodes = [node for story in stories for node in story["nodes"].values()]
        cutscenes = sum(node["type"] == "cutscene" for node in nodes)
        interactives = sum(node["type"] == "interactive" for node in nodes)
        choices = sum(node["type"] == "choice" for node in nodes)
        endings = sum(node["type"] == "ending" for node in nodes)
        self.assertEqual(cutscenes, choices * 3)
        self.assertEqual(interactives, choices)
        self.assertEqual(endings, len(stories))

    def test_family_classmates_rewind_story_wires_local_assets_and_four_s1_nodes(self) -> None:
        story = app.get_story("family-classmates-rewind")
        self.assertEqual("campus-rebirth", story["skin"])
        self.assertEqual("campus", story["palette"])
        self.assertEqual("陆星辰", story["hero"])
        live_nodes = [node for node in story["nodes"].values() if node["type"] == "interactive"]
        self.assertEqual(4, len(live_nodes))
        self.assertTrue(all(len(node["live_directives"]) >= 3 for node in live_nodes))
        main_family = {character["id"]: character for character in story["characters"] if character["id"] in {"lu-xingchen", "young-lu-mingchuan", "young-xu-tang"}}
        self.assertEqual({"lu-xingchen", "young-lu-mingchuan", "young-xu-tang"}, set(main_family))
        self.assertTrue(all("D:\\AI剧\\角色人物图" in character["asset_path"] for character in main_family.values()))
        self.assertEqual("Ryan", main_family["lu-xingchen"]["s1_voice"])
        self.assertEqual("Andre", main_family["young-lu-mingchuan"]["s1_voice"])
        self.assertEqual("Tina", main_family["young-xu-tang"]["s1_voice"])

    def test_s1_voice_aliases_convert_legacy_voice_names(self) -> None:
        self.assertEqual("Ryan", app.character_s1_voice({"voice": "Juniper"}))
        self.assertEqual("Harvey", app.character_s1_voice({"voice": "Atlas"}))
        self.assertEqual("Andre", app.character_s1_voice({"voice": "Dylan"}))
        self.assertEqual("Tina", app.character_s1_voice({"voice": "Qiao"}))

    def test_family_classmates_rewind_client_payload_exposes_local_story_asset_routes(self) -> None:
        response = self.client.get("/api/stories/family-classmates-rewind")
        self.assertEqual(200, response.status_code)
        story = response.get_json()
        self.assertEqual("campus-rebirth", story["skin"])
        hero = next(character for character in story["characters"] if character["id"] == "lu-xingchen")
        self.assertTrue(hero["asset_url"].startswith(("/api/story-assets/family-classmates-rewind/character/", "/generated/assets/family-classmates-rewind/")))
        live_node = story["nodes"]["family-classmates-rewind-c1-s1"]
        self.assertTrue(live_node["avatar_url"].startswith(("/api/story-assets/family-classmates-rewind/portrait/", "/generated/assets/family-classmates-rewind/")))
        self.assertTrue(live_node["poster_url"].startswith("/api/story-assets/family-classmates-rewind/node/"))

    def test_zero_hour_link_covers_the_three_s1_gameplay_patterns(self) -> None:
        story = app.get_story("zero-hour-link")
        self.assertEqual("sci-fi-apocalypse", story["skin"])
        live_nodes = [node for node in story["nodes"].values() if node["type"] == "interactive"]
        self.assertEqual(3, len(live_nodes))
        self.assertEqual(
            {"静默指挥 / 复合动作", "情绪共调 / 心理干预", "高压谈判 / 语气识别"},
            {node["interaction_mode"] for node in live_nodes},
        )
        self.assertTrue(all(len(node["live_directives"]) >= 3 for node in live_nodes))

    def test_zero_hour_link_s1_persona_includes_its_action_contract(self) -> None:
        story = app.get_story("zero-hour-link")
        node = app.get_node(story, "zero-hour-link-c1-s1")
        persona = app.s1_persona(story, node, {"state": story["initial_state"], "choices": []})
        self.assertIn(node["interaction_mode"], persona)
        self.assertIn(node["live_directives"][0], persona)
        self.assertIn("不得把自由对话说成已经改变了正式分支结果", persona)

    @patch("app.request_task")
    def test_image_generation_uses_viduimage_2_text_to_image_payload(self, request_task: object) -> None:
        story = app.get_story("snow-border")
        character = app.get_character(story, "shen-zhihe")
        app.submit_image_job(story, character)
        request_task.assert_called_once()  # type: ignore[attr-defined]
        endpoint, payload = request_task.call_args.args  # type: ignore[attr-defined]
        self.assertEqual("/ent/v2/reference2image", endpoint)
        self.assertEqual("viduimage-2", payload["model"])
        self.assertEqual([], payload["images"])
        self.assertEqual("9:16", payload["aspect_ratio"])
        self.assertEqual("2K", payload["resolution"])
        self.assertEqual("high", payload["quality"])

    @patch("app.request_task")
    @patch("app.file_data_uri", return_value="data:image/png;base64,c2FmZS1yZWZlcmVuY2U=")
    def test_s1_portrait_uses_a_dedicated_16_by_9_reference_image(self, _: object, request_task: object) -> None:
        story = app.get_story("snow-border")
        character = app.get_character(story, "shen-zhihe")
        app.submit_s1_portrait_job(story, character, ROOT / "generated" / "assets" / "snow-border" / "shen-zhihe.png")
        request_task.assert_called_once()  # type: ignore[attr-defined]
        endpoint, payload = request_task.call_args.args  # type: ignore[attr-defined]
        self.assertEqual("/ent/v2/reference2image", endpoint)
        self.assertEqual("viduimage-2", payload["model"])
        self.assertEqual("16:9", payload["aspect_ratio"])
        self.assertEqual(["data:image/png;base64,c2FmZS1yZWZlcmVuY2U="], payload["images"])
        self.assertIn("face and shoulders fully visible", payload["prompt"])
        self.assertIn("no cropped head", payload["prompt"])

    def test_story_client_payload_hides_generation_prompts(self) -> None:
        response = self.client.get("/api/stories/snow-border")
        self.assertEqual(200, response.status_code)
        story = response.get_json()
        self.assertTrue(all("image_prompt" not in character for character in story["characters"]))
        for node in story["nodes"].values():
            self.assertNotIn("render_plan", node)

    def test_production_requires_explicit_confirmation(self) -> None:
        response = self.client.post("/api/production/images/submit", json={})
        self.assertEqual(400, response.status_code)
        self.assertIn("confirm", response.get_json()["error"])

    def test_resume_worker_requires_explicit_confirmation(self) -> None:
        response = self.client.post("/api/production/resume", json={})
        self.assertEqual(400, response.status_code)
        self.assertIn("confirm", response.get_json()["error"])

    @patch("app.s1_portrait_path", return_value=None)
    def test_s1_requires_a_generated_16_by_9_portrait_before_network_call(self, _: object) -> None:
        response = self.client.post("/api/live/start", json={"story_id": "snow-border", "node_id": "snow-border-c1-s1"})
        self.assertEqual(400, response.status_code)
        self.assertIn("16:9", response.get_json()["error"])

    def test_s1_live_payload_uses_the_dedicated_portrait_uri(self) -> None:
        provider_response = Mock(status_code=201, content=b"{}")
        provider_response.json.return_value = {"live": {"id": "live-test"}, "rtc": {"token": "token"}}
        with patch("app.s1_portrait_path", return_value=ROOT / "generated" / "assets" / "snow-border" / "shen-zhihe" / "s1.png"), patch(
            "app.file_data_uri", return_value="data:image/png;base64,czEtcG9ydHJhaXQ="
        ), patch("app.api_headers", return_value={}), patch("app.requests.post", return_value=provider_response) as post:
            response = self.client.post("/api/live/start", json={"story_id": "snow-border", "node_id": "snow-border-c1-s1"})
        self.assertEqual(201, response.status_code)
        avatar = post.call_args.kwargs["json"]["avatar"]
        self.assertEqual("data:image/png;base64,czEtcG9ydHJhaXQ=", avatar["image_uri"])
        self.assertEqual("沈知禾", avatar["name"])

    def test_pending_remote_task_count_includes_s1_portraits(self) -> None:
        with patch("app.load_jobs", return_value={
            "image": {"kind": "image", "state": "success", "story_id": "snow-border"},
            "s1": {"kind": "s1-image", "state": "processing", "story_id": "snow-border"},
            "clip": {"kind": "clip", "state": "queueing", "story_id": "zero-hour-link"},
            "movie": {"kind": "movie", "state": "pending"},
        }):
            self.assertEqual(2, app.pending_remote_task_count())
            self.assertEqual(1, app.pending_remote_task_count([{"id": "snow-border"}]))

    def test_production_resume_persists_confirmed_scope(self) -> None:
        with patch("app.save_autopilot") as save_autopilot, patch("app.start_production_worker", return_value=True), patch("app.load_autopilot", return_value={"enabled": True, "scope": "selected", "story_ids": ["zero-hour-link"]}):
            response = self.client.post("/api/production/resume", json={"confirm": True, "story_ids": ["zero-hour-link"]})
        self.assertEqual(202, response.status_code)
        save_autopilot.assert_called_once_with(("zero-hour-link",))

    def test_console_live_payload_forwards_s1_capabilities(self) -> None:
        provider_response = Mock(status_code=201, content=b"{}")
        provider_response.json.return_value = {"live": {"id": "console-live"}, "rtc": {"token": "rtc-token", "user_id": "user"}}
        body = {
            "persona": "你是温和、专业的产品顾问。",
            "image_uri": "https://assets.example.com/avatar.png",
            "name": "顾问 Tina",
            "voice": "Tina",
            "greeting_instruction": "自然问候用户并询问今天最想解决的问题。",
            "call_mode": "video",
            "audio": {"enable_transcription": True},
            "extra_motion": True,
            "vad": {"type": "server", "threshold": 0.45, "silence_duration_ms": 400, "idle_timeout_ms": 6000},
            "llm": {"temperature": 0.8, "top_p": 0.85, "top_k": 24, "frequency_penalty": 1, "presence_penalty": 0.3, "seed": -1, "max_tokens": 120},
            "idle_timeout_seconds": 600,
            "memory_retrieval": {"enabled": True, "endpoint": "https://memory.example.com/search", "authorization": "Bearer memory-secret", "timeout_ms": 2500},
            "knowledge_retrieval": {"enabled": True, "endpoint": "https://knowledge.example.com/search", "authorization": "Bearer knowledge-secret", "timeout_ms": 3000},
        }
        with patch("app.api_headers", return_value={}), patch("app.requests.post", return_value=provider_response) as post:
            response = self.client.post("/api/console/live/start", json=body)
        self.assertEqual(201, response.status_code)
        payload = post.call_args.kwargs["json"]
        self.assertEqual("顾问 Tina", payload["avatar"]["name"])
        self.assertEqual(body["greeting_instruction"], payload["avatar"]["greeting_instruction"])
        self.assertTrue(payload["audio"]["enable_transcription"])
        self.assertTrue(payload["extra_motion"])
        self.assertEqual(6000, payload["vad"]["idle_timeout_ms"])
        self.assertEqual("https://memory.example.com/search", payload["memory_retrieval"]["endpoint"])
        self.assertEqual(120, payload["llm"]["max_tokens"])

    def test_console_live_retrieval_requires_authorization_before_provider_call(self) -> None:
        body = {
            "persona": "专业顾问",
            "image_uri": "https://assets.example.com/avatar.png",
            "memory_retrieval": {"enabled": True, "endpoint": "https://memory.example.com/search"},
        }
        with patch("app.requests.post") as post:
            response = self.client.post("/api/console/live/start", json=body)
        self.assertEqual(400, response.status_code)
        self.assertIn("authorization", response.get_json()["error"])
        post.assert_not_called()

    def test_console_transcripts_store_only_sanitized_entries(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(app, "CONSOLE_TRANSCRIPT_DIR", Path(temp_dir)):
            response = self.client.post(
                "/api/console/transcripts",
                json={
                    "live_id": "console-live",
                    "entries": [
                        {"speaker": "user", "text": "请介绍一下这个方案", "event_at_ms": 1700000000000, "seq_id": 7},
                        {"speaker": "avatar", "text": "我会先梳理你的目标。", "latency_ms": 840, "authorization": "should-not-persist"},
                    ],
                },
            )
            self.assertEqual(201, response.status_code)
            transcript_file = Path(temp_dir) / "console-live.jsonl"
            rows = [json.loads(line) for line in transcript_file.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(2, len(rows))
        self.assertEqual("user", rows[0]["speaker"])
        self.assertNotIn("authorization", rows[1])
        self.assertEqual(840, rows[1]["latency_ms"])

    def test_console_transcripts_reject_path_like_live_id(self) -> None:
        response = self.client.post("/api/console/transcripts", json={"live_id": "../secrets", "entry": {"speaker": "user", "text": "x"}})
        self.assertEqual(400, response.status_code)


if __name__ == "__main__":
    unittest.main()
