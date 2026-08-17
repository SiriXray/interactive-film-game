"""Seed the sci-fi S1 story import without submitting any Vidu generation task."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

from build_manifest import build_story, validate


ROOT = Path(__file__).resolve().parents[1]
IMPORTS_DIR = ROOT / "data" / "imports"
CURRENT_MANIFEST = ROOT / "data" / "stories.json"
STORY_ID = "zero-hour-link"
LEGACY_STORY_ID = "heart-voice-divorce"


SPEC: dict[str, Any] = {
    "id": STORY_ID,
    "title": "零时联线：暗夜庇护所",
    "tagline": "隔着一层监控玻璃，把她从尸潮、寒潮与谎言里带回来。",
    "genre": "末世生存 / 实时指挥 / 心理干预",
    "palette": "apocalypse",
    "skin": "sci-fi-apocalypse",
    "hero": "苏野",
    "hero_character": "su-ye",
    "model_plan": "剧情段落由 15 秒 Q3 Mix / Q3 Drama 预生成；S1 用于静默复合动作指挥、情绪共调和高压谈判。实时对话影响角色关系与表演，正式选择才改变世界状态。",
    "state_labels": {
        "noise": "噪声暴露",
        "trust": "同伴信任",
        "anchor": "心理锚点",
        "evidence": "疫苗线索",
    },
    "initial_state": {"noise": 0, "trust": 0, "anchor": 0, "evidence": 0},
    "characters": [
        {
            "id": "su-ye",
            "name": "苏野",
            "role": "庇护所外勤救援员，右臂受伤后被困一楼大厅",
            "voice": "Qiao",
            "image_prompt": "Vertical 9:16 cinematic apocalypse character key art, Su Ye, East Asian woman late twenties, athletic emergency rescue worker with a short dark bob, alert expressive eyes, worn navy rescue jacket with a small white medical patch, right upper arm bandaged, holding a dim flashlight in a ruined shelter lobby, cold blue emergency light and distant red alarm glow, realistic live-action drama, single subject, no text, no watermark.",
        },
        {
            "id": "luo-qian",
            "name": "罗谦",
            "role": "富人区安保队长，掌握疫苗冷库的通行权限",
            "voice": "Andre",
            "image_prompt": "Vertical 9:16 cinematic post-apocalypse security character key art, Luo Qian, East Asian man early thirties, precise guarded expression, dark security uniform under a rain-stained tactical coat, compact rifle lowered but ready, a biometric access badge at his collar, sterile luxury corridor with broken white light, realistic live-action drama, single subject, no text, no watermark.",
        },
        {
            "id": "dr-an",
            "name": "安博士",
            "role": "地下监控室的流行病学家，知道疫苗批次的真相",
            "voice": "Joseph Chen",
            "image_prompt": "Vertical 9:16 cinematic post-apocalypse scientist character key art, Dr. An, East Asian man in his forties with tired kind eyes, gray thermal shirt under a worn lab vest, holding an old tablet with a vaccine inventory map, underground monitoring room lit by cyan screens, realistic live-action drama, single subject, no text, no watermark.",
        },
    ],
    "ending": {
        "title": "信号没有熄灭",
        "text": "你没有替她们承担每一个选择，却让每一句指令、每一次沉默和每一次安慰，都在最后的门前留下了重量。",
        "variants": [
            {
                "when": {"trust": 3, "anchor": 2, "evidence": 2},
                "title": "救援编号 07",
                "text": "苏野带着疫苗穿过黎明前的隔离区。她在通讯里叫出你的名字，安博士把这条路线标成了下一支救援队的生路。",
            },
            {
                "when": {"evidence": 3},
                "title": "疫苗窄门",
                "text": "你们拿到了冷库和批次记录，却不得不在封锁落下前离开。真相被带出富人区，代价是这座庇护所再也回不去。",
            },
            {
                "when": {"noise": 2},
                "title": "隔离区火光",
                "text": "警报最终惊动了尸潮。苏野没有变异，却带着未愈的伤口守住了你们争取来的最后一扇门。",
            },
            {
                "when": {},
                "title": "仍在通话中",
                "text": "天亮得很慢。监控屏幕上只剩雪花和一盏微弱的绿灯，但另一端的人还在呼吸，还在等下一句指令。",
            },
        ],
    },
    "chapters": [
        {
            "title": "监控室里的生死连线",
            "setup_title": "一楼的灯灭了",
            "setup_narration": "尸潮撞断了庇护所外门。你被锁在地下监控室，苏野独自留在一楼大厅，右臂的血正沿着袖口往下滴。",
            "setup_cast": ["su-ye"],
            "setup_beats": [
                "A wide view from a damaged security camera: a dark shelter lobby, emergency lights strobing, Su Ye limps behind a checkout counter while silhouettes press against glass doors.",
                "Close on Su Ye pressing a bandaged right arm against her ribs, holding her breath as a loose metal sign trembles above her.",
                "Her earpiece catches the player's voice; she looks up toward a ceiling camera, then notices a fire bottle and a low service passage beside the shelves.",
            ],
            "s1_title": "把声音压到它们听不见",
            "s1_prompt": "苏野贴着货架望向镜头。她需要你给出一条能执行的指令：先做什么、哪只手做、最后往哪里走。",
            "s1_reason": "玩家的语速、音量和复合动作指令会被苏野即时感知。她会用紧张表情、停顿和动作节奏回应，但尸潮结果仍由下一步正式选择确认。",
            "s1_goal": "压低声音，确认她右臂受伤；接受玩家关于下蹲、按住伤口、拿取燃烧瓶或转向服务通道的复合指令。每次只确认当前能看到的动作，不宣布尸潮结果。",
            "s1_forbidden": "不得承诺某条路线一定安全；不得提前引爆燃烧瓶、触发消防栓或宣布尸潮已经发现她；不得增加第三条正式路线。",
            "s1_mode": "静默指挥 / 复合动作",
            "s1_brief": "请用短句、低音量、明确顺序指挥她。你的说话方式会改变她的呼吸、表情和动作节奏。",
            "s1_directives": ["慢慢蹲下", "右手按住伤口", "左手拿燃烧瓶后退到货架后"],
            "s1_start_label": "接通监控",
            "s1_persona_rules": "对清晰的复合动作指令作出可见的分步反应；玩家急躁或高声时表现出惊恐、停顿、压低呼吸并看向门口。",
            "choice_prompt": "监控里，丧尸已经撞碎第一层玻璃。苏野要把哪一种风险留给自己？",
            "options": [
                {
                    "id": "silent-shelves",
                    "label": "熄灭手电，贴着货架静默撤向服务通道",
                    "tone": "survive",
                    "state_delta": {"noise": -2, "trust": 1},
                    "result_title": "货架后的呼吸",
                    "result_narration": "苏野关掉手电，在货架阴影里一点点挪动。撞门声从身后掠过，服务通道的门锁却只开了一道缝。",
                    "result_cast": ["su-ye"],
                    "result_beats": [
                        "Su Ye turns off her flashlight and crouch-walks through a narrow gap between shelves, breathing through clenched teeth.",
                        "A zombie silhouette slams into the glass doors as she freezes behind stacked water crates.",
                        "She reaches a half-open service door and slips her fingers around its bent handle without making a sound.",
                    ],
                },
                {
                    "id": "water-diversion",
                    "label": "砸开消防栓，用水流和警报把尸潮引离大厅",
                    "tone": "risk",
                    "state_delta": {"noise": 2, "evidence": 1},
                    "result_title": "水声盖过尖叫",
                    "result_narration": "水柱撞开大厅的尘土，也冲出了墙后被人掩藏的富人区运货标识。尸潮被引向另一边，整栋楼的警报却一起响了。",
                    "result_cast": ["su-ye"],
                    "result_beats": [
                        "Su Ye swings a fire extinguisher into a wall hydrant; a violent stream of water tears across the ruined lobby.",
                        "Alarm lights flare red as shadows turn toward the water spray instead of the service passage.",
                        "Behind the shattered wall panel, a luxury district shipment tag floats in the water at Su Ye's feet.",
                    ],
                },
            ],
        },
        {
            "title": "寒潮里的心跳",
            "setup_title": "别让她一个人听见风",
            "setup_narration": "你们躲进通风井尽头的旧诊室。寒潮从破窗灌进来，苏野的手开始发抖，她说墙里有人在叫她的名字。",
            "setup_cast": ["su-ye", "dr-an"],
            "setup_model": "viduq3-drama",
            "setup_beats": [
                "In a cramped abandoned clinic, Su Ye sits by a weak heater with her knees drawn up while Dr. An searches a frost-covered medicine cabinet.",
                "Wind pushes snow through a cracked window; Su Ye's breath quickens and she stares at a dark doorway as if hearing someone call her.",
                "The monitoring tablet shows a slow pulse line while Dr. An silently signals the player that Su Ye is close to panic.",
            ],
            "s1_title": "先把她带回这一分钟",
            "s1_prompt": "苏野不敢看镜头。她说自己会拖累所有人。现在不是给答案，而是让她重新跟上你的呼吸。",
            "s1_reason": "这是情绪共调节点。玩家可以讲一段具体的未来、带她数呼吸，或坚定地让她看向镜头；S1 应连续呈现从发抖、落泪到重新聚焦的表情流转。",
            "s1_goal": "回应玩家的安抚、陪伴或有节奏的呼吸引导；逐步从惊恐转为能听见指令。保持脆弱但不失行动能力，最后请玩家确认是继续休整还是带伤前进。",
            "s1_forbidden": "不得把安抚直接判成成功或失败；不得说她已经变异、已经痊愈或能无代价继续行动；不得增加第三种正式行动。",
            "s1_mode": "情绪共调 / 心理干预",
            "s1_brief": "不要急着解决问题。用具体、缓慢、可跟随的话把她留在当下。",
            "s1_directives": ["看着我", "吸气四拍，停一拍", "把下一次呼吸留给天亮"],
            "s1_start_label": "接通陪伴",
            "s1_persona_rules": "根据玩家的语气持续改变微表情、肩颈紧张和呼吸节奏；温和、具体的陪伴让她逐步稳定，刺激或沉默让她更难集中。",
            "choice_prompt": "体温还在下降。你们是把时间留给她，还是把机会留给疫苗线索？",
            "options": [
                {
                    "id": "stay-and-breathe",
                    "label": "留在诊室完成一轮休整，等她的呼吸真正稳下来",
                    "tone": "heart",
                    "state_delta": {"trust": 2, "anchor": 2, "noise": -1},
                    "result_title": "掌心的温度",
                    "result_narration": "苏野把手从颤抖的膝盖上移开，第一次主动接过安博士递来的热水。窗外仍是暴风雪，她却能重新听见你的声音。",
                    "result_cast": ["su-ye", "dr-an"],
                    "result_beats": [
                        "Su Ye follows a slow breathing rhythm with eyes closed while the heater's weak orange light warms her face.",
                        "Dr. An wraps a thermal blanket around her shoulders as her hands finally stop shaking.",
                        "Su Ye opens her eyes, grips the flashlight with steadier hands, and nods toward the exit.",
                    ],
                },
                {
                    "id": "move-while-cold",
                    "label": "带伤前进，趁尸潮被引走时追查运货标识",
                    "tone": "risk",
                    "state_delta": {"evidence": 1, "trust": -1, "anchor": -1},
                    "result_title": "冻住的车牌",
                    "result_narration": "你们在地下车库找到一辆富人区冷链车。苏野没有再哭，却把每一次咳嗽都压进了围巾里。",
                    "result_cast": ["su-ye", "dr-an"],
                    "result_beats": [
                        "Su Ye pulls on her rescue jacket and forces herself through the clinic door before the heater dies.",
                        "In an icy underground garage, Dr. An wipes frost from a luxury cold-chain vehicle plate.",
                        "Su Ye leans against the vehicle for one hidden cough, then points the player toward a secure access tunnel.",
                    ],
                },
            ],
        },
        {
            "title": "富人区的白色走廊",
            "setup_title": "通行证在谁的口袋里",
            "setup_narration": "冷链车把你们带进富人区地下入口。疫苗就在白色走廊尽头，安保队长罗谦却拦下苏野，要求她说出不存在的授权编号。",
            "setup_cast": ["su-ye", "luo-qian", "dr-an"],
            "setup_beats": [
                "A sterile white security corridor under flickering lights; Su Ye and Dr. An stand before a sealed vaccine door while Luo Qian blocks the way.",
                "Luo Qian studies Su Ye's blood-stained rescue patch, one hand hovering near a biometric scanner and the other near his lowered weapon.",
                "On a nearby monitor, a vaccine batch list flashes for one second before a lockdown countdown begins.",
            ],
            "s1_title": "让他相信你，或让他暴露自己",
            "s1_prompt": "罗谦盯着镜头问：你们是谁？苏野等你决定这是一场镇定的伪装，还是一次把他的谎言逼出来的谈判。",
            "s1_reason": "玩家的停顿、语速和措辞将影响罗谦的审视、皱眉、上膛或放低武器等实时表演。谈判的正式结果仍由下一步策略确认。",
            "s1_goal": "以冷静、克制的安保队长身份回应；要求玩家给出一致的伪装口径或谈判策略，并根据语气表现怀疑、试探或短暂动摇。只披露当前走廊可见的信息。",
            "s1_forbidden": "不得直接交出疫苗、通行权限或幕后真相；不得提前开枪或宣布谈判成功；不得引入第三种正式策略。",
            "s1_character": "luo-qian",
            "s1_mode": "高压谈判 / 语气识别",
            "s1_brief": "说得越短越好。给出身份、理由和一个能被当场核验的细节。",
            "s1_directives": ["报出研究组身份", "把通行证留在口袋", "请他先核对冷链编号"],
            "s1_start_label": "接通谈判",
            "s1_persona_rules": "根据玩家的语速、停顿和自洽程度表现审视、怀疑、皱眉、短暂放松或手指扣紧武器；不替玩家补全谎言。",
            "choice_prompt": "倒计时只剩四十秒。门前的每个人都握着一半真相。",
            "options": [
                {
                    "id": "trade-the-proof",
                    "label": "交出运货标识，逼罗谦用冷链记录换一次开门机会",
                    "tone": "truth",
                    "state_delta": {"evidence": 2, "trust": 1, "noise": -1},
                    "result_title": "白名单之外",
                    "result_narration": "罗谦看见被隐藏的运货编号，终于把枪口垂下。冷库门开了一条缝，里面不只有疫苗，还有一整份被抹掉的配送名单。",
                    "result_cast": ["su-ye", "luo-qian", "dr-an"],
                    "result_beats": [
                        "Su Ye places the recovered shipment tag on a scanner while Luo Qian watches the screen with a tightening jaw.",
                        "The sealed vaccine door unlocks by a narrow margin, cold vapor pouring into the white corridor.",
                        "Dr. An photographs a hidden distribution list as Luo Qian lowers his weapon and looks toward the alarm light.",
                    ],
                },
                {
                    "id": "break-the-lock",
                    "label": "趁警报切换时强行破门，抢在封锁前拿走疫苗",
                    "tone": "risk",
                    "state_delta": {"evidence": 1, "noise": 2, "anchor": -1},
                    "result_title": "门响得太大",
                    "result_narration": "门锁被撬开的那一刻，走廊也响起了整层楼的警报。苏野抱住疫苗箱，罗谦没有追，却在身后按下了隔离区的红灯。",
                    "result_cast": ["su-ye", "luo-qian"],
                    "result_beats": [
                        "Su Ye and Dr. An force a metal tool into the vaccine door seam as the countdown reaches zero.",
                        "The lock breaks with a loud crack; red alarms flood the corridor while Su Ye grabs a compact vaccine case.",
                        "Luo Qian stands beneath rotating red light and activates a quarantine switch as the team disappears into cold vapor.",
                    ],
                },
            ],
        },
    ],
}


def build_zero_hour_link() -> dict[str, Any]:
    spec = copy.deepcopy(SPEC)
    chapters = spec["chapters"]
    story = build_story(spec)
    for index, chapter in enumerate(chapters, start=1):
        node = story["nodes"][f"{STORY_ID}-c{index}-s1"]
        node.update(
            {
                "interaction_mode": chapter["s1_mode"],
                "live_brief": chapter["s1_brief"],
                "live_directives": chapter["s1_directives"],
                "start_label": chapter["s1_start_label"],
                "persona_rules": chapter["s1_persona_rules"],
            }
        )
    return story


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def migrate_legacy_story() -> bool:
    destination = IMPORTS_DIR / f"{LEGACY_STORY_ID}.story.json"
    if destination.exists():
        return False
    manifest = json.loads(CURRENT_MANIFEST.read_text(encoding="utf-8"))
    story = next((item for item in manifest.get("stories", []) if item.get("id") == LEGACY_STORY_ID), None)
    if story is None:
        raise ValueError(f"{LEGACY_STORY_ID} was not found in {CURRENT_MANIFEST}")
    write_json(destination, story)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed the Zero Hour Link playable S1 story import.")
    parser.add_argument("--check", action="store_true", help="Validate the story without writing files.")
    args = parser.parse_args()
    story = build_zero_hour_link()
    errors = validate({"stories": [story]})
    if errors:
        print("\n".join(errors))
        return 1
    if args.check:
        print(f"ok: {story['id']}, {len(story['nodes'])} nodes, 3 S1 modes")
        return 0
    legacy_created = migrate_legacy_story()
    destination = IMPORTS_DIR / f"{STORY_ID}.story.json"
    write_json(destination, story)
    print(f"wrote {destination}")
    if legacy_created:
        print(f"migrated {IMPORTS_DIR / f'{LEGACY_STORY_ID}.story.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
