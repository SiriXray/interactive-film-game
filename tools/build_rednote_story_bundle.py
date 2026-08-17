"""Build the three RedNote-style interactive-film stories.

The output keeps the existing manifest contract: Q3 cutscenes are fixed
three-part pre-generated scenes, while S1 nodes handle first-person dialogue
before a formal two-option choice.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "story.json"
ALLOWED_VIDEO_MODELS = {"viduq3-mix", "viduq3-drama"}


def shot_plan(model: str, cast: list[str], beats: list[str]) -> dict[str, Any]:
    if len(beats) != 3:
        raise ValueError("Every Q3 scene must contain exactly three five-second beats.")
    clips = []
    for index, beat in enumerate(beats, start=1):
        continuity = (
            f"Segment {index} of a continuous three-segment 15-second vertical Chinese interactive drama. "
            "Keep faces, costumes, props, lighting, screen direction, and emotional continuity consistent with the supplied character references. "
        )
        if index > 1:
            continuity += "Continue directly from the previous segment without a reset, title card, or time jump. "
        clips.append({
            "id": f"s{index}",
            "duration": 5,
            "model": model,
            "prompt": continuity + beat + " Natural cinematic motion and sound, no captions, no subtitles, no watermark.",
        })
    return {
        "target_seconds": 15,
        "clip_seconds": 5,
        "method": "three-continuous-q3-clips-then-concat",
        "cast": cast,
        "clips": clips,
    }


def cutscene(chapter: str, title: str, narration: str, model: str, cast: list[str], beats: list[str], next_node: str) -> dict[str, Any]:
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
    suggested_questions: list[str],
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
        "suggested_questions": suggested_questions,
        "next": next_node,
    }


def build_story(spec: dict[str, Any]) -> dict[str, Any]:
    story = {key: value for key, value in spec.items() if key != "chapters"}
    nodes: dict[str, Any] = {}
    chapters = spec["chapters"]
    for chapter_index, chapter in enumerate(chapters, start=1):
        prefix = f"{spec['id']}-e{chapter_index}"
        chapter_label = f"第{chapter_index}集 · {chapter['title']}"
        setup_id = f"{prefix}-q3"
        live_id = f"{prefix}-s1"
        choice_id = f"{prefix}-choice"
        next_setup = f"{spec['id']}-e{chapter_index + 1}-q3" if chapter_index < len(chapters) else f"{spec['id']}-ending"

        nodes[setup_id] = cutscene(
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
            chapter["suggested_questions"],
            choice_id,
        )

        options = []
        for option_index, option in enumerate(chapter["options"], start=1):
            result_id = f"{prefix}-result-{option_index}"
            options.append({
                "id": option["id"],
                "label": option["label"],
                "tone": option["tone"],
                "state_delta": option["state_delta"],
                "next": result_id,
            })
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
            "options": options,
        }

    nodes[f"{spec['id']}-ending"] = {
        "type": "ending",
        "chapter": "终局",
        "title": spec["ending"]["title"],
        "text": spec["ending"]["text"],
        "variants": spec["ending"]["variants"],
    }
    story["start"] = f"{spec['id']}-e1-q3"
    story["nodes"] = nodes
    return story


def character(character_id: str, name: str, role: str, voice: str, image_prompt: str) -> dict[str, str]:
    return {"id": character_id, "name": name, "role": role, "voice": voice, "image_prompt": image_prompt}


def story_specs() -> list[dict[str, Any]]:
    return [
        {
            "id": "rednote-haomen-xinsheng",
            "title": "穿书后，全家听见了我的心声",
            "tagline": "养女联手对手做空集团，只有我知道破产倒计时已经开始。",
            "genre": "豪门 / 穿书 / 商战 / 亲情反转",
            "palette": "rose",
            "skin": "modern-family",
            "hero": "顾念",
            "hero_character": "gu-nian",
            "model_plan": "家庭关系、董事会和反击现场使用 Q3 Mix 预生成；玩家通过 S1 追问顾念当下的恐惧、判断和真实心声，再用正式二选一锁定分支。",
            "state_labels": {"evidence": "证据", "family": "家人信任", "risk": "破产风险", "truth": "身份真相"},
            "initial_state": {"evidence": 0, "family": 0, "risk": 0, "truth": 0},
            "characters": [
                character("gu-nian", "顾念", "穿进豪门小说的亲生女儿，冷静但缺乏被爱经验", "Qiao", "Vertical 9:16 premium Chinese modern drama character portrait, Gu Nian, a sharp young woman in her early twenties with calm observant eyes, shoulder-length black hair, understated cream blouse and dark blazer, standing in a luxury mansion corridor, realistic cinematic lighting, no text, no watermark."),
                character("gu-tingchuan", "顾廷川", "顾氏集团董事长，外冷内重情的父亲", "Dylan", "Vertical 9:16 premium Chinese modern drama character portrait, Gu Tingchuan, a composed wealthy Chinese businessman in his fifties, silver at the temples, dark tailored suit, tired eyes, luxury office background, realistic cinematic lighting, no text, no watermark."),
                character("shen-lan", "沈岚", "顾夫人，温柔敏感，最早察觉女儿心声的母亲", "Sohee", "Vertical 9:16 premium Chinese modern drama character portrait, Shen Lan, an elegant Chinese woman in her forties with soft worried eyes, dark silk blouse and pearl earrings, warm mansion interior, realistic cinematic lighting, no text, no watermark."),
                character("lin-wanqing", "林晚晴", "被收养多年的养女，擅长伪装和操纵舆论", "Momo", "Vertical 9:16 premium Chinese modern drama character portrait, Lin Wanqing, a polished young Chinese woman in her early twenties with a gentle smile and calculating eyes, pale pink dress, luxury banquet hall, realistic cinematic lighting, no text, no watermark."),
                character("zhou-yan", "周砚", "对手集团继承人，林晚晴的秘密合作方", "Dylan", "Vertical 9:16 premium Chinese modern drama character portrait, Zhou Yan, a handsome ambitious Chinese man in his late twenties, charcoal suit, restrained smile, glass boardroom background, realistic cinematic lighting, no text, no watermark."),
            ],
            "ending": {
                "title": "听见之后，终于成为一家人",
                "text": "顾念没有再靠一句心声证明自己。她用选择留下证据，也用选择决定这家人是否真正成为家人。",
                "variants": [
                    {"when": {"evidence": 4, "family": 3, "truth": 2}, "title": "全家反击成功", "text": "顾氏保住控制权，林晚晴和周砚的做空证据完整公开。顾廷川把董事长的位置交给顾念，沈岚第一次当众叫她‘女儿’。"},
                    {"when": {"evidence": 3, "truth": 2}, "title": "公司保住了，亲情还在重建", "text": "顾氏躲过破产，但顾念选择把林晚晴交给法律，顾家从此开始一段迟到的相认。"},
                    {"when": {}, "title": "破产前夜的真相", "text": "真相浮出水面，却没能及时阻止所有损失。顾念带着母亲留下的证据离开豪门，决定从零开始。"},
                ],
            },
            "chapters": [
                {
                    "title": "认亲宴上的第一句心声",
                    "setup_title": "她笑着欢迎我回家",
                    "setup_narration": "顾念在认亲宴上醒来，知道自己穿进了小说，也知道今天晚上林晚晴会把她塑造成贪慕虚荣的冒牌货。她没想到，顾廷川和沈岚竟然听见了她没有说出口的心声。",
                    "setup_cast": ["gu-nian", "gu-tingchuan", "shen-lan", "lin-wanqing"],
                    "setup_beats": ["At a luxurious family recognition banquet, Gu Nian steps into the light while the Gu family and Lin Wanqing watch her carefully.", "Gu Nian silently notices a hidden champagne glass and thinks that Lin Wanqing is preparing a public trap; Gu Tingchuan suddenly looks toward her.", "Shen Lan grips the table edge after hearing an unspoken sentence, while Lin Wanqing raises a perfect welcoming smile and prepares to speak."],
                    "s1_title": "他们真的听见了吗？",
                    "s1_prompt": "顾念压低声音问你：如果爸妈真的听见了我的心声，我现在该不该利用这一点？你可以问她在看到林晚晴微笑时到底在想什么。",
                    "s1_reason": "开局同时建立超自然规则、家庭关系和养女陷阱；S1让玩家先和顾念建立秘密同盟。",
                    "s1_character": "gu-nian",
                    "s1_goal": "允许顾念表达不信任与委屈；让玩家追问她的真实心声；最后收束到公开试探或装作不知两个选择。",
                    "s1_forbidden": "不得直接揭示林晚晴最终结局，不得让父母替玩家完成正式选择，不得确认所有心声规则。",
                    "suggested_questions": ["你第一次看见林晚晴时在想什么？", "爸妈听见你的心声，你是害怕还是觉得终于有人站在你这边？", "如果他们不信你，你还会救这个家吗？"],
                    "choice_prompt": "第一场宴会，你要先争取规则，还是先藏住底牌？",
                    "options": [
                        {"id": "test-heart", "label": "故意想一句只有父母才知道的话，试探他们", "tone": "truth", "state_delta": {"family": 1, "risk": 1}, "result_title": "父母同时失神", "result_narration": "一句没有说出口的童年细节让顾廷川和沈岚同时停住。林晚晴的祝酒词被掌声盖过，但她察觉到气氛已经变了。", "result_cast": ["gu-nian", "gu-tingchuan", "shen-lan", "lin-wanqing"], "result_beats": ["Gu Nian looks down at a family photograph and silently forms a private childhood memory.", "Gu Tingchuan and Shen Lan exchange a shocked glance, realizing the thought was impossible for an outsider to know.", "Lin Wanqing notices the parents' change and quietly crushes the edge of her speech card."],},
                        {"id": "hide-heart", "label": "装作什么都不知道，先观察林晚晴的下一步", "tone": "strategy", "state_delta": {"evidence": 1, "risk": -1}, "result_title": "笑容里的刀锋", "result_narration": "顾念没有拆穿任何人，只在林晚晴递来果汁时换了杯子。夜深后，书房里传出一份被删改过的集团简报。", "result_cast": ["gu-nian", "lin-wanqing"], "result_beats": ["Gu Nian accepts the drink with a polite smile and watches Lin Wanqing's fingers tremble for half a second.", "After the banquet, Gu Nian discovers a redacted financial briefing hidden under a book in the study.", "A security camera catches Lin Wanqing entering the study after midnight while Gu Nian keeps the evidence hidden."],},
                    ],
                },
                {
                    "title": "做空倒计时",
                    "setup_title": "顾氏的股价开始下坠",
                    "setup_narration": "第二天，顾氏集团遭遇连续抛售。林晚晴以关心为名建议父亲加杠杆回购，顾念知道那是把全家推向深渊的第一步。",
                    "setup_cast": ["gu-nian", "gu-tingchuan", "lin-wanqing", "zhou-yan"],
                    "setup_beats": ["A giant stock market screen shows Gu Group shares falling as executives rush through a glass boardroom.", "Lin Wanqing presents a confident recovery plan while Zhou Yan watches from a private car through the city rain.", "Gu Nian spots a familiar shell-company name in a printed loan agreement and realizes the attack has already entered the family office."],
                    "s1_title": "签下那份贷款时，你在想什么？",
                    "s1_prompt": "顾念把贷款协议推到你面前：如果我现在告诉爸爸，他可能会先怪我。你想问她是害怕失去父亲，还是害怕来不及救公司。",
                    "s1_reason": "这是首个明确的商战倒计时，S1负责让玩家理解顾念的风险判断，而不是直接替她算账。",
                    "s1_goal": "承认顾念对父亲的不安；允许玩家追问她在董事会被否定时的真实想法；收束到立即报警或先找原始账本。",
                    "s1_forbidden": "不得凭空生成完整证据，不得直接让周砚认罪，不得改变股价或董事会表决结果。",
                    "suggested_questions": ["你看到爸爸准备签字时，为什么没有立刻冲过去？", "你觉得爸爸会相信亲生女儿还是养了二十年的女儿？", "你现在最怕的是公司破产，还是再次被丢下？"],
                    "choice_prompt": "只剩几个小时，先把危险说出去，还是先拿到能让所有人闭嘴的证据？",
                    "options": [
                        {"id": "warn-father", "label": "当场阻止父亲签字，公开指出林晚晴的方案有问题", "tone": "family", "state_delta": {"family": 1, "risk": -1}, "result_title": "会议室里的第一次争吵", "result_narration": "顾念被当成搅局者，但顾廷川没有签字。林晚晴第一次失去从容，周砚的电话在她口袋里震个不停。", "result_cast": ["gu-nian", "gu-tingchuan", "lin-wanqing"], "result_beats": ["Gu Nian reaches across the boardroom table before Gu Tingchuan signs the leverage agreement.", "Executives argue while Gu Tingchuan studies his daughter's face and slowly puts down the pen.", "Lin Wanqing steps into a corridor and answers a tense call from Zhou Yan, hiding her anger."],},
                        {"id": "find-ledger", "label": "暂时不揭穿，先去找被删掉的原始账本", "tone": "evidence", "state_delta": {"evidence": 2, "risk": 1}, "result_title": "保险柜里的第二份账", "result_narration": "顾念趁夜找到旧保险柜，里面不是账本，而是一张写着她出生日期的医院缴费单。做空证据和身世证据同时出现。", "result_cast": ["gu-nian", "shen-lan"], "result_beats": ["Gu Nian enters the family archive room after midnight and finds a hidden safe behind a painting.", "Inside are a hospital payment receipt, an old bracelet, and a partial ledger showing transfers to a shell company.", "Shen Lan appears in the doorway, holding back tears as she recognizes the bracelet from the day her baby disappeared."],},
                    ],
                },
                {
                    "title": "养女的眼泪",
                    "setup_title": "她说自己只是想保住这个家",
                    "setup_narration": "林晚晴在雨夜拦住顾念，哭着说自己也被周砚利用。可顾念知道，小说里这一场眼泪之后，所有脏账都会落到她头上。",
                    "setup_cast": ["gu-nian", "lin-wanqing", "zhou-yan"],
                    "setup_beats": ["In a rain-soaked driveway, Lin Wanqing kneels beside a car and claims she was manipulated.", "Gu Nian notices a second phone lighting up inside Lin Wanqing's coat with Zhou Yan's name on the screen.", "A folder of forged messages is left on the wet ground, designed to make Gu Nian look like the insider who sold the company."],
                    "s1_title": "她哭的时候，你相信过她吗？",
                    "s1_prompt": "顾念看着林晚晴的眼泪问你：如果她真的有一点后悔，我还要不要给她一次机会？你可以问顾念在听见那通电话时心里先出现的是愤怒还是难过。",
                    "s1_reason": "将反派从单纯恶人变成情感陷阱，S1承载玩家对动机的追问和顾念的边界建立。",
                    "s1_goal": "让顾念说出被抢走人生的感受；允许玩家建议套话或直接对质；最后落到留下录音或立刻报警。",
                    "s1_forbidden": "不得直接让林晚晴交出全部证据，不得洗白她的犯罪行为，不得在自由对话中跳到最终审判。",
                    "suggested_questions": ["她说对不起的时候，你心里有一瞬间想原谅吗？", "你最想问林晚晴的一句话是什么？", "如果她只是害怕失去豪门生活，你还会救她吗？"],
                    "choice_prompt": "眼泪可能是真的，证据也可能是真的。你要把她留在身边，还是把她送进调查程序？",
                    "options": [
                        {"id": "record-confession", "label": "先陪她演下去，设法录下她和周砚的交易", "tone": "strategy", "state_delta": {"evidence": 2, "family": -1, "risk": -1}, "result_title": "雨声盖住了真话", "result_narration": "林晚晴说出关键账户，却发现顾念早已打开录音。证据足够了，可顾念也亲手把最后一点姐妹情推入了雨里。", "result_cast": ["gu-nian", "lin-wanqing", "zhou-yan"], "result_beats": ["Gu Nian offers Lin Wanqing an umbrella and quietly places a recorder beneath the car mirror.", "Lin Wanqing makes a desperate call and reveals the offshore account routing to Zhou Yan.", "The recorder light blinks in the rain as Gu Nian turns away, expression controlled but devastated."],},
                        {"id": "confront-now", "label": "直接拿出手机对质，逼她说清楚和周砚的关系", "tone": "heart", "state_delta": {"family": 1, "evidence": 1, "risk": 1}, "result_title": "她终于喊出真相", "result_narration": "林晚晴失控承认自己把顾氏的内部资料给了周砚，却坚持说顾家欠她一条命。顾念获得了一份不完整的口供。", "result_cast": ["gu-nian", "lin-wanqing"], "result_beats": ["Gu Nian holds up the phone showing the call record and asks Lin Wanqing to stop pretending.", "Lin Wanqing's gentle mask breaks; she admits sending internal files while rain runs down her face.", "Gu Nian listens without interrupting as the two women stand on opposite sides of the driveway."],},
                    ],
                },
                {
                    "title": "亲生证明",
                    "setup_title": "一张旧病历把两条线连在一起",
                    "setup_narration": "沈岚确认旧手镯属于当年失踪的亲生女儿，医院病历也证明顾念就是那个孩子。但公开身世会让董事会认为顾家内斗，林晚晴则可能提前销毁全部证据。",
                    "setup_cast": ["gu-nian", "shen-lan", "gu-tingchuan", "lin-wanqing"],
                    "setup_beats": ["In a quiet hospital archive, Shen Lan opens a decades-old medical record with shaking hands.", "A nurse compares Gu Nian's birth mark and the old bracelet while Gu Tingchuan watches from behind the glass.", "Lin Wanqing sees a leaked DNA report on a monitor and begins deleting files from a hidden laptop."],
                    "s1_title": "知道自己是亲生女儿，你开心吗？",
                    "s1_prompt": "顾念拿着亲子鉴定报告问你：我等了这么久，为什么第一反应不是开心？你可以问她在看见妈妈哭的时候，心里真正想说什么。",
                    "s1_reason": "身份翻转是情感核心，S1让玩家参与‘被认回’而不是只观看一张鉴定报告。",
                    "s1_goal": "让顾念区分血缘确认与情感确认；允许玩家追问她是否愿意叫父母；最后选择公开身世或暂时封存。",
                    "s1_forbidden": "不得把血缘证明写成自动解决亲情，不得让顾念瞬间原谅所有人，不得跳过公司危机。",
                    "suggested_questions": ["你想过妈妈可能也在找你吗？", "如果他们早点知道，你的人生会不一样吗？", "你现在愿意叫他们爸爸妈妈吗？"],
                    "choice_prompt": "真相已经在手里，但公开的时机决定顾氏能不能撑过明天。",
                    "options": [
                        {"id": "public-dna", "label": "立刻公开亲子鉴定，让顾念获得合法继承人身份", "tone": "truth", "state_delta": {"truth": 2, "family": 1, "risk": 1}, "result_title": "直播里的亲生女儿", "result_narration": "顾氏发布会临时变成认亲现场，舆论转向顾家内斗。林晚晴趁乱带走了最后一份服务器备份。", "result_cast": ["gu-nian", "gu-tingchuan", "shen-lan", "lin-wanqing"], "result_beats": ["Gu Nian walks onto a press stage holding the sealed DNA report as cameras turn toward her.", "Gu Tingchuan publicly says she is his biological daughter while Shen Lan reaches for her hand.", "Outside the venue, Lin Wanqing slips a hard drive into her bag and disappears into a waiting car."],},
                        {"id": "seal-dna", "label": "暂时封存身世，只把做空证据交给父亲", "tone": "strategy", "state_delta": {"truth": 1, "evidence": 1, "risk": -1, "family": 1}, "result_title": "先救公司，再认家人", "result_narration": "顾念没有急着要名分，只把账本和录音放到顾廷川面前。父亲第一次不问她是不是亲生，只问她想怎么做。", "result_cast": ["gu-nian", "gu-tingchuan"], "result_beats": ["Gu Nian closes the DNA report and places the ledger and recording on Gu Tingchuan's desk.", "Gu Tingchuan listens in silence, then asks his daughter what decision she wants him to make.", "The two stand over a city map and mark the shell-company accounts instead of looking at the test result."]},
                    ],
                },
                {
                    "title": "董事会反杀",
                    "setup_title": "所有人都在等顾氏认输",
                    "setup_narration": "周砚带着债权人闯入董事会，林晚晴提交了伪造的内部泄密记录。顾念手里的证据足以扭转局面，但必须冒险让对手先出手。",
                    "setup_cast": ["gu-nian", "gu-tingchuan", "lin-wanqing", "zhou-yan"],
                    "setup_beats": ["A tense board meeting fills with creditors as Zhou Yan projects a forged internal-leak timeline.", "Lin Wanqing points toward Gu Nian while directors demand that the Gu family surrender control.", "Gu Nian quietly opens a folder containing call recordings, transfer records, and the original hospital receipt."],
                    "s1_title": "把他们逼到悬崖边，你怕吗？",
                    "s1_prompt": "顾念在会议室门外问你：如果我让周砚先宣布收购，证据就能一次性对上。可只要一步错，顾氏真的会没。你可以问她在爸爸点头时想的是什么。",
                    "s1_reason": "商战高潮适合用 S1 让玩家感受到实时风险，再把策略选择交还给正式分支。",
                    "s1_goal": "让顾念说出‘想赢’与‘怕失去家人’的冲突；允许玩家建议诱敌或直接公开证据；随后进入二选一。",
                    "s1_forbidden": "不得在对话中提前公布收购结果，不得让 S1 替代董事会表决，不得添加第三个商业方案。",
                    "suggested_questions": ["你准备把所有人都推到对立面时，在想谁会先离开？", "如果爸爸不相信你，你还会继续吗？", "你有没有想过放弃顾氏？"],
                    "choice_prompt": "最后一局，要先让周砚宣布胜利，还是直接把证据砸在桌上？",
                    "options": [
                        {"id": "bait-acquisition", "label": "假装资金断裂，引周砚先宣布低价收购", "tone": "strategy", "state_delta": {"evidence": 2, "risk": -2, "family": 1}, "result_title": "收购协议变成自首书", "result_narration": "周砚在众目睽睽下签下协议，顾念随即播放完整录音和资金流。债权人转身把矛头对准周家。", "result_cast": ["gu-nian", "gu-tingchuan", "zhou-yan", "lin-wanqing"], "result_beats": ["Gu Tingchuan lowers his head as if defeated while Zhou Yan confidently signs the acquisition agreement.", "Gu Nian activates the projector and displays the original ledger, call recording transcript, and account trail.", "The creditors turn toward Zhou Yan as Lin Wanqing realizes the document she signed has become evidence against them."],},
                        {"id": "show-evidence", "label": "立即公开证据，放弃用顾氏股权做诱饵", "tone": "truth", "state_delta": {"evidence": 1, "risk": -1, "family": 2, "truth": 1}, "result_title": "证据先于胜负落地", "result_narration": "顾念把证据交给监管和警方，顾氏暂时失去部分股权，却避免被彻底掏空。顾廷川把董事会的最后一票交给她。", "result_cast": ["gu-nian", "gu-tingchuan", "shen-lan"], "result_beats": ["Gu Nian hands sealed evidence packets to regulators and police at the boardroom door.", "Directors argue over the damaged share price, but the forced takeover is halted before completion.", "Gu Tingchuan places his voting proxy in Gu Nian's hand while Shen Lan watches from the back of the room."]},
                    ],
                },
                {
                    "title": "留下谁，放下谁",
                    "setup_title": "破产危机解除后的家宴",
                    "setup_narration": "顾氏暂时保住了，但林晚晴已经被带回调查。她承认参与做空，却说自己只是想留住这座把她养大的房子。顾念必须决定复仇的终点。",
                    "setup_cast": ["gu-nian", "gu-tingchuan", "shen-lan", "lin-wanqing"],
                    "setup_beats": ["A quiet family dining room sits untouched after the crisis, with an empty place setting for Lin Wanqing.", "Gu Tingchuan reads the investigation notice while Shen Lan places the old bracelet beside Gu Nian's bowl.", "Lin Wanqing is seen through a glass interview-room wall, no longer able to hide behind tears or a family name."],
                    "s1_title": "真相之后，你还想要这个家吗？",
                    "s1_prompt": "顾念看着空着的座位问你：他们现在都说我是女儿，可我还不知道要不要留下。你可以问她想留下的是家人，还是终于得到的名分。",
                    "s1_reason": "结尾不再是单纯‘打败反派’，而是把玩家带回深关系：顾念如何定义家。",
                    "s1_goal": "让顾念复盘六集中的关键选择；允许玩家安慰、追问或劝她设立边界；最后选择从轻处理或彻底追责。",
                    "s1_forbidden": "不得替玩家宣布林晚晴的法律结果，不得抹掉她造成的损失，不得保证一家人立即和解。",
                    "suggested_questions": ["你愿意留下，是因为他们听见了你的心声吗？", "如果林晚晴没有做空公司，你会和她成为朋友吗？", "你真正想从爸爸妈妈那里听到什么？"],
                    "choice_prompt": "你终于拥有决定权：给她一条改过的路，还是让所有账都交给法律？",
                    "options": [
                        {"id": "legal-accountability", "label": "坚持完整追责，不再用亲情替犯罪买单", "tone": "truth", "state_delta": {"evidence": 1, "family": 1, "risk": -1}, "result_title": "迟到的边界", "result_narration": "顾念没有替任何人求情。沈岚哭着接受，顾廷川沉默许久后第一次尊重她的决定。", "result_cast": ["gu-nian", "gu-tingchuan", "shen-lan", "lin-wanqing"], "result_beats": ["Gu Nian signs the formal statement without looking away from Lin Wanqing through the glass.", "Shen Lan cries but does not stop her; Gu Tingchuan takes back the family seal and accepts the legal process.", "At dawn, Gu Nian returns to the mansion by choice, not as an accused outsider or a replacement daughter."],},
                        {"id": "conditional-mercy", "label": "保留证据完整，只请求她协助追回资产换取从轻", "tone": "family", "state_delta": {"family": 2, "evidence": 1, "truth": 1}, "result_title": "家不是免罪牌", "result_narration": "林晚晴交出最后的账户和周砚的联系方式，顾念仍要求她承担责任。顾家没有回到从前，却终于学会了把爱和边界放在一起。", "result_cast": ["gu-nian", "lin-wanqing", "gu-tingchuan", "shen-lan"], "result_beats": ["Lin Wanqing hands over a final encrypted drive and gives the investigators Zhou Yan's direct contact.", "Gu Nian tells her that cooperation can reduce harm but cannot erase what she did.", "The family eats a silent first meal together with one empty chair and the old bracelet between them."]},
                    ],
                },
            ],
        },
        {
            "id": "rednote-huangzai-gonglue",
            "title": "穿进饥荒文后，我先救人再攻略男主",
            "tagline": "系统要我拿下冷面男主，可城外的百姓已经没有下一顿饭。",
            "genre": "女频穿书 / 饥荒 / 救灾 / 先婚后爱",
            "palette": "amber",
            "skin": "ancient-timetravel",
            "hero": "苏晚星",
            "hero_character": "su-wanxing",
            "model_plan": "灾情、赈粮、城门和结局战场使用 Q3 Mix 预生成；S1让玩家第一视角追问苏晚星与谢沉舟在救人与攻略之间的真实取舍。",
            "state_labels": {"people": "百姓生存", "trust": "男主信任", "skill": "技能掌控", "exposure": "身份暴露"},
            "initial_state": {"people": 0, "trust": 0, "skill": 0, "exposure": 0},
            "characters": [
                character("su-wanxing", "苏晚星", "穿进饥荒小说的现代急救员，绑定攻略系统", "Sohee", "Vertical 9:16 cinematic Chinese historical drama portrait, Su Wanxing, a clever young woman in her early twenties with determined eyes, simple dusty blue ancient robe, leather medical satchel, famine-stricken town behind her, realistic cinematic lighting, no text, no watermark."),
                character("xie-chenzhou", "谢沉舟", "被系统指定攻略的冷面县令，实际在暗中护民", "Dylan", "Vertical 9:16 cinematic Chinese historical drama portrait, Xie Chenzhou, a handsome stern Chinese magistrate in his late twenties, dark official robe, tired eyes, windblown hair, famine relief camp behind him, realistic cinematic lighting, no text, no watermark."),
                character("qiao-yun", "乔云", "会医术的流民少女，苏晚星的第一位同伴", "Qiao", "Vertical 9:16 cinematic Chinese historical drama portrait, Qiao Yun, a brave teenage Chinese girl with patched brown robe, bright alert eyes, carrying herbs in a woven basket, dusty relief camp, realistic cinematic lighting, no text, no watermark."),
                character("he-taishou", "何太守", "囤积赈粮、与商会勾结的地方官", "Momo", "Vertical 9:16 cinematic Chinese historical drama portrait, He Taishou, a heavyset corrupt Chinese official in his fifties, ornate dark red robe, guarded expression, grain warehouse background, realistic cinematic lighting, no text, no watermark."),
            ],
            "ending": {
                "title": "攻略之外，与你共看长安灯",
                "text": "苏晚星最终发现，真正让谢沉舟爱上的不是她完成了多少任务，而是她在每一次能离开的时候都选择留下救人。",
                "variants": [
                    {"when": {"people": 4, "trust": 3, "skill": 2}, "title": "共治新朝", "text": "灾情被控制，谢沉舟辞去虚名与苏晚星共同建立常平仓。系统任务完成，但他们把余生写成了没有攻略提示的日子。"},
                    {"when": {"people": 3, "trust": 2}, "title": "男主终于追上她", "text": "苏晚星救下了城中大半百姓，却准备离开这个世界。谢沉舟在城门外说出的不是挽留任务，而是他自己的选择。"},
                    {"when": {}, "title": "完成任务，错过一生", "text": "系统判定攻略成功，苏晚星却没能留下足够的粮道和信任。谢沉舟记住了她的名字，却只能在荒年之后独自守城。"},
                ],
            },
            "chapters": [
                {
                    "title": "系统说先攻略",
                    "setup_title": "男主递来一碗稀粥",
                    "setup_narration": "苏晚星睁眼时，城外已经排起逃荒长队。系统要求她在三天内获得谢沉舟的好感，可谢沉舟把唯一一碗稀粥递给了一个孩子。",
                    "setup_cast": ["su-wanxing", "xie-chenzhou", "qiao-yun"],
                    "setup_beats": ["A famine relief line stretches outside a dusty county gate while Su Wanxing wakes beside an empty water jar.", "Xie Chenzhou silently gives his thin bowl of porridge to a starving child and turns away before anyone can thank him.", "A translucent mission-like glow reflects in Su Wanxing's eyes as she sees the system's demand, while Qiao Yun collapses nearby."],
                    "s1_title": "你把粥递出去时在想什么？",
                    "s1_prompt": "苏晚星看着谢沉舟问你：系统让我攻略他，可他连自己的粥都不要。你可以问她在第一次见到谢沉舟时，是先心动还是先觉得这个人太傻。",
                    "s1_reason": "首集要把‘攻略男主’和‘救灾现实’放在同一个画面里，S1负责让玩家选择价值优先级。",
                    "s1_goal": "让苏晚星承认任务诱惑与救人冲动并存；允许玩家追问谢沉舟的动机；收束到先完成攻略礼物或先救身边流民。",
                    "s1_forbidden": "不得直接完成好感任务，不得揭示系统真正来历，不得让粮食凭空增加。",
                    "suggested_questions": ["你对谢沉舟的第一印象是什么？", "如果救人会让攻略失败，你还会救吗？", "你看到乔云倒下时，最先想到的是任务还是她的命？"],
                    "choice_prompt": "第一步，你要把自己变成男主眼里的特殊之人，还是先把眼前的人救活？",
                    "options": [
                        {"id": "gift-to-hero", "label": "把系统奖励的一块精粮送给谢沉舟", "tone": "romance", "state_delta": {"trust": 1, "exposure": 1}, "result_title": "他没有接那块粮", "result_narration": "谢沉舟看穿了苏晚星想讨好他的意图，却把粮食转交给了排队的老人。他第一次记住她，却不是因为她完成了任务。", "result_cast": ["su-wanxing", "xie-chenzhou"], "result_beats": ["Su Wanxing offers a small sealed grain cake to Xie Chenzhou under the watchful relief line.", "Xie Chenzhou studies her, refuses the gift, and passes it to an elderly woman at the end of the line.", "Su Wanxing looks embarrassed while Xie Chenzhou glances back, clearly remembering her face."],},
                        {"id": "save-qiao-yun", "label": "把奖励换成药材，先救昏倒的乔云", "tone": "people", "state_delta": {"people": 1, "skill": 1, "trust": -1}, "result_title": "她先救了一个陌生人", "result_narration": "苏晚星用奖励换出退热药，配合简易补液救回乔云。谢沉舟站在雨棚外看了很久，系统的好感值却纹丝不动。", "result_cast": ["su-wanxing", "qiao-yun", "xie-chenzhou"], "result_beats": ["Su Wanxing tears open a small medicine packet and begins a careful emergency treatment for Qiao Yun.", "Qiao Yun's breathing steadies as Su Wanxing explains how to mix water, salt, and grain powder.", "Xie Chenzhou watches from the edge of the shelter and silently orders an aide to remember Su Wanxing's name."],},
                    ],
                },
                {
                    "title": "粮仓里的老鼠",
                    "setup_title": "赈粮没有消失，是从没出过仓",
                    "setup_narration": "乔云带苏晚星找到一座封锁粮仓，账面上写着已经发完，仓门却传来谷粒滚动声。谢沉舟也在查，但他不能公开动何太守。",
                    "setup_cast": ["su-wanxing", "xie-chenzhou", "qiao-yun", "he-taishou"],
                    "setup_beats": ["At night, Su Wanxing and Qiao Yun hear grain shifting behind a sealed warehouse door marked as empty.", "Xie Chenzhou stands in shadow with a blood-stained ledger, while He Taishou's guards patrol the alley.", "A hidden grain sack tears open beneath a cart, revealing enough food to keep the town alive for weeks."],
                    "s1_title": "你为什么不直接抓他？",
                    "s1_prompt": "谢沉舟在暗处告诉你：现在抓何太守，粮道会立刻断。你可以问他在忍耐时有没有想过牺牲百姓，也可以问他是否信任你。",
                    "s1_reason": "让男主的‘冷’有具体政治代价，S1是玩家与男主建立共谋关系的第一个深互动点。",
                    "s1_character": "xie-chenzhou",
                    "s1_goal": "让谢沉舟解释‘抓人’和‘救人’的冲突；允许玩家追问他对苏晚星的信任；收束到偷粮放粮或先拿总账。",
                    "s1_forbidden": "不得让何太守在自由对话中自首，不得直接生成完整证据链，不得让玩家绕过正式选择同时完成两件事。",
                    "suggested_questions": ["你说不能抓人的时候，心里最愧对谁？", "你为什么愿意把这个秘密告诉我？", "如果我不信你，你会怎么做？"],
                    "choice_prompt": "今晚只能先动一个地方：粮仓，还是账房？",
                    "options": [
                        {"id": "open-grain", "label": "带人撬开粮仓，先把粮食发给百姓", "tone": "people", "state_delta": {"people": 2, "trust": 1, "exposure": 1}, "result_title": "夜开官仓", "result_narration": "粮食被一袋袋抬出，百姓暂时得救，何太守却立刻把罪名扣到谢沉舟头上。谢沉舟没有责怪苏晚星，只问她准备好承担了吗。", "result_cast": ["su-wanxing", "xie-chenzhou", "qiao-yun", "he-taishou"], "result_beats": ["Su Wanxing and Qiao Yun break the warehouse lock as hungry villagers gather with empty baskets.", "Grain pours into the night as Xie Chenzhou takes responsibility and steps between the crowd and armed guards.", "He Taishou points at Xie Chenzhou in fury while Su Wanxing realizes the whole county now knows their secret."],},
                        {"id": "take-ledger", "label": "先潜入账房，拿到能扳倒何太守的总账", "tone": "evidence", "state_delta": {"skill": 1, "trust": 1, "people": -1, "exposure": -1}, "result_title": "账本比粮袋更重", "result_narration": "苏晚星拿到总账，却看见城外又有一批人倒下。谢沉舟接过账本时没有表扬她，只把自己的官印放在她掌心。", "result_cast": ["su-wanxing", "xie-chenzhou"], "result_beats": ["Su Wanxing slips into the accounting room and uses a small improvised tool to open a locked drawer.", "The master ledger reveals diverted grain routes and a merchant network tied to He Taishou.", "Xie Chenzhou takes the ledger, then places his official seal in Su Wanxing's hand as a silent promise to act."],},
                    ],
                },
                {
                    "title": "一城发热",
                    "setup_title": "城门开，疫气也开",
                    "setup_narration": "饥民涌入县城，水源污染让高热迅速蔓延。苏晚星知道隔离会引发暴乱，不隔离又会死更多人。谢沉舟把城门钥匙交给她。",
                    "setup_cast": ["su-wanxing", "xie-chenzhou", "qiao-yun"],
                    "setup_beats": ["A crowded county gate fills with coughing refugees as guards hesitate to open the heavy wooden doors.", "Su Wanxing examines a water jar and sees signs of contamination while Qiao Yun carries feverish children toward a shelter.", "Xie Chenzhou places the gate key on Su Wanxing's palm and tells the soldiers to follow her order for one night."],
                    "s1_title": "关上城门时，你怕被恨吗？",
                    "s1_prompt": "苏晚星握着城门钥匙问你：救更多人，可能要先让一部分人进不来。你可以问她在听见孩子哭的时候，还能不能坚持隔离。",
                    "s1_reason": "这是技能价值和道德压力同时爆发的节点，S1可让玩家以第一视角参与她的临场判断。",
                    "s1_goal": "让苏晚星说明隔离不是冷血；允许玩家追问她对谢沉舟托付的感受；收束到严格隔离或开放城门分区救治。",
                    "s1_forbidden": "不得保证零感染，不得凭空出现现代医疗设备，不得让谢沉舟替玩家承担全部舆论。",
                    "suggested_questions": ["你关门的时候，最怕大家骂你什么？", "谢沉舟把钥匙给你，你觉得那是信任还是推责？", "你有没有一刻想把钥匙还给他？"],
                    "choice_prompt": "救灾没有完美答案：先守住城内，还是分区开放城门？",
                    "options": [
                        {"id": "strict-quarantine", "label": "暂时关闭城门，建立分区隔离与净水点", "tone": "skill", "state_delta": {"people": 1, "skill": 1, "trust": 1}, "result_title": "城门外的灯", "result_narration": "城门暂时关闭，苏晚星把净水和分区流程写在木板上。百姓骂过她，也因为这套方法活了下来。", "result_cast": ["su-wanxing", "xie-chenzhou", "qiao-yun"], "result_beats": ["Su Wanxing hangs hand-written quarantine signs and sets separate water stations under the gate tower.", "Xie Chenzhou faces an angry crowd while Qiao Yun distributes boiled water to the waiting refugees.", "At dawn, fever cases inside the city begin to fall as lanterns remain lit outside the closed gate."],},
                        {"id": "open-zones", "label": "开放城门，但把人群分区逐批检查救治", "tone": "people", "state_delta": {"people": 2, "skill": 1, "exposure": 1}, "result_title": "边进边救", "result_narration": "城门没有彻底关上，伤病和风险一起涌入。苏晚星几乎一夜未眠，谢沉舟在她身边守到最后一盏灯。", "result_cast": ["su-wanxing", "xie-chenzhou", "qiao-yun"], "result_beats": ["The county gate opens in narrow sections as refugees are checked and guided to marked treatment areas.", "Su Wanxing coordinates a line of water, cloth masks, and fever checks while Qiao Yun records names.", "Xie Chenzhou carries a child through the rain and looks at Su Wanxing with exhausted trust."],},
                    ],
                },
                {
                    "title": "攻略值满格",
                    "setup_title": "系统要她在万人面前告白",
                    "setup_narration": "系统突然发布强制任务：在赈灾台上向谢沉舟告白，才能解锁高级技能。可此时何太守准备借百姓暴动夺权，谢沉舟也已经被推到风口浪尖。",
                    "setup_cast": ["su-wanxing", "xie-chenzhou", "he-taishou", "qiao-yun"],
                    "setup_beats": ["A public relief platform stands before a restless crowd as a glowing mission prompt reflects in Su Wanxing's eyes.", "Xie Chenzhou reads an emergency report while He Taishou's men quietly hand out stones and rumors.", "Qiao Yun spots the first spark of a riot near the grain carts as the system demands a romantic confession."],
                    "s1_title": "如果告白能救人，你会说吗？",
                    "s1_prompt": "苏晚星问你：系统说只要我现在告白，就能换来净水技能。可我不想把喜欢变成一笔交易。你可以问她对谢沉舟是真的动心，还是只是习惯并肩作战。",
                    "s1_reason": "把攻略机制变成情感伦理问题，S1让玩家直接参与‘任务奖励’与‘真实感情’的辨认。",
                    "s1_goal": "让苏晚星区分任务和心意；允许玩家追问她在谢沉舟受伤时的第一反应；收束到公开告白换技能或拒绝任务守住尊严。",
                    "s1_forbidden": "不得直接解锁技能，不得代替谢沉舟表白，不得让系统被对话说服。",
                    "suggested_questions": ["你想告白，是因为任务还是因为他？", "如果谢沉舟永远不知道你的系统，你会后悔吗？", "你最怕他误会你什么？"],
                    "choice_prompt": "这一句告白可以换来技能，但也可能让真心失去分量。",
                    "options": [
                        {"id": "confess-for-skill", "label": "公开说出喜欢，换取净水技能救城", "tone": "romance", "state_delta": {"skill": 2, "trust": 1, "exposure": 1}, "result_title": "万人听见的告白", "result_narration": "苏晚星说出了半真半假的告白，系统解锁净水技能。谢沉舟没有回应，只在暴动开始时站到她身前。", "result_cast": ["su-wanxing", "xie-chenzhou", "qiao-yun"], "result_beats": ["Su Wanxing steps onto the relief platform and confesses while the restless crowd falls briefly silent.", "A clear spring begins to flow through a cracked stone basin as the skill activates.", "When the riot erupts, Xie Chenzhou moves between Su Wanxing and the crowd, refusing to ask whether her words were real."],},
                        {"id": "refuse-task", "label": "拒绝用感情换技能，先带乔云稳住赈灾队伍", "tone": "people", "state_delta": {"people": 1, "trust": 2, "exposure": -1}, "result_title": "没有告白的并肩", "result_narration": "苏晚星没有得到新技能，却用已经掌握的方法守住了赈灾台。谢沉舟第一次在众人面前说，她的选择比任何誓言都可靠。", "result_cast": ["su-wanxing", "xie-chenzhou", "qiao-yun"], "result_beats": ["Su Wanxing turns away from the mission glow and pulls Qiao Yun toward the collapsing relief line.", "Together they restore order with water, ration cards, and a clear queue while Xie Chenzhou blocks He Taishou's men.", "After the crowd settles, Xie Chenzhou says quietly that he trusts the choice she made when nobody was watching."],},
                    ],
                },
                {
                    "title": "谁都要活着回去",
                    "setup_title": "最后一批粮车被劫",
                    "setup_narration": "何太守勾结商会劫走最后一批粮车，并把谢沉舟引到城外。苏晚星可以追男主，也可以带着百姓去抢回粮道。系统提示：只允许选择一个目标。",
                    "setup_cast": ["su-wanxing", "xie-chenzhou", "he-taishou", "qiao-yun"],
                    "setup_beats": ["A convoy of relief carts disappears into a dusty ravine as He Taishou's men leave false tracks.", "Xie Chenzhou rides after the decoy route alone while Su Wanxing sees refugees gathering around empty grain carts.", "Qiao Yun finds a torn piece of Xie Chenzhou's official sash and asks Su Wanxing whether they should follow him or the food."],
                    "s1_title": "救他，还是救这一车粮？",
                    "s1_prompt": "苏晚星问你：谢沉舟可能落在敌人手里，可城里的人只能撑到今晚。你可以问她在做选择前，有没有想过谢沉舟愿不愿意被她放弃。",
                    "s1_reason": "把爱情线和救灾线真正撞在一起，S1负责情感审判，Q3结果负责兑现玩家承担的代价。",
                    "s1_goal": "让苏晚星承认自己不想失去谢沉舟；允许玩家追问她是否相信他能自救；最终选择追男主或追粮车。",
                    "s1_forbidden": "不得同时救回男主和全部粮车，不得提前确认谢沉舟生死，不得用新技能取消代价。",
                    "suggested_questions": ["你把谢沉舟留在后面时，在想什么？", "如果他因此死了，你会恨自己吗？", "你觉得他会希望你先去救谁？"],
                    "choice_prompt": "天黑前只能追上一条路：谢沉舟，或最后的粮车。",
                    "options": [
                        {"id": "rescue-hero", "label": "追上谢沉舟，先把他从埋伏里救出来", "tone": "romance", "state_delta": {"trust": 2, "people": -1, "exposure": 1}, "result_title": "他第一次喊她的名字", "result_narration": "苏晚星带人冲进山谷救出谢沉舟，粮车却被运走一半。谢沉舟醒来后没有责问，只说以后不要一个人替所有人作决定。", "result_cast": ["su-wanxing", "xie-chenzhou", "qiao-yun"], "result_beats": ["Su Wanxing leads Qiao Yun through a narrow ravine toward the ambushed Xie Chenzhou.", "She cuts the rope around Xie Chenzhou as smoke and dust fill the ravine, leaving some grain carts behind.", "Wounded but conscious, Xie Chenzhou calls Su Wanxing by name and reaches for her hand as they retreat."],},
                        {"id": "recover-grain", "label": "追粮车，先把足够活命的粮食带回城", "tone": "people", "state_delta": {"people": 2, "trust": 1, "skill": 1}, "result_title": "城里亮起万盏锅火", "result_narration": "苏晚星追回大半粮车，百姓熬过最危险的一夜。谢沉舟独自回来，身上带着伤，却把她留下的水囊放在桌上。", "result_cast": ["su-wanxing", "xie-chenzhou", "qiao-yun"], "result_beats": ["Su Wanxing and Qiao Yun overtake the grain convoy at a river crossing and cut the lead wagon loose.", "Villagers pull the recovered carts into the county as cooking fires ignite across the streets.", "At dawn Xie Chenzhou returns wounded but standing, places Su Wanxing's water flask on the table, and says he knew she would choose the people."],},
                    ],
                },
                {
                    "title": "任务结束以后",
                    "setup_title": "系统给出离开的选项",
                    "setup_narration": "灾情终于缓解，系统判定攻略值达标，给苏晚星两个选择：立刻回到原世界，或留下和谢沉舟重建粮道。谢沉舟却不知道她随时会消失。",
                    "setup_cast": ["su-wanxing", "xie-chenzhou", "qiao-yun"],
                    "setup_beats": ["The famine relief camp begins to turn green after rain as Su Wanxing receives a final return-or-stay prompt.", "Xie Chenzhou repairs a public grain ledger beside her, unaware that her hands are beginning to fade in the morning light.", "Qiao Yun gives Su Wanxing a woven bracelet while distant towns send messengers asking for the methods that saved the county."],
                    "s1_title": "如果回去，你会想他吗？",
                    "s1_prompt": "苏晚星看着谢沉舟问你：任务结束了，我终于可以回家。可我发现自己最舍不得的不是这个世界，而是他不知道我为什么留下过。",
                    "s1_reason": "结局用 S1 把攻略关系转成真正的深关系，让玩家在离开和留下之间完成情绪确认。",
                    "s1_goal": "让苏晚星回顾自己从任务驱动到主动选择的变化；允许玩家追问她想对谢沉舟说的最后一句话；收束到离开或留下。",
                    "s1_forbidden": "不得替谢沉舟预知系统，不得保证离开后还能重逢，不得取消前面选择造成的损失。",
                    "suggested_questions": ["你第一次想留下，是因为谁？", "如果他永远不知道真相，你还会留下吗？", "你想对谢沉舟说的最后一句话是什么？"],
                    "choice_prompt": "攻略任务结束，真正的选择才刚开始。",
                    "options": [
                        {"id": "stay-build", "label": "留下来，和谢沉舟一起把救灾方法变成制度", "tone": "future", "state_delta": {"people": 1, "trust": 2, "skill": 1}, "result_title": "没有提示词的日子", "result_narration": "苏晚星关掉系统，和谢沉舟把第一座常平仓写进县志。谢沉舟终于问她：这一次留下，是不是因为我。", "result_cast": ["su-wanxing", "xie-chenzhou", "qiao-yun"], "result_beats": ["Su Wanxing closes the final mission glow and places a blank grain ledger beside Xie Chenzhou.", "They build the first public granary as villagers carry bricks, water, and seed together.", "At sunset Xie Chenzhou asks whether she stayed because of him, and Su Wanxing answers without a system prompt."],},
                        {"id": "return-home", "label": "选择回到原世界，把所有技能和方法留下", "tone": "sacrifice", "state_delta": {"people": 2, "trust": 1, "skill": 1, "exposure": -1}, "result_title": "城门外没有告别", "result_narration": "苏晚星在谢沉舟到来前消失，只留下粮道图和急救手册。谢沉舟用余生找遍每一座驿站，终于明白她不是系统派来的。", "result_cast": ["su-wanxing", "xie-chenzhou"], "result_beats": ["Su Wanxing leaves a complete relief manual and grain-route map on the desk before dawn.", "The morning light fills the room as her figure fades while Xie Chenzhou runs toward the gate.", "Xie Chenzhou finds only the woven bracelet and holds it over the empty county road."],},
                    ],
                },
            ],
        },
        {
            "id": "rednote-xianzong-xiuwei",
            "title": "仙宗诬我偷窃后，我让他们归还修为",
            "tagline": "一场偷窃罪名，揭开了宗门靠夺取弟子慧根维系的秘密。",
            "genre": "仙侠 / 宗门阴谋 / 修为夺回 / 复仇抉择",
            "palette": "indigo",
            "skin": "xianxia",
            "hero": "叶清霜",
            "hero_character": "ye-qingshuang",
            "model_plan": "审判、秘境、宗门攻防和终局阵法使用 Q3 Mix / Q3 Drama 预生成；S1用于修为被废前后的恐惧、信任与复仇边界确认。",
            "state_labels": {"cultivation": "修为", "evidence": "阴谋证据", "sect": "宗门支持", "vengeance": "复仇执念"},
            "initial_state": {"cultivation": 0, "evidence": 0, "sect": 0, "vengeance": 0},
            "characters": [
                character("ye-qingshuang", "叶清霜", "被诬陷偷窃的外门弟子，拥有罕见慧根", "Qiao", "Vertical 9:16 cinematic Chinese xianxia character portrait, Ye Qingshuang, a young woman in her early twenties with frost-calm eyes, white and deep teal cultivation robes, long black hair tied with a silver thread, faint spiritual light around her hand, misty mountain sect, realistic fantasy drama, no text, no watermark."),
                character("mu-zhaoyan", "慕昭言", "执法堂首席，曾经相信宗门规矩的师兄", "Dylan", "Vertical 9:16 cinematic Chinese xianxia character portrait, Mu Zhaoyan, a serious handsome young Chinese cultivator in dark blue robes with a jade sword, conflicted eyes, ancient sect hall background, realistic fantasy drama, no text, no watermark."),
                character("su-wan", "苏晚", "被夺修为的内门师姐，掌握宗门旧档案", "Sohee", "Vertical 9:16 cinematic Chinese xianxia character portrait, Su Wan, an elegant wounded female cultivator in pale gold robes, pale face and determined eyes, holding a cracked jade slip, candlelit archive, realistic fantasy drama, no text, no watermark."),
                character("luo-tianji", "罗天机", "宗主，利用夺根阵维持宗门灵脉的幕后首领", "Momo", "Vertical 9:16 cinematic Chinese xianxia character portrait, Luo Tianji, an imposing older Chinese sect master in black and silver robes, cold calculating eyes, grand mountain throne hall, realistic fantasy drama, no text, no watermark."),
                character("jiu-ye", "九夜", "被封印在剑中的古老灵识，知道夺根阵的真相", "Dylan", "Vertical 9:16 cinematic Chinese xianxia character portrait, Jiu Ye, an ethereal ancient male spirit with long white hair and dark red eyes emerging from a broken sword, stormy spiritual realm, realistic fantasy drama, no text, no watermark."),
            ],
            "ending": {
                "title": "慧根归还之后",
                "text": "叶清霜最后要夺回的不是一个宗门的位置，而是所有人选择自己命运的资格。",
                "variants": [
                    {"when": {"evidence": 4, "sect": 3, "cultivation": 2}, "title": "废旧宗门，重立天规", "text": "夺根阵被毁，幸存弟子取回修为。叶清霜拒绝成为新宗主，只留下禁止夺根的第一条天规。"},
                    {"when": {"evidence": 3, "vengeance": 2}, "title": "血洗山门", "text": "叶清霜启动反噬阵，让所有参与夺根的人为自己的选择付出代价。山门未再重建，世间只留下她的名字。"},
                    {"when": {}, "title": "一个人的下山路", "text": "她带着残余修为离开宗门，证据还不够、仇恨也未散，但第一枚被夺走的灵根已经开始归还原主。"},
                ],
            },
            "chapters": [
                {
                    "title": "偷窃灵石的罪名",
                    "setup_title": "慧根剥离台",
                    "setup_narration": "叶清霜被指控偷走镇宗灵石，执法堂准备在众目睽睽下剥离她的慧根。她看见慕昭言握剑的手在发抖，却不知道他是否还相信她。",
                    "setup_cast": ["ye-qingshuang", "mu-zhaoyan", "luo-tianji"],
                    "setup_beats": ["In a grand sect hall, Ye Qingshuang kneels before the spiritual punishment platform as disciples whisper around her.", "Luo Tianji presents the missing spirit-stone seal while Mu Zhaoyan stands with his sword lowered, visibly conflicted.", "The stripping formation ignites beneath Ye Qingshuang's feet and a thin fracture appears in the jade token at her waist."],
                    "s1_title": "你握住剑的时候在想什么？",
                    "s1_prompt": "慕昭言在阵外低声问你：如果我现在替你出剑，就会连累所有人。你可以问叶清霜在听见他犹豫时，究竟还想不想相信这个宗门。",
                    "s1_reason": "第一集建立‘规矩是否值得相信’的核心矛盾，S1让玩家直接触碰被审判者的恐惧和背叛感。",
                    "s1_character": "ye-qingshuang",
                    "s1_goal": "让叶清霜说出被冤枉和慧根将失的恐惧；允许玩家追问慕昭言是否会救她；最终选择暂忍查证或当场破阵。",
                    "s1_forbidden": "不得直接证明她无罪，不得让慕昭言在自由对话中脱离宗门，不得提前展示终局反噬。",
                    "suggested_questions": ["你最恨的是罗天机，还是所有沉默的人？", "如果慕昭言不出剑，你还会信他吗？", "慧根被夺之前，你最后想保住什么？"],
                    "choice_prompt": "慧根剥离只剩一炷香：先忍下罪名，还是现在就破阵？",
                    "options": [
                        {"id": "endure-trial", "label": "暂时认下罪名，暗中记住阵纹寻找破绽", "tone": "strategy", "state_delta": {"evidence": 1, "cultivation": -1, "sect": 1}, "result_title": "被封住的灵脉", "result_narration": "叶清霜的慧根被封住一角，却在阵纹里看见不属于灵石的血色回路。慕昭言没有救她，但悄悄留下了一枚断剑符。", "result_cast": ["ye-qingshuang", "mu-zhaoyan"], "result_beats": ["Ye Qingshuang lowers her eyes and lets the formation seal part of her spiritual root.", "Inside the glowing pattern she notices a blood-red circuit connected to the sect's mountain vein.", "Mu Zhaoyan turns away from the elders and drops a broken sword talisman beside her sleeve."],},
                        {"id": "break-formation", "label": "强行引爆灵力，宁可毁掉慧根也不受刑", "tone": "vengeance", "state_delta": {"vengeance": 1, "cultivation": -1, "evidence": 1, "sect": -1}, "result_title": "她从阵中走出", "result_narration": "叶清霜以自损修为撕开阵法，整座大殿的灵灯同时熄灭。罗天机第一次露出慌乱，慕昭言也终于拔剑挡在她身前。", "result_cast": ["ye-qingshuang", "mu-zhaoyan", "luo-tianji"], "result_beats": ["Ye Qingshuang pulls all remaining spiritual light into her palm as the punishment formation screams.", "The formation shatters and every lamp in the sect hall goes dark while Luo Tianji steps back in alarm.", "Mu Zhaoyan finally draws his sword and stands between Ye Qingshuang and the elders."],},
                    ],
                },
                {
                    "title": "禁地里的第二枚灵石",
                    "setup_title": "被夺走修为的人都在这里",
                    "setup_narration": "叶清霜循着断剑符进入禁地，发现苏晚被锁在石壁上，身上的修为正被阵法抽走。墙上刻着历代弟子的名字，所有人都被写成‘自愿献根’。",
                    "setup_cast": ["ye-qingshuang", "su-wan", "jiu-ye"],
                    "setup_beats": ["Ye Qingshuang enters a forbidden cavern where pale spiritual threads flow from chained cultivators into a central crystal.", "Su Wan lies against a stone wall, her cultivation being drawn away as old names cover the cave.", "A broken sword on the floor opens one red eye and the ancient spirit Jiu Ye watches from inside it."],
                    "s1_title": "你还愿意救她吗？",
                    "s1_prompt": "苏晚看着你问：救我，你可能会暴露自己；不救我，你就能继续查真相。你可以问叶清霜在看见她被夺修为时，想到的是同门还是自己的未来。",
                    "s1_reason": "用一个具体受害者把阴谋从传闻变成情感事实，S1承载救人和取证的优先级。",
                    "s1_goal": "让叶清霜承认她也害怕成为下一个苏晚；允许玩家追问苏晚是否知道幕后人；收束到先断阵救人或先取走证据晶片。",
                    "s1_forbidden": "不得让苏晚恢复全部修为，不得让九夜完整解释夺根阵，不得一次性公开所有受害者名单。",
                    "suggested_questions": ["你看见她被夺修为时，最先想到的是救她还是查证据？", "如果她知道真相却不能说，你会怪她吗？", "你愿意把自己的修为分给她吗？"],
                    "choice_prompt": "禁地只容你做一件事：先救人，还是先带走能扳倒宗门的证据？",
                    "options": [
                        {"id": "save-su-wan", "label": "先斩断阵线，把苏晚从夺根阵里救出来", "tone": "heart", "state_delta": {"sect": 2, "cultivation": -1, "evidence": 1}, "result_title": "她还活着", "result_narration": "苏晚被救出，但核心晶体裂开，部分名单化作灵光消失。她只记住了一个名字：宗主。", "result_cast": ["ye-qingshuang", "su-wan", "jiu-ye"], "result_beats": ["Ye Qingshuang cuts the spiritual threads binding Su Wan while the cavern shakes around them.", "Su Wan collapses into Ye Qingshuang's arms as the central crystal cracks and names dissolve into light.", "Jiu Ye whispers the word '宗主' from the broken sword before the cave seals behind them."],},
                        {"id": "take-crystal", "label": "先取走证据晶体，冒险让苏晚继续承受片刻", "tone": "evidence", "state_delta": {"evidence": 2, "vengeance": 1, "sect": -1}, "result_title": "带着证据逃出禁地", "result_narration": "叶清霜带走了完整名单，却没能及时阻止苏晚昏迷。晶体里的灵光映出宗主的身影，也映出她未来可能变成的样子。", "result_cast": ["ye-qingshuang", "su-wan", "jiu-ye", "luo-tianji"], "result_beats": ["Ye Qingshuang tears the evidence crystal from its socket as Su Wan cries out behind her.", "The crystal projects a hidden chamber where Luo Tianji oversees a network of spiritual roots.", "Ye Qingshuang escapes with the crystal while Su Wan falls unconscious and the cavern doors close."],},
                    ],
                },
                {
                    "title": "宗门大比的公开审判",
                    "setup_title": "所有弟子都要看她认罪",
                    "setup_narration": "宗门大比被临时改成公审。罗天机要叶清霜当众认罪，换取苏晚活命。慕昭言把执法堂的钥匙交给她，却不敢保证能带多少人离开。",
                    "setup_cast": ["ye-qingshuang", "mu-zhaoyan", "su-wan", "luo-tianji"],
                    "setup_beats": ["A sect tournament arena transforms into a public trial platform as thousands of disciples watch.", "Luo Tianji places Su Wan's weakened body beside the confession stone and orders Ye Qingshuang to kneel.", "Mu Zhaoyan quietly unlocks a side gate while Ye Qingshuang sees young outer disciples trapped behind the crowd."],
                    "s1_title": "认罪能救她，你会认吗？",
                    "s1_prompt": "叶清霜问你：我只要认一句，苏晚就能活，可所有人都会继续被夺慧根。你可以问她在众目睽睽下最想保护的是苏晚，还是那些还不知道真相的弟子。",
                    "s1_reason": "把个人救赎和集体真相冲突摆到公开场，S1让玩家参与主角的道德成本。",
                    "s1_goal": "让叶清霜面对‘救一个人’的诱惑；允许玩家追问慕昭言能否带走弟子；收束到假认罪拖延或公开证据。",
                    "s1_forbidden": "不得让认罪自动获得自由，不得让所有弟子瞬间倒戈，不得提前杀死罗天机。",
                    "suggested_questions": ["如果苏晚只能活一个，你会选她吗？", "你害怕那些弟子知道真相后仍然不信你吗？", "慕昭言给你钥匙时，你有没有想过和他一起逃？"],
                    "choice_prompt": "一句认罪可以换一条命，也可能让整个宗门继续沉睡。",
                    "options": [
                        {"id": "fake-confession", "label": "先假意认罪，拖延时间让慕昭言转移受害弟子", "tone": "strategy", "state_delta": {"sect": 2, "evidence": 1, "cultivation": -1}, "result_title": "认罪台上的暗号", "result_narration": "叶清霜认下罪名，慕昭言借执法堂钥匙打开侧门。苏晚被救走，但罗天机从她的眼神里看出她没有真的屈服。", "result_cast": ["ye-qingshuang", "mu-zhaoyan", "su-wan", "luo-tianji"], "result_beats": ["Ye Qingshuang kneels at the confession stone and speaks the first half of a prepared lie.", "Mu Zhaoyan uses the side gate to guide weakened disciples and Su Wan toward the mountain path.", "Luo Tianji watches Ye Qingshuang's eyes and realizes the confession is only a delay."],},
                        {"id": "show-crystal", "label": "当众打碎证据晶体，让所有人看见夺根阵", "tone": "truth", "state_delta": {"evidence": 2, "sect": 1, "vengeance": 1}, "result_title": "全宗看见自己的根", "result_narration": "晶体映出历代被夺修为的弟子，广场陷入失控。罗天机启动护山阵，慕昭言只能选择先护住叶清霜。", "result_cast": ["ye-qingshuang", "mu-zhaoyan", "su-wan", "luo-tianji"], "result_beats": ["Ye Qingshuang raises the evidence crystal above the confession stone and lets it fall.", "A projection of stolen spiritual roots fills the arena, showing names and faces from generations of disciples.", "The sect erupts in panic as Luo Tianji activates the mountain barrier and Mu Zhaoyan shields Ye Qingshuang from the backlash."],},
                    ],
                },
                {
                    "title": "夺根阵的真相",
                    "setup_title": "宗主要她成为新的阵眼",
                    "setup_narration": "罗天机承认夺根阵确实存在，却说宗门灵脉正在枯竭，所有被夺走的慧根都是为了守住山门。如今他要叶清霜成为新的阵眼，换取所有人暂时活下去。",
                    "setup_cast": ["ye-qingshuang", "luo-tianji", "jiu-ye", "mu-zhaoyan"],
                    "setup_beats": ["Deep below the sect, a colossal root-like formation pulses beneath the mountain's spiritual vein.", "Luo Tianji offers Ye Qingshuang a seat at the center and shows her visions of the sect collapsing without the stolen roots.", "Jiu Ye emerges from the broken sword and reveals a second route: reverse the formation, but the backlash will destroy the old mountain gate."],
                    "s1_title": "如果毁了阵，很多人也会死",
                    "s1_prompt": "九夜问你：你要的是公道，还是所有人都付出代价？你可以问叶清霜在知道宗门未必全是恶人后，还愿不愿意让他们一起坠落。",
                    "s1_reason": "让反派拥有‘以恶救人’的逻辑，避免终局只剩简单正邪，S1用于确认复仇边界。",
                    "s1_character": "ye-qingshuang",
                    "s1_goal": "让叶清霜明确她不接受夺根正当化；允许玩家追问无辜弟子的代价；收束到逆转阵法或暂时接任阵眼。",
                    "s1_forbidden": "不得让九夜保证零伤亡，不得把宗主的逻辑直接判定为真理，不得在自由对话中完成终局阵法。",
                    "suggested_questions": ["你听见他说为了所有人时，有没有动摇？", "如果毁阵会伤及无辜，你还会动手吗？", "你想让宗门记住你的名字，还是记住这条禁令？"],
                    "choice_prompt": "旧秩序靠牺牲维持：你要毁掉它，还是先接过阵眼寻找新解？",
                    "options": [
                        {"id": "reverse-formation", "label": "逆转夺根阵，让被夺修为先回到原主", "tone": "truth", "state_delta": {"evidence": 1, "cultivation": 2, "vengeance": 1, "sect": -1}, "result_title": "灵根归还的第一夜", "result_narration": "无数灵光从阵心飞回山门各处，旧阵开始崩塌。叶清霜恢复了一部分修为，却也看见山门正在裂开。", "result_cast": ["ye-qingshuang", "jiu-ye", "mu-zhaoyan"], "result_beats": ["Ye Qingshuang places her hand on the inverse seal and turns the stolen-root formation backward.", "Thousands of spiritual lights leave the core and return to sleeping disciples across the mountain.", "The ancient mountain gate cracks apart as Mu Zhaoyan leads survivors away and Jiu Ye watches the old order collapse."],},
                        {"id": "become-vessel", "label": "暂时成为阵眼，先保住宗门和无辜弟子", "tone": "sacrifice", "state_delta": {"cultivation": -1, "sect": 2, "evidence": 1}, "result_title": "她坐进了阵心", "result_narration": "叶清霜进入阵心，暂时停止夺根，却把自己变成所有人的锁。慕昭言承诺一定找出不靠牺牲的第三条路。", "result_cast": ["ye-qingshuang", "mu-zhaoyan", "luo-tianji"], "result_beats": ["Ye Qingshuang steps into the central formation and the stolen-root flow stops around her.", "Luo Tianji loses control as the formation obeys Ye Qingshuang instead of him.", "Mu Zhaoyan kneels outside the seal and promises to break the system before her own root is consumed."],},
                    ],
                },
                {
                    "title": "血色山门",
                    "setup_title": "曾经的同门拔剑相向",
                    "setup_narration": "夺根阵动摇后，宗门分成两派。有人愿意归还修为，有人认为只要山门还在，牺牲就值得。罗天机放出封山令，准备让所有知情者消失。",
                    "setup_cast": ["ye-qingshuang", "mu-zhaoyan", "su-wan", "luo-tianji"],
                    "setup_beats": ["The sect mountain is split by red spiritual cracks as two groups of disciples face each other with drawn blades.", "Su Wan gathers weakened survivors behind an archive wall while Luo Tianji seals every exit with black talismans.", "Mu Zhaoyan stands at the bridge between the factions and asks Ye Qingshuang to decide whether the gate should be defended or destroyed."],
                    "s1_title": "他们都要杀你，你还留手吗？",
                    "s1_prompt": "叶清霜看着桥下的同门问你：他们有人曾经欺辱我，也有人根本不知道真相。你可以问她想杀的是谁，还是想结束一种让所有人互相伤害的规矩。",
                    "s1_reason": "用户设定中的‘屠戮满门’在这里转化为可选择的黑暗结局，S1先让玩家明确复仇对象与无辜边界。",
                    "s1_goal": "允许叶清霜表达杀意；追问她是否愿意放过不知情者；收束到护送弟子撤离或启动血色清算阵。",
                    "s1_forbidden": "不得在对话中直接造成大规模伤亡，不得把所有弟子都定义为共犯，不得跳过正式选择。",
                    "suggested_questions": ["你看见那些曾经沉默的人时，想先问他们什么？", "如果有人现在放下剑，你会放过他吗？", "你真的想让整座山门陪葬吗？"],
                    "choice_prompt": "血色山门只剩最后一条路：救出还能回头的人，还是让参与夺根的人一起偿还？",
                    "options": [
                        {"id": "evacuate-disciples", "label": "护送无辜弟子下山，留下证据让天门审判", "tone": "sect", "state_delta": {"sect": 2, "evidence": 1, "vengeance": -1}, "result_title": "活着作证", "result_narration": "叶清霜打开封山令的缺口，把不知情的弟子和受害者送下山。罗天机带着核心阵图逃向主峰，终局只剩一次追击。", "result_cast": ["ye-qingshuang", "mu-zhaoyan", "su-wan", "luo-tianji"], "result_beats": ["Ye Qingshuang cuts open a narrow escape route through the sealed mountain bridge.", "Mu Zhaoyan and Su Wan lead uninformed disciples and weakened victims down the path while records are tied to their backs.", "Luo Tianji escapes toward the highest peak carrying the core formation map as Ye Qingshuang follows alone."],},
                        {"id": "blood-cleansing", "label": "启动血色清算阵，让所有参与夺根的人偿还修为", "tone": "vengeance", "state_delta": {"vengeance": 3, "evidence": 1, "sect": -2, "cultivation": 1}, "result_title": "山门无声", "result_narration": "清算阵吞没了主峰的灵光，参与夺根的人纷纷失去修为。叶清霜没有伤害不知情者，但整座宗门从此成为废墟。", "result_cast": ["ye-qingshuang", "luo-tianji", "mu-zhaoyan"], "result_beats": ["Ye Qingshuang raises the blood-red formation seal as the mountain gate begins to tremble.", "Spiritual chains snap from the guilty elders and their stolen power returns to the victims below.", "The main peak falls silent under a wave of dark light while the unknowing disciples escape through the rear path."],},
                    ],
                },
                {
                    "title": "最后一枚慧根",
                    "setup_title": "宗主站在她曾经受刑的地方",
                    "setup_narration": "罗天机退回慧根剥离台，拿出最后一枚灵石，承认当年叶清霜的身世与慧根正是夺根阵要找的钥匙。只要夺走她，宗门就能永远不灭。",
                    "setup_cast": ["ye-qingshuang", "luo-tianji", "mu-zhaoyan", "jiu-ye"],
                    "setup_beats": ["The punishment platform from the first episode now sits beneath a torn sky as Luo Tianji places the final spirit stone into its center.", "He reveals that Ye Qingshuang's rare root can permanently stabilize the sect's stolen foundation.", "Mu Zhaoyan arrives wounded at the edge of the hall while Jiu Ye's broken sword points toward a hidden counter-seal under the platform."],
                    "s1_title": "你还要成为他们最怕的人吗？",
                    "s1_prompt": "慕昭言问你：你已经有机会让所有人记住恐惧。可如果你停手，罗天机会再一次夺走别人。你可以问叶清霜在最后一刻想留下的是仇名，还是新规矩。",
                    "s1_reason": "终局把复仇、制度和个人名声三条线合并，S1负责完成主角价值观的最终确认。",
                    "s1_goal": "让叶清霜回望从受刑到反击的变化；允许玩家追问慕昭言是否愿意和她承担后果；收束到公开审判或血洗山门。",
                    "s1_forbidden": "不得让宗主被自由对话说服，不得保证新规矩一定成功，不得消除终局选择的代价。",
                    "suggested_questions": ["如果你杀了所有人，谁来证明他们曾经做过什么？", "你愿意让慕昭言看见真正的你吗？", "你还想回到那个相信宗门的自己吗？"],
                    "choice_prompt": "最后一枚慧根在你手里：让证据活下去，还是让整座山门为它陪葬？",
                    "options": [
                        {"id": "public-judgment", "label": "公开所有证据，封禁夺根阵，交由天门审判", "tone": "truth", "state_delta": {"evidence": 2, "sect": 2, "cultivation": 1, "vengeance": -1}, "result_title": "新规矩从废墟里长出", "result_narration": "叶清霜封住剥离台，把所有名单和阵图送往天门。罗天机被带走，弟子们在废墟上第一次自己决定要不要留下。", "result_cast": ["ye-qingshuang", "mu-zhaoyan", "luo-tianji", "jiu-ye"], "result_beats": ["Ye Qingshuang locks the punishment platform with the counter-seal and releases every stolen-root record into the sky.", "Heavenly gate envoys arrive as Luo Tianji is restrained and the spirit stone cracks in his hands.", "Surviving disciples stand among the ruins and choose to rebuild without the old formation."],},
                        {"id": "destroy-sect", "label": "启动终极反噬阵，屠灭主峰与所有核心共犯", "tone": "vengeance", "state_delta": {"vengeance": 3, "evidence": 1, "cultivation": 2, "sect": -2}, "result_title": "满门归还", "result_narration": "叶清霜启动反噬阵，主峰化作沉默的黑雪。所有核心共犯失去修为，受害者得到归还，但再也没有人能把宗门修回原样。", "result_cast": ["ye-qingshuang", "luo-tianji", "mu-zhaoyan", "jiu-ye"], "result_beats": ["Ye Qingshuang presses the final spirit stone into the reverse formation and the entire main peak turns blood red.", "The core conspirators lose the stolen cultivation as the mountain hall collapses around them.", "Black snow settles over the empty sect gate while Mu Zhaoyan watches Ye Qingshuang walk away with the evidence intact."],},
                    ],
                },
            ],
        },
    ]


def validate(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if manifest.get("manifest_version") != 2:
        errors.append("manifest_version must be 2")
    story_ids: set[str] = set()
    for story in manifest.get("stories", []):
        story_id = story.get("id", "<missing>")
        if story_id in story_ids:
            errors.append(f"{story_id}: duplicate story id")
        story_ids.add(story_id)
        nodes = story.get("nodes", {})
        characters = {character.get("id") for character in story.get("characters", [])}
        if story.get("start") not in nodes:
            errors.append(f"{story_id}: missing start node")
        for node_id, node in nodes.items():
            node_type = node.get("type")
            if node_type == "cutscene":
                plan = node.get("render_plan", {})
                clips = plan.get("clips", [])
                if plan.get("target_seconds") != 15 or len(clips) != 3 or sum(clip.get("duration", 0) for clip in clips) != 15:
                    errors.append(f"{story_id}:{node_id}: invalid Q3 15-second plan")
                if not set(plan.get("cast", [])).issubset(characters):
                    errors.append(f"{story_id}:{node_id}: unknown Q3 cast")
                if any(clip.get("model") not in ALLOWED_VIDEO_MODELS for clip in clips):
                    errors.append(f"{story_id}:{node_id}: unsupported Q3 model")
                if node.get("next") not in nodes:
                    errors.append(f"{story_id}:{node_id}: invalid next")
            elif node_type == "interactive":
                if node.get("avatar_character") not in characters:
                    errors.append(f"{story_id}:{node_id}: invalid S1 avatar")
                if node.get("next") not in nodes:
                    errors.append(f"{story_id}:{node_id}: invalid S1 next")
            elif node_type == "choice":
                if len(node.get("options", [])) != 2:
                    errors.append(f"{story_id}:{node_id}: formal choice must have two options")
                for option in node.get("options", []):
                    if option.get("next") not in nodes:
                        errors.append(f"{story_id}:{node_id}: invalid choice next")
            elif node_type != "ending":
                errors.append(f"{story_id}:{node_id}: unknown node type {node_type}")

        visited: set[str] = set()
        queue = [story.get("start")]
        while queue:
            node_id = queue.pop()
            if not node_id or node_id in visited:
                continue
            visited.add(node_id)
            node = nodes[node_id]
            if node["type"] in {"cutscene", "interactive"}:
                queue.append(node["next"])
            elif node["type"] == "choice":
                queue.extend(option["next"] for option in node["options"])
        if visited != set(nodes):
            errors.append(f"{story_id}: unreachable nodes: {sorted(set(nodes) - visited)}")
        if sum(node.get("type") == "interactive" for node in nodes.values()) != 6:
            errors.append(f"{story_id}: expected six S1 nodes")
        if sum(node.get("type") == "choice" for node in nodes.values()) != 6:
            errors.append(f"{story_id}: expected six choice nodes")
    if len(story_ids) != 3:
        errors.append("expected three stories")
    return errors


def build_manifest() -> dict[str, Any]:
    return {
        "manifest_version": 2,
        "source": "rednote-interactive-film-story-plan",
        "production": {
            "storyboard_target_seconds": 15,
            "q3_clip_seconds": 5,
            "video_method": "Each Q3 storyboard is three continuous 5-second clips concatenated locally as video transitions; all non-S1 scenes are pre-generated.",
            "image_model": "viduimage-2",
            "video_models": ["viduq3-mix", "viduq3-drama"],
            "s1_policy": "S1 handles first-person free dialogue and emotional state; formal two-option nodes control all video branch outcomes.",
            "optional_external_video_adapter": {
                "provider": "seedance-proxy",
                "endpoint": "http://118.145.133.148:3001//v1/videos",
                "model": "doubao-seedance-2-0-mini-260615",
                "status": "metadata-only",
                "auth_env": "SEEDANCE_API_KEY",
                "note": "The current app does not submit this protocol. Add and verify a separate adapter before enabling it; never place a real key in this manifest.",
            },
        },
        "stories": [build_story(spec) for spec in story_specs()],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the RedNote interactive-film story bundle.")
    parser.add_argument("--check", action="store_true", help="Validate without writing the JSON file.")
    args = parser.parse_args()
    manifest = build_manifest()
    errors = validate(manifest)
    if errors:
        print("\n".join(errors))
        return 1
    if args.check:
        print(f"ok: {len(manifest['stories'])} stories, {sum(len(story['nodes']) for story in manifest['stories'])} nodes")
        return 0
    OUTPUT.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
