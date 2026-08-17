from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from pathlib import Path, PurePosixPath
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify a portable interactive-film delivery.")
    parser.add_argument("--url", help="Also verify a running server, for example http://127.0.0.1:5100")
    parser.add_argument("--user", default=os.getenv("CONSOLE_AUTH_USER", ""), help="Optional HTTP Basic user")
    parser.add_argument("--password", default=os.getenv("CONSOLE_AUTH_PASS", ""), help="Optional HTTP Basic password")
    return parser.parse_args()


def load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def generated_path(media_url: str) -> Path:
    prefix = "/generated/"
    if not media_url.startswith(prefix):
        raise ValueError(f"not a generated media URL: {media_url}")
    relative = PurePosixPath(media_url.removeprefix(prefix))
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"unsafe generated media URL: {media_url}")
    return ROOT / "generated" / Path(*relative.parts)


def find_absolute_asset_refs(value: object, location: str = "manifest") -> list[str]:
    refs: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_location = f"{location}.{key}"
            if key in {"asset_path", "s1_portrait_path", "poster_path"} and isinstance(child, str):
                if Path(child).is_absolute():
                    refs.append(f"{child_location}={child}")
            refs.extend(find_absolute_asset_refs(child, child_location))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            refs.extend(find_absolute_asset_refs(child, f"{location}[{index}]"))
    return refs


def auth_headers(user: str, password: str) -> dict[str, str]:
    if not user:
        return {}
    token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {token}"}


def get_json(url: str, headers: dict[str, str]) -> object:
    request = Request(url, headers=headers)
    with urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def verify_server(base_url: str, user: str, password: str) -> list[str]:
    errors: list[str] = []
    base_url = base_url.rstrip("/")
    headers = auth_headers(user, password)
    try:
        health = get_json(f"{base_url}/api/health", headers)
        if not isinstance(health, dict) or health.get("ok") is not True:
            errors.append("/api/health did not return ok=true")
        stories = get_json(f"{base_url}/api/stories", headers)
        story_items = stories.get("stories", []) if isinstance(stories, dict) else []
        if not story_items:
            errors.append("/api/stories returned no stories")
    except HTTPError as exc:
        errors.append(f"server returned HTTP {exc.code}; provide --user/--password if Basic Auth is enabled")
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        errors.append(f"server check failed: {exc}")
    return errors


def main() -> int:
    args = parse_args()
    errors: list[str] = []
    warnings: list[str] = []

    required = [
        ROOT / "app.py",
        ROOT / "requirements.txt",
        ROOT / "static" / "index.html",
        ROOT / "data" / "stories.json",
        ROOT / "data" / "production-jobs.json",
        ROOT / "generated" / "assets",
        ROOT / "generated" / "clips",
        ROOT / "generated" / "movies",
    ]
    for path in required:
        if not path.exists():
            errors.append(f"required path missing: {path.relative_to(ROOT)}")

    jobs: dict[str, object] = {}
    manifest: dict[str, object] = {}
    if not errors:
        try:
            loaded_jobs = load_json(ROOT / "data" / "production-jobs.json")
            loaded_manifest = load_json(ROOT / "data" / "stories.json")
            if not isinstance(loaded_jobs, dict) or not isinstance(loaded_manifest, dict):
                raise ValueError("jobs and manifest must be JSON objects")
            jobs = loaded_jobs
            manifest = loaded_manifest
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"JSON validation failed: {exc}")

    media_jobs = 0
    media_counts = {"image": 0, "s1-image": 0, "clip": 0, "movie": 0, "other": 0}
    for job_id, raw_record in jobs.items():
        if not isinstance(raw_record, dict) or raw_record.get("state") != "success":
            continue
        media_url = raw_record.get("media_url")
        if not isinstance(media_url, str) or not media_url.startswith("/generated/"):
            continue
        media_jobs += 1
        kind = str(raw_record.get("kind") or "other")
        media_counts[kind if kind in media_counts else "other"] += 1
        try:
            path = generated_path(media_url)
        except ValueError as exc:
            errors.append(f"{job_id}: {exc}")
            continue
        if not path.is_file():
            errors.append(f"{job_id}: media file missing: {path.relative_to(ROOT)}")
        elif path.stat().st_size == 0:
            errors.append(f"{job_id}: media file is empty: {path.relative_to(ROOT)}")

    if jobs and media_jobs == 0:
        errors.append("production-jobs.json contains no successful generated media")

    story_count = len(manifest.get("stories", [])) if isinstance(manifest.get("stories"), list) else 0
    if manifest and story_count == 0:
        errors.append("stories.json contains no stories")
    absolute_refs = find_absolute_asset_refs(manifest)
    if absolute_refs:
        warnings.append(f"manifest contains {len(absolute_refs)} machine-local absolute asset paths")
        warnings.extend(absolute_refs[:5])

    if not (ROOT.parent / "agent" / "memory.py").is_file():
        warnings.append("../agent/memory.py is missing; PolarDB Mem0 callbacks will be unavailable")

    if args.url:
        errors.extend(verify_server(args.url, args.user, args.password))

    print(f"stories={story_count}")
    print(f"successful_media_jobs={media_jobs}")
    print("media=" + ", ".join(f"{key}:{value}" for key, value in media_counts.items()))
    for warning in warnings:
        print(f"WARNING: {warning}")
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    if errors:
        return 1
    print("DELIVERY_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
