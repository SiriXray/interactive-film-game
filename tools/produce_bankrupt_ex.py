"""Drive paid Q3-mix production for the bankrupt-ex story only.

Reuses app.py's production worker so submission, polling, download and ffmpeg
concatenation behave exactly like the in-app autopilot. Scoped to one story so
no other story spends credits. Character and S1 portraits are already seeded
locally, so only the 27 Q3 clips (9 cutscenes x 3) are paid work here.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app  # noqa: E402

STORY_ID = "bankrupt-ex"


def main() -> int:
    scope = (STORY_ID,)
    stories = app.production_scope(scope)
    if not stories:
        print(f"story {STORY_ID} not found in manifest")
        return 1
    print(f"producing scope={scope} (blocking until all movies are local)")
    # Run the same loop the in-app autopilot uses; it returns once every movie
    # in scope is composed locally (or nothing is left to do for 4 rounds).
    app.production_worker_loop(scope)
    status = app.production_status()
    for story in status["stories"]:
        if story["id"] != STORY_ID:
            continue
        print(
            f"images {story['images']['ready']}/{story['images']['total']} "
            f"s1 {story['s1_portraits']['ready']}/{story['s1_portraits']['total']} "
            f"clips {story['clips']['ready']}/{story['clips']['total']} "
            f"movies {story['movies']['ready']}/{story['movies']['total']}"
        )
        for cut in story["cutscenes"]:
            print(f"  {cut['node_id']}: {cut['state']} {cut.get('media_url','')}")
    print(f"failed jobs: {status['totals']['failed']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
