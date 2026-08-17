# -*- coding: utf-8 -*-
"""Standalone fake RAG upstream for the Vidu S1 knowledge_retrieval demo.

Architecture: Vidu cloud -> (tunnel) -> app.py /knowledge/search -> (localhost) -> THIS.
This service only needs to be reachable by app.py, so localhost is fine.

It answers the upstream contract that /knowledge/search expects:
  request : {query, max_results, knowledge_types[], live_id, reason}
  response: {"knowledge": [{id, title, content, type, source, updated_at, confidence, url}]}

Knowledge domain is tuned to 莱奥伦(Leaoluon)'s world so the avatar can *explain*
expert forest/herbal/nature-healing lore grounded in real entries, not hallucinate.

Run:  py -3.14 fake_knowledge_source.py    (default port 5300)
Then in .env:  KNOWLEDGE_UPSTREAM_URL=http://127.0.0.1:5300/search
"""
from __future__ import annotations

import os
import time
from flask import Flask, jsonify, request

app = Flask(__name__)

# Each entry: keywords drive naive semantic match; content is what the avatar explains.
KNOWLEDGE_BASE = [
    {
        "id": "kb_moss_navigation",
        "title": "苔藓辨向",
        "type": "forest_survival",
        "keywords": ["方向", "迷路", "辨向", "苔藓", "指南", "找路", "东南西北"],
        "content": "在密林里迷失方向时，可观察树干与岩石上的苔藓：苔藓喜阴湿，通常在背阳、朝北的一面生长得更厚更密。结合正午阳光的方位，就能大致判断南北。但不可全然依赖——地形与水汽会改变分布，最好多看几棵树取共识。",
    },
    {
        "id": "kb_edible_berries",
        "title": "野莓可食性判别",
        "type": "forest_survival",
        "keywords": ["野莓", "浆果", "能吃", "可食", "有毒", "采摘", "食物"],
        "content": "林间野莓并非都可入口。聚合状、颜色柔和的深蓝与红褐色浆果多数温和，而色泽过分艳丽（尤其纯白与蜡质光亮）的果实需警惕。稳妥之道是只采认得的种类；不确定时先小量触唇静待，绝不贪多。晨露浸润过的成熟野莓最清甜。",
    },
    {
        "id": "kb_water_purify",
        "title": "山泉与净水",
        "type": "forest_survival",
        "keywords": ["水", "山泉", "喝水", "净水", "过滤", "煮沸", "溪流"],
        "content": "流动的山泉与溪流上游通常比静水洁净。取水后仍建议煮沸后再饮，可去除多数微生物。若无火，可用细砂、木炭与碎石层层铺叠做简易过滤，但这只能滤去杂质，不能替代煮沸。清晨的溪水最为清冽。",
    },
    {
        "id": "kb_herbal_wound",
        "title": "草木止血与外伤",
        "type": "herbal_medicine",
        "keywords": ["止血", "受伤", "外伤", "草药", "伤口", "疗愈", "包扎"],
        "content": "轻微外伤时，洁净的蓍草、车前草叶片揉出汁液敷于伤口，有助收敛止血；苔藓柔软洁净者可作临时敷垫。但深创、动脉出血须优先按压加压止血，草木仅为辅助。处理前务必先净手净创，避免污染。",
    },
    {
        "id": "kb_calming_herbs",
        "title": "安神与自然疗愈",
        "type": "nature_healing",
        "keywords": ["安神", "焦虑", "睡不着", "放松", "疗愈", "情绪", "平静", "薰衣草"],
        "content": "自然界有许多抚平心绪之物：薰衣草与洋甘菊的气息能舒缓紧张，温热的花草茶助眠；更根本的是聆听自然白噪音——风穿林叶、溪流与鸟鸣，能让呼吸慢下来。焦虑时试着深长呼吸、把注意力放在一片叶子的纹理上，心便会渐渐静。",
    },
    {
        "id": "kb_forest_night",
        "title": "林间夜宿与保暖",
        "type": "forest_survival",
        "keywords": ["过夜", "夜宿", "保暖", "取暖", "露营", "睡觉", "寒冷"],
        "content": "林间过夜，选背风、地势略高、远离枯枝的干燥处。以落叶与干草铺厚成隔潮层，能显著减少地面失温——离地保暖比盖得厚更关键。若能生火，火堆置于身侧与背风岩石之间可反射热量。切记留意火星，勿伤草木。",
    },
    {
        "id": "kb_animal_tracks",
        "title": "林间生灵的踪迹",
        "type": "nature_lore",
        "keywords": ["动物", "小鹿", "踪迹", "脚印", "生灵", "鸟", "松鼠", "辨认"],
        "content": "读懂林间踪迹能与生灵和平共处：偶蹄的心形足印多是小鹿，成串小巧的爪痕常属松鼠，晨昏是它们活动的时辰。观察而不惊扰，保持距离与安静，它们便会渐渐接纳你的存在。喂食需克制，人类食物未必适合它们。",
    },
]


def score(entry: dict, query: str, requested_types: list[str]) -> int:
    q = query.lower()
    hits = sum(1 for kw in entry["keywords"] if kw.lower() in q)
    if requested_types and entry["type"] in requested_types:
        hits += 1  # gentle boost when the caller asked for this type
    return hits


@app.route("/search", methods=["POST"])
def search():
    body = request.get_json(silent=True) or {}
    query = str(body.get("query") or "").strip()
    max_results = int(body.get("max_results") or 3)
    requested_types = body.get("knowledge_types") if isinstance(body.get("knowledge_types"), list) else []
    if not query:
        return jsonify({"knowledge": []})

    ranked = sorted(KNOWLEDGE_BASE, key=lambda e: score(e, query, requested_types), reverse=True)
    ranked = [e for e in ranked if score(e, query, requested_types) > 0][: max(1, min(max_results, 10))]
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    knowledge = [{
        "id": e["id"],
        "title": e["title"],
        "content": e["content"],
        "type": e["type"],
        "source": "leaoluon_forest_lore",
        "updated_at": now,
        "confidence": 0.9,
        "url": "",
    } for e in ranked]
    print("[fake-knowledge] query=%r types=%s -> %d hits" % (query, requested_types, len(knowledge)))
    return jsonify({"knowledge": knowledge})


@app.route("/health")
def health():
    return jsonify({"ok": True, "entries": len(KNOWLEDGE_BASE)})


if __name__ == "__main__":
    port = int(os.getenv("FAKE_KNOWLEDGE_PORT", "5300"))
    print("fake knowledge RAG on http://127.0.0.1:%d/search  (%d entries)" % (port, len(KNOWLEDGE_BASE)))
    app.run(host="127.0.0.1", port=port, debug=False)
