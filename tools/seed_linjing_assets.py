"""Seed the Lin Jin story with existing local character assets.

This avoids resubmitting character reference images when the user already has
approved assets on disk. It does not submit paid Vidu tasks.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STORY_ID = "linjin-swordbone"
IMPORT_STORY = ROOT / "data" / "imports" / f"{STORY_ID}.story.json"
JOBS_FILE = ROOT / "data" / "production-jobs.json"
GENERATED_ASSETS = ROOT / "generated" / "assets" / STORY_ID


def public_asset(path: Path) -> str:
    return "/generated/" + path.resolve().relative_to((ROOT / "generated").resolve()).as_posix()


def load_json(path: Path, fallback: dict) -> dict:
    if not path.exists():
        return fallback
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return fallback
    return data if isinstance(data, dict) else fallback


def make_s1_portrait(source: Path, destination: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not ffmpeg:
        shutil.copy2(source, destination)
        return
    command = [
        ffmpeg,
        "-y",
        "-i",
        str(source),
        "-vf",
        "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=black",
        "-frames:v",
        "1",
        str(destination),
    ]
    subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main() -> int:
    story = load_json(IMPORT_STORY, {})
    source_assets = story.get("source_assets")
    if not isinstance(source_assets, dict):
        raise RuntimeError("linjin-swordbone source_assets missing")
    jobs = load_json(JOBS_FILE, {})
    now = int(time.time())
    for character_id, source_text in source_assets.items():
        source = Path(str(source_text))
        if not source.exists():
            raise FileNotFoundError(source)
        character_dir = GENERATED_ASSETS / character_id
        character_dir.mkdir(parents=True, exist_ok=True)
        image_path = GENERATED_ASSETS / f"{character_id}{source.suffix.lower()}"
        s1_path = character_dir / f"s1{source.suffix.lower()}"
        shutil.copy2(source, image_path)
        make_s1_portrait(source, s1_path)

        image_id = f"image:{STORY_ID}:{character_id}"
        jobs[image_id] = {
            "id": image_id,
            "kind": "image",
            "story_id": STORY_ID,
            "character_id": character_id,
            "task_id": "local-import",
            "state": "success",
            "created_at": now,
            "updated_at": now,
            "media_url": public_asset(image_path),
            "remote_url": "",
            "error": "",
            "source": "local-existing-asset",
        }

        s1_id = f"s1-image:{STORY_ID}:{character_id}"
        jobs[s1_id] = {
            "id": s1_id,
            "kind": "s1-image",
            "story_id": STORY_ID,
            "character_id": character_id,
            "task_id": "local-import",
            "state": "success",
            "created_at": now,
            "updated_at": now,
            "media_url": public_asset(s1_path),
            "remote_url": "",
            "error": "",
            "source": "local-existing-asset-16x9",
        }
    JOBS_FILE.write_text(json.dumps(jobs, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"seeded {len(source_assets)} characters for {STORY_ID}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
