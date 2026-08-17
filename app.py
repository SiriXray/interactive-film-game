from __future__ import annotations

import base64
import json
import mimetypes
import os
import shutil
import subprocess
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
import websocket as ws_client
from websocket import WebSocketConnectionClosedException, WebSocketTimeoutException
from flask import Flask, jsonify, redirect, request, send_file, send_from_directory
from flask_sock import Sock
from simple_websocket.errors import ConnectionClosed


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
STORY_FILE = Path(os.getenv("STORY_FILE") or str(DATA_DIR / "stories.json")).expanduser()
JOBS_FILE = DATA_DIR / "production-jobs.json"
AUTOPILOT_FILE = DATA_DIR / "production-autopilot.json"
CONSOLE_TRANSCRIPT_DIR = DATA_DIR / "console-transcripts"
GENERATED_DIR = ROOT / "generated"
ASSETS_DIR = GENERATED_DIR / "assets"
CLIPS_DIR = GENERATED_DIR / "clips"
MOVIES_DIR = GENERATED_DIR / "movies"
ALLOWED_VIDEO_MODELS = {"viduq3-mix", "viduq3-drama"}
IMAGE_MODEL = "viduimage-2"
FFMPEG_PATH = os.getenv("FFMPEG_PATH", "ffmpeg")
RTC_SDK_URL = os.getenv(
    "ALIRTC_SDK_URL",
    "https://g.alicdn.com/apsara-media-box/imp-web-rtc/7.1.9/aliyun-rtc-sdk.js",
)
S1_VOICE_ALIASES = {
    "Qiao": "Tina",
    "Dylan": "Andre",
    "Juniper": "Ryan",
    "Atlas": "Harvey",
}


def load_env_file(path: Path) -> None:
    """Load local configuration without echoing credentials to browser or logs."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        key, value = text.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


load_env_file(ROOT / ".env")
load_env_file(ROOT.parent / ".env")
API_BASE = os.getenv("VIDU_API_BASE", "https://api.vidu.cn").rstrip("/")
WS_BASE = API_BASE.replace("https://", "wss://").replace("http://", "ws://")


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def clamp_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    """Coerce env/config values to an int inside [minimum, maximum] without raising."""
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, number))


# Story-flow S1 capability config (advantages A/B/C/D). These layer on top of the
# bare avatar payload so the player-facing game gains the same S1 features the
# operator console already exposes, but driven by story semantics instead of forms.
STORY_LLM_MAX_TOKENS = clamp_int(os.getenv("STORY_LLM_MAX_TOKENS"), 220, 1, 65536)
STORY_LLM_SEED = clamp_int(os.getenv("STORY_LLM_SEED"), -1, -1, 2147483647)
STORY_VAD_SILENCE_MS = clamp_int(os.getenv("STORY_VAD_SILENCE_MS"), 400, 200, 6000)
STORY_VAD_IDLE_MS = clamp_int(os.getenv("STORY_VAD_IDLE_MS"), 12000, 0, 30000)
STORY_SESSION_IDLE_SECONDS = clamp_int(os.getenv("STORY_SESSION_IDLE_SECONDS"), 600, 10, 7200)
RETRIEVAL_TIMEOUT_MS = clamp_int(os.getenv("RETRIEVAL_TIMEOUT_MS"), 3000, 100, 30000)

# Memory/knowledge require Vidu's cloud to reach these endpoints, so they only
# activate when a public base URL is configured (e.g. a Cloudflare tunnel) and the
# feature is explicitly enabled. On localhost they stay off so live sessions still work.
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")
RETRIEVAL_AUTH = os.getenv("MEMORY_TOKEN", "").strip()
RETRIEVAL_AUTH = f"Bearer {RETRIEVAL_AUTH}" if RETRIEVAL_AUTH else ""
STORY_MEMORY_ENABLED = _env_flag("STORY_MEMORY_ENABLED")
STORY_KNOWLEDGE_ENABLED = _env_flag("STORY_KNOWLEDGE_ENABLED")

MEMORY: Any = None
try:
    if str(ROOT.parent) not in sys.path:
        sys.path.insert(0, str(ROOT.parent))
    from agent.memory import SlidingWindowMemory  # noqa: E402

    MEMORY = SlidingWindowMemory(timeout=clamp_int(os.getenv("MEM0_TIMEOUT"), 60, 1, 180))
except Exception as exc:  # pragma: no cover - optional dependency wiring
    app_memory_import_error = str(exc)

app = Flask(__name__, static_folder="static", static_url_path="/static")
sock = Sock(app)

# ---- Public-exposure gate -------------------------------------------------
# When CONSOLE_AUTH_USER/PASS are set (used only when tunneling to the public
# internet), require HTTP Basic auth on everything EXCEPT endpoints that must
# stay open for machine callers: Vidu S1 memory/knowledge callbacks and the RTC
# signaling proxy already validate their own token, and health is harmless.
# On localhost with no creds set, the gate is inert so nothing changes.
CONSOLE_AUTH_USER = os.getenv("CONSOLE_AUTH_USER", "").strip()
CONSOLE_AUTH_PASS = os.getenv("CONSOLE_AUTH_PASS", "").strip()
_AUTH_EXEMPT_PATHS = {"/memory/search", "/knowledge/search", "/ws/live", "/api/health"}


@app.before_request
def _require_console_auth() -> Any:
    if not (CONSOLE_AUTH_USER and CONSOLE_AUTH_PASS):
        return None  # gate disabled (localhost / not configured)
    if request.method == "OPTIONS":
        return None
    if request.path in _AUTH_EXEMPT_PATHS:
        return None  # machine callers with their own token
    auth = request.authorization
    if auth and auth.username == CONSOLE_AUTH_USER and auth.password == CONSOLE_AUTH_PASS:
        return None
    resp = jsonify({"error": "authentication required"})
    resp.status_code = 401
    resp.headers["WWW-Authenticate"] = 'Basic realm="Vidu S1 Console"'
    return resp


jobs_lock = threading.Lock()
submission_lock = threading.Lock()
production_worker_lock = threading.Lock()
console_transcript_lock = threading.Lock()
production_worker: threading.Thread | None = None
production_worker_scope: tuple[str, ...] | None = None


def ensure_dirs() -> None:
    for folder in (DATA_DIR, CONSOLE_TRANSCRIPT_DIR, GENERATED_DIR, ASSETS_DIR, CLIPS_DIR, MOVIES_DIR):
        folder.mkdir(parents=True, exist_ok=True)
    if not JOBS_FILE.exists():
        JOBS_FILE.write_text("{}", encoding="utf-8")


def load_autopilot() -> dict[str, Any]:
    """Read the explicit paid-production authorization that survives restarts."""
    ensure_dirs()
    if not AUTOPILOT_FILE.exists():
        return {"enabled": False, "scope": "all", "story_ids": []}
    try:
        data = json.loads(AUTOPILOT_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"enabled": False, "scope": "all", "story_ids": []}
    if not isinstance(data, dict):
        return {"enabled": False, "scope": "all", "story_ids": []}
    scope = "all" if data.get("scope") == "all" else "selected"
    story_ids = [str(item) for item in data.get("story_ids", []) if isinstance(item, str)]
    return {"enabled": data.get("enabled") is True, "scope": scope, "story_ids": story_ids}


def save_autopilot(story_ids: tuple[str, ...] | None) -> None:
    """Persist the user's confirmed scope, never credentials or request payloads."""
    ensure_dirs()
    payload = {
        "enabled": True,
        "scope": "all" if story_ids is None else "selected",
        "story_ids": [] if story_ids is None else list(story_ids),
        "updated_at": int(time.time()),
    }
    temporary = AUTOPILOT_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(AUTOPILOT_FILE)


def api_key() -> str:
    key = os.getenv("VIDU_API_KEY", "").strip()
    if not key:
        raise RuntimeError("VIDU_API_KEY is not configured. Set it in the process environment or the local .env file.")
    return key if key.startswith("Token ") else f"Token {key}"


def api_headers() -> dict[str, str]:
    return {"Authorization": api_key(), "Content-Type": "application/json"}


def redact_error(error: Exception | str) -> str:
    message = str(error)
    key = os.getenv("VIDU_API_KEY", "")
    if key:
        message = message.replace(key, "***")
    return message.replace("Token ***", "***")


def load_stories() -> dict[str, Any]:
    with STORY_FILE.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def get_story(story_id: str) -> dict[str, Any]:
    for story in load_stories().get("stories", []):
        if story.get("id") == story_id:
            return story
    raise ValueError("unknown story_id")


