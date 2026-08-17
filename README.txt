Vidu interactive film game - pre-generated FMV production workflow

Open the experience through the local Flask server, not file://:

  set VIDU_API_KEY=vda_your_key
  py -3.14 app.py
  start http://127.0.0.1:5100/

The supplied API key is never written to this project. Put it in the process
environment or an untracked .env file with VIDU_API_KEY=... before starting.

Production order

1. Open the production queue and click "生成全部角色图". This submits the eight
   viduimage-2 protagonist / focal-NPC portrait tasks after an explicit browser
   confirmation.
2. Use "刷新任务状态" until all portraits are ready.
3. Click "提交下一批 Q3 分镜" for a small batch, or "继续全量生产" to start the
   resumable worker. It submits legal five-second Q3 Mix / Q3 Drama jobs only
   after the needed portraits exist, and never re-submits an existing task ID.
4. Refresh again. Each 15-second storyboard is composed from its three
   consecutive five-second source clips with ffmpeg and becomes playable in the
   FMV experience.

Approved full-production autopilot

When "continue full production" is confirmed without story_ids, the app stores
an explicit all-story authorization in data/production-autopilot.json. The
worker then keeps polling existing Vidu task IDs, submits only missing character
images, S1 portraits, and Q3 clips, and keeps composing missing 15-second movies.
It resumes the same scope after a local server restart and never re-submits an
existing task ID. Delete production-autopilot.json only if you intentionally
want to stop automatic paid follow-up submissions.

The manifest contains four five-chapter stories, 60 pre-generated cutscenes,
180 Q3 clip tasks, and 20 S1-only emotional / consequential interaction nodes.
S1 is never pre-generated: it is created only when a player reaches a marked
node, with current chapter, formal state, selected choices, and spoiler limits
passed to the server-side persona.

If ffmpeg is not on PATH, set FFMPEG_PATH to its executable before starting.
No video generation or live session is submitted automatically on app launch.

RedNote story bundle

The three new six-episode stories are generated into data/story.json. To run
that bundle without replacing the original four stories:

  $env:STORY_FILE='C:\Users\26670\Documents\vidu-demo\interactive-film-game\data\story.json'
  $env:VIDU_API_KEY='your_key'
  py -3 app.py

The bundle can also be copied into a different manifest loader because it
keeps the same manifest_version 2, stories, nodes, Q3 render_plan, S1, choice,
and ending fields as data/stories.json.

Validation

  py -3.14 tools\build_manifest.py --check
  py -3.14 -m unittest discover -s tests -v
  py -3.14 -m py_compile app.py tools\build_manifest.py
  node browser_check.cjs
