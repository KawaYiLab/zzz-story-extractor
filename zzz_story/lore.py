"""Worldbuilding and lore extraction: agents, equipment, inter-knot, cinema, glossary, street."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .clean import clean_text
from .textmap import TextMap

# Map internal char tags in GalGame/Date events to avatar codes / names
CHAR_TAG_ALIASES: dict[str, str] = {
    "partnerno11": "1041",
    "partnernroma": "1571",
    "partnerorpheus": "1301",
    "partnerroxy": "1621",
    "partnersoukaku": "1131",
    "partnersunna": "1171",
    "partneryeshunguang": "1431",
    "partnerunagi": "1091",
    "partnerastra": "1311",
    "partnerhugo": "1291",
    "partnerclaret": "1611",
    "partnersigrid": "1591",
    "partnerremielle": "1581",
    "partnervelina": "1561",
    "partnerpromeia": "1541",
    "partnercissia": "1521",
    "partnerjufufu": "1391",
    "partneryanagi": "1221",
    "partnerharumasa": "1201",
    "partnerevelyn": "1321",
    "partnervivian": "1331",
    "partnernangongyu": "1511",
    "partneraria": "1501",
    "partnersummer": "1491",
    "partneryidhari": "1051",
    "partneryuzuha": "1411",
    "partnerbanyue": "1471",
    "partnerazural": "1481",
    "partnernorano": "1441",
    "partnerlucia": "1451",
    "partnerseed": "1461",
    "partnertrigger": "1361",
    "partnerpulchra": "1351",
    "partnerzhao": "1341",
    "partneralice": "1401",
    "partnerpanyinhu": "1421",
    "partneryixuan": "1371",
}


def _clean(raw: str, default: str = "") -> str:
    if not raw:
        return default
    cleaned = clean_text(raw).text.strip()
    return cleaned if cleaned else default


def extract_lore(
    text_map: TextMap,
    avatar_base_data: dict[str, Any] | list[Any] | None,
    out_dir: Path,
) -> dict[str, int]:
    """Extract all worldview / lore categories and output structured Markdown files."""
    lore_dir = out_dir / "lore"
    lore_dir.mkdir(parents=True, exist_ok=True)

    stats: dict[str, int] = {}

    stats.update(_extract_agents(text_map, avatar_base_data, lore_dir / "agents"))
    stats.update(_extract_equipment(text_map, lore_dir / "equipment"))
    stats.update(_extract_interknot(text_map, lore_dir / "interknot"))
    stats.update(_extract_cinema(text_map, lore_dir / "cinema"))
    stats.update(_extract_glossary(text_map, lore_dir / "glossary"))
    stats.update(_extract_street(text_map, lore_dir / "street"))

    _generate_lore_index(lore_dir, stats)
    return stats


def _extract_agents(
    tm: TextMap,
    avatar_base_data: dict[str, Any] | list[Any] | None,
    agents_dir: Path,
) -> dict[str, int]:
    agents_dir.mkdir(parents=True, exist_ok=True)

    # 1. Parse playable avatars from AvatarBaseTemplateTb
    raw_entries: list[dict[str, Any]] = []
    if isinstance(avatar_base_data, dict):
        if "IAEFFFFLKNB" in avatar_base_data:
            raw_entries = avatar_base_data["IAEFFFFLKNB"]
        else:
            for v in avatar_base_data.values():
                if isinstance(v, list):
                    raw_entries = v
                    break
    elif isinstance(avatar_base_data, list):
        raw_entries = avatar_base_data

    playable: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for e in raw_entries:
        name_key = e.get("HAKHHHCAENA") or ""
        name = tm.get(name_key)
        if name and name not in seen_names:
            seen_names.add(name)
            playable.append(e)

    # Collect GalGame hangout stories by char tag
    gal_events: dict[str, dict[str, list[tuple[str, str]]]] = defaultdict(lambda: defaultdict(list))
    for k, v in tm.items():
        if k.startswith("PartnerTalk_GalGame_"):
            parts = k.split("_")
            if len(parts) >= 5:
                tag = parts[2].lower()
                eid = parts[3]
                lid = parts[4]
                gal_events[tag][eid].append((lid, _clean(v)))

    # Collect Mindscape Cinema stories (Talent_..._Desc_02)
    talent_stories: dict[str, list[str]] = defaultdict(list)
    for k, v in tm.items():
        if "Talent_" in k and k.endswith("_Desc_02"):
            # e.g. Alice_Talent_01_Desc_02
            char_prefix = k.split("_")[0].lower()
            text = _clean(v)
            if text and len(text) > 10:
                talent_stories[char_prefix].append(text)

    # Group avatars by Camp
    camp_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    agent_count = 0

    avatar_info_list: list[dict[str, Any]] = []

    for a in playable:
        aid = str(a.get("PFOAJKNPCHL", 0))
        name = _clean(tm.get(a.get("HAKHHHCAENA", ""), ""))
        full_name = _clean(tm.get(a.get("JGHFBBCBBBA", ""), name))
        camp_id = a.get("OOOHMBMDLBI", 0)
        camp_name = _clean(
            tm.get(f"PartnerCamp_Name_{camp_id:02d}", tm.get(f"PartnerCamp_Name_{camp_id}", "未知阵营"))
        )
        code = str(a.get("FEKFJBFGANO") or "")

        birthday = _clean(tm.get(f"Partner_Birthday_{aid}", ""))
        stature = _clean(tm.get(f"Partner_Stature_{aid}", ""))
        race = _clean(tm.get(f"Partner_Race_{aid}", ""))
        feature_desc = _clean(tm.get(f"Item_Avatar_{aid}_Des", ""))

        # Profile entries (Partner_ProfileDesc_{aid}, _1, _2...)
        profiles: list[str] = []
        p_main = _clean(tm.get(f"Partner_ProfileDesc_{aid}", ""))
        if p_main:
            profiles.append(p_main)
        for i in range(1, 10):
            p_sub = _clean(tm.get(f"Partner_ProfileDesc_{aid}_{i}", ""))
            if p_sub:
                profiles.append(p_sub)

        # Impressions
        impression = _clean(tm.get(f"Partner_Impression_{aid}", ""))

        # W-Engine
        w_engine_names: list[str] = []
        for rank in ("S", "A", "B"):
            w_name = _clean(tm.get(f"Item_Weapon_{rank}_{aid}_Name", ""))
            if w_name:
                w_engine_names.append(f"{w_name} ({rank}级)")

        # Hangout stories
        hangouts: list[dict[str, Any]] = []
        char_tags = [code.lower(), f"partner{code.lower()}"]
        for tag, mapped_aid in CHAR_TAG_ALIASES.items():
            if mapped_aid == aid:
                char_tags.append(tag)

        matched_eids: set[str] = set()
        for tag in char_tags:
            if tag in gal_events:
                for eid, lines in gal_events[tag].items():
                    if eid in matched_eids:
                        continue
                    matched_eids.add(eid)
                    title = _clean(tm.get(f"Title_{eid}", f"专属邀约 {eid}"))
                    sorted_lines = [text for _, text in sorted(lines, key=lambda x: x[0])]
                    hangouts.append({"title": title, "lines": sorted_lines})

        # Mindscape stories
        cinema_poems = talent_stories.get(code.lower(), [])

        info = {
            "id": aid,
            "name": name,
            "full_name": full_name,
            "camp": camp_name,
            "code": code,
            "birthday": birthday,
            "stature": stature,
            "race": race,
            "feature_desc": feature_desc,
            "profiles": profiles,
            "impression": impression,
            "w_engines": w_engine_names,
            "hangouts": hangouts,
            "cinema_poems": cinema_poems,
        }
        avatar_info_list.append(info)
        camp_groups[camp_name].append(info)
        agent_count += 1

    # Write Camp Files
    camp_file_map = {
        "狡兔屋": "01_狡兔屋.md",
        "白祇重工": "02_白祇重工.md",
        "维多利亚家政": "03_维多利亚家政.md",
        "刑侦特勤组": "04_刑侦特勤组.md",
        "奥波勒斯小队": "05_奥波勒斯小队.md",
        "对空六课": "06_对空六课.md",
        "卡吕冬之子": "07_卡吕冬之子.md",
        "天琴座": "08_天琴座与反舌鸟.md",
        "反舌鸟": "08_天琴座与反舌鸟.md",
        "云岿山": "09_云岿山与怪啖屋.md",
        "怪啖屋": "09_云岿山与怪啖屋.md",
        "坎卜斯黑枝": "10_坎卜斯黑枝与妄想天使.md",
        "妄想天使": "10_坎卜斯黑枝与妄想天使.md",
        "达识结社": "11_达识结社与空巡局.md",
        "空巡局": "11_达识结社与空巡局.md",
        "外务筹策局": "11_达识结社与空巡局.md",
    }

    # Group by target filename
    files_to_camps: dict[str, list[str]] = defaultdict(list)
    for camp_name in camp_groups:
        fname = camp_file_map.get(camp_name, "12_漫游者与特别存在.md")
        files_to_camps[fname].append(camp_name)

    for fname, camps in sorted(files_to_camps.items()):
        md_lines = [f"# 新艾利都阵营档案：{' / '.join(camps)}\n"]
        for camp in camps:
            md_lines.append(f"## 阵营：{camp}\n")
            agents = camp_groups[camp]
            for ag in sorted(agents, key=lambda x: int(x["id"]) if x["id"].isdigit() else 9999):
                md_lines.append(f"### {ag['name']}（{ag['full_name']}）\n")
                md_lines.append("| 属性 | 档案记录 |")
                md_lines.append("| :--- | :--- |")
                md_lines.append(f"| **代理人ID** | `{ag['id']}` (`{ag['code']}`) |")
                md_lines.append(f"| **所属阵营** | {ag['camp']} |")
                if ag["birthday"]:
                    md_lines.append(f"| **生日** | {ag['birthday']} |")
                if ag["race"]:
                    md_lines.append(f"| **种族** | {ag['race']} |")
                if ag["stature"]:
                    md_lines.append(f"| **身高/体型** | {ag['stature']} |")
                if ag["w_engines"]:
                    md_lines.append(f"| **专属/推荐音擎** | {', '.join(ag['w_engines'])} |")
                md_lines.append("")

                if ag["feature_desc"]:
                    md_lines.append(f"> **特写记录**：\n> {ag['feature_desc'].replace(chr(10), chr(10) + '> ')}\n")

                if ag["profiles"]:
                    md_lines.append("#### 深度身世与机密档案\n")
                    for i, prof in enumerate(ag["profiles"], 1):
                        md_lines.append(f"**档案记录 0{i}**：\n\n{prof}\n")

                if ag["impression"]:
                    md_lines.append("#### 同伴评语与印象\n")
                    md_lines.append(f"> {ag['impression'].replace(chr(10), chr(10) + '> ')}\n")

                if ag["cinema_poems"]:
                    md_lines.append("#### 意象影画风味篇章\n")
                    for i, poem in enumerate(ag["cinema_poems"], 1):
                        md_lines.append(f"**影画第 {i} 幕**：\n```text\n{poem}\n```\n")

                if ag["hangouts"]:
                    md_lines.append(f"#### 专属信赖邀约与日常剧情（共 {len(ag['hangouts'])} 幕）\n")
                    for h in ag["hangouts"]:
                        md_lines.append(f"##### {h['title']}\n")
                        for line in h["lines"]:
                            md_lines.append(f"- {line}")
                        md_lines.append("")
                md_lines.append("---\n")

        (agents_dir / fname).write_text("\n".join(md_lines), encoding="utf-8")

    # Write Overview Table
    ov_lines = ["# 新艾利都代理人全景总览\n"]
    ov_lines.append("| ID | 姓名 | 全名 | 阵营 | 生日 | 种族 | 体型 | 专属音擎 | 档案/邀约 |")
    ov_lines.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
    for ag in sorted(avatar_info_list, key=lambda x: int(x["id"]) if x["id"].isdigit() else 9999):
        w_str = ag["w_engines"][0] if ag["w_engines"] else "-"
        hang_count = f"{len(ag['hangouts'])} 幕" if ag["hangouts"] else "-"
        ov_lines.append(
            f"| `{ag['id']}` | **{ag['name']}** | {ag['full_name']} | {ag['camp']} | "
            f"{ag['birthday'] or '-'} | {ag['race'] or '-'} | {ag['stature'] or '-'} | {w_str} | {hang_count} |"
        )
    (agents_dir / "00_代理人全景总览.md").write_text("\n".join(ov_lines), encoding="utf-8")

    return {"lore_agents": agent_count}


def _extract_equipment(tm: TextMap, equip_dir: Path) -> dict[str, int]:
    equip_dir.mkdir(parents=True, exist_ok=True)

    # 1. Drive Discs (EquipmentSuit_*_story)
    discs: list[dict[str, str]] = []
    for k, v in tm.items():
        if k.startswith("EquipmentSuit_") and k.endswith("_name"):
            suit_id = k.split("_")[1]
            story = _clean(tm.get(f"EquipmentSuit_{suit_id}_story", ""))
            two_pc = _clean(tm.get(f"EquipmentSuit_{suit_id}_2_des", ""))
            four_pc = _clean(tm.get(f"EquipmentSuit_{suit_id}_4_des", ""))
            tag = _clean(tm.get(f"EquipmentSuit_{suit_id}_Tag", ""))
            if story:
                discs.append({
                    "id": suit_id,
                    "name": _clean(v),
                    "story": story,
                    "two_pc": two_pc,
                    "four_pc": four_pc,
                    "tag": tag,
                })

    disc_md = ["# 新艾利都驱动盘唱片物语\n"]
    disc_md.append("> 驱动盘不仅是调节以太适配率的作战插件，更铭刻着旧文明与新艾利都流传的旋律与历史纪实。\n")
    for d in sorted(discs, key=lambda x: int(x["id"]) if x["id"].isdigit() else 9999):
        disc_md.append(f"## 《{d['name']}》（编号：{d['id']}）\n")
        if d["tag"]:
            disc_md.append(f"**定位特征**：`{d['tag']}`\n")
        disc_md.append("### 唱片文献与背景纪事\n")
        disc_md.append(f"> {d['story'].replace(chr(10), chr(10) + '> ')}\n")
        disc_md.append("### 调律共鸣效果\n")
        disc_md.append(f"- **2件套**：{d['two_pc']}")
        disc_md.append(f"- **4件套**：{d['four_pc']}\n")
        disc_md.append("---\n")
    (equip_dir / "01_驱动盘唱片物语.md").write_text("\n".join(disc_md), encoding="utf-8")

    # 2. W-Engines (Item_Weapon_*)
    engines: list[dict[str, str]] = []
    for k, v in tm.items():
        if k.startswith("Item_Weapon_") and k.endswith("_Name"):
            base = k[:-5]
            desc = _clean(tm.get(f"{base}_Desc", ""))
            special = _clean(tm.get(f"{base}_SpecialDesc", ""))
            buff_name = _clean(tm.get(f"{base}_Buff_Name", ""))
            buff_des = _clean(tm.get(f"{base}_Buff_Des", ""))
            parts = base.split("_")
            rank = parts[2] if len(parts) > 2 else "A"
            wid = parts[3] if len(parts) > 3 else ""
            if desc and not desc.startswith("Test"):
                engines.append({
                    "id": wid,
                    "rank": rank,
                    "name": _clean(v),
                    "desc": desc,
                    "special": special,
                    "buff_name": buff_name,
                    "buff_des": buff_des,
                })

    engine_md = ["# 新艾利都音擎档案与题记\n"]
    engine_md.append("> 音擎是空洞作战的核心动力装置。每一款特制音擎的外壳与调谐回路，都封存着设计者的执念与战士的烈火足迹。\n")
    for eng in sorted(engines, key=lambda x: (x["rank"] != "S", x["rank"] != "A", x["name"])):
        engine_md.append(f"## 【{eng['name']}】（{eng['rank']}级音擎）\n")
        if eng["special"]:
            engine_md.append(f"> **专属题记**：*{eng['special']}*\n")
        engine_md.append("### 音擎构造与由来\n")
        engine_md.append(f"{eng['desc']}\n")
        if eng["buff_name"] or eng["buff_des"]:
            engine_md.append(f"### 核心改装回路：{eng['buff_name']}\n")
            engine_md.append(f"{eng['buff_des']}\n")
        engine_md.append("---\n")
    (equip_dir / "02_音擎档案与题记.md").write_text("\n".join(engine_md), encoding="utf-8")

    # 3. Bangboos (Bangboo_Name_* & Bangboo_Desc_*)
    bangboos: list[dict[str, Any]] = []
    for k, v in tm.items():
        if k.startswith("Bangboo_Name_") and not any(sub in k for sub in ["_en_", "Skill"]):
            bid = k.replace("Bangboo_Name_", "")
            desc = _clean(tm.get(f"Bangboo_Desc_{bid}", ""))
            en_name = _clean(tm.get(f"Bangboo_Name_en_{bid}", ""))
            act_title = _clean(tm.get(f"Bangboo_ActiveSkill_Title_{bid}", ""))
            act_des = _clean(tm.get(f"Bangboo_ActiveSkill_Des_{bid}", ""))
            qte_title = _clean(tm.get(f"Bangboo_QTE_Title_{bid}", ""))
            qte_des = _clean(tm.get(f"Bangboo_QTE_Des_{bid}", ""))
            talent_title = _clean(tm.get(f"Bangboo_TalentSkill_Title_{bid}", ""))
            talent_des = _clean(tm.get(f"Bangboo_TalentSkill_Des_{bid}_01", ""))

            # Voice tips
            voice_lines = []
            for i in range(1, 10):
                line = _clean(tm.get(f"Tips_{bid}0{i}", tm.get(f"Tips_{bid}{i:02d}", "")))
                if line and "嗯" in line:
                    voice_lines.append(line)

            if desc:
                bangboos.append({
                    "id": bid,
                    "name": _clean(v),
                    "en_name": en_name,
                    "desc": desc,
                    "active_title": act_title,
                    "active_des": act_des,
                    "qte_title": qte_title,
                    "qte_des": qte_des,
                    "talent_title": talent_title,
                    "talent_des": talent_des,
                    "voices": voice_lines,
                })

    bangboo_md = ["# 新艾利都邦布机体图鉴\n"]
    bangboo_md.append("> 邦布（Bangboo）是新艾利都社会不可或缺的人工智能伙伴，也是空洞探索中唯一具备高以太适性的机械向导。\n")
    for b in sorted(bangboos, key=lambda x: int(x["id"]) if x["id"].isdigit() else 9999):
        bangboo_md.append(f"## {b['name']}（{b['en_name']}）\n")
        bangboo_md.append(f"> **机体格言**：*{b['desc']}*\n")
        if b["active_title"] or b["active_des"]:
            bangboo_md.append(f"### 主动技：{b['active_title']}\n{b['active_des']}\n")
        if b["qte_title"] or b["qte_des"]:
            bangboo_md.append(f"### 邦布连携技：{b['qte_title']}\n{b['qte_des']}\n")
        if b["talent_title"] or b["talent_des"]:
            bangboo_md.append(f"### 专属额外能力：{b['talent_title']}\n{b['talent_des']}\n")
        if b["voices"]:
            bangboo_md.append("### 邦布语音台词\n")
            for vl in b["voices"]:
                bangboo_md.append(f"- {vl}")
            bangboo_md.append("")
        bangboo_md.append("---\n")
    (equip_dir / "03_邦布机体图鉴.md").write_text("\n".join(bangboo_md), encoding="utf-8")

    # 4. Collectibles (CollectionDesc_*)
    collections: list[dict[str, str]] = []
    for k, v in tm.items():
        if k.startswith("CollectionDesc_"):
            cid = k.replace("CollectionDesc_", "")
            name = _clean(tm.get(f"CollectionName_{cid}", f"藏品 {cid}"))
            text = _clean(v)
            if text and len(text) > 10:
                collections.append({"name": name, "desc": text})

    col_md = ["# 录像店展示架与收藏品风味物语\n"]
    col_md.append("> Random Play 货架上陈列的纪念品与市井手办，记录着六分街街坊与委托人的生活趣事。\n")
    for c in collections:
        col_md.append(f"## 【{c['name']}】\n\n{c['desc']}\n\n---\n")
    (equip_dir / "04_收藏展架与风味展品.md").write_text("\n".join(col_md), encoding="utf-8")

    return {
        "lore_discs": len(discs),
        "lore_w_engines": len(engines),
        "lore_bangboos": len(bangboos),
        "lore_collectibles": len(collections),
    }


def _extract_interknot(tm: TextMap, knot_dir: Path) -> dict[str, int]:
    knot_dir.mkdir(parents=True, exist_ok=True)

    # 1. Commissions (QuestDesc_*)
    quests: list[dict[str, str]] = []
    for k, v in tm.items():
        if k.startswith("QuestDesc_") and len(v.strip()) >= 15:
            qid = k.replace("QuestDesc_", "")
            name = _clean(tm.get(f"QuestName_{qid}", "未命名委托"))
            target = _clean(tm.get(f"QuestTarget_{qid}", ""))
            desc = _clean(v)
            quests.append({"id": qid, "name": name, "target": target, "desc": desc})

    q_md = ["# 绳网（Inter-Knot）委托档案与都市怪谈\n"]
    q_md.append("> 传奇绳匠「法厄同」从绳网终端承接的各类委托信。包含了新艾利都市民的真实求助、空洞灾害调查与民间奇闻。\n")
    for q in sorted(quests, key=lambda x: int(x["id"]) if x["id"].isdigit() else 9999):
        q_md.append(f"## 【{q['name']}】（委托编号：{q['id']}）\n")
        q_md.append("### 委托背景详情\n")
        q_md.append(f"{q['desc']}\n")
        if q["target"]:
            q_md.append(f"**任务指引**：{q['target']}\n")
        q_md.append("---\n")
    (knot_dir / "01_委托人任务档案.md").write_text("\n".join(q_md), encoding="utf-8")

    # 2. Private Messages (Message_*)
    threads: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for k, v in tm.items():
        if k.startswith("Message_"):
            mid = k.replace("Message_", "")
            text = _clean(v)
            if not text or "占位" in text:
                continue
            # Thread ID is first 7 digits if len >= 7, else prefix
            thread_id = mid[:7] if len(mid) >= 7 else mid[:4]
            threads[thread_id].append((mid, text))

    msg_md = ["# 绳网私信与手机即时通讯记录\n"]
    msg_md.append("> 法厄同个人手持终端中的短信与私信聊天记录，收录代理人、委托人与治安官的日常通讯与八卦吐槽。\n")
    msg_count = 0
    for tid in sorted(threads.keys()):
        lines = threads[tid]
        if len(lines) < 2:
            continue
        msg_md.append(f"## 对话频段 #{tid}\n")
        for mid, text in sorted(lines, key=lambda x: x[0]):
            msg_md.append(f"> 💬 **[{mid}]** {text}\n")
            msg_count += 1
        msg_md.append("---\n")
    (knot_dir / "02_绳网私信与手机短信.md").write_text("\n".join(msg_md), encoding="utf-8")

    return {"lore_quests": len(quests), "lore_messages": msg_count}


def _extract_cinema(tm: TextMap, cinema_dir: Path) -> dict[str, int]:
    cinema_dir.mkdir(parents=True, exist_ok=True)

    # 1. Movies & Reviews
    movies: list[dict[str, Any]] = []
    # Movies config
    for i in range(1, 100):
        desc_k = f"Cinema_CinemaConfig_{i:02d}_Description"
        name_k = f"Cinema_CinemaConfig_{i:02d}_Name"
        title_k = f"Cinema_CinemaConfig_{i:02d}_Tittle"
        if desc_k in tm or name_k in tm or title_k in tm:
            desc = _clean(tm.get(desc_k, ""))
            name = _clean(tm.get(title_k, tm.get(name_k, f"经典影片 #{i:02d}")))
            # Collect comments
            comments: list[str] = []
            prefix = f"Cinema_Comment_{i}"
            for k, v in tm.items():
                if k.startswith(prefix) and "Content" in k:
                    c_text = _clean(v)
                    if c_text and c_text not in comments:
                        comments.append(c_text)

            if desc:
                movies.append({"id": f"{i:02d}", "name": name, "desc": desc, "comments": comments})

    c_md = ["# Random Play 录像店旧文明电影与大众影评\n"]
    c_md.append("> 录像店藏品中收录的旧文明黄金时代经典电影、特摄剧、纪录片与顾客大众影评。\n")
    total_comments = 0
    for m in movies:
        c_md.append(f"## 《{m['name']}》（录像带编号：{m['id']}）\n")
        c_md.append("### 剧情梗概与题材背景\n")
        c_md.append(f"{m['desc']}\n")
        if m["comments"]:
            c_md.append("### 顾客观影札记与热门影评\n")
            for c in m["comments"]:
                c_md.append(f"- 💬 *“{c}”*")
                total_comments += 1
            c_md.append("")
        c_md.append("---\n")
    (cinema_dir / "01_旧文明电影与影评.md").write_text("\n".join(c_md), encoding="utf-8")

    return {"lore_movies": len(movies), "lore_movie_comments": total_comments}


def _extract_glossary(tm: TextMap, gloss_dir: Path) -> dict[str, int]:
    gloss_dir.mkdir(parents=True, exist_ok=True)

    # 1. World Tips & Hollow Rules
    tips: list[str] = []
    lore_keywords = ["以太", "空洞", "侵蚀", "治安", "绳匠", "盗洞客", "防卫军", "赫利俄斯", "新艾利都", "旧都", "邦布", "音擎"]
    for k, v in tm.items():
        if k.startswith("Tips_") and len(v) > 20:
            if not any(token in v for token in ["LAYOUT_", "Action:UI", "IconMap:", "点击[", "按键"]):
                if any(w in v for w in lore_keywords):
                    cleaned = _clean(v)
                    if cleaned and cleaned not in tips:
                        tips.append(cleaned)

    # Main chapter titles & tips
    ch_tips: list[tuple[str, str]] = []
    for k, v in tm.items():
        if k.startswith("ChapterTipsMain_"):
            cid = k.replace("ChapterTipsMain_", "")
            ch_tips.append((cid, _clean(v)))

    t_md = ["# 新艾利都世界观百科与空洞规则\n"]
    t_md.append("> 涵盖新艾利都官方条例、以太物理规则、空洞灾害评级与历史纪事。\n")
    t_md.append("## 核心章节历程纪事\n")
    for cid, title in sorted(ch_tips, key=lambda x: int(x[0]) if x[0].isdigit() else 9999):
        t_md.append(f"- **幕次 {cid}**：{title}")
    t_md.append("\n## 空洞调查与以太生存法则（Tips 典藏）\n")
    for tip in sorted(tips):
        t_md.append(f"- {tip}")
    (gloss_dir / "01_空洞与以太规则.md").write_text("\n".join(t_md), encoding="utf-8")

    # 2. Tarot Cards / Hollow Resonances (TarotCard_*)
    tarots: list[dict[str, str]] = []
    for k, v in tm.items():
        if k.startswith("TarotCard_") and k.endswith("_story"):
            tid = k.split("_")[1]
            name = _clean(tm.get(f"TarotCard_{tid}_name", f"鸣徽 #{tid}"))
            des = _clean(tm.get(f"TarotCard_{tid}_des", ""))
            story = _clean(v)
            if story:
                tarots.append({"name": name, "des": des, "story": story})

    tc_md = ["# 零号空洞鸣徽考据与古物预言\n"]
    tc_md.append("> 零号空洞深处凝结的以太鸣徽。其上依附着旧文明探险者的执念与神秘预言。\n")
    for tc in tarots:
        tc_md.append(f"## 【{tc['name']}】\n")
        tc_md.append(f"> {tc['story']}\n")
        if tc["des"]:
            tc_md.append(f"**共鸣效能**：{tc['des']}\n")
        tc_md.append("---\n")
    (gloss_dir / "02_空洞鸣徽与古物预言.md").write_text("\n".join(tc_md), encoding="utf-8")

    return {"lore_tips": len(tips), "lore_tarots": len(tarots)}


def _extract_street(tm: TextMap, street_dir: Path) -> dict[str, int]:
    street_dir.mkdir(parents=True, exist_ok=True)

    # Ambient dialogues
    street_lines: list[str] = []
    for k, v in tm.items():
        if k.startswith("PasserBy_BubbleStory_") or k.startswith("PasserBy_Bubble_"):
            cleaned = _clean(v)
            if cleaned and len(cleaned) > 10 and not cleaned.startswith("LAYOUT"):
                if cleaned not in street_lines:
                    street_lines.append(cleaned)

    s_md = ["# 新艾利都市井众生相与街区传闻\n"]
    s_md.append("> 六分街、光映广场、黑雁工地与芭莱大厦前，市民、商贩、流浪动物与路人邦布的日常环境对话。\n")
    for line in street_lines[:1000]:
        s_md.append(f"- 🗣️ {line}")
    (street_dir / "01_街区路人与市井闲聊.md").write_text("\n".join(s_md), encoding="utf-8")

    return {"lore_street_lines": len(street_lines)}


def _generate_lore_index(lore_dir: Path, stats: dict[str, int]) -> None:
    lines = [
        "# 绝区零（ZZZ）全量世界观与设定文献库\n",
        "本目录由 `zzz-story-extractor` 自动解析自游戏文本包与配置表，完整收录了主线对话之外的全部核心世界观与深层文献。\n",
        "## 目录导览\n",
        "### 1. 代理人全景与身世秘史 (`lore/agents/`)",
        "- [00_代理人全景总览](agents/00_代理人全景总览.md)：全 72 位代理人基本资料总览汇总表",
        "- [01_狡兔屋](agents/01_狡兔屋.md)：安比、猫又、妮可、比利、星徽·比利",
        "- [02_白祇重工](agents/02_白祇重工.md)：珂蕾妲、安东、本、格莉丝",
        "- [03_维多利亚家政](agents/03_维多利亚家政.md)：可琳、莱卡恩、丽娜、艾莲",
        "- [04_刑侦特勤组](agents/04_刑侦特勤组.md)：朱鸢、青衣、赛斯、简·杜",
        "- [05_奥波勒斯小队](agents/05_奥波勒斯小队.md)：凯撒、露西、莱特、柏妮思、派派、波可娜、「11号」、「扳机」、「席德」",
        "- [06_对空六课](agents/06_对空六课.md)：星见雅、浅羽悠真、月城柳、苍角、希希芙",
        "- [07_卡吕冬之子](agents/07_卡吕冬之子.md)：外环机车党联盟与荒野开拓者",
        "- [08_天琴座与反舌鸟](agents/08_天琴座与反舌鸟.md)：耀嘉音、伊芙琳、雨果、薇薇安",
        "- [09_云岿山与怪啖屋](agents/09_云岿山与怪啖屋.md)：仪玄、橘福福、潘引壶、叶瞬光、伊德海莉、爱丽丝、柚叶、真斗、卢西娅",
        "- [10_坎卜斯黑枝与妄想天使](agents/10_坎卜斯黑枝与妄想天使.md)：照、般岳、琉音、千夏、爱芮、南宫羽、普罗米娅、挽昼、菲欧妮",
        "- [11_达识结社与空巡局](agents/11_达识结社与空巡局.md)：维琳娜、诺姆、希格莉德、克拉蕾、洛克茜、蕾米埃尔",
        "- [12_漫游者与特别存在](agents/12_漫游者与特别存在.md)：哲、铃、流浪猫小黑等\n",
        "### 2. 装备文献与造物图鉴 (`lore/equipment/`)",
        "- [01_驱动盘唱片物语](equipment/01_驱动盘唱片物语.md)：全 30 套驱动盘唱片背景故事与调律属性",
        "- [02_音擎档案与题记](equipment/02_音擎档案与题记.md)：全 105 款音擎专属构造说明、被动效果与题记引言",
        "- [03_邦布机体图鉴](equipment/03_邦布机体图鉴.md)：全 35+ 邦布机体格言、技能连携与萌趣战斗台词",
        "- [04_收藏展架与风味展品](equipment/04_收藏展架与风味展品.md)：录像店货架手办与纪念品风味物语\n",
        "### 3. 绳网论坛与通讯 (`lore/interknot/`)",
        "- [01_委托人任务档案](interknot/01_委托人任务档案.md)：700+ 长篇委托求助信、事件背景与空洞救援记录",
        "- [02_绳网私信与手机短信](interknot/02_绳网私信与手机短信.md)：即时通讯私信会话流（日常吐槽、八卦求助、协会联络）\n",
        "### 4. Random Play 录像店影音档案 (`lore/cinema/`)",
        "- [01_旧文明电影与影评](cinema/01_旧文明电影与影评.md)：录像店全部经典影片长梗概与顾客大众影评\n",
        "### 5. 新艾利都世界观百科与空洞规则 (`lore/glossary/`)",
        "- [01_空洞与以太规则](glossary/01_空洞与以太规则.md)：主线章节历程纪事、以太活性、侵蚀机制与治安法规",
        "- [02_空洞鸣徽与古物预言](glossary/02_空洞鸣徽与古物预言.md)：零号空洞鸣徽考据与古物渊源\n",
        "### 6. 街区众生相与市井传闻 (`lore/street/`)",
        "- [01_街区路人与市井闲聊](street/01_街区路人与市井闲聊.md)：六分街、光映广场等街区路人环境对话\n",
        "## 统计概要\n",
        f"- **收录代理人**：{stats.get('lore_agents', 0)} 位",
        f"- **收录驱动盘唱片**：{stats.get('lore_discs', 0)} 套",
        f"- **收录音擎装备**：{stats.get('lore_w_engines', 0)} 款",
        f"- **收录邦布图鉴**：{stats.get('lore_bangboos', 0)} 只",
        f"- **收录长篇委托**：{stats.get('lore_quests', 0)} 条",
        f"- **收录短信对话**：{stats.get('lore_messages', 0)} 条",
        f"- **收录旧文明影片**：{stats.get('lore_movies', 0)} 部（影评 {stats.get('lore_movie_comments', 0)} 条）",
        f"- **收录空洞词条**：{stats.get('lore_tips', 0)} 条，**鸣徽古物**：{stats.get('lore_tarots', 0)} 个",
    ]
    (lore_dir / "README.md").write_text("\n".join(lines), encoding="utf-8")