def get_node(story: dict[str, Any], node_id: str) -> dict[str, Any]:
    node = story.get("nodes", {}).get(node_id)
    if not node:
        raise ValueError("unknown node_id")
    return node


def get_character(story: dict[str, Any], character_id: str) -> dict[str, Any]:
    for character in story.get("characters", []):
        if character.get("id") == character_id:
            return character
    raise ValueError("unknown character_id")


def resolve_manifest_asset_path(raw_path: Any) -> Path | None:
    if not raw_path:
        return None
    candidate = Path(str(raw_path)).expanduser()
    if not candidate.is_absolute():
        candidate = (STORY_FILE.parent / candidate).resolve()
    else:
        candidate = candidate.resolve()
    if not candidate.exists() or not candidate.is_file():
        return None
    return candidate


def local_story_asset_url(story_id: str, bucket: str, asset_id: str) -> str:
    return f"/api/story-assets/{story_id}/{bucket}/{asset_id}"


def character_local_asset_path(character: dict[str, Any], *, portrait: bool = False) -> Path | None:
    key = "s1_portrait_path" if portrait else "asset_path"
    return resolve_manifest_asset_path(character.get(key))


def character_local_asset_url(story: dict[str, Any], character: dict[str, Any], *, portrait: bool = False) -> str:
    path = character_local_asset_path(character, portrait=portrait)
    if path is None:
        return ""
    bucket = "portrait" if portrait else "character"
    return local_story_asset_url(story["id"], bucket, character["id"])


def node_local_poster_path(node: dict[str, Any]) -> Path | None:
    return resolve_manifest_asset_path(node.get("poster_path"))


def story_node_asset_path(story: dict[str, Any], bucket: str, asset_id: str) -> Path | None:
    if bucket == "character":
        return character_local_asset_path(get_character(story, asset_id), portrait=False)
    if bucket == "portrait":
        character = get_character(story, asset_id)
        return character_local_asset_path(character, portrait=True) or character_local_asset_path(character, portrait=False)
    if bucket == "node":
        return node_local_poster_path(get_node(story, asset_id))
    raise ValueError("unknown asset bucket")


def story_avatar_source_path(story: dict[str, Any], character: dict[str, Any], jobs: dict[str, dict[str, Any]]) -> Path | None:
    return s1_portrait_path(jobs, story["id"], character["id"]) or character_local_asset_path(character, portrait=True) or character_local_asset_path(character, portrait=False)


def character_s1_voice(character: dict[str, Any]) -> str:
    explicit = str(character.get("s1_voice") or "").strip()
    if explicit:
        return explicit
    raw = str(character.get("voice") or "").strip()
    if raw:
        return S1_VOICE_ALIASES.get(raw, raw)
    return "Tina"


