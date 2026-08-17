"""Build the checked-in FMV production manifest from the approved story plan.

The manifest intentionally contains no Vidu credentials. It is deterministic so
that production jobs can resume by stable story, node, and clip identifiers.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "stories.json"
IMPORTS_DIR = ROOT / "data" / "imports"
TARGET_SECONDS = 15
CLIP_SECONDS = 5


def shot_plan(model: str, cast: list[str], beats: list[str]) -> dict[str, Any]:
    """Split one 15-second storyboard into legal, continuous 5-second Q3 clips."""
    if len(beats) != 3:
        raise ValueError("Every Q3 storyboard must have exactly three five-second beats.")
    clips = []
    for index, beat in enumerate(beats, start=1):
        continuity = (
            f"Segment {index} of a continuous three-segment 15-second vertical FMV scene. "
            "Keep faces, costumes, weather, props, lighting, and screen direction consistent with the supplied character references. "
        )
        if index > 1:
            continuity += "Continue directly from the previous segment without a reset or a title card. "
        clips.append(
            {
                "id": f"s{index}",
                "duration": CLIP_SECONDS,
                "model": model,
                "prompt": continuity + beat + " Cinematic Chinese interactive drama, natural motion and sound, no captions, no subtitles, no watermark.",
            }
        )
    return {
        "target_seconds": TARGET_SECONDS,
        "clip_seconds": CLIP_SECONDS,
        "method": "three-continuous-q3-clips-then-concat",
        "cast": cast,
        "clips": clips,
    }


def cutscene(
    chapter: str,
    title: str,
    narration: str,
    model: str,
    cast: list[str],
    beats: list[str],
    next_node: str,
) -> dict[str, Any]:
    return {
        "type": "cutscene",
        "chapter": chapter,
        "title": title,
        "narration": narration,
        "pre_generated": True,
        "render_plan": shot_plan(model, cast, beats),
        "next": next_node,
    }


def interactive(
    chapter: str,
    title: str,
    prompt: str,
    reason: str,
    avatar_character: str,
    current_goal: str,
    forbidden: str,
    next_node: str,
) -> dict[str, Any]:
    return {
        "type": "interactive",
        "chapter": chapter,
        "title": title,
        "prompt": prompt,
        "live_mode": "vidu-s1-first-person",
        "avatar_character": avatar_character,
        "interaction_reason": reason,
        "current_goal": current_goal,
        "forbidden": forbidden,
        "next": next_node,
    }


def build_story(spec: dict[str, Any]) -> dict[str, Any]:
    nodes: dict[str, Any] = {}
    chapters = spec.pop("chapters")
    for chapter_index, chapter in enumerate(chapters, start=1):
        prefix = f"{spec['id']}-c{chapter_index}"
        chapter_label = f"第{chapter_index}章 · {chapter['title']}"
        live_id = f"{prefix}-s1"
        choice_id = f"{prefix}-choice"
        next_setup = f"{spec['id']}-c{chapter_index + 1}-setup" if chapter_index < len(chapters) else f"{spec['id']}-ending"
        nodes[f"{prefix}-setup"] = cutscene(
            chapter_label,
            chapter["setup_title"],
            chapter["setup_narration"],
            chapter.get("setup_model", "viduq3-mix"),
            chapter["setup_cast"],
            chapter["setup_beats"],
            live_id,
        )
        nodes[live_id] = interactive(
            chapter_label,
            chapter["s1_title"],
            chapter["s1_prompt"],
            chapter["s1_reason"],
            chapter.get("s1_character", spec["hero_character"]),
            chapter["s1_goal"],
            chapter["s1_forbidden"],
            choice_id,
        )
        choices = []
        for option_index, option in enumerate(chapter["options"], start=1):
            result_id = f"{prefix}-result-{option_index}"
            choices.append(
                {
                    "id": option["id"],
                    "label": option["label"],
                    "tone": option["tone"],
                    "state_delta": option["state_delta"],
                    "next": result_id,
                }
            )
            nodes[result_id] = cutscene(
                chapter_label + " · 结果",
                option["result_title"],
                option["result_narration"],
                option.get("result_model", "viduq3-drama"),
                option["result_cast"],
                option["result_beats"],
                next_setup,
            )
        nodes[choice_id] = {
            "type": "choice",
            "chapter": chapter_label + " · 正式抉择",
            "title": "正式抉择",
            "prompt": chapter["choice_prompt"],
            "options": choices,
        }

    nodes[f"{spec['id']}-ending"] = {
        "type": "ending",
        "chapter": "终局",
        "title": spec["ending"]["title"],
        "text": spec["ending"]["text"],
        "variants": spec["ending"]["variants"],
    }
    spec["start"] = f"{spec['id']}-c1-setup"
    spec["nodes"] = nodes
    return spec


def story_specs() -> list[dict[str, Any]]:
    return [
        {
            "id": "snow-border",
            "title": "雪关有田，养出战神",
            "tagline": "在冻土、狼群与军令之间，替她守住一村人的春天。",
            "genre": "边关异能 / 生存 / 战神",
            "palette": "snow",
            "hero": "沈知禾",
            "hero_character": "shen-zhihe",
            "model_plan": "所有剧情均为 15 秒预生成 Q3 Mix / Q3 Drama 成片；五个会影响人命、战局或信任的节点，才开启 S1 第一人称对话。",
            "state_labels": {"food": "粮食", "trust": "战神信任", "risk": "异兽与敌军风险", "secret": "灵田秘密"},
            "initial_state": {"food": 0, "trust": 0, "risk": 0, "secret": 0},
            "characters": [
                {
                    "id": "shen-zhihe",
                    "name": "沈知禾",
                    "role": "将门遗女，灵田异能者",
                    "voice": "Qiao",
                    "s1_voice": "Hana",
                    "image_prompt": "Vertical 9:16 cinematic Chinese historical character key art, Shen Zhihe, a resilient woman in her mid twenties, intelligent dark eyes, weathered charcoal exile robe layered with a faded blue military cloak, loose black hair tied with a worn bronze military tag, a faint green life-vein glow beneath one palm, snowy frontier wind, upper body and hands clearly visible, realistic period drama, no text, no watermark.",
                },
                {
                    "id": "lu-chenchuan",
                    "name": "陆沉川",
                    "role": "失忆巨汉，八尺战神",
                    "voice": "Dylan",
                    "image_prompt": "Vertical 9:16 cinematic Chinese historical character key art, Lu Chenchuan, an exceptionally tall broad-shouldered warrior in his early thirties, stern kind face with a scar at the brow, long dark hair, torn black frontier armor under a fur cloak, a steel wolf pendant, snow on his shoulders, powerful but wounded, realistic period drama, no text, no watermark.",
                },
            ],
            "ending": {
                "title": "春天的旗与田",
                "text": "你没有替沈知禾抹去代价，只让她在每一次下令时知道：有人认真听过她的害怕。",
                "variants": [
                    {"when": {"food": 2, "trust": 1}, "title": "关山之主", "text": "灵田成为边关粮仓，陆沉川留守雪关，村民在新旗帜下迎来春耕。"},
                    {"when": {"trust": 2}, "title": "雪关军魂", "text": "陆沉川重披战甲，沈知禾用粮草改写战局；风雪里升起凯旋的军旗。"},
                    {"when": {}, "title": "无名丰年", "text": "秘密没有被夺走。沈知禾带着村民向更远的荒地出发，把丰年种在无人知晓的新城。"},
                ],
            },
            "chapters": [
                {
                    "title": "冻土下的第一粒种子",
                    "setup_title": "第一粒种子",
                    "setup_narration": "押解队消失在风雪里，孩子冻得发紫。沈知禾触到一块还能发芽的黑土，狼群却已循着异光靠近。",
                    "setup_cast": ["shen-zhihe"],
                    "setup_beats": [
                        "A wide view of a desolate snowbound exile village after the escort riders vanish over a white ridge; Shen Zhihe reaches a sick child beside empty sacks.",
                        "Close on Shen Zhihe kneeling at dark frozen soil; green living veins briefly pulse under her palm while snow whips around her face.",
                        "The villagers see the green glow with hope while shadowy wolf shapes and distant animal eyes approach through the blizzard beyond the fence.",
                    ],
                    "s1_title": "先救谁，都会留下遗憾",
                    "s1_prompt": "沈知禾攥紧军牌问你：先催熟粟米救全村，还是先种药草救高烧的孩子？你可以问她会不会后悔，也可以先安慰她。",
                    "s1_reason": "孩子濒死与全村断粮构成不可逆的人命抉择，主角处在第一次使用异能的强烈恐惧中。",
                    "s1_goal": "承认害怕但不逃避；听玩家的安慰或追问；将讨论收束到先救全村或先救孩子两个正式选择。",
                    "s1_forbidden": "不得透露狼群进攻后的结果，不得新增第三种救法，不得承诺异能没有代价。",
                    "choice_prompt": "这一夜，她只能先救一边。",
                    "options": [
                        {
                            "id": "feed-village", "label": "催熟粟米，先让全村活过今晚", "tone": "resource", "state_delta": {"food": 2, "risk": 1},
                            "result_title": "一锅粟米粥", "result_narration": "荒地一夜结穗，锅里终于有了热气。村民低头喝粥时，雪原深处也亮起兽瞳。", "result_cast": ["shen-zhihe"],
                            "result_beats": ["Millet ears rise rapidly through black snow-covered earth as Shen Zhihe steadies herself after using magic.", "Villagers ladle steaming millet porridge, children regain color and silently look toward Shen Zhihe with new trust.", "From Shen Zhihe's point of view, pairs of bright beast eyes appear one by one in the far blue-white storm."],
                        },
                        {
                            "id": "save-child", "label": "种出药草，先救高烧的孩子", "tone": "heart", "state_delta": {"trust": 1, "food": -1},
                            "result_title": "一株回春草", "result_narration": "药草在冰缝里舒展，孩子的呼吸慢慢稳住。可锅里只剩清水，村里人的目光也变得复杂。", "result_cast": ["shen-zhihe"],
                            "result_beats": ["A luminous medicinal herb opens through cracked ice as Shen Zhihe carefully plucks it.", "The feverish child drinks medicine and finally breathes evenly while Shen Zhihe watches in exhausted relief.", "Empty cooking pots and hungry villagers frame Shen Zhihe as she faces their conflicted, silent looks."],
                        },
                    ],
                },
                {
                    "title": "雪沟里的巨人",
                    "setup_title": "带血的陌生人",
                    "setup_narration": "沈知禾循着血迹走进雪沟，发现被兽夹困住的陆沉川。带他回去，会耗掉村里最后的药。",
                    "setup_cast": ["shen-zhihe", "lu-chenchuan"],
                    "setup_beats": ["Shen Zhihe follows dark blood marks across a narrow frozen ravine, keeping a lantern low against the snow.", "A gigantic wounded man, Lu Chenchuan, is trapped in an iron beast trap; he wakes and snaps a wolf bone with one hand to drive predators away.", "Shen Zhihe looks from his bleeding leg to the small pouch of medicine in her palm, calculating the village's last reserve."],
                    "s1_title": "陌生人值不值得一村的药",
                    "s1_prompt": "沈知禾没有立刻靠近。你可以问她：一个陌生人，值得拿全村最后的药换吗？",
                    "s1_reason": "救下陆沉川会永久改变战神线与村庄资源，主角的善意与生存理性直接冲突。",
                    "s1_goal": "解释药材所剩无几，也承认不忍心把活人留在雪地；听取劝阻或善意，最后请玩家正式确认。",
                    "s1_forbidden": "不得说出陆沉川真实身份，不得保证他会报恩，不得修改药材存量。",
                    "choice_prompt": "最后一包药，只能按在一个方向上。",
                    "options": [
                        {
                            "id": "bring-him-home", "label": "救他回村，赌他能活下来", "tone": "trust", "state_delta": {"trust": 2, "food": -1},
                            "result_title": "雪屋里的火", "result_narration": "陆沉川在火边醒来，沉默地替她劈开冻木。村里的药柜却少了一格。", "result_cast": ["shen-zhihe", "lu-chenchuan"],
                            "result_beats": ["Shen Zhihe and villagers struggle to carry the giant warrior through snow toward a dim wooden hut.", "By firelight, Shen Zhihe treats Lu Chenchuan's wound while he grips the bed frame in silent pain.", "At dawn Lu Chenchuan splits frozen logs with one hand as Shen Zhihe closes the nearly empty medicine box."],
                        },
                        {
                            "id": "tell-border-army", "label": "留下粮药，通知边军来接人", "tone": "risk", "state_delta": {"risk": -1, "trust": -1},
                            "result_title": "雪地里的军哨", "result_narration": "边军带走巨汉，留下一枚陌生的军哨。沈知禾的药和粮保住了，但那双眼睛再没看向她。", "result_cast": ["shen-zhihe", "lu-chenchuan"],
                            "result_beats": ["Shen Zhihe sets a small ration and medicine beside the trapped warrior, then lights a signal fire on the ridge.", "Border soldiers arrive through snow and lift Lu Chenchuan onto a stretcher; he looks back, wary and wounded.", "A lone military whistle rests in Shen Zhihe's glove after the soldiers disappear into the whiteout."],
                        },
                    ],
                },
                {
                    "title": "第一场丰收与第一把火",
                    "setup_title": "热饭之后的火光",
                    "setup_narration": "灵田一夜丰收，村里第一次吃上热饭。夜里敌军斥候纵火，陆沉川徒手挡住燃烧的木梁，记忆碎片翻涌。",
                    "setup_cast": ["shen-zhihe", "lu-chenchuan"],
                    "setup_beats": ["A warm frontier meal in a humble snow village; fresh grain is stacked near a glowing stove as Shen Zhihe allows herself one relieved smile.", "At night flames race along a wooden granary wall, enemy scouts vanish behind drifting snow, and villagers panic.", "Lu Chenchuan catches a burning timber bare-handed to shield Shen Zhihe; fragmented battlefield images flash in his eyes."],
                    "s1_title": "记忆回来后，他会不会离开",
                    "s1_prompt": "火光未熄，陆沉川却盯着自己的手发怔。你可以问他：恢复记忆后，还会不会离开沈知禾？",
                    "s1_reason": "身份记忆将影响战神是否离开，纵火也让灵田的秘密面临暴露，是感情与战略同时升级的节点。",
                    "s1_character": "lu-chenchuan",
                    "s1_goal": "只表达此刻的亏欠与守护欲，承认记忆碎片令人害怕；接住玩家的试探，不作永久承诺。",
                    "s1_forbidden": "不得说出战神身份或敌人意图，不得承诺结局，不得决定是否公开灵田。",
                    "choice_prompt": "丰收的光已经被看见，秘密还守得住吗？",
                    "options": [
                        {
                            "id": "open-fields", "label": "公开灵田，号召全村守护", "tone": "resource", "state_delta": {"food": 2, "secret": 1, "risk": 1},
                            "result_title": "所有人都看见了绿", "result_narration": "沈知禾打开粮仓，全村围住灵田。人心聚起，远处的敌军也记住了那束绿光。", "result_cast": ["shen-zhihe", "lu-chenchuan"],
                            "result_beats": ["Shen Zhihe pulls open the granary door and reveals abundant grain to stunned villagers.", "Villagers form a determined protective ring around the glowing field while Lu Chenchuan stands at the gate.", "From a snowy ridge, an enemy scout watches the green glow through a spyglass before slipping away."],
                        },
                        {
                            "id": "hide-fields", "label": "毁掉半亩灵田，假装只是好年景", "tone": "secret", "state_delta": {"secret": -1, "food": -1, "risk": -1},
                            "result_title": "埋回冻土的绿", "result_narration": "她亲手掩埋半亩灵田，给敌人留下普通丰收的假象。寒风吹过，沈知禾没有回头。", "result_cast": ["shen-zhihe", "lu-chenchuan"],
                            "result_beats": ["Before dawn Shen Zhihe cuts down part of the radiant crop, her face tight with grief.", "Lu Chenchuan quietly helps cover the glowing soil with snow and ordinary straw.", "The village presents a modest grain stack to passing scouts while Shen Zhihe watches from behind a frost-covered window."],
                        },
                    ],
                },
                {
                    "title": "战神该不该出关",
                    "setup_title": "两条路，都要他",
                    "setup_narration": "边军请陆沉川回营破敌；同一夜，异兽围住村子。战场与村庄，都在等他。",
                    "setup_cast": ["shen-zhihe", "lu-chenchuan"],
                    "setup_beats": ["Border cavalry arrive at the snowy village with an urgent war banner and recognize a mark on Lu Chenchuan's armor.", "At the same time, large shadowy beasts circle the wooden palisade; villagers hold torches and trembling farm tools.", "Shen Zhihe and Lu Chenchuan stand between the open army road and the threatened village gate, unable to move."],
                    "s1_title": "若他走了回不来，我该怪谁",
                    "s1_prompt": "沈知禾把军牌贴在心口：你替我选。若他走了回不来，我该怪谁？",
                    "s1_reason": "战局和村庄会被不同选择直接改写，且主角将承担失去陆沉川的情绪风险，是全剧最强的后悔节点。",
                    "s1_goal": "允许脆弱与依赖被看见，向玩家询问代价；不得将决定推卸给玩家，最终要求正式选择。",
                    "s1_forbidden": "不得剧透哪条线胜利，不得承诺陆沉川生还，不得把玩家安慰写成恋爱承诺。",
                    "choice_prompt": "让战神去改写战局，还是让他留在雪关？",
                    "options": [
                        {
                            "id": "send-to-war", "label": "让陆沉川出关，先破敌军", "tone": "war", "state_delta": {"trust": 1, "risk": 1},
                            "result_title": "北风里的背影", "result_narration": "陆沉川翻身上马，回头只说了一句“等我”。村口的火把被风吹得几乎熄灭。", "result_cast": ["shen-zhihe", "lu-chenchuan"],
                            "result_beats": ["Lu Chenchuan fastens repaired armor as Shen Zhihe silently ties the old military tag to his wrist.", "He rides out with border cavalry through a blue dawn snowstorm, looking back once at the village gate.", "Shen Zhihe turns from his disappearing silhouette to rally villagers beneath flickering torches."],
                        },
                        {
                            "id": "hold-the-gate", "label": "让陆沉川留守，先保住村子", "tone": "village", "state_delta": {"food": 1, "trust": 1, "risk": -1},
                            "result_title": "雪关不退", "result_narration": "陆沉川站上村墙，异兽在火箭下退去。远处军报传来，边军的战线却开始后撤。", "result_cast": ["shen-zhihe", "lu-chenchuan"],
                            "result_beats": ["Lu Chenchuan climbs the palisade and raises a heavy spear while Shen Zhihe directs villagers below.", "A fierce but non-graphic defense drives the beasts back with fire arrows and collapsing snow barriers.", "A mud-stained messenger brings a retreat report as Shen Zhihe sees smoke far beyond the quiet village."],
                        },
                    ],
                },
                {
                    "title": "春天的旗与田",
                    "setup_title": "敌军、异兽与朝堂使者",
                    "setup_narration": "春雪初融，敌军、异兽和朝堂使者同时抵达。灵田、村民与边军终于要为同一件事站在一起。",
                    "setup_cast": ["shen-zhihe", "lu-chenchuan"],
                    "setup_beats": ["Spring thaw reveals a broad glowing field beside the rebuilt snow village; villagers, soldiers, and children work side by side.", "Enemy banners and a wary court envoy appear on opposite ridges while distant beasts stalk the melting forest edge.", "Shen Zhihe and Lu Chenchuan stand before the field, each holding part of the old military tag as everyone waits for an order."],
                    "s1_title": "这一次，她不必独自下令",
                    "s1_prompt": "最后的风雪终于停了。沈知禾问你：我该把田和人交给谁，才不算辜负这一整个冬天？",
                    "s1_reason": "终局前的责任、功劳和归属交汇，主角有明显情绪波动，选择将改变终局文案和权力结构。",
                    "s1_goal": "回顾玩家一路的态度，表达对村民与陆沉川的责任；把感受收束成守土或出征的正式方向。",
                    "s1_forbidden": "不得提前选择终局称号，不得新增朝堂交易，不得否定已发生的前四章结果。",
                    "choice_prompt": "最后一面旗，要插在雪关，还是插向更远的战场？",
                    "options": [
                        {
                            "id": "raise-field-flag", "label": "守住雪关，让灵田成为所有人的粮仓", "tone": "village", "state_delta": {"food": 1, "trust": 1},
                            "result_title": "田埂上的新旗", "result_narration": "新旗插在田埂上。陆沉川放下战甲，村民把第一把春种交到沈知禾手里。", "result_cast": ["shen-zhihe", "lu-chenchuan"],
                            "result_beats": ["Shen Zhihe plants a new frontier flag at the edge of the flourishing field as villagers gather around.", "Lu Chenchuan removes his battered armor and helps a child place the first spring seed in Shen Zhihe's palm.", "The camera rises above the snowmelt village and radiant green fields under a clear blue sky."],
                        },
                        {
                            "id": "raise-war-flag", "label": "以粮草开路，让雪关军再出征", "tone": "war", "state_delta": {"trust": 1, "risk": 1},
                            "result_title": "风雪尽头的军旗", "result_narration": "粮车驶向前线，陆沉川重披战甲。沈知禾留在旗后，替所有人守住回家的路。", "result_cast": ["shen-zhihe", "lu-chenchuan"],
                            "result_beats": ["Rows of grain carts depart the green field toward a mountain pass while Shen Zhihe gives precise orders.", "Lu Chenchuan mounts in restored armor and shares a quiet determined look with Shen Zhihe.", "A long column of soldiers and grain carts moves through sunlit snow beneath a newly raised frontier banner."],
                        },
                    ],
                },
            ],
        },
        {
            "id": "life-hexagram",
            "title": "卦尽一线生",
            "tagline": "她每替人改一次命，自己的命火就会熄一寸。",
            "genre": "玄学悬疑 / 续命 / 反转",
            "palette": "ink",
            "hero": "闻昭",
            "hero_character": "wen-zhao",
            "model_plan": "雨夜、命火、替命阵与真相反转是预生成 Q3 段落；濒死、师兄对峙和是否献祭之前的情绪承接只走 S1。",
            "state_labels": {"life": "剩余寿数", "clue": "偷命线索", "truth": "真相接近度", "bond": "师兄羁绊"},
            "initial_state": {"life": 0, "clue": 0, "truth": 0, "bond": 0},
            "characters": [
                {
                    "id": "wen-zhao", "name": "闻昭", "role": "只剩七日寿数的卦师", "voice": "Qiao", "s1_voice": "Sohee",
                    "image_prompt": "Vertical 9:16 cinematic Chinese fantasy mystery character key art, Wen Zhao, a clever young female diviner with pale tired face and observant eyes, long black hair pinned with a cracked jade hairpin, deep indigo hanfu with rain-dark sleeves, holding glowing divination sticks and a small brass lantern with a dying flame, rainy ancient street at night, realistic supernatural drama, no text, no watermark.",
                },
                {
                    "id": "xie-wujiu", "name": "谢无咎", "role": "失踪师兄，偷命阵谜团中心", "voice": "Andre",
                    "image_prompt": "Vertical 9:16 cinematic Chinese fantasy mystery character key art, Xie Wujiiu, a composed man around thirty with a sorrowful sharp gaze, long black hair tied low, black and muted crimson scholar-warrior robe, an ancient talisman burned at the edge between two fingers, faint red soul-fire threads around one wrist, rain and shadowed temple corridor, realistic supernatural drama, no text, no watermark.",
                },
            ],
            "ending": {
                "title": "最后一卦算给自己", "text": "闻昭第一次把卦签指向自己。你没有替她决定生死，但让她在命火熄灭前拥有一次清醒的选择。",
                "variants": [
                    {"when": {"life": 1, "truth": 2}, "title": "借命不偷命", "text": "闻昭找到留一线的命理规则，带着尚未熄灭的命火继续为人指路。"},
                    {"when": {"bond": 2}, "title": "同罪同偿", "text": "她与谢无咎共同承担因果，活下来却失去通灵能力，终于能像普通人一样看日出。"},
                    {"when": {}, "title": "一城灯火", "text": "全城命火重新亮起。雨夜卦摊上，只剩玩家听过的那句笑话。"},
                ],
            },
            "chapters": [
                {
                    "title": "只剩七日的卦摊", "setup_title": "雨夜的最后一盏灯", "setup_narration": "闻昭的命火只剩七日。一位母亲求她找回失踪女儿，酬金却刚好够买一盏续命灯。", "setup_cast": ["wen-zhao"],
                    "setup_beats": ["Rain falls across an ancient night market as Wen Zhao sets up a small divination table beneath a torn umbrella.", "A tiny flame above Wen Zhao's brass lantern visibly shrinks while a desperate mother kneels with a missing girl's ribbon.", "A merchant displays an expensive life-extending lamp in a nearby shop as Wen Zhao holds the ribbon and hesitates."],
                    "s1_title": "善良，还是不想变冷漠", "s1_prompt": "闻昭压低声音问你：我救她，是因为善良，还是因为我怕自己变成冷漠的人？", "s1_reason": "寿数仅余七日，救人与自救在同一笔交易里，主角用玩笑掩盖明显的濒死恐惧。", "s1_goal": "承认想活下去不是罪，接住玩家安慰；把决定收束到买灯或起卦救人。", "s1_forbidden": "不得说出失踪者位置，不得保证续命灯有效，不得增加寿数来源。", "choice_prompt": "一盏灯，和一个失踪的人，先握住哪一个？",
                    "options": [
                        {"id": "buy-lamp", "label": "收下酬金，先续自己的命", "tone": "survive", "state_delta": {"life": 2, "clue": -1}, "result_title": "多借来的一夜", "result_narration": "续命灯亮起，闻昭多活了一夜。巷口却只剩一只湿透的绣鞋。", "result_cast": ["wen-zhao"], "result_beats": ["Wen Zhao pays for the life lamp and its warm flame brightens her pale face.", "She walks through rain toward the old alley too late, holding the missing girl's ribbon.", "A single soaked embroidered shoe rests in a puddle beside a faintly glowing red symbol." ]},
                        {"id": "find-girl", "label": "免费起卦，先救失踪女孩", "tone": "truth", "state_delta": {"life": -1, "clue": 2}, "result_title": "命火的裂缝", "result_narration": "卦签烧成一条红线，带她找到地下暗室。女孩尚有气息，墙上却刻着偷命阵。", "result_cast": ["wen-zhao"], "result_beats": ["Wen Zhao burns divination sticks and a thin red light line threads through the rainy alley.", "She forces open a hidden cellar door and finds the missing girl alive but unconscious.", "Her lantern reveals an ominous life-stealing array carved into the cellar wall." ]},
                    ],
                },
                {
                    "title": "将死的富商与活着的乞儿", "setup_title": "富商的价码", "setup_narration": "将死富商要用重金，把死劫转到街边乞儿身上；乞儿却是唯一见过偷命者的人。", "setup_cast": ["wen-zhao"],
                    "setup_beats": ["An opulent sickroom contrasts with a starving street outside; a wealthy merchant grips Wen Zhao's sleeve and offers a chest of silver.", "Outside, a frightened young beggar draws the same red array symbol in dust and looks toward the mansion.", "Wen Zhao sees the merchant's dimming life-fire stretch like a red thread toward the beggar."],
                    "s1_title": "想活下去，不是罪", "s1_prompt": "你可以问闻昭：你是不是也有一点，想拿这笔钱替自己多活几天？", "s1_reason": "主角被迫直面求生欲和利用无辜者的边界，且证人会决定案件真相。", "s1_goal": "坦承求生欲，同时坚持不拿无辜者换命；接受玩家关于设局或保护的建议。", "s1_forbidden": "不得揭示富商或乞儿的后续命运，不得许诺能安全转命。", "choice_prompt": "钱、证人和底线，闻昭只能先守住两样。",
                    "options": [
                        {"id": "protect-witness", "label": "拒绝富商，保护乞儿证人", "tone": "truth", "state_delta": {"clue": 1, "life": -1}, "result_title": "雨棚下的证词", "result_narration": "闻昭把乞儿带进雨棚。孩子说出一个名字，也让富商的门客盯上了她。", "result_cast": ["wen-zhao"], "result_beats": ["Wen Zhao turns away the silver chest and puts her cloak around the young beggar.", "Under a rain shelter the beggar whispers a name while Wen Zhao records it on a talisman.", "Men from the mansion watch them through rain from a distant covered walkway." ]},
                        {"id": "bait-merchant", "label": "假意答应，借富商设局套话", "tone": "risk", "state_delta": {"clue": 2, "truth": 1, "life": -1}, "result_title": "因果反噬", "result_narration": "假阵启动的一瞬，闻昭拿到了账册，却被红线反咬，命火又暗了一截。", "result_cast": ["wen-zhao"], "result_beats": ["Wen Zhao lays a false array on polished floor tiles as the merchant greedily steps inside.", "The red life thread lashes back at Wen Zhao's wrist while she grabs a hidden ledger.", "She escapes into rain clutching the ledger, the flame in her lantern visibly weaker." ]},
                    ],
                },
                {
                    "title": "命火相连的师兄", "setup_title": "失踪师兄回来了", "setup_narration": "闻昭在账册里找到师兄谢无咎的印记。两人的命火已被绑在一起，杀他，她也可能死。", "setup_cast": ["wen-zhao", "xie-wujiu"],
                    "setup_beats": ["Wen Zhao opens the stolen ledger in an abandoned shrine and finds her missing master's seal stamped in red ink.", "Xie Wujiiu emerges from a shadowed temple corridor; a red life-fire thread binds his wrist to Wen Zhao's.", "Both freeze as the shared thread burns bright between them, turning the rain-soaked temple red."],
                    "s1_title": "他害过人，你还会救他吗", "s1_prompt": "谢无咎站在阴影里。你可以问闻昭：如果他真的害过人，你还会救他吗？", "s1_reason": "亲情、罪责和共生死亡同时出现，玩家需要帮助主角承接摇摆而非直接获得谜底。", "s1_goal": "承认情感与怀疑并存，讨论调查与保护自身的边界；请求玩家正式选择进入阵中或交给镇夜司。", "s1_forbidden": "不得说明谢无咎是否有罪、阵法真相或最终死亡。", "choice_prompt": "相信师兄，还是相信制度？",
                    "options": [
                        {"id": "enter-array", "label": "跟谢无咎进阵，亲眼看真相", "tone": "bond", "state_delta": {"bond": 2, "truth": 1}, "result_title": "阵眼里的旧信", "result_narration": "阵里藏着师父留下的信，也藏着谢无咎没说出口的代价。两人的命火越缠越紧。", "result_cast": ["wen-zhao", "xie-wujiu"], "result_beats": ["Wen Zhao and Xie Wujiiu step into a rotating underground array lit by red talismans.", "A sealed letter from their master floats above the array, reflected in both their wet eyes.", "The shared flame thread tightens around their wrists as the chamber trembles." ]},
                        {"id": "call-night-watch", "label": "交给镇夜司，先保住更多人", "tone": "truth", "state_delta": {"truth": 2, "bond": -1}, "result_title": "锁链与雨声", "result_narration": "镇夜司锁住谢无咎，却也准备把阵法连同证据一起焚毁。闻昭第一次怀疑谁才在遮掩真相。", "result_cast": ["wen-zhao", "xie-wujiu"], "result_beats": ["Night Watch officers surround Xie Wujiiu with lanterns and black iron chains.", "Wen Zhao sees a senior officer toss pages of the ledger toward a brazier.", "Xie Wujiiu is led away through rain as Wen Zhao stares at the burning evidence." ]},
                    ],
                },
                {
                    "title": "拿自己的命换全城的命", "setup_title": "万盏命火同时熄灭", "setup_narration": "偷命大阵启动，全城百姓的命火一起熄灭。闻昭发现自己是阵眼的反向钥匙。", "setup_cast": ["wen-zhao", "xie-wujiu"],
                    "setup_beats": ["Across a dense ancient city at dusk, thousands of small life lanterns flicker out at once.", "Wen Zhao stands at the central array as red lines radiate under the streets and her own lantern flame turns white.", "Xie Wujiiu reaches toward her through the collapsing array while citizens weaken around them."],
                    "s1_title": "别把自己当成一件工具", "s1_prompt": "闻昭的命火只剩一点。你可以劝她别把自己当工具，也可以陪她数完最后的光。", "s1_reason": "全城规模的生死与主角自我牺牲冲动达到顶点，需用实时近景承接离别和劝阻。", "s1_goal": "允许玩家安慰、劝阻、追问代价；承认害怕死，但不把结局交给自由聊天。", "s1_forbidden": "不得说明哪种选择能救多少人，不得剧透生还，不得复活任何人。", "choice_prompt": "用最后的命火破阵，还是先保留一线生机？",
                    "options": [
                        {"id": "break-array", "label": "燃尽命火，先救全城", "tone": "sacrifice", "state_delta": {"truth": 2, "life": -2}, "result_title": "一城灯火", "result_narration": "白光穿过阵眼，整座城的命火重新点亮。闻昭却在光里慢慢失去声音。", "result_cast": ["wen-zhao", "xie-wujiu"], "result_beats": ["Wen Zhao raises her lantern into the central array as a wave of white light begins to spread.", "Thousands of windows across the city glow warm again while red stealing threads shatter.", "Xie Wujiiu catches Wen Zhao as the last white light fades from her trembling hand." ]},
                        {"id": "save-witness", "label": "先救核心证人，保留破阵机会", "tone": "survive", "state_delta": {"life": 1, "truth": 1, "clue": 1}, "result_title": "留下一线", "result_narration": "闻昭把仅剩的力气留给证人。阵法没有立刻破，但真相终于有了能说出口的人。", "result_cast": ["wen-zhao"], "result_beats": ["Wen Zhao shields a key witness from a collapsing red life thread inside the central array.", "The witness wakes and grips a talisman bearing the organizer's mark while Wen Zhao staggers.", "Outside, portions of the city remain dark as Wen Zhao's small lantern steadies with one thin flame." ]},
                    ],
                },
                {
                    "title": "最后一卦算给自己", "setup_title": "卦签第一次指向她", "setup_narration": "大阵崩塌后，闻昭摊开最后一把卦签。寿数、证词和师兄的命火，都等她为自己算一次。", "setup_cast": ["wen-zhao", "xie-wujiu"],
                    "setup_beats": ["Dawn after the storm: Wen Zhao sits at her battered divination table amid scattered talismans and broken red threads.", "She pours the final divination sticks onto a cloth as Xie Wujiiu watches from a respectful distance.", "One stick points toward Wen Zhao; her lantern now holds a small steady flame reflected in her eyes."],
                    "s1_title": "这一卦，只算给自己", "s1_prompt": "闻昭把最后一根卦签递给你：若活下去要背很多债，我还该不该为自己求一次生？", "s1_reason": "真相已经落地，主角从救人模式转向自我价值的终局情绪，需要玩家帮助她命名而非替她逃避。", "s1_goal": "回顾玩家始终如何看待她的求生；确认她值得为自己留一线；收束到新规则或共同承担。", "s1_forbidden": "不得提前给出结局称号，不得改写已扣除的寿数或已揭露的罪责。", "choice_prompt": "最后一卦，是为天下留灯，还是为自己留一线？",
                    "options": [
                        {"id": "new-rule", "label": "立新规则：借命不偷命", "tone": "truth", "state_delta": {"life": 1, "truth": 1}, "result_title": "留一线的卦师", "result_narration": "闻昭烧掉旧阵图，把最后一盏灯留在卦摊。来问命的人，终于能先学会为自己负责。", "result_cast": ["wen-zhao"], "result_beats": ["Wen Zhao burns the old life-stealing diagrams in a brazier as morning light enters the alley.", "She replaces them with a plain new divination board beside a steady lantern.", "People line up at her small stall while Wen Zhao gives a calm, grounded smile." ]},
                        {"id": "share-cause", "label": "与谢无咎共同承担因果", "tone": "bond", "state_delta": {"bond": 1, "life": 1}, "result_title": "同罪同偿", "result_narration": "两人把命火从枷锁改成誓约。通灵的光熄了，但他们第一次能并肩走在太阳下。", "result_cast": ["wen-zhao", "xie-wujiu"], "result_beats": ["Wen Zhao and Xie Wujiiu place their wrists over a calm white flame, not a red binding thread.", "The supernatural glow fades from their hands as they accept ordinary scars and morning air.", "They walk side by side through a sunlit market, leaving the old rain-soaked shrine behind." ]},
                    ],
                },
            ],
        },
        {
            "id": "market-gate",
            "title": "荒年菜场通今古",
            "tagline": "一扇门通往凌晨菜场，也通往一家人的新日子。",
            "genre": "荒年 / 时空互助 / 家庭成长",
            "palette": "market",
            "hero": "许春娘",
            "hero_character": "xu-chunniang",
            "model_plan": "现代菜场、荒年村庄和时空门的视觉结果预生成；关于先顾家、孩子读书与门该不该关闭的情绪对话由 S1 即时完成。",
            "state_labels": {"family": "家人安稳", "village": "村庄互助", "gate": "时空门暴露风险", "future": "孩子的未来"},
            "initial_state": {"family": 0, "village": 0, "gate": 0, "future": 0},
            "characters": [
                {
                    "id": "xu-chunniang", "name": "许春娘", "role": "荒年守家的六旬寡妇", "voice": "Hana",
                    "image_prompt": "Vertical 9:16 cinematic Chinese historical character key art, Xu Chunniang, a capable woman in her early sixties with a lined warm face and resolute eyes, gray hair in a practical bun, patched brown ancient work clothes, carrying a woven basket of modern vegetables beside an old stone stove, a faint doorway glow behind her, realistic period drama, no text, no watermark.",
                },
                {
                    "id": "a-li", "name": "阿梨", "role": "聪明好学的孙女", "voice": "Ono Anna",
                    "image_prompt": "Vertical 9:16 cinematic Chinese historical character key art, A Li, a bright twelve-year-old Chinese village girl with curious eyes and two simple braids, patched pale blue ancient clothes, holding a modern pencil and a small paper notebook close to her chest, soft doorway light and an old market in the background, realistic period drama, no text, no watermark.",
                },
            ],
            "ending": {"title": "菜场不是金山，是新的日子", "text": "许春娘守住的从来不是一扇门，而是一家人不必再被荒年决定的权利。", "variants": [
                {"when": {"village": 2, "future": 1}, "title": "共益菜场", "text": "门成了公开互助的合作社，村里人学会用规则分享资源，而不是抢夺资源。"},
                {"when": {"family": 2}, "title": "门归家人", "text": "她先保住了家，也慢慢让家人学会承担外面的风雨。"},
                {"when": {}, "title": "关门留种", "text": "时空门永久关闭，留下的种子、账本和孩子们成了真正的未来。"},
            ]},
            "chapters": [
                {
                    "title": "一篮烂菜能救几口人", "setup_title": "凌晨三点的菜场", "setup_narration": "许春娘从现代菜场捡回临期菜。回到古代，孙子高烧，村里也断了粮。", "setup_cast": ["xu-chunniang"],
                    "setup_beats": ["At a modern wholesale market before dawn, Xu Chunniang carefully gathers discarded but usable vegetables into a woven basket.", "She steps through a faint glowing doorway behind an ancient stone stove and emerges in a drought-stricken historical village.", "Inside her dim home, a feverish child lies under a thin quilt while hungry villagers wait outside near empty grain jars."],
                    "s1_title": "先顾自家，是不是自私", "s1_prompt": "许春娘隔着旧收音机问你：婶子先顾自家，是不是自私？", "s1_reason": "孙辈高烧和村庄断粮同时发生，老年女性主角承受家庭伦理与公共责任的强烈拉扯。", "s1_goal": "说清她既要护住孩子也不愿看邻里饿死；接住玩家劝慰并收束为两项正式分配。", "s1_forbidden": "不得凭空增加食物、药品或时空门开启时间，不得评价玩家自私。", "choice_prompt": "这篮菜和一点钱，先落在谁的锅里？",
                    "options": [
                        {"id": "save-family", "label": "先换药和白米，救家人", "tone": "family", "state_delta": {"family": 2, "village": -1}, "result_title": "白米和退烧药", "result_narration": "孩子退了烧，白米也进了锅。院门外的空碗却越来越多。", "result_cast": ["xu-chunniang"], "result_beats": ["Xu Chunniang trades vegetables in the modern market for rice and medicine, counting every coin.", "Back home she feeds warm rice porridge and medicine to the feverish child, who slowly opens his eyes.", "Outside the old courtyard, several neighbors hold empty bowls while Xu Chunniang hears them through the closed door." ]},
                        {"id": "feed-village", "label": "先熬大锅菜，救村里老人孩子", "tone": "village", "state_delta": {"village": 2, "family": -1}, "result_title": "一锅菜汤", "result_narration": "大锅菜救了半个村子，孙子却仍在发烧。许春娘把最后一片姜留给了家。", "result_cast": ["xu-chunniang"], "result_beats": ["Xu Chunniang chops mixed vegetables beside a large outdoor pot as weak villagers gather with bowls.", "Steam rises over a communal meal; elders and children eat with tears of relief.", "She returns to her home with one small piece of ginger and sits beside the still-feverish child." ]},
                    ],
                },
                {
                    "title": "第一笔生意不能做给谁", "setup_title": "富户盯上了雨棚", "setup_narration": "她把现代塑料布改成雨棚。村里富户想高价包下货物，逃荒队里却有产妇即将临盆。", "setup_cast": ["xu-chunniang"],
                    "setup_beats": ["Xu Chunniang stretches bright modern plastic sheeting into a sturdy rain shelter over an ancient market lane.", "A richly dressed local landowner inspects the material and offers grain while his servants measure the doorway area.", "Nearby, exhausted refugees arrive with a pregnant woman in labor as rain begins to fall."],
                    "s1_title": "规矩要先立给谁看", "s1_prompt": "许春娘问你：我若跟富户合作，能护住村子；可门是不是也就不再是我的了？", "s1_reason": "资源换保护与救助弱者互相冲突，富户掌控秘密会改变长期风险，是权力边界的关键节点。", "s1_goal": "鼓励她提出条件和规则，不让她独自扛村庄；收束为与富户合作或帮助逃荒队。", "s1_forbidden": "不得给出第三项交易，不得说明富户之后是否背叛，不得保证时空门安全。", "choice_prompt": "第一笔大买卖，交给粮仓，还是交给人情？",
                    "options": [
                        {"id": "deal-landowner", "label": "与富户合作，换护村粮仓", "tone": "resource", "state_delta": {"family": 1, "gate": 2}, "result_title": "粮仓的锁", "result_narration": "粮仓终于有了余粮，富户手里也多了一把看不见的钥匙。许春娘看着那把锁，心里发沉。", "result_cast": ["xu-chunniang"], "result_beats": ["Xu Chunniang signs a simple grain agreement with the landowner under the plastic rain shelter.", "Sacks of grain fill a guarded village storehouse while the landowner watches the old stove from afar.", "Xu Chunniang notices a servant discreetly mark the stones near the hidden doorway." ]},
                        {"id": "help-refugees", "label": "把货给逃荒队，换人情和劳力", "tone": "village", "state_delta": {"village": 2, "future": 1}, "result_title": "雨棚下的新生", "result_narration": "产妇平安生下孩子，逃荒队留下各地消息。许春娘得到的不是粮仓，是一张活路网。", "result_cast": ["xu-chunniang"], "result_beats": ["Under the makeshift rain shelter, women help the refugee mother while Xu Chunniang provides clean cloth and warm food.", "A newborn cries as relieved travelers offer maps and news from distant roads.", "New helpers repair village roofs with Xu Chunniang, turning the shelter into a small community hub." ]},
                    ],
                },
                {
                    "title": "孙女想去门那边上学", "setup_title": "一支铅笔的愿望", "setup_narration": "菜场管理员的女儿愿意教阿梨认字；族老却说女孩不该总往“鬼门”跑。", "setup_cast": ["xu-chunniang", "a-li"],
                    "setup_beats": ["At the modern market, a kind school-age girl shows A Li how to write characters with a pencil on scrap paper.", "A Li returns through the stove doorway clutching the notebook, excitement glowing on her face.", "In the ancient village hall, stern elders confront Xu Chunniang while A Li hides the pencil behind her back."],
                    "s1_title": "我是不是不该有这么大的愿望", "s1_prompt": "阿梨小声问你：我是不是不该有这么大的愿望？许春娘也在等你开口。", "s1_reason": "孙女的受教育愿望与族规冲突，许春娘担心失去孩子，是代际成长的高情绪节点。", "s1_character": "a-li", "s1_goal": "让阿梨表达想读书但不想让奶奶为难；接受鼓励并请玩家帮助她把愿望落到正式方案。", "s1_forbidden": "不得保证现代学校录取，不得贬低古代家人，不得决定门的最终归属。", "choice_prompt": "让阿梨去看更大的世界，还是先把脚下的日子站稳？",
                    "options": [
                        {"id": "modern-study", "label": "送阿梨去现代短学", "tone": "future", "state_delta": {"future": 2, "gate": 1}, "result_title": "门那边的字", "result_narration": "阿梨学会写自己的名字，也让更多现代人开始留意这个凌晨出现的女孩。", "result_cast": ["xu-chunniang", "a-li"], "result_beats": ["A Li practices writing her name at a quiet modern market office table while Xu Chunniang watches through the doorway.", "She returns to the village and teaches younger children simple characters in dust with a stick.", "A modern market worker notices the old doorway light as A Li disappears through it with her notebook." ]},
                        {"id": "ancient-ledger", "label": "留在古代，先学会账本与生意", "tone": "family", "state_delta": {"family": 1, "future": 1, "gate": -1}, "result_title": "账本上的路", "result_narration": "阿梨把委屈写进账本，也把每一袋粮的去处算得清清楚楚。她没有停下，只是换了一条路。", "result_cast": ["xu-chunniang", "a-li"], "result_beats": ["Xu Chunniang patiently teaches A Li to tally grain and trade items in an old account book.", "A Li accurately records village exchanges while skeptical elders begin to trust her work.", "At night she privately writes her name again beside a small pencil hidden in the ledger." ]},
                    ],
                },
                {
                    "title": "门要关了", "setup_title": "三分钟的两边", "setup_narration": "时空门每次只开三分钟。现代菜场突发火警，古代村庄却正遭蝗灾。两边都有人等她。", "setup_cast": ["xu-chunniang"],
                    "setup_beats": ["The old stove doorway flickers with a visible three-minute hourglass-like glow as Xu Chunniang checks a worn pocket watch.", "On the modern side, a market fire alarm flashes and smoke begins to fill a storage aisle.", "On the ancient side, a dark swarm of locusts descends over the village's fragile crops while people call for Xu Chunniang."],
                    "s1_title": "三分钟，救哪一边", "s1_prompt": "许春娘没有时间哭。她请你用一句话告诉她：先往哪边跑？", "s1_reason": "双世界灾害同时爆发且门开启时间有限，实时互动用于时间压力下的共决策与情绪支撑。", "s1_goal": "快速复述两边代价，接受一句鼓励或建议，并立即请求正式选择。", "s1_forbidden": "不得延长开门时间，不得说任何一边已被救下，不得让玩家自由创造资源。", "choice_prompt": "门只开三分钟，这一次留给谁？",
                    "options": [
                        {"id": "save-modern", "label": "留在现代救人，承担暴露", "tone": "risk", "state_delta": {"village": -1, "gate": 2, "future": 1}, "result_title": "警铃里的身影", "result_narration": "许春娘拉出被困的人，也被监控拍下背影。古代的蝗灾没有等她。", "result_cast": ["xu-chunniang"], "result_beats": ["Xu Chunniang guides trapped modern market workers through smoke toward an emergency exit.", "A security camera catches her profile as she uses an old basket to carry supplies.", "She returns through a fading doorway to find ancient crop leaves stripped by locusts." ]},
                        {"id": "save-village", "label": "带最后一批种子回古代", "tone": "village", "state_delta": {"village": 2, "family": 1, "gate": -1}, "result_title": "种子穿过火光", "result_narration": "她抱着种子冲回古代，村子保住了春耕。另一边的朋友，只能隔着关上的门等她。", "result_cast": ["xu-chunniang"], "result_beats": ["Xu Chunniang gathers emergency seed packets in the smoky modern market while fire alarms flash.", "She runs through the glowing doorway clutching the seed packets as it narrows behind her.", "Villagers sow the rescued seeds into protected soil while Xu Chunniang looks back at the now-dark stove." ]},
                    ],
                },
                {
                    "title": "菜场不是金山，是新的日子", "setup_title": "门的归属", "setup_narration": "荒年将尽，富户和现代管理员都逼近秘密。许春娘必须决定这扇门该为谁打开。", "setup_cast": ["xu-chunniang", "a-li"],
                    "setup_beats": ["At spring's edge, Xu Chunniang lays vegetables, seed packets, account books, and the old radio on a wooden table.", "The village landowner arrives from one side as a concerned modern market manager appears through the faint doorway from the other.", "A Li stands beside her grandmother, holding both a pencil and an ancient ledger as the doorway pulses behind them."],
                    "s1_title": "这扇门，到底该为谁开", "s1_prompt": "许春娘问你：若把门交给大家，我怕守不住；若只留给家人，我又怕辜负太多人。", "s1_reason": "权力、互助与家庭安全在终局对撞，主角需要从“独自扛”转向主动建立边界。", "s1_goal": "帮助她命名规则与害怕，肯定她有权选择；收束为共益机制或先守家门。", "s1_forbidden": "不得透露结局、不得让门无限开启、不得答应富户或管理员任何新条件。", "choice_prompt": "最后的钥匙，交给规则，还是交给家人？",
                    "options": [
                        {"id": "shared-market", "label": "建立公开互助规则，让门服务大家", "tone": "village", "state_delta": {"village": 2, "future": 1}, "result_title": "共益菜场", "result_narration": "门前立起账本和轮值表。许春娘不再一个人守夜，村里也不再靠抢夺过日子。", "result_cast": ["xu-chunniang", "a-li"], "result_beats": ["Xu Chunniang posts a clear shared ledger and rotation list beside the old stove doorway.", "Villagers and modern friends exchange seeds and food under agreed rules while A Li records each item.", "The camera moves through a thriving cooperative market where Xu Chunniang finally rests with a cup of tea." ]},
                        {"id": "keep-for-family", "label": "先把门留给家人，慢慢教他们独立", "tone": "family", "state_delta": {"family": 2, "gate": -1}, "result_title": "一家的夜班", "result_narration": "许春娘暂时关上门，只把种子和账本留给孩子们。她知道，守住家也不是退缩。", "result_cast": ["xu-chunniang", "a-li"], "result_beats": ["Xu Chunniang gently closes the old stove doorway after carrying through a final basket of seeds.", "Her family works together to sort seeds and reconcile the household ledger by lamplight.", "A Li plants the first seed at dawn as Xu Chunniang watches their home grow steadier." ]},
                    ],
                },
            ],
        },
        {
            "id": "palace-market",
            "title": "冷宫超市不打烊",
            "tagline": "一碗泡面引来假侍卫，也引来一座宫城的秘密。",
            "genre": "宫廷轻喜剧 / 权谋 / 治愈",
            "palette": "palace",
            "hero": "姜晚棠",
            "hero_character": "jiang-wantang",
            "model_plan": "冷宫超市、夜市、搜宫与权谋结果均为预生成 Q3 段落；身份试探、拒绝练习与是否信任皇帝的情绪实时使用 S1。",
            "state_labels": {"kindness": "超市善意值", "intel": "宫廷情报", "trust": "皇帝信任", "exposure": "超市暴露风险"},
            "initial_state": {"kindness": 0, "intel": 0, "trust": 0, "exposure": 0},
            "characters": [
                {
                    "id": "jiang-wantang", "name": "姜晚棠", "role": "被打入冷宫的废妃，夜半超市掌柜", "voice": "Sohee",
                    "image_prompt": "Vertical 9:16 cinematic Chinese historical fantasy character key art, Jiang Wantang, a sharp witty woman in her late twenties, poised face and watchful eyes, dark auburn hair with a simple gold hairpin, elegant but slightly worn crimson and ink palace robe, holding a steaming instant noodle cup beside glowing modern supermarket shelves hidden in an ancient cold palace, realistic premium costume drama, no text, no watermark.",
                },
                {
                    "id": "xiao-chengyan", "name": "萧承晏", "role": "微服蹭饭的皇帝", "voice": "Dylan",
                    "image_prompt": "Vertical 9:16 cinematic Chinese historical fantasy character key art, Xiao Chengyan, a restrained handsome emperor around thirty, intelligent tired eyes, black hair in a practical guard topknot, dark navy guard robe concealing subtle imperial embroidery, holding wooden chopsticks over a steaming hotpot, ancient cold palace doorway and modern shop glow, realistic premium costume drama, no text, no watermark.",
                },
            ],
            "ending": {"title": "最后一张会员卡", "text": "姜晚棠终于明白，超市给她的不是依附谁的资格，而是把善意变成规则的能力。", "variants": [
                {"when": {"trust": 2, "intel": 1}, "title": "帝后同盟", "text": "两人公开整顿后宫，冷宫超市成了真正的宫廷救助站。"},
                {"when": {"intel": 2}, "title": "冷宫合伙人", "text": "她选择冷宫众人，夜市成了所有人共同经营的避风处。"},
                {"when": {}, "title": "独立掌柜", "text": "姜晚棠带着超市离宫开店，萧承晏只能照规矩排队蹭饭。"},
            ]},
            "chapters": [
                {
                    "title": "泡面香飘三里宫", "setup_title": "翻墙来的假侍卫", "setup_narration": "姜晚棠用最后一包泡面救下冻晕的小太监，香味却引来翻墙的皇帝。他装成侍卫，只问能不能再来一碗。", "setup_cast": ["jiang-wantang", "xiao-chengyan"],
                    "setup_beats": ["In a snow-cold ancient palace, Jiang Wantang cooks instant noodles beside hidden glowing convenience-store shelves for a fainted young eunuch.", "The fragrant steam drifts over a cold palace wall as a man in a dark guard robe awkwardly climbs down into the courtyard.", "The disguised Xiao Chengyan stares at the noodle cup with restrained hunger while Jiang Wantang narrows her eyes."],
                    "s1_title": "这个人，太像皇帝了", "s1_prompt": "姜晚棠压低声音问你：这个人说话太像皇帝了。我是不是又太容易心软？", "s1_reason": "陌生权力者突然闯入私密空间，身份试探与心软自责同时出现，决定开启轻喜剧或悬疑线。", "s1_goal": "用吐槽掩饰警觉，允许玩家提醒与安慰；将判断收束为请他吃饭记账或赶走查身份。", "s1_forbidden": "不得确认皇帝身份，不得透露他来冷宫的真正目的，不得新增第三种处理方式。", "choice_prompt": "一碗泡面，换一份人情，还是换一份警觉？",
                    "options": [
                        {"id": "feed-and-ledger", "label": "请他吃，但记一笔人情账", "tone": "trust", "state_delta": {"trust": 1, "kindness": 1}, "result_title": "欠条和第二碗面", "result_narration": "假侍卫吃得很认真，也欠得很认真。姜晚棠把账记下，心里却多了一个问号。", "result_cast": ["jiang-wantang", "xiao-chengyan"], "result_beats": ["Jiang Wantang sets a steaming noodle cup before the disguised emperor and writes a debt in a small ledger.", "Xiao Chengyan eats with surprising gratitude, trying to maintain a guard's composure.", "Jiang Wantang closes the ledger and notices a subtle imperial callus on his hand." ]},
                        {"id": "drive-and-investigate", "label": "赶他走，先查清身份", "tone": "risk", "state_delta": {"intel": 1, "exposure": -1}, "result_title": "墙头的玉扣", "result_narration": "姜晚棠把人赶出冷宫，却在墙角捡到一枚龙纹玉扣。她知道麻烦不会自己走远。", "result_cast": ["jiang-wantang", "xiao-chengyan"], "result_beats": ["Jiang Wantang points firmly toward the cold palace gate while the disguised emperor sheepishly retreats.", "He climbs back over the wall, accidentally dropping a small jade clasp near the snow-covered stones.", "Jiang Wantang picks up the clasp and sees the hidden dragon pattern in the lamplight." ]},
                    ],
                },
                {
                    "title": "一瓶退烧药换谁的命", "setup_title": "冷宫没人肯来", "setup_narration": "冷宫侍女高烧，太医院不肯来。假侍卫说能调御医，但那会让所有人知道冷宫有异常。", "setup_cast": ["jiang-wantang", "xiao-chengyan"],
                    "setup_beats": ["A young palace maid burns with fever in a sparse cold palace room while Jiang Wantang checks the nearly empty hidden store shelf.", "The disguised Xiao Chengyan offers to summon an imperial doctor, his authority briefly slipping into his voice.", "Jiang Wantang looks between a modern fever medicine bottle and the guarded palace corridor outside."],
                    "s1_title": "一个侍卫，凭什么调御医", "s1_prompt": "你可以直接问他：若你真是侍卫，凭什么调得动御医？", "s1_reason": "侍女生命危险与身份秘密被迫碰撞，主角和皇帝的信任需要实时试探而不提前揭底。", "s1_character": "xiao-chengyan", "s1_goal": "给出含糊但真诚的关心，承认不能解释全部；接受玩家追问，不确认身份。", "s1_forbidden": "不得说自己是皇帝，不得透露御医会如何行动，不得判断哪种药一定有效。", "choice_prompt": "救人要快，秘密也只剩这一层。",
                    "options": [
                        {"id": "use-medicine", "label": "用现代退烧药，保住秘密", "tone": "kindness", "state_delta": {"kindness": -2, "exposure": -1}, "result_title": "药瓶里的代价", "result_narration": "侍女退了烧，货架却暗下去一格。姜晚棠知道超市的善意值被用掉了。", "result_cast": ["jiang-wantang"], "result_beats": ["Jiang Wantang takes the last fever medicine from a glowing shelf as the store lights dim slightly.", "She carefully gives medicine to the sick maid, who gradually steadies her breathing.", "The hidden shelf loses one row of light while Jiang Wantang records the cost in her ledger." ]},
                        {"id": "call-doctor", "label": "让假侍卫调御医", "tone": "trust", "state_delta": {"trust": 2, "exposure": 1}, "result_title": "不该来的御医", "result_narration": "御医深夜赶到，救下侍女，也让冷宫门外多了几双探究的眼睛。", "result_cast": ["jiang-wantang", "xiao-chengyan"], "result_beats": ["The disguised emperor quietly issues an order from the shadowed courtyard.", "An imperial doctor rushes into the cold palace and treats the maid under Jiang Wantang's guarded gaze.", "Servants whisper outside the gate as Jiang Wantang sees more curious eyes gathering in the corridor." ]},
                    ],
                },
                {
                    "title": "冷宫的夜市开张", "setup_title": "每个人都带着秘密", "setup_narration": "姜晚棠把零食、肥皂和保温杯改成冷宫夜市，妃嫔、太监和宫女各怀目的前来交换秘密。皇后的人混入其中。", "setup_cast": ["jiang-wantang"],
                    "setup_beats": ["At night the cold palace courtyard transforms into a discreet market of snacks, soap, cups, and handwritten tokens under warm lanterns.", "Palace maids, eunuchs, and concubines quietly exchange small goods for whispered information while Jiang Wantang observes each face.", "One elegant stranger in a plain cloak pauses beside the soap stall, her gaze too controlled for an ordinary visitor."],
                    "s1_title": "练习一次，不再讨好所有人", "s1_prompt": "姜晚棠想先和你演练：若有人越界要货，我该怎么拒绝，才不再把自己交出去？", "s1_reason": "夜市扩大让敌方渗透风险骤升，主角长期讨好与边界建立需要角色扮演式实时练习。", "s1_goal": "和玩家做简短拒绝演练，表达想保护宫女；将策略收束为开放夜市或熟人会员制。", "s1_forbidden": "不得说出皇后派谁来，不得免费增加情报，不得改变夜市既有货物。", "choice_prompt": "夜市要靠热闹活下去，还是靠边界活下去？",
                    "options": [
                        {"id": "open-market", "label": "接纳所有人，扩大夜市", "tone": "intel", "state_delta": {"intel": 2, "exposure": 2}, "result_title": "热闹里的眼线", "result_narration": "夜市越开越热闹，秘密也越多。姜晚棠拿到关键情报，却发现有人盯上了货架。", "result_cast": ["jiang-wantang"], "result_beats": ["The night market grows lively as many palace workers trade goods and pass hidden notes.", "Jiang Wantang receives a crucial sealed message while smiling politely to customers.", "The cloaked stranger studies the glowing shelves through a gap in hanging lanterns." ]},
                        {"id": "member-market", "label": "只做熟人买卖，严控会员", "tone": "secret", "state_delta": {"intel": 1, "exposure": -1}, "result_title": "一张张会员牌", "result_narration": "夜市安静下来，来的人更少，却每一个都能说出真话。姜晚棠错过了一条线索，也守住了门。", "result_cast": ["jiang-wantang"], "result_beats": ["Jiang Wantang hands simple membership tokens only to trusted palace workers at a quiet gate.", "Inside, a small circle of women share honest information over warm tea and snacks.", "Outside, the cloaked stranger finds the closed courtyard empty and leaves with a suspicious glance." ]},
                    ],
                },
                {
                    "title": "皇帝天天来蹭饭，到底图什么", "setup_title": "火锅后的身份", "setup_narration": "萧承晏在后门吃火锅，终于承认自己就是皇帝，却说他也被朝堂掣肘。冷宫同一刻被搜查。", "setup_cast": ["jiang-wantang", "xiao-chengyan"],
                    "setup_beats": ["Jiang Wantang and Xiao Chengyan share a steaming modern hotpot behind the hidden store shelves, briefly relaxed.", "Xiao Chengyan removes his guard token and reveals an imperial jade seal, his expression serious rather than triumphant.", "Palace search lanterns sweep across the cold palace wall as guards begin pounding on the outer gate."],
                    "s1_title": "信他，会不会又后悔", "s1_prompt": "姜晚棠终于问你：我怕的不是喜欢谁，我怕再一次把命交给别人。信他，会不会后悔？", "s1_reason": "身份揭露、搜宫危机和主角的关系创伤同时爆发，必须由 S1 承接边界、安慰与试探。", "s1_goal": "说出她害怕失去自主而非单纯恋爱；接住劝她结盟或保持边界的意见，随后要求正式选择。", "s1_forbidden": "不得保证皇帝真心，不得剧透搜宫结果，不得让玩家替姜晚棠承诺结盟。", "choice_prompt": "把超市交给皇权保护，还是把命运握回自己手里？",
                    "options": [
                        {"id": "ally-emperor", "label": "与皇帝结盟，公开反击", "tone": "trust", "state_delta": {"trust": 2, "intel": 1, "exposure": 2}, "result_title": "搜宫门前的圣旨", "result_narration": "萧承晏挡在搜宫队前，姜晚棠也不再躲在他身后。两人第一次把话说在所有人面前。", "result_cast": ["jiang-wantang", "xiao-chengyan"], "result_beats": ["Xiao Chengyan steps before the search party and reveals the imperial seal under torchlight.", "Jiang Wantang walks beside him, holding the store ledger rather than hiding behind him.", "The search guards lower their weapons as the cold palace doors open onto a newly visible lit space." ]},
                        {"id": "move-shelves", "label": "自己转移货架，独自应对", "tone": "independent", "state_delta": {"intel": 1, "trust": -1, "exposure": -1}, "result_title": "货架后的暗门", "result_narration": "姜晚棠趁搜宫前转走货架。皇帝站在空屋里，第一次明白她不需要被谁拯救。", "result_cast": ["jiang-wantang", "xiao-chengyan"], "result_beats": ["Jiang Wantang rapidly moves glowing shelves through a hidden rotating wall mechanism.", "The search party enters a plain cold palace room and finds no trace of the store.", "Xiao Chengyan looks at the empty room while Jiang Wantang watches safely from a concealed passage." ]},
                    ],
                },
                {
                    "title": "最后一张会员卡", "setup_title": "超市的最终规则", "setup_narration": "超市给出最终规则：只能给一人一张永久会员卡。姜晚棠要把它交给皇帝、冷宫众人，还是留给自己。", "setup_cast": ["jiang-wantang", "xiao-chengyan"],
                    "setup_beats": ["A single gold membership card appears on a dark counter in the hidden supermarket, casting warm light on Jiang Wantang's face.", "Xiao Chengyan, palace women, and the cold palace staff wait at a respectful distance without reaching for it.", "Jiang Wantang holds the card before the old palace gate as sunrise spreads across the courtyard."],
                    "s1_title": "这张卡，不该再替谁牺牲", "s1_prompt": "姜晚棠问你：我若把它留给自己，会不会又被人说自私？", "s1_reason": "终局将决定主角的依附关系和救助系统归属，她需要确认自我选择不等于自私。", "s1_goal": "支持她保持边界、承认对众人的责任；把决定收束为共同救助或独立经营。", "s1_forbidden": "不得提前宣布终局、不得增加第二张永久卡、不得替任何角色要求卡。", "choice_prompt": "最后一张会员卡，是权力的入口，还是她自己的出口？",
                    "options": [
                        {"id": "share-card", "label": "交给冷宫众人，共同经营救助站", "tone": "intel", "state_delta": {"intel": 2, "kindness": 1}, "result_title": "冷宫合伙人", "result_narration": "姜晚棠把卡放到众人中间。冷宫不再是废弃角落，而成了每个人都能进门的避风处。", "result_cast": ["jiang-wantang", "xiao-chengyan"], "result_beats": ["Jiang Wantang places the gold card in the center of a table surrounded by palace women and staff.", "Together they organize food, medicine, and records in a transformed bright cold palace market.", "Xiao Chengyan waits at the entrance with a bowl, smiling as Jiang Wantang sets the rules." ]},
                        {"id": "keep-card", "label": "留给自己，带着超市离宫开店", "tone": "independent", "state_delta": {"trust": -1, "kindness": 1, "exposure": -1}, "result_title": "独立掌柜", "result_narration": "姜晚棠带着超市走出宫门。萧承晏排在新店门口，手里还攥着那本欠账。", "result_cast": ["jiang-wantang", "xiao-chengyan"], "result_beats": ["Jiang Wantang places the gold card in her own sleeve and walks through the palace gate with the glowing store doorway following.", "A lively new street shop opens with modern shelves inside and an ancient signboard outside.", "Xiao Chengyan waits in an ordinary customer line holding the old debt ledger while Jiang Wantang smiles from behind the counter." ]},
                    ],
                },
            ],
        },
    ]


def build_manifest() -> dict[str, Any]:
    stories = [build_story(spec) for spec in story_specs()]
    stories.extend(load_imported_stories())
    return {
        "manifest_version": 2,
        "source": "四部短剧互动化策划.txt",
        "production": {
            "storyboard_target_seconds": TARGET_SECONDS,
            "q3_clip_seconds": CLIP_SECONDS,
            "video_method": "Each 15-second storyboard is three continuous 5-second Q3 clips concatenated locally as video transitions.",
            "image_model": "viduimage-2",
            "video_models": ["viduq3-mix", "viduq3-drama"],
            "s1_policy": "Only marked high-emotion or consequential decision nodes create a Vidu S1 live session. Free dialogue may influence relationship tone but cannot rewrite formal branches.",
        },
        "stories": stories,
    }


def load_imported_stories() -> list[dict[str, Any]]:
    if not IMPORTS_DIR.exists():
        return []
    stories = []
    for path in sorted(IMPORTS_DIR.glob("*.story.json")):
        with path.open("r", encoding="utf-8") as file:
            story = json.load(file)
        if not isinstance(story, dict):
            raise ValueError(f"{path.name}: imported story must be an object")
        stories.append(story)
    return stories


def validate(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for story in manifest["stories"]:
        nodes = story["nodes"]
        characters = {character["id"] for character in story["characters"]}
        if story["start"] not in nodes:
            errors.append(f"{story['id']}: start node missing")
        for node_id, node in nodes.items():
            if node["type"] == "cutscene":
                plan = node["render_plan"]
                if plan["target_seconds"] != TARGET_SECONDS or len(plan["clips"]) != 3:
                    errors.append(f"{story['id']}:{node_id}: expected three 5-second clips")
                if sum(clip["duration"] for clip in plan["clips"]) != TARGET_SECONDS:
                    errors.append(f"{story['id']}:{node_id}: invalid total duration")
                if not set(plan["cast"]).issubset(characters):
                    errors.append(f"{story['id']}:{node_id}: unknown cast member")
                if node["next"] not in nodes:
                    errors.append(f"{story['id']}:{node_id}: missing next node")
            elif node["type"] == "interactive":
                if node["avatar_character"] not in characters:
                    errors.append(f"{story['id']}:{node_id}: missing S1 avatar")
                if node["next"] not in nodes:
                    errors.append(f"{story['id']}:{node_id}: missing next node")
            elif node["type"] == "choice":
                if not 2 <= len(node["options"]) <= 3:
                    errors.append(f"{story['id']}:{node_id}: formal choice must have two or three options")
                for option in node["options"]:
                    if option["next"] not in nodes:
                        errors.append(f"{story['id']}:{node_id}: missing option target")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the interactive-film FMV manifest.")
    parser.add_argument("--check", action="store_true", help="Validate without writing the manifest.")
    args = parser.parse_args()
    manifest = build_manifest()
    errors = validate(manifest)
    if errors:
        print("\n".join(errors))
        return 1
    if args.check:
        print(f"ok: {len(manifest['stories'])} stories, {sum(len(s['nodes']) for s in manifest['stories'])} nodes")
        return 0
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