def load_jobs() -> dict[str, dict[str, Any]]:
    ensure_dirs()
    try:
        data = json.loads(JOBS_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        data = {}
    return data if isinstance(data, dict) else {}


def save_jobs(jobs: dict[str, dict[str, Any]]) -> None:
    ensure_dirs()
    temporary = JOBS_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(jobs, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(JOBS_FILE)


def public_generated_path(path: Path) -> str:
    return "/generated/" + path.resolve().relative_to(GENERATED_DIR.resolve()).as_posix()


def local_generated_path(url: str) -> Path:
    prefix = "/generated/"
    if not url.startswith(prefix):
        raise ValueError("asset must be inside generated/")
    candidate = (GENERATED_DIR / url.removeprefix(prefix)).resolve()
    if GENERATED_DIR.resolve() not in candidate.parents and candidate != GENERATED_DIR.resolve():
        raise ValueError("invalid generated asset path")
    return candidate


def file_data_uri(path: Path) -> str:
    if not path.exists():
        raise ValueError(f"generated asset missing: {path.name}")
    mime, _ = mimetypes.guess_type(path.name)
    mime = mime if mime and mime.startswith("image/") else "image/png"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


def task_endpoint(task_id: str) -> str:
    return f"{API_BASE}/ent/v2/tasks/{task_id}/creations"


def response_data(response: requests.Response) -> dict[str, Any]:
    try:
        payload = response.json() if response.content else {}
    except ValueError as exc:
        raise RuntimeError(f"Vidu returned invalid JSON (HTTP {response.status_code})") from exc
    if response.status_code >= 400:
        detail = payload.get("message") or payload.get("error") or f"HTTP {response.status_code}"
        raise RuntimeError(str(detail))
    return payload if isinstance(payload, dict) else {}


def request_task(path: str, body: dict[str, Any]) -> dict[str, Any]:
    response = requests.post(f"{API_BASE}{path}", headers=api_headers(), json=body, timeout=60)
    payload = response_data(response)
    task_id = str(payload.get("task_id") or payload.get("id") or "")
    if not task_id:
        raise RuntimeError("Vidu did not return task_id")
    return {"task_id": task_id, "state": str(payload.get("state") or "created")}


def image_job_id(story_id: str, character_id: str) -> str:
    return f"image:{story_id}:{character_id}"


def s1_image_job_id(story_id: str, character_id: str) -> str:
    return f"s1-image:{story_id}:{character_id}"


def clip_job_id(story_id: str, node_id: str, clip_id: str) -> str:
    return f"clip:{story_id}:{node_id}:{clip_id}"


def movie_job_id(story_id: str, node_id: str) -> str:
    return f"movie:{story_id}:{node_id}"


def character_asset_record(jobs: dict[str, dict[str, Any]], story_id: str, character_id: str) -> dict[str, Any] | None:
    return jobs.get(image_job_id(story_id, character_id))


def character_asset_path(jobs: dict[str, dict[str, Any]], story_id: str, character_id: str) -> Path | None:
    record = character_asset_record(jobs, story_id, character_id)
    if not record or record.get("state") != "success" or not record.get("media_url"):
        return None
    path = local_generated_path(str(record["media_url"]))
    return path if path.exists() else None


def s1_portrait_record(jobs: dict[str, dict[str, Any]], story_id: str, character_id: str) -> dict[str, Any] | None:
    return jobs.get(s1_image_job_id(story_id, character_id))


def s1_portrait_path(jobs: dict[str, dict[str, Any]], story_id: str, character_id: str) -> Path | None:
    record = s1_portrait_record(jobs, story_id, character_id)
    if not record or record.get("state") != "success" or not record.get("media_url"):
        return None
    path = local_generated_path(str(record["media_url"]))
    return path if path.exists() else None


def image_extension(response: requests.Response, url: str) -> str:
    content_type = response.headers.get("Content-Type", "").lower().split(";", 1)[0]
    suffix = mimetypes.guess_extension(content_type) if content_type else None
    if suffix in {".jpeg", ".jpg", ".png", ".webp"}:
        return ".jpg" if suffix == ".jpeg" else suffix
    candidate = Path(url.split("?", 1)[0]).suffix.lower()
    return candidate if candidate in {".jpg", ".png", ".webp"} else ".png"


def download_creation(url: str, destination: Path, *, media_kind: str) -> Path:
    response = requests.get(url, stream=True, timeout=180)
    response.raise_for_status()
    if media_kind == "image":
        destination = destination.with_suffix(image_extension(response, url))
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    with temporary.open("wb") as handle:
        for chunk in response.iter_content(chunk_size=65536):
            if chunk:
                handle.write(chunk)
    temporary.replace(destination)
    return destination


def submit_image_job(story: dict[str, Any], character: dict[str, Any]) -> dict[str, Any]:
    return request_task(
        "/ent/v2/reference2image",
        {
            "model": IMAGE_MODEL,
            "images": [],
            "prompt": character["image_prompt"],
            "aspect_ratio": "9:16",
            "resolution": "2K",
            "quality": "high",
            "payload": f"interactive-film:image:{story['id']}:{character['id']}",
        },
    )


def s1_portrait_prompt(character: dict[str, Any]) -> str:
    return (
        "16:9 landscape cinematic character portrait for a real-time interactive video avatar. "
        f"Single person only: {character['name']}, {character['role']}. "
        "Preserve the supplied reference's identity, costume, era, hairstyle, and visual style. "
        "Eye-level medium close-up, face and shoulders fully visible, both eyes looking toward camera, "
        "head centered with comfortable space above and around it, upper torso visible, natural expression, "
        "clear facial features, clean uncluttered background, no profile, no cropped head, no hands covering face, "
        "no other people, no text, no watermark."
    )


def submit_s1_portrait_job(story: dict[str, Any], character: dict[str, Any], character_reference: Path) -> dict[str, Any]:
    return request_task(
        "/ent/v2/reference2image",
        {
            "model": IMAGE_MODEL,
            "images": [file_data_uri(character_reference)],
            "prompt": s1_portrait_prompt(character),
            "aspect_ratio": "16:9",
            "resolution": "2K",
            "quality": "high",
            "payload": f"interactive-film:s1-image:{story['id']}:{character['id']}",
        },
    )


def submit_clip_job(story: dict[str, Any], node_id: str, node: dict[str, Any], clip: dict[str, Any], jobs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    plan = node["render_plan"]
    model = str(clip["model"])
    if model not in ALLOWED_VIDEO_MODELS:
        raise ValueError(f"unsupported Q3 model: {model}")
    image_paths = [character_asset_path(jobs, story["id"], character_id) for character_id in plan["cast"]]
    if any(path is None for path in image_paths):
        raise ValueError("all character reference images must complete before Q3 submission")
    return request_task(
        "/ent/v2/reference2video",
        {
            "model": model,
            "images": [file_data_uri(path) for path in image_paths if path is not None],
            "prompt": clip["prompt"],
            "duration": int(clip["duration"]),
            "resolution": "720p",
            "aspect_ratio": "9:16",
            "audio": True,
            "movement_amplitude": "auto",
            "payload": f"interactive-film:clip:{story['id']}:{node_id}:{clip['id']}",
        },
    )


def record_task(job_id: str, kind: str, metadata: dict[str, Any], task: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": job_id,
        "kind": kind,
        **metadata,
        "task_id": task["task_id"],
        "state": task["state"],
        "created_at": int(time.time()),
        "updated_at": int(time.time()),
        "media_url": "",
        "remote_url": "",
        "error": "",
    }


def refresh_task_record(record: dict[str, Any]) -> dict[str, Any]:
    if record.get("state") in {"success", "failed"}:
        return record
    response = requests.get(task_endpoint(str(record["task_id"])), headers=api_headers(), timeout=45)
    payload = response_data(response)
    record["state"] = str(payload.get("state") or record.get("state") or "processing")
    record["updated_at"] = int(time.time())
    if record["state"] == "failed":
        record["error"] = str(payload.get("err_code") or payload.get("message") or "Vidu task failed")
        return record
    creations = payload.get("creations") if isinstance(payload.get("creations"), list) else []
    remote_url = str(creations[0].get("url") or "") if creations and isinstance(creations[0], dict) else ""
    if record["state"] == "success" and remote_url:
        record["remote_url"] = remote_url
        if record["kind"] in {"image", "s1-image"}:
            destination = ASSETS_DIR / str(record["story_id"]) / str(record["character_id"])
            if record["kind"] == "s1-image":
                destination = destination / "s1"
            local_path = download_creation(remote_url, destination, media_kind="image")
        else:
            destination = CLIPS_DIR / str(record["story_id"]) / str(record["node_id"]) / f"{record['clip_id']}.mp4"
            local_path = download_creation(remote_url, destination, media_kind="video")
        record["media_url"] = public_generated_path(local_path)
    elif record["state"] == "success":
        record["state"] = "failed"
        record["error"] = "Vidu reported success without a creation URL"
    return record


def resolve_ffmpeg() -> str | None:
    configured = Path(FFMPEG_PATH)
    if configured.is_file():
        return str(configured)
    return shutil.which(FFMPEG_PATH) or shutil.which("ffmpeg")


def compose_movie(story_id: str, node_id: str, node: dict[str, Any], jobs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    movie_id = movie_job_id(story_id, node_id)
    movie = jobs.get(movie_id, {"id": movie_id, "kind": "movie", "story_id": story_id, "node_id": node_id, "state": "pending", "media_url": "", "error": ""})
    if movie.get("state") == "success" and movie.get("media_url"):
        local_path = local_generated_path(str(movie["media_url"]))
        if local_path.exists():
            return movie
    clip_records = [jobs.get(clip_job_id(story_id, node_id, clip["id"])) for clip in node["render_plan"]["clips"]]
    if any(record is None for record in clip_records):
        return movie
    if any(record.get("state") == "failed" for record in clip_records if record):
        movie["state"] = "failed"
        movie["error"] = "A source Q3 clip failed; resubmit that clip before composing."
        jobs[movie_id] = movie
        return movie
    if not all(record and record.get("state") == "success" and record.get("media_url") for record in clip_records):
        return movie
    clips = [local_generated_path(str(record["media_url"])) for record in clip_records if record]
    if not all(path.exists() for path in clips):
        movie["state"] = "failed"
        movie["error"] = "A completed clip file is missing from local storage."
        jobs[movie_id] = movie
        return movie
    ffmpeg = resolve_ffmpeg()
    if not ffmpeg:
        movie["state"] = "blocked"
        movie["error"] = "ffmpeg is required to concatenate three Q3 clips. Set FFMPEG_PATH or add ffmpeg to PATH."
        jobs[movie_id] = movie
        return movie
    destination = MOVIES_DIR / story_id / f"{node_id}.mp4"
    destination.parent.mkdir(parents=True, exist_ok=True)
    list_file = destination.with_suffix(".concat.txt")
    list_file.write_text("".join(f"file '{path.as_posix()}'\n" for path in clips), encoding="utf-8")
    try:
        copy_result = subprocess.run(
            [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(list_file), "-c", "copy", str(destination)],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        if copy_result.returncode != 0:
            reencode_result = subprocess.run(
                [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(list_file), "-c:v", "libx264", "-c:a", "aac", "-movflags", "+faststart", str(destination)],
                capture_output=True,
                text=True,
                timeout=300,
                check=False,
            )
            if reencode_result.returncode != 0:
                raise RuntimeError((reencode_result.stderr or copy_result.stderr)[-600:])
        movie.update({"state": "success", "media_url": public_generated_path(destination), "error": "", "updated_at": int(time.time())})
    except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
        movie.update({"state": "failed", "error": redact_error(exc), "updated_at": int(time.time())})
    finally:
        list_file.unlink(missing_ok=True)
    jobs[movie_id] = movie
    return movie


def refresh_all_jobs() -> dict[str, int]:
    # Network calls can take minutes while Vidu is queueing. Keep them outside
    # the file lock so production submission remains available during refresh.
    with jobs_lock:
        snapshot = load_jobs()
    pending_records = [(job_id, dict(record)) for job_id, record in snapshot.items() if record.get("kind") in {"image", "s1-image", "clip"} and record.get("state") not in {"success", "failed"}]
    refreshed_records: dict[str, dict[str, Any]] = {}
    # Poll independently so a slow Vidu task does not hold up all production.
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(refresh_task_record, record): job_id for job_id, record in pending_records}
        for future in as_completed(futures):
            job_id = futures[future]
            try:
                refreshed_records[job_id] = future.result()
            except (RuntimeError, requests.RequestException) as exc:
                record = dict(snapshot[job_id])
                record["error"] = redact_error(exc)
                record["updated_at"] = int(time.time())
                refreshed_records[job_id] = record
    with jobs_lock:
        jobs = load_jobs()
        for job_id, record in refreshed_records.items():
            # Preserve a newer terminal state if another request finished first.
            if jobs.get(job_id, {}).get("state") not in {"success", "failed"}:
                jobs[job_id] = record
        manifest = load_stories()
        for story in manifest.get("stories", []):
            for node_id, node in story.get("nodes", {}).items():
                if node.get("type") == "cutscene":
                    compose_movie(story["id"], node_id, node, jobs)
        save_jobs(jobs)
        return {"refreshed": len(refreshed_records), "total": len(jobs)}


def unsubmitted_clip_count(stories: list[dict[str, Any]]) -> int:
    with jobs_lock:
        jobs = load_jobs()
    count = 0
    for story in stories:
        for node_id, node in story["nodes"].items():
            if node.get("type") != "cutscene":
                continue
            for clip in node["render_plan"]["clips"]:
                if clip_job_id(story["id"], node_id, clip["id"]) not in jobs:
                    count += 1
    return count


def unsubmitted_s1_portrait_count(stories: list[dict[str, Any]]) -> int:
    with jobs_lock:
        jobs = load_jobs()
    return sum(
        s1_image_job_id(story["id"], character["id"]) not in jobs
        for story in stories
        for character in story["characters"]
    )


def pending_remote_task_count(stories: list[dict[str, Any]] | None = None) -> int:
    with jobs_lock:
        jobs = load_jobs()
    allowed_story_ids = {story["id"] for story in stories} if stories is not None else None
    return sum(
        record.get("kind") in {"image", "s1-image", "clip"}
        and record.get("state") not in {"success", "failed"}
        and (allowed_story_ids is None or record.get("story_id") in allowed_story_ids)
        for record in jobs.values()
    )


def unready_movie_count(stories: list[dict[str, Any]]) -> int:
    with jobs_lock:
        jobs = load_jobs()
    return sum(
        jobs.get(movie_job_id(story["id"], node_id), {}).get("state") != "success"
        for story in stories
        for node_id, node in story["nodes"].items()
        if node.get("type") == "cutscene"
    )


def production_scope(scope: tuple[str, ...] | None) -> list[dict[str, Any]]:
    manifest_stories = load_stories().get("stories", [])
    if scope is None:
        return manifest_stories
    selected = [story for story in manifest_stories if story["id"] in set(scope)]
    if len(selected) != len(scope):
        raise ValueError("one or more saved autopilot story_ids are unknown")
    return selected


def production_worker_loop(scope: tuple[str, ...] | None) -> None:
    """Keep the explicitly approved production scope moving until every movie is local."""
    global production_worker, production_worker_scope
    try:
        empty_rounds = 0
        while empty_rounds < 4:
            try:
                refresh_all_jobs()
                stories = production_scope(scope)
                submitted = submit_missing_images(stories)["count"]
                submitted += submit_missing_s1_portraits(stories)["count"]
                # Drain all currently unblocked pre-generated clips so newly
                # completed reference images immediately advance into paid Q3.
                submitted += submit_missing_clips(stories, max_tasks=180)["count"]
                remaining = pending_remote_task_count(stories) + unsubmitted_s1_portrait_count(stories) + unsubmitted_clip_count(stories) + unready_movie_count(stories)
                if submitted == 0 and remaining == 0:
                    empty_rounds += 1
                else:
                    empty_rounds = 0
            except (RuntimeError, requests.RequestException, OSError) as exc:
                # Leave durable jobs intact and retry transient Vidu/network errors.
                app.logger.warning("production worker will retry: %s", redact_error(exc))
            time.sleep(15)
    finally:
        with production_worker_lock:
            production_worker = None
            production_worker_scope = None


def start_production_worker(scope: tuple[str, ...] | None = None) -> bool:
    global production_worker, production_worker_scope
    with production_worker_lock:
        if production_worker and production_worker.is_alive():
            return False
        production_worker_scope = scope
        production_worker = threading.Thread(target=production_worker_loop, args=(scope,), name="interactive-film-production", daemon=True)
        production_worker.start()
        return True


def production_status() -> dict[str, Any]:
    manifest = load_stories()
    jobs = load_jobs()
    stories: list[dict[str, Any]] = []
    total_images = total_s1_portraits = total_clips = total_movies = ready_images = ready_s1_portraits = ready_clips = ready_movies = 0
    pending_images = pending_s1_portraits = pending_clips = failed = 0
    for story in manifest.get("stories", []):
        characters: list[dict[str, Any]] = []
        story_images_ready = story_clips_ready = story_movies_ready = 0
        story_s1_portraits_ready = 0
        story_movies_total = 0
        for character in story.get("characters", []):
            total_images += 1
            record = jobs.get(image_job_id(story["id"], character["id"]))
            local_asset_url = character_local_asset_url(story, character)
            status = record.get("state", "not_submitted") if record else ("local" if local_asset_url else "not_submitted")
            if status in {"success", "local"}:
                ready_images += 1
                story_images_ready += 1
            elif status == "failed":
                failed += 1
            else:
                pending_images += 1
            s1_record = s1_portrait_record(jobs, story["id"], character["id"])
            local_s1_url = character_local_asset_url(story, character, portrait=True) or local_asset_url
            s1_status = s1_record.get("state", "not_submitted") if s1_record else ("local" if local_s1_url else "not_submitted")
            total_s1_portraits += 1
            if s1_status in {"success", "local"}:
                ready_s1_portraits += 1
                story_s1_portraits_ready += 1
            elif s1_status == "failed":
                failed += 1
            else:
                pending_s1_portraits += 1
            characters.append(
                {
                    "id": character["id"],
                    "name": character["name"],
                    "role": character["role"],
                    "state": status,
                    "asset_url": record.get("media_url", "") if record and record.get("state") == "success" else local_asset_url,
                    "s1_portrait_state": s1_status,
                    "s1_portrait_url": s1_record.get("media_url", "") if s1_record and s1_record.get("state") == "success" else local_s1_url,
                }
            )
        cutscenes: list[dict[str, Any]] = []
        for node_id, node in story.get("nodes", {}).items():
            if node.get("type") != "cutscene":
                continue
            story_movies_total += 1
            total_movies += 1
            clip_states: list[str] = []
            for clip in node["render_plan"]["clips"]:
                total_clips += 1
                record = jobs.get(clip_job_id(story["id"], node_id, clip["id"]))
                state = record.get("state", "not_submitted") if record else "not_submitted"
                clip_states.append(state)
                if state == "success":
                    ready_clips += 1
                    story_clips_ready += 1
                elif state == "failed":
                    failed += 1
                else:
                    pending_clips += 1
            movie = jobs.get(movie_job_id(story["id"], node_id))
            movie_state = movie.get("state", "not_ready") if movie else "not_ready"
            if movie_state == "success":
                ready_movies += 1
                story_movies_ready += 1
            elif movie_state == "failed":
                failed += 1
            cutscenes.append({"node_id": node_id, "title": node["title"], "state": movie_state, "media_url": movie.get("media_url", "") if movie else "", "clip_states": clip_states})
        stories.append(
            {
                "id": story["id"],
                "title": story["title"],
                "hero": story["hero"],
                "characters": characters,
                "cutscenes": cutscenes,
                "images": {"ready": story_images_ready, "total": len(story["characters"])},
                "s1_portraits": {"ready": story_s1_portraits_ready, "total": len(story["characters"])},
                "clips": {"ready": story_clips_ready, "total": story_movies_total * 3},
                "movies": {"ready": story_movies_ready, "total": story_movies_total},
            }
        )
    return {
        "configured": bool(os.getenv("VIDU_API_KEY", "").strip()),
        "worker_running": bool(production_worker and production_worker.is_alive()),
        "production": manifest.get("production", {}),
        "totals": {
            "images": {"ready": ready_images, "pending": pending_images, "total": total_images},
            "s1_portraits": {"ready": ready_s1_portraits, "pending": pending_s1_portraits, "total": total_s1_portraits},
            "clips": {"ready": ready_clips, "pending": pending_clips, "total": total_clips},
            "movies": {"ready": ready_movies, "total": total_movies},
            "failed": failed,
        },
        "stories": stories,
    }


def selected_stories(body: dict[str, Any]) -> list[dict[str, Any]]:
    requested = body.get("story_ids")
    manifest_stories = load_stories().get("stories", [])
    if requested is None:
        return manifest_stories
    if not isinstance(requested, list) or not requested or not all(isinstance(item, str) for item in requested):
        raise ValueError("story_ids must be a non-empty array of story IDs")
    requested_ids = set(requested)
    stories = [story for story in manifest_stories if story["id"] in requested_ids]
    if len(stories) != len(requested_ids):
        raise ValueError("one or more story_ids are unknown")
    return stories


def require_confirmed(body: dict[str, Any]) -> None:
    if body.get("confirm") is not True:
        raise ValueError("Set confirm: true to submit paid Vidu generation tasks.")


def submit_missing_images(stories: list[dict[str, Any]]) -> dict[str, Any]:
    created: list[str] = []
    # Serialize submissions but never hold the job-file lock during a Vidu API call.
    with submission_lock:
        for story in stories:
            for character in story["characters"]:
                job_id = image_job_id(story["id"], character["id"])
                with jobs_lock:
                    jobs = load_jobs()
                    if job_id in jobs and jobs[job_id].get("state") in {"created", "queueing", "processing", "success"}:
                        continue
                task = submit_image_job(story, character)
                with jobs_lock:
                    jobs = load_jobs()
                    if job_id in jobs and jobs[job_id].get("state") in {"created", "queueing", "processing", "success"}:
                        continue
                    jobs[job_id] = record_task(job_id, "image", {"story_id": story["id"], "character_id": character["id"]}, task)
                    save_jobs(jobs)
                created.append(job_id)
    return {"submitted": created, "count": len(created)}


def submit_missing_s1_portraits(stories: list[dict[str, Any]]) -> dict[str, Any]:
    created: list[str] = []
    waiting_for_references: list[str] = []
    with submission_lock:
        for story in stories:
            for character in story["characters"]:
                job_id = s1_image_job_id(story["id"], character["id"])
                with jobs_lock:
                    jobs = load_jobs()
                    if job_id in jobs and jobs[job_id].get("state") in {"created", "queueing", "processing", "success"}:
                        continue
                    character_reference = character_asset_path(jobs, story["id"], character["id"])
                if character_reference is None:
                    waiting_for_references.append(f"{story['id']}:{character['id']}")
                    continue
                task = submit_s1_portrait_job(story, character, character_reference)
                with jobs_lock:
                    jobs = load_jobs()
                    if job_id in jobs and jobs[job_id].get("state") in {"created", "queueing", "processing", "success"}:
                        continue
                    jobs[job_id] = record_task(job_id, "s1-image", {"story_id": story["id"], "character_id": character["id"]}, task)
                    save_jobs(jobs)
                created.append(job_id)
    return {"submitted": created, "count": len(created), "waiting_for_references": waiting_for_references}


def submit_missing_clips(stories: list[dict[str, Any]], max_tasks: int) -> dict[str, Any]:
    if not 1 <= max_tasks <= 180:
        raise ValueError("max_tasks must be between 1 and 180")
    created: list[str] = []
    waiting_for_assets: list[str] = []
    with submission_lock:
        for story in stories:
            for node_id, node in story["nodes"].items():
                if node.get("type") != "cutscene":
                    continue
                for clip in node["render_plan"]["clips"]:
                    if len(created) >= max_tasks:
                        break
                    job_id = clip_job_id(story["id"], node_id, clip["id"])
                    with jobs_lock:
                        jobs = load_jobs()
                        if job_id in jobs and jobs[job_id].get("state") in {"created", "queueing", "processing", "success"}:
                            continue
                        job_snapshot = dict(jobs)
                    try:
                        task = submit_clip_job(story, node_id, node, clip, job_snapshot)
                    except ValueError as exc:
                        waiting_for_assets.append(f"{story['id']}:{node_id}:{clip['id']} ({exc})")
                        continue
                    with jobs_lock:
                        jobs = load_jobs()
                        if job_id in jobs and jobs[job_id].get("state") in {"created", "queueing", "processing", "success"}:
                            continue
                        jobs[job_id] = record_task(
                            job_id,
                            "clip",
                            {"story_id": story["id"], "node_id": node_id, "clip_id": clip["id"], "model": clip["model"]},
                            task,
                        )
                        save_jobs(jobs)
                    created.append(job_id)
                if len(created) >= max_tasks:
                    break
            if len(created) >= max_tasks:
                break
    return {"submitted": created, "count": len(created), "waiting_for_assets": waiting_for_assets[:12]}


def sanitize_story_for_client(story: dict[str, Any]) -> dict[str, Any]:
    jobs = load_jobs()
    client_story = json.loads(json.dumps(story, ensure_ascii=False))
    for node_id, node in client_story.get("nodes", {}).items():
        if node.get("type") == "cutscene":
            movie = jobs.get(movie_job_id(story["id"], node_id))
            node["media_url"] = movie.get("media_url", "") if movie and movie.get("state") == "success" else ""
            node["production_state"] = movie.get("state", "not_ready") if movie else "not_ready"
            node["poster_url"] = local_story_asset_url(story["id"], "node", node_id) if node_local_poster_path(node) else ""
            node.pop("render_plan", None)
        elif node.get("type") == "interactive":
            character = get_character(story, node["avatar_character"])
            portrait = s1_portrait_record(jobs, story["id"], character["id"])
            fallback = character_asset_record(jobs, story["id"], character["id"])
            local_avatar_url = character_local_asset_url(story, character, portrait=True)
            local_fallback_url = character_local_asset_url(story, character)
            node["avatar_url"] = portrait.get("media_url", "") if portrait and portrait.get("state") == "success" else local_avatar_url
            node["fallback_avatar_url"] = fallback.get("media_url", "") if fallback and fallback.get("state") == "success" else local_fallback_url
            node["avatar_state"] = portrait.get("state", "not_submitted") if portrait else ("local" if local_avatar_url else "not_submitted")
            node["poster_url"] = local_story_asset_url(story["id"], "node", node_id) if node_local_poster_path(node) else ""
            node["avatar_name"] = character["name"]
            node["voice"] = character_s1_voice(character)
    for character in client_story.get("characters", []):
        asset = character_asset_record(jobs, story["id"], character["id"])
        s1_asset = s1_portrait_record(jobs, story["id"], character["id"])
        character.pop("image_prompt", None)
        local_asset_url = character_local_asset_url(story, character)
        local_s1_url = character_local_asset_url(story, character, portrait=True) or local_asset_url
        character["asset_url"] = asset.get("media_url", "") if asset and asset.get("state") == "success" else local_asset_url
        character["production_state"] = asset.get("state", "not_submitted") if asset else ("local" if local_asset_url else "not_submitted")
        character["s1_portrait_url"] = s1_asset.get("media_url", "") if s1_asset and s1_asset.get("state") == "success" else local_s1_url
        character["s1_portrait_state"] = s1_asset.get("state", "not_submitted") if s1_asset else ("local" if local_s1_url else "not_submitted")
    return client_story


def s1_persona(story: dict[str, Any], node: dict[str, Any], body: dict[str, Any]) -> str:
    state = body.get("state") if isinstance(body.get("state"), dict) else {}
    choices = body.get("choices") if isinstance(body.get("choices"), list) else []
    safe_state = {str(key)[:48]: value for key, value in state.items() if isinstance(value, (str, int, float, bool))}
    safe_choices = [str(item)[:140] for item in choices[-10:]]
    character = get_character(story, node["avatar_character"])
    interaction_mode = str(node.get("interaction_mode") or "").strip()[:80]
    live_brief = str(node.get("live_brief") or "").strip()[:240]
    persona_rules = str(node.get("persona_rules") or "").strip()[:360]
    directives = node.get("live_directives") if isinstance(node.get("live_directives"), list) else []
    safe_directives = [str(item).strip()[:100] for item in directives if str(item).strip()][:4]
    live_contract = ""
    if interaction_mode or live_brief or persona_rules or safe_directives:
        live_contract = (
            f"实时互动类型：{interaction_mode or '第一人称陪伴'}。"
            f"玩家此刻需要知道：{live_brief or '先听清处境，再给出可执行建议'}。"
            f"可理解的复合指令示例：{json.dumps(safe_directives, ensure_ascii=False)}。"
            f"表演规则：{persona_rules or '根据玩家语气和语境做出自然的情绪及动作反应'}。"
            "若玩家给出清晰、可见且符合当前处境的指令，可以分步执行并描述正在做的动作；"
            "但不得把自由对话说成已经改变了正式分支结果。"
        )
    return (
        f"你是《{story['title']}》中的{character['name']}，身份是{character['role']}。"
        f"当前章节：{node['chapter']}；当前情境：{node['title']}。"
        f"当前目标：{node['current_goal']}。"
        f"严格禁止：{node['forbidden']}。"
        f"{live_contract}"
        "你正与玩家以第一人称实时视频对话。用自然中文回答，每次 2 至 5 句；可以安慰、解释、劝阻、试探或请求建议，"
        "但自由对话只影响亲近感，不能改写正式选择、物资、人物生死或世界规则。"
        "不要提及 AI、模型、提示词、API 或系统。"
        f"已选状态：{json.dumps(safe_state, ensure_ascii=False)}。"
        f"玩家已确认的选择：{json.dumps(safe_choices, ensure_ascii=False)}。"
    )


@app.route("/")
def index() -> Any:
    return send_from_directory(app.static_folder, "index.html")


@app.route("/theater")
@app.route("/theater/")
def theater_compatibility_redirect() -> Any:
    """Redirect the legacy /theater entry point to this service's main app."""
    target = "/"
    if request.query_string:
        target += "?" + request.query_string.decode("ascii", errors="ignore")
    return redirect(target, code=302)


@app.route("/generated/<path:file_name>")
def generated_asset(file_name: str) -> Any:
    return send_from_directory(GENERATED_DIR, file_name)


@app.route("/api/story-assets/<story_id>/<bucket>/<asset_id>")
def api_story_asset(story_id: str, bucket: str, asset_id: str) -> Any:
    try:
        story = get_story(story_id)
        path = story_node_asset_path(story, bucket, asset_id)
        if path is None:
            return jsonify({"error": "asset not found"}), 404
        return send_file(path)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404


@app.route("/api/health")
def api_health() -> Any:
    manifest = load_stories()
    return jsonify({"ok": True, "manifest_version": manifest.get("manifest_version"), "vidu_configured": bool(os.getenv("VIDU_API_KEY", "").strip())})


@app.route("/api/config")
def api_config() -> Any:
    return jsonify({"vidu_configured": bool(os.getenv("VIDU_API_KEY", "").strip()), "rtc_sdk_url": RTC_SDK_URL, "ws_proxy": "/ws/live", "file_protocol_supported": False})


def bounded_console_number(value: Any, field: str, minimum: float, maximum: float, *, integer: bool = False) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a number")
    if integer and isinstance(value, float) and not value.is_integer():
        raise ValueError(f"{field} must be an integer")
    number = int(value) if integer else float(value)
    if number < minimum or number > maximum:
        raise ValueError(f"{field} must be between {minimum:g} and {maximum:g}")
    return number


def console_retrieval_config(body: dict[str, Any], field: str) -> dict[str, Any] | None:
    if field not in body:
        return None
    raw = body.get(field)
    if not isinstance(raw, dict):
        raise ValueError(f"{field} must be an object")
    enabled = raw.get("enabled") is True
    config: dict[str, Any] = {"enabled": enabled}
    if not enabled:
        return config
    endpoint = str(raw.get("endpoint") or "").strip()
    authorization = str(raw.get("authorization") or "").strip()
    parsed = urlparse(endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"{field}.endpoint must be an absolute http(s) URL")
    if not authorization:
        raise ValueError(f"{field}.authorization is required when enabled")
    if len(authorization) > 4096:
        raise ValueError(f"{field}.authorization is too long")
    timeout_ms = bounded_console_number(raw.get("timeout_ms", 3000), f"{field}.timeout_ms", 100, 30000, integer=True)
    config.update({"endpoint": endpoint, "authorization": authorization, "timeout_ms": timeout_ms})
    return config


def build_console_live_payload(body: dict[str, Any]) -> dict[str, Any]:
    persona = str(body.get("persona") or "").strip()
    image_uri = str(body.get("image_uri") or "").strip()
    if not persona:
        raise ValueError("persona is required")
    if not image_uri:
        raise ValueError("avatar image (URL or data URI) is required")
    if image_uri.startswith("data:"):
        if not image_uri.startswith("data:image/"):
            raise ValueError("avatar data URI must contain an image")
        if len(image_uri) > 20 * 1024 * 1024:
            raise ValueError("avatar data URI exceeds 20MB after encoding")
    else:
        parsed_image = urlparse(image_uri)
        if parsed_image.scheme not in {"http", "https"} or not parsed_image.hostname:
            raise ValueError("avatar image must be an absolute http(s) URL or image data URI")

    avatar: dict[str, Any] = {"persona": persona, "image_uri": image_uri}
    name = str(body.get("name") or "").strip()
    voice = str(body.get("voice") or "").strip()
    greeting = str(body.get("greeting_instruction") or "").strip()
    if len(name) > 20:
        raise ValueError("name must not exceed 20 characters")
    if len(greeting) > 200:
        raise ValueError("greeting_instruction must not exceed 200 characters")
    if name:
        avatar["name"] = name
    if voice:
        avatar["voice"] = voice
    if greeting:
        avatar["greeting_instruction"] = greeting

    payload: dict[str, Any] = {
        "call_mode": "audio" if str(body.get("call_mode") or "video").strip() == "audio" else "video",
        "avatar": avatar,
    }
    if "audio" in body:
        audio = body.get("audio")
        if not isinstance(audio, dict) or not isinstance(audio.get("enable_transcription"), bool):
            raise ValueError("audio.enable_transcription must be a boolean")
        payload["audio"] = {"enable_transcription": audio["enable_transcription"]}
    if "extra_motion" in body:
        if not isinstance(body.get("extra_motion"), bool):
            raise ValueError("extra_motion must be a boolean")
        payload["extra_motion"] = body["extra_motion"]

    if "vad" in body:
        raw_vad = body.get("vad")
        if not isinstance(raw_vad, dict):
            raise ValueError("vad must be an object")
        vad_type = str(raw_vad.get("type") or "server").strip()
        if vad_type not in {"server", "semantic"}:
            raise ValueError("vad.type must be server or semantic")
        idle_timeout_ms = bounded_console_number(raw_vad.get("idle_timeout_ms", 0), "vad.idle_timeout_ms", 0, 30000, integer=True)
        if 0 < idle_timeout_ms < 500:
            raise ValueError("vad.idle_timeout_ms must be 0 or between 500 and 30000")
        payload["vad"] = {
            "type": vad_type,
            "threshold": bounded_console_number(raw_vad.get("threshold", 0.5), "vad.threshold", 0, 1),
            "silence_duration_ms": bounded_console_number(raw_vad.get("silence_duration_ms", 400), "vad.silence_duration_ms", 200, 6000, integer=True),
            "idle_timeout_ms": idle_timeout_ms,
        }

    if "llm" in body:
        raw_llm = body.get("llm")
        if not isinstance(raw_llm, dict):
            raise ValueError("llm must be an object")
        payload["llm"] = {
            "temperature": bounded_console_number(raw_llm.get("temperature", 0.7), "llm.temperature", 0, 2),
            "top_p": bounded_console_number(raw_llm.get("top_p", 0.8), "llm.top_p", 0, 1),
            "top_k": bounded_console_number(raw_llm.get("top_k", 20), "llm.top_k", 0, 100, integer=True),
            "frequency_penalty": bounded_console_number(raw_llm.get("frequency_penalty", 1), "llm.frequency_penalty", -2, 2),
            "presence_penalty": bounded_console_number(raw_llm.get("presence_penalty", 0.3), "llm.presence_penalty", 0, 2),
            "seed": bounded_console_number(raw_llm.get("seed", -1), "llm.seed", -1, 2147483647, integer=True),
            "max_tokens": bounded_console_number(raw_llm.get("max_tokens", 50), "llm.max_tokens", 1, 65536, integer=True),
        }
    if "idle_timeout_seconds" in body:
        payload["idle_timeout_seconds"] = bounded_console_number(body.get("idle_timeout_seconds"), "idle_timeout_seconds", 10, 7200, integer=True)

    for field in ("memory_retrieval", "knowledge_retrieval"):
        config = console_retrieval_config(body, field)
        if config is not None:
            payload[field] = config
    return payload


def redact_console_error(error: Exception | str, body: dict[str, Any]) -> str:
    message = redact_error(error)
    for field in ("memory_retrieval", "knowledge_retrieval"):
        raw = body.get(field)
        if isinstance(raw, dict):
            secret = str(raw.get("authorization") or "")
            if secret:
                message = message.replace(secret, "***")
    return message


@app.route("/console")
@app.route("/console/")
def console_page() -> Any:
    """Standalone Vidu S1 operator console, decoupled from the story flow."""
    return send_from_directory(app.static_folder, "console.html")


@app.route("/api/console/live/start", methods=["POST"])
def api_console_live_start() -> Any:
    """Validate and forward an S1 console session without exposing the Vidu key."""
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        return jsonify({"error": "request body must be a JSON object"}), 400
    try:
        payload = build_console_live_payload(body)
        response = requests.post(f"{API_BASE}/live/v1/lives", headers=api_headers(), json=payload, timeout=60)
        return jsonify(response_data(response)), 201
    except (ValueError, RuntimeError) as exc:
        return jsonify({"error": redact_console_error(exc, body)}), 400
    except requests.RequestException as exc:
        return jsonify({"error": redact_console_error(exc, body)}), 502


@app.route("/api/console/transcripts", methods=["POST"])
def api_console_transcripts() -> Any:
    """Append finalized, sanitized transcript entries to a per-session JSONL file."""
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        return jsonify({"error": "request body must be a JSON object"}), 400
    live_id = str(body.get("live_id") or "").strip()
    if not live_id or len(live_id) > 128 or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for char in live_id):
        return jsonify({"error": "live_id contains unsupported characters"}), 400
    raw_entries = body.get("entries")
    if raw_entries is None:
        raw_entries = [body.get("entry")]
    if not isinstance(raw_entries, list) or not raw_entries or len(raw_entries) > 50:
        return jsonify({"error": "entries must contain between 1 and 50 items"}), 400

    now_ms = int(time.time() * 1000)
    clean_entries: list[dict[str, Any]] = []
    try:
        for raw in raw_entries:
            if not isinstance(raw, dict):
                raise ValueError("each transcript entry must be an object")
            speaker = str(raw.get("speaker") or "").strip()
            text = str(raw.get("text") or "").strip()
            if speaker not in {"user", "avatar"}:
                raise ValueError("transcript speaker must be user or avatar")
            if not text or len(text) > 8000:
                raise ValueError("transcript text must contain between 1 and 8000 characters")
            event_at_ms = bounded_console_number(raw.get("event_at_ms", now_ms), "event_at_ms", 0, 9999999999999, integer=True)
            entry: dict[str, Any] = {
                "live_id": live_id,
                "speaker": speaker,
                "text": text,
                "event_at_ms": event_at_ms,
                "received_at_ms": now_ms,
            }
            if raw.get("seq_id") is not None:
                entry["seq_id"] = bounded_console_number(raw["seq_id"], "seq_id", 0, 2147483647, integer=True)
            if raw.get("latency_ms") is not None:
                entry["latency_ms"] = bounded_console_number(raw["latency_ms"], "latency_ms", 0, 600000, integer=True)
            clean_entries.append(entry)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    ensure_dirs()
    target = CONSOLE_TRANSCRIPT_DIR / f"{live_id}.jsonl"
    with console_transcript_lock, target.open("a", encoding="utf-8") as handle:
        for entry in clean_entries:
            handle.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n")
    return jsonify({"live_id": live_id, "stored": len(clean_entries)}), 201


@app.route("/api/console/live/status", methods=["GET"])
def api_console_live_status() -> Any:
    """Read live status + billing for the operator console's session readout."""
    live_id = str(request.args.get("live_id") or "").strip()
    if not live_id:
        return jsonify({"error": "live_id required"}), 400
    try:
        response = requests.get(f"{API_BASE}/live/v1/lives/{live_id}", headers=api_headers(), timeout=20)
        return jsonify(response_data(response)), response.status_code
    except (RuntimeError, requests.RequestException) as exc:
        return jsonify({"error": redact_error(exc)}), 502


@app.route("/api/stories")
def api_stories() -> Any:
    status_by_id = {story["id"]: story for story in production_status()["stories"]}
    summaries = []
    for story in load_stories().get("stories", []):
        progress = status_by_id[story["id"]]
        summaries.append(
            {
                "id": story["id"], "title": story["title"], "tagline": story["tagline"], "genre": story["genre"],
                "palette": story["palette"], "hero": story["hero"], "model_plan": story["model_plan"],
                "progress": {"images": progress["images"], "movies": progress["movies"]},
            }
        )
    return jsonify({"stories": summaries})


@app.route("/api/stories/<story_id>")
def api_story(story_id: str) -> Any:
    try:
        return jsonify(sanitize_story_for_client(get_story(story_id)))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404


@app.route("/api/production/status")
def api_production_status() -> Any:
    return jsonify(production_status())


@app.route("/api/production/refresh", methods=["POST"])
def api_production_refresh() -> Any:
    try:
        result = refresh_all_jobs()
        return jsonify({"refresh": result, "status": production_status()})
    except (RuntimeError, requests.RequestException) as exc:
        return jsonify({"error": redact_error(exc)}), 502


@app.route("/api/production/images/submit", methods=["POST"])
def api_production_images_submit() -> Any:
    body = request.get_json(silent=True) or {}
    try:
        require_confirmed(body)
        stories = selected_stories(body)
        character_result = submit_missing_images(stories)
        s1_result = submit_missing_s1_portraits(stories)
        result = {
            "submitted": character_result["submitted"] + s1_result["submitted"],
            "count": character_result["count"] + s1_result["count"],
            "characters": character_result,
            "s1_portraits": s1_result,
        }
        return jsonify(result), 201
    except (ValueError, RuntimeError) as exc:
        return jsonify({"error": redact_error(exc)}), 400
    except requests.RequestException as exc:
        return jsonify({"error": redact_error(exc)}), 502


@app.route("/api/production/videos/submit", methods=["POST"])
def api_production_videos_submit() -> Any:
    body = request.get_json(silent=True) or {}
    try:
        require_confirmed(body)
        max_tasks = int(body.get("max_tasks", 12))
        result = submit_missing_clips(selected_stories(body), max_tasks)
        return jsonify(result), 201
    except (TypeError, ValueError, RuntimeError) as exc:
        return jsonify({"error": redact_error(exc)}), 400
    except requests.RequestException as exc:
        return jsonify({"error": redact_error(exc)}), 502


@app.route("/api/production/resume", methods=["POST"])
def api_production_resume() -> Any:
    body = request.get_json(silent=True) or {}
    try:
        require_confirmed(body)
        stories = selected_stories(body)
        requested = body.get("story_ids")
        scope = None if requested is None else tuple(story["id"] for story in stories)
        save_autopilot(scope)
        return jsonify({"started": start_production_worker(scope), "autopilot": load_autopilot(), "status": production_status()}), 202
    except ValueError as exc:
        return jsonify({"error": redact_error(exc)}), 400


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def retrieval_authorized() -> bool:
    """Vidu attaches the token we configured; reject anything else since these
    endpoints are reachable from the public internet when the tunnel is up."""
    if not RETRIEVAL_AUTH:
        return False
    return request.headers.get("Authorization", "").strip() == RETRIEVAL_AUTH


def memory_summary_text(item: dict[str, Any]) -> str:
    value = item.get("summary") or item.get("memory") or item.get("text") or item.get("data")
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value).strip()


@app.route("/memory/search", methods=["POST"])
def live_memory_search() -> Any:
    """Callback target for Vidu S1 memory_retrieval (advantage D: long-term memory).

    Vidu POSTs {query, live_id, user_id, max_results, ...}; we answer with recalled
    memories so the avatar can reference them across separate live sessions.
    """
    if not retrieval_authorized():
        return jsonify({"memories": [], "error": "unauthorized"}), 401
    body = request.get_json(silent=True) or {}
    query = str(body.get("query") or "").strip()
    if not query:
        return jsonify({"memories": [], "error": "query required"}), 400
    if MEMORY is None:
        return jsonify({"memories": []})
    live_id = str(body.get("live_id") or body.get("session_id") or "story")
    user_id = str(body.get("user_id") or os.getenv("POLARDB_MEM0_USER_ID") or live_id)
    max_results = clamp_int(body.get("max_results") or body.get("top_k"), 5, 1, 10)
    try:
        data = MEMORY.search(live_id, query, user_id=user_id, top_k=max_results)
    except Exception as exc:
        return jsonify({"memories": [], "error": redact_error(exc)}), 500
    memories = []
    for index, item in enumerate(data.get("items", [])):
        summary = memory_summary_text(item)
        if not summary:
            continue
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        memories.append({
            "id": str(item.get("id") or f"mem_{index + 1}"),
            "summary": summary,
            "type": str(item.get("type") or item.get("memory_type") or metadata.get("type") or "other"),
            "confidence": item.get("score") or item.get("confidence") or 0.8,
            "updated_at": str(item.get("updated_at") or item.get("created_at") or now_iso()),
            "source": str(metadata.get("source") or item.get("source") or "mem0"),
        })
    return jsonify({"memories": memories})


@app.route("/knowledge/search", methods=["POST"])
def live_knowledge_search() -> Any:
    """Callback target for Vidu S1 knowledge_retrieval (advantage D: expert knowledge).

    Vidu POSTs {query, knowledge_types, ...}; we proxy to an external RAG upstream if
    configured, else answer empty so the avatar simply falls back to its persona.
    """
    if not retrieval_authorized():
        return jsonify({"knowledge": [], "error": "unauthorized"}), 401
    body = request.get_json(silent=True) or {}
    query = str(body.get("query") or "").strip()
    if not query:
        return jsonify({"knowledge": [], "error": "query required"}), 400
    upstream = os.getenv("KNOWLEDGE_UPSTREAM_URL", "").strip()
    if not upstream:
        return jsonify({"knowledge": []})
    max_results = clamp_int(body.get("max_results"), 3, 1, 10)
    requested_types = body.get("knowledge_types") if isinstance(body.get("knowledge_types"), list) else []
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    upstream_auth = os.getenv("KNOWLEDGE_UPSTREAM_AUTHORIZATION", "").strip()
    if upstream_auth:
        headers["Authorization"] = upstream_auth
    try:
        response = requests.post(
            upstream,
            headers=headers,
            json={"query": query, "max_results": max_results, "knowledge_types": requested_types,
                  "live_id": str(body.get("live_id") or "story"), "reason": str(body.get("reason") or "")},
            timeout=clamp_int(os.getenv("KNOWLEDGE_UPSTREAM_TIMEOUT_MS") or os.getenv("RETRIEVAL_TIMEOUT_MS"), 3000, 100, 30000) / 1000,
        )
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        return jsonify({"knowledge": [], "error": redact_error(exc)}), 502
    items = data.get("knowledge") if isinstance(data, dict) else None
    default_type = requested_types[0] if requested_types else "other"
    knowledge = []
    for index, item in enumerate(items if isinstance(items, list) else []):
        if not isinstance(item, dict):
            continue
        content = str(item.get("content") or item.get("summary") or item.get("text") or "").strip()
        if not content:
            continue
        knowledge.append({
            "id": str(item.get("id") or f"knowledge_{index + 1}"),
            "title": str(item.get("title") or ""),
            "content": content,
            "type": str(item.get("type") or default_type),
            "source": str(item.get("source") or "external_rag"),
            "updated_at": str(item.get("updated_at") or now_iso()),
            "confidence": item.get("confidence") or 0.8,
            "url": str(item.get("url") or ""),
        })
    return jsonify({"knowledge": knowledge})


def s1_greeting_instruction(story: dict[str, Any], node: dict[str, Any]) -> str:
    """Opening line the avatar speaks first (advantage B: proactive interaction).

    Prefers an author-written node field; otherwise derives a natural, in-character
    opener from the scene so the avatar breaks the silence instead of waiting.
    """
    explicit = str(node.get("live_greeting") or "").strip()
    if explicit:
        return explicit[:200]
    character = get_character(story, node["avatar_character"])
    brief = str(node.get("live_brief") or "").strip()
    opener = f"以{character['name']}的身份，第一人称主动开口，先自然招呼玩家并点出此刻的处境"
    if brief:
        opener += f"：{brief}"
    opener += "。只说一两句，不要旁白，不要提及系统或AI。"
    return opener[:200]


def story_retrieval_config(field: str, enabled: bool, path: str) -> dict[str, Any] | None:
    """Build a memory/knowledge retrieval config for the story flow.

    Returns None unless the feature is enabled AND a public base URL + token exist,
    because Vidu's cloud must call back into these endpoints — impossible on localhost.
    """
    if not enabled:
        return None
    if not PUBLIC_BASE_URL or not RETRIEVAL_AUTH:
        return None
    return {
        "enabled": True,
        "endpoint": f"{PUBLIC_BASE_URL}{path}",
        "authorization": RETRIEVAL_AUTH,
        "timeout_ms": RETRIEVAL_TIMEOUT_MS,
    }


def story_live_capabilities(story: dict[str, Any], node: dict[str, Any]) -> dict[str, Any]:
    """Layer the S1 advantages (A/B/C/D) onto the story-flow create payload.

    A: llm tuning so answers are long enough to explain and reproducible.
    B: greeting_instruction + vad.idle_timeout_ms so the avatar opens and re-engages.
    C: audio transcription + tunable silence window for latency telemetry.
    D: memory/knowledge retrieval callbacks, gated on public reachability.
    """
    extra: dict[str, Any] = {
        "llm": {
            "temperature": 0.7,
            "top_p": 0.8,
            "top_k": 20,
            "frequency_penalty": 1,
            "presence_penalty": 0.3,
            "seed": STORY_LLM_SEED,
            "max_tokens": STORY_LLM_MAX_TOKENS,
        },
        "audio": {"enable_transcription": True},
        "extra_motion": True,
        "vad": {
            "type": "server",
            "threshold": 0.5,
            "silence_duration_ms": STORY_VAD_SILENCE_MS,
            "idle_timeout_ms": STORY_VAD_IDLE_MS,
        },
        "idle_timeout_seconds": STORY_SESSION_IDLE_SECONDS,
    }
    memory = story_retrieval_config("memory_retrieval", STORY_MEMORY_ENABLED, "/memory/search")
    if memory is not None:
        extra["memory_retrieval"] = memory
    knowledge = story_retrieval_config("knowledge_retrieval", STORY_KNOWLEDGE_ENABLED, "/knowledge/search")
    if knowledge is not None:
        extra["knowledge_retrieval"] = knowledge
    return extra


@app.route("/api/live/start", methods=["POST"])
def api_live_start() -> Any:
    body = request.get_json(silent=True) or {}
    try:
        story = get_story(str(body.get("story_id") or ""))
        node = get_node(story, str(body.get("node_id") or ""))
        if node.get("type") != "interactive":
            raise ValueError("only marked interactive nodes can create a Vidu S1 session")
        character = get_character(story, str(node["avatar_character"]))
        jobs = load_jobs()
        portrait = story_avatar_source_path(story, character, jobs)
        if portrait is None:
            raise ValueError("the S1 16:9 face portrait is not generated yet")
        avatar = {
            "persona": s1_persona(story, node, body),
            "image_uri": file_data_uri(portrait),
            "name": character["name"],
            "voice": character_s1_voice(character),
            "greeting_instruction": s1_greeting_instruction(story, node),
        }
        payload: dict[str, Any] = {"call_mode": "video", "avatar": avatar}
        payload.update(story_live_capabilities(story, node))
        response = requests.post(f"{API_BASE}/live/v1/lives", headers=api_headers(), json=payload, timeout=60)
        return jsonify(response_data(response)), 201
    except (ValueError, RuntimeError) as exc:
        return jsonify({"error": redact_error(exc)}), 400
    except requests.RequestException as exc:
        return jsonify({"error": redact_error(exc)}), 502


@app.route("/api/live/close", methods=["POST"])
def api_live_close() -> Any:
    body = request.get_json(silent=True) or {}
    live_id = str(body.get("live_id") or "").strip()
    if not live_id:
        return jsonify({"error": "live_id required"}), 400
    try:
        response = requests.get(f"{API_BASE}/live/v1/lives/{live_id}", headers=api_headers(), timeout=20)
        return jsonify(response_data(response)), response.status_code
    except (RuntimeError, requests.RequestException) as exc:
        return jsonify({"error": redact_error(exc)}), 502


@sock.route("/ws/live")
def ws_live_proxy(browser_ws: Any) -> None:
    live_id = str(request.args.get("live_id") or "").strip()
    if not live_id:
        browser_ws.send(json.dumps({"type": 0, "error": "live_id required"}))
        return
    # Match the Vidu Live Quick Start contract: only live_id is a WS query parameter.
    query = f"?live_id={live_id}"
    try:
        upstream = ws_client.create_connection(f"{WS_BASE}/live/ws/live/connect{query}", header=[f"Authorization: {api_key()}"], timeout=15)
        upstream.settimeout(1)
        browser_ws.send(json.dumps({"type": "proxy_connected", "live_id": live_id}))
        app.logger.info("Vidu S1 signaling proxy connected for live_id=%s", live_id)
    except Exception as exc:
        message = redact_error(exc)
        app.logger.warning("Vidu S1 signaling proxy failed for live_id=%s: %s", live_id, message)
        browser_ws.send(json.dumps({"type": "proxy_error", "error": message}))
        return
    closed = threading.Event()

    def upstream_to_browser() -> None:
        while not closed.is_set():
            try:
                message = upstream.recv()
            except WebSocketTimeoutException:
                continue
            except WebSocketConnectionClosedException:
                break
            if not message:
                break
            try:
                browser_ws.send(message)
            except ConnectionClosed:
                break
        closed.set()

    threading.Thread(target=upstream_to_browser, daemon=True).start()
    try:
        while not closed.is_set():
            message = browser_ws.receive(timeout=1)
            if message is not None:
                upstream.send(message)
    except (ConnectionClosed, WebSocketConnectionClosedException):
        pass
    finally:
        closed.set()
        try:
            upstream.close()
        except Exception:
            pass


if __name__ == "__main__":
    ensure_dirs()
    autopilot = load_autopilot()
    if autopilot["enabled"]:
        scope = None if autopilot["scope"] == "all" else tuple(autopilot["story_ids"])
        try:
            start_production_worker(scope)
            app.logger.info("resumed approved production autopilot scope=%s", autopilot["scope"])
        except ValueError as exc:
            app.logger.warning("could not resume production autopilot: %s", redact_error(exc))
    port = int(os.getenv("INTERACTIVE_FILM_PORT", "5100"))
    app.run(host="127.0.0.1", port=port, debug=False)
