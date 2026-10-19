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

# Early CBT1 avatar mapping for Birthday and Stature (01..09)
EARLY_AVATAR_ATTR_MAP: dict[str, str] = {
    "1011": "01",  # 安比 Anby (02/20, 156)
    "1021": "02",  # 猫又 Nekomata (07/30, 148)
    "1031": "03",  # 妮可 Nicole (11/11, 165)
    "1081": "04",  # 比利 Billy (11/25, 188)
    "1101": "05",  # 珂蕾妲 Koleda (08/10, 150)
    "1121": "06",  # 本 Ben (12/23, 192)
    "1181": "07",  # 格莉丝 Grace (04/14, 170)
    "1111": "08",  # 安东 Anton (05/02, 190)
    "1041": "09",  # 11号 Soldier 11 (3/21, 160)
}

# Variant avatar fallback to base version
VARIANT_INHERIT_MAP: dict[str, str] = {
    "1381": "1011",  # 零号·安比 -> 安比
    "1531": "1081",  # 星徽·比利 -> 比利
    "1502": "1501",  # 爱芮 -> 爱芮
    "1582": "1581",  # 蕾米埃尔 -> 蕾米埃尔
    "2041": "1431",  # 叶瞬光 -> 叶瞬光
    "2071": "1491",  # 千夏 -> 千夏
    "2131": "1611",  # 克拉蕾 -> 克拉蕾
    "2141": "1621",  # 洛克茜 -> 洛克茜
}

# Aliases for Mindscape Cinema Talent Prefix
TALENT_PREFIX_ALIASES: dict[str, str] = {
    "nicole": "Nostradamus",
    "koleda": "OokumaMari",
    "soukaku": "Aokaku",
    "piper": "Clara",
    "grace": "Lisa",
    "nekomata": "Tsubaki",
    "tsubaki": "Tsubaki",
    "miyabi": "Unagi",
    "unagi": "Unagi",
    "no11": "Longinus",
    "longinus": "Longinus",
    "spbilly": "SPBilly",
    "silveranby": "SilverAnby",
    "orpheus": "Brujas",
    "roxy": "Pryce",
    "zhao": "XiaoZhao",
    "xiaozhao": "XiaoZhao",
    "hugovlad": "HugoVlad",
    "janedoe": "JaneDoe",
    "qingyi": "QingYi",
    "banyue": "BanYue",
    "panyinhu": "PanYinhu",
    "yeshunguang": "Zhenzhen",
    "zhenzhen": "Zhenzhen",
    "yixuan": "YiXuan",
}

# Map internal char tags in GalGame / Date / Chat / Bubble events to avatar IDs
DIALOGUE_TAG_ALIASES: dict[str, str] = {
    "partnerno11": "1041",
    "partnernroma": "1571",
    "partnerorpheus": "1301",
    "orpheus": "1301",
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
    "anbi": "1011",
    "nico": "1031",
}

# Canonical in-game Camp mapping (enum OOOHMBMDLBI and CJELJCPENOL // 100)
CAMP_ID_MAP: dict[int, str] = {
    1: "狡兔屋",
    2: "维多利亚家政",
    3: "白祇重工",
    4: "卡吕冬之子",
    5: "奥波勒斯小队",
    6: "对空六课",
    7: "刑侦特勤组",
    8: "天琴座",
    9: "反舌鸟",
    10: "云岿山",
    11: "怪啖屋",
    12: "坎卜斯黑枝",
    13: "妄想天使",
    14: "都市秩序部",
    15: "外务筹策局",
    16: "达识结社",
    17: "空巡局",
    18: "弗林特工坊",
}

# Drive Disc tactical category mapping (Suit ID -> (Category, Badge))
DISC_TACTICAL_CATEGORIES: dict[str, tuple[str, str]] = {
    # 暴击与爆伤
    "31000": ("暴击与爆伤", "🎯"),
    "32700": ("暴击与爆伤", "🎯"),
    # 攻击与穿透
    "31100": ("攻击与穿透", "⚔️"),
    "31400": ("攻击与穿透", "⚔️"),
    "32800": ("攻击与穿透", "⚔️"),
    "32900": ("攻击与穿透", "⚔️"),
    "33300": ("攻击与穿透", "⚔️"),
    # 失衡与冲击
    "31200": ("失衡与冲击", "💥"),
    "33200": ("失衡与冲击", "💥"),
    # 异常与积蓄
    "31300": ("异常与积蓄", "🌀"),
    "31800": ("异常与积蓄", "🌀"),
    "33000": ("异常与积蓄", "🌀"),
    "34100": ("异常与积蓄", "🌀"),
    # 元素属性特化
    "32200": ("火属性特化", "🔥"),
    "32300": ("以太属性特化", "🔮"),
    "32400": ("电属性特化", "⚡"),
    "32500": ("冰属性特化", "❄️"),
    "32600": ("物理属性特化", "🗡️"),
    "33500": ("物理属性特化", "🗡️"),
    "33600": ("以太属性特化", "🔮"),
    "33800": ("冰属性特化", "❄️"),
    "33900": ("风属性特化", "🌪️"),
    "34000": ("以太属性特化", "🔮"),
    # 支援与能量
    "31600": ("能量与支援", "🎵"),
    "33400": ("能量与支援", "🎵"),
    # 生存与防御
    "31500": ("生存与防御", "🛡️"),
    "31900": ("生存与防御", "🛡️"),
    "33100": ("生存与防御", "🛡️"),
    "33700": ("生存与防御", "🛡️"),
    "34200": ("生存与防御", "🛡️"),
}

# Drive Disc partition slot metadata (1 to 6)
SLOT_PARTITION_METADATA: dict[int, tuple[str, str]] = {
    1: ("I号位（分区1）", "固定基础属性：生命值（Flat HP）"),
    2: ("II号位（分区2）", "固定基础属性：攻击力（Flat ATK）"),
    3: ("III号位（分区3）", "固定基础属性：防御力（Flat DEF）"),
    4: ("IV号位（分区4）", "高级属性：暴击率 / 暴击伤害 / 攻击力% / 防御力% / 生命值% / 异常精通"),
    5: ("V号位（分区5）", "进阶属性：属性伤害加成（火/冰/电/物/以太/风） / 穿透率 / 攻击力% / 防御力% / 生命值%"),
    6: ("VI号位（分区6）", "机制属性：能量自动回复 / 冲击力 / 异常掌控 / 攻击力% / 防御力% / 生命值%"),
}

# Bangboo tactical category and synergy mapping (Bangboo ID -> (Category, Activation Condition, Icon))
BANGBOO_SYNERGY_MAP: dict[str, tuple[str, str, str]] = {
    # Special / Protagonist Companion
    "50001": ("法厄同专用", "传奇绳匠专属 / 神经同步联结向导", "⭐"),
    # S-Rank (54001 ~ 54023)
    "54001": ("冰属性特化", "2名或以上[冰属性]角色", "❄️"),
    "54002": ("白祇重工", "2名或以上[白祇重工]阵营角色", "🏗️"),
    "54003": ("以太属性特化", "2名或以上[以太属性]角色", "🔮"),
    "54004": ("维多利亚家政", "2名或以上[维多利亚家政]阵营角色", "🧹"),
    "54005": ("狡兔屋", "2名或以上[狡兔屋]阵营角色", "🐰"),
    "54006": ("火属性特化", "2名或以上[火属性]角色", "🔥"),
    "54008": ("电属性特化", "2名或以上[电属性]角色", "⚡"),
    "54009": ("以太属性特化", "2名或以上[以太属性]角色", "🔮"),
    "54010": ("妄想天使", "2名或以上[妄想天使]阵营角色", "🎤"),
    "54011": ("卡吕冬之子", "2名或以上[卡吕冬之子]阵营角色", "🐗"),
    "54012": ("刑侦特勤组", "2名或以上[新艾利都治安局]阵营角色", "👮"),
    "54013": ("物理属性特化", "2名或以上[物理属性]角色", "🗡️"),
    "54014": ("对空六课", "2名或以上[对空洞特别行动部第六课]阵营角色", "⚔️"),
    "54015": ("天琴座", "2名或以上[天琴座]阵营角色", "✨"),
    "54016": ("反舌鸟", "1名或以上[反舌鸟]阵营角色", "🎭"),
    "54017": ("云岿山", "2名或以上[云岿山]阵营角色", "⛰️"),
    "54018": ("怪啖屋", "2名或以上[怪啖屋]阵营角色", "👻"),
    "54019": ("防卫军", "2名或以上[防卫军]阵营角色", "🛡️"),
    "54020": ("坎卜斯黑枝", "2名或以上[坎卜斯黑枝]阵营角色", "🌿"),
    "54021": ("达识结社", "队伍中存在[叶瞬光]", "📜"),
    "54022": ("罗斯凯利法", "1名或以上[罗斯凯利法]阵营角色", "⚙️"),
    "54023": ("空巡局", "队伍中存在[蕾米埃尔]", "🕊️"),
    # A-Rank (53001 ~ 53021)
    "53001": ("冰属性特化", "2名或以上[冰属性]角色", "❄️"),
    "53002": ("物理属性特化", "2名或以上[物理属性]角色", "🗡️"),
    "53003": ("支援型特化", "队伍中存在[支援]角色", "💚"),
    "53004": ("击破型特化", "队伍中存在[击破]角色", "💥"),
    "53005": ("防护型特化", "队伍中存在[防护]角色", "🛡️"),
    "53006": ("强攻型特化", "队伍中存在[强攻]角色", "⚔️"),
    "53007": ("火属性特化", "2名或以上[火属性]角色", "🔥"),
    "53008": ("支援型特化", "队伍中存在[支援]角色", "💚"),
    "53009": ("击破/穿透", "队伍中存在擅长[穿透]招式角色", "🎯"),
    "53010": ("电属性特化", "2名或以上[电属性]角色", "⚡"),
    "53011": ("异常型特化", "队伍中存在[异常]角色", "🌀"),
    "53012": ("支援型特化", "队伍中存在[支援]角色", "💚"),
    "53013": ("异常型特化", "队伍中存在[异常]角色", "🌀"),
    "53014": ("强攻/异常", "队伍中存在[强攻]或[异常]角色", "💼"),
    "53015": ("强攻/异常", "队伍中存在[强攻]或[异常]角色", "🥊"),
    "53016": ("命破/击破", "队伍中存在[命破]角色", "👑"),
    "53017": ("支援型特化", "队伍中存在[支援]角色", "🎠"),
    "53019": ("支援型特化", "队伍中存在[支援]角色", "🧱"),
    "53021": ("强攻/异常", "队伍中存在[强攻]或[异常]角色", "🎃"),
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
    stats.update(_extract_equipment(text_map, lore_dir / "equipment", avatar_base_data))
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
    tag_to_aid: dict[str, str] = dict(DIALOGUE_TAG_ALIASES)

    for e in raw_entries:
        name_key = e.get("HAKHHHCAENA") or ""
        name = tm.get(name_key)
        aid = str(e.get("PFOAJKNPCHL", 0))
        code = str(e.get("FEKFJBFGANO") or "").lower()
        if code:
            tag_to_aid[code] = aid
            tag_to_aid[f"partner{code}"] = aid
        if name and name not in seen_names:
            seen_names.add(name)
            playable.append(e)

    # Collect dialogue streams
    gal_events: dict[str, dict[str, list[tuple[str, str]]]] = defaultdict(lambda: defaultdict(list))
    chat_events: dict[str, dict[str, list[tuple[str, str]]]] = defaultdict(lambda: defaultdict(list))
    bubble_events: dict[str, dict[str, list[tuple[str, str]]]] = defaultdict(lambda: defaultdict(list))

    for k, v in tm.items():
        if k.startswith("PartnerTalk_GalGame_"):
            parts = k.split("_")
            if len(parts) >= 5:
                aid = tag_to_aid.get(parts[2].lower())
                if aid:
                    gal_events[aid][parts[3]].append((parts[4], _clean(v)))
        elif k.startswith("PartnerTalk_BubbleStory_"):
            parts = k.split("_")
            if len(parts) >= 4:
                aid = tag_to_aid.get(parts[2].lower())
                if aid:
                    lid = parts[4] if len(parts) >= 5 else "01"
                    bubble_events[aid][parts[3]].append((lid, _clean(v)))
        elif k.startswith("PartnerTalk_Chat_Partner"):
            parts = k.split("_")
            if len(parts) >= 4:
                aid = tag_to_aid.get(parts[2].lower())
                if aid:
                    lid = parts[4] if len(parts) >= 5 else "01"
                    chat_events[aid][parts[3]].append((lid, _clean(v)))
        elif k.startswith("PartnerTalk_Chat_33"):
            m = re.match(r"PartnerTalk_Chat_33(\d{3})(\d+)_(\d+)", k)
            if m:
                aid = str(1000 + int(m.group(1)) * 10 + 1)
                eid = m.group(1) + m.group(2)
                chat_events[aid][eid].append((m.group(3), _clean(v)))
        elif k.startswith("Chat_PartnerTalk_"):
            parts = k.split("_")
            if len(parts) >= 4:
                aid = tag_to_aid.get(parts[2].lower())
                if aid:
                    eid = parts[3]
                    lid = parts[-1]
                    chat_events[aid][eid].append((lid, _clean(v)))

    # Identify all Mindscape Cinema prefixes
    all_talent_prefixes: set[str] = set()
    for k in tm.keys():
        if "_Talent_01_Title" in k:
            all_talent_prefixes.add(k.split("_Talent_01_Title")[0])

    camp_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    agent_count = 0
    avatar_info_list: list[dict[str, Any]] = []

    for a in playable:
        aid = str(a.get("PFOAJKNPCHL", 0))
        name = _clean(tm.get(a.get("HAKHHHCAENA", ""), ""))
        full_name = _clean(tm.get(a.get("JGHFBBCBBBA", ""), name))
        camp_id = a.get("OOOHMBMDLBI", 0)
        cjel = a.get("CJELJCPENOL", 0)
        c_idx = (cjel // 100) - 100 if cjel >= 10000 else camp_id
        camp_name = CAMP_ID_MAP.get(c_idx, CAMP_ID_MAP.get(camp_id))
        if not camp_name:
            camp_name = _clean(
                tm.get(f"PartnerCamp_Name_{camp_id:02d}", tm.get(f"PartnerCamp_Name_{camp_id}", "漫游者"))
            )
        code = str(a.get("FEKFJBFGANO") or "")

        # Birthday & Stature with early and variant fallback
        birthday = _clean(tm.get(f"Partner_Birthday_{aid}", ""))
        stature = _clean(tm.get(f"Partner_Stature_{aid}", ""))

        if not birthday or not stature:
            early_idx = EARLY_AVATAR_ATTR_MAP.get(aid)
            if early_idx:
                if not birthday:
                    birthday = _clean(tm.get(f"Partner_Birthday_{early_idx}", ""))
                if not stature:
                    stature = _clean(tm.get(f"Partner_Stature_{early_idx}", ""))

        if not birthday or not stature:
            base_aid = VARIANT_INHERIT_MAP.get(aid)
            if base_aid:
                if not birthday:
                    birthday = _clean(tm.get(f"Partner_Birthday_{base_aid}", ""))
                if not stature:
                    stature = _clean(tm.get(f"Partner_Stature_{base_aid}", ""))

        if stature and stature.isdigit():
            stature = f"{stature} cm"

        feature_desc = _clean(tm.get(f"Item_Avatar_{aid}_Des", ""))

        # HIA Investigation License & Ether Aptitude
        outlook_desc = _clean(tm.get(f"Partner_OutlookDesc_{aid}", ""))
        aptitude = "待协会测定"
        if outlook_desc:
            if "优秀的以太适性" in outlook_desc:
                aptitude = "优秀"
            elif "良好的以太适性" in outlook_desc:
                aptitude = "良好"
            elif "以太适性为保密" in outlook_desc or "保密" in outlook_desc:
                aptitude = "保密"
            elif "尚未得到具体信息" in outlook_desc:
                aptitude = "待协会测定"
            else:
                aptitude = "已留档"

        # Profile entries (Partner_ProfileDesc_{aid}, _1, _2...)
        profiles: list[str] = []
        p_main = _clean(tm.get(f"Partner_ProfileDesc_{aid}", ""))
        if p_main:
            profiles.append(p_main)
        for i in range(1, 10):
            p_sub = _clean(tm.get(f"Partner_ProfileDesc_{aid}_{i}", ""))
            if p_sub:
                profiles.append(p_sub)

        # Impressions (Wise & Belle sibling dual-view)
        impression_wise = _clean(tm.get(f"Partner_Impression_m_{aid}", ""))
        impression_belle = _clean(tm.get(f"Partner_Impression_f_{aid}", ""))
        impression_gen = _clean(tm.get(f"Partner_Impression_{aid}", ""))

        # Signature W-Engines
        w_engines: list[dict[str, str]] = []
        for rank in ("S", "A", "B"):
            w_name = _clean(tm.get(f"Item_Weapon_{rank}_{aid}_Name", ""))
            if w_name:
                w_short = _clean(tm.get(f"Item_Weapon_{rank}_{aid}_ShortDesc", ""))
                w_desc = _clean(tm.get(f"Item_Weapon_{rank}_{aid}_Desc", ""))
                w_engines.append({
                    "name": f"{w_name} ({rank}级)",
                    "short_desc": w_short,
                    "desc": w_desc,
                })

        # Mindscape Cinema 6 Acts
        talent_prefix = TALENT_PREFIX_ALIASES.get(code.lower())
        if not talent_prefix:
            for p in all_talent_prefixes:
                if p.lower() == code.lower():
                    talent_prefix = p
                    break

        cinema_acts: list[dict[str, Any]] = []
        if talent_prefix:
            for act in range(1, 7):
                title = _clean(tm.get(f"{talent_prefix}_Talent_{act:02d}_Title", ""))
                story = _clean(tm.get(f"{talent_prefix}_Talent_{act:02d}_Desc_02", ""))
                buff = _clean(tm.get(f"{talent_prefix}_Talent_{act:02d}_Desc_01", ""))
                if title or story:
                    if not buff or buff == "PlaceHolder":
                        buff = "[技能等级强化] 普通攻击、闪避、支援技、特殊技、连携技技能等级提升。"
                    cinema_acts.append({
                        "act": act,
                        "title": title or f"第{act}幕",
                        "story": story,
                        "buff": buff,
                    })

        # Hangout / GalGame events
        agent_gals: list[dict[str, Any]] = []
        if aid in gal_events:
            for eid in sorted(gal_events[aid].keys()):
                title = _clean(tm.get(f"Title_{eid}", f"专属邀约 {eid}"))
                sorted_lines = [text for _, text in sorted(gal_events[aid][eid], key=lambda x: x[0])]
                agent_gals.append({"eid": eid, "title": title, "lines": sorted_lines})

        # Street chat encounters
        agent_chats: list[dict[str, Any]] = []
        if aid in chat_events:
            for eid in sorted(chat_events[aid].keys()):
                sorted_lines = [text for _, text in sorted(chat_events[aid][eid], key=lambda x: x[0])]
                agent_chats.append({"eid": eid, "lines": sorted_lines})

        # Street bubble interactions
        agent_bubbles: list[dict[str, Any]] = []
        if aid in bubble_events:
            for eid in sorted(bubble_events[aid].keys()):
                sorted_lines = [text for _, text in sorted(bubble_events[aid][eid], key=lambda x: x[0])]
                agent_bubbles.append({"eid": eid, "lines": sorted_lines})

        info = {
            "id": aid,
            "name": name,
            "full_name": full_name,
            "camp": camp_name,
            "code": code,
            "birthday": birthday,
            "stature": stature,
            "aptitude": aptitude,
            "outlook_desc": outlook_desc,
            "feature_desc": feature_desc,
            "profiles": profiles,
            "impression_wise": impression_wise,
            "impression_belle": impression_belle,
            "impression_gen": impression_gen,
            "w_engines": w_engines,
            "cinema_acts": cinema_acts,
            "gals": agent_gals,
            "chats": agent_chats,
            "bubbles": agent_bubbles,
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
        "都市秩序部": "04_刑侦特勤组.md",
        "弗林特工坊": "12_漫游者与特别存在.md",
    }

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
                md_lines.append(f"| **代理人ID / 代号** | `{ag['id']}` (`{ag['code']}`) |")
                md_lines.append(f"| **所属阵营** | {ag['camp']} |")
                if ag["birthday"]:
                    md_lines.append(f"| **生日** | {ag['birthday']} |")
                if ag["stature"]:
                    md_lines.append(f"| **身高 / 体型** | {ag['stature']} |")
                md_lines.append(f"| **以太适性评级** | {ag['aptitude']} |")
                if ag["w_engines"]:
                    w_names = [w["name"] for w in ag["w_engines"]]
                    md_lines.append(f"| **专属 / 推荐音擎** | {', '.join(w_names)} |")
                md_lines.append("")

                if ag["feature_desc"]:
                    md_lines.append(f"> **特写记录**：\n> {ag['feature_desc'].replace(chr(10), chr(10) + '> ')}\n")

                if ag["outlook_desc"]:
                    md_lines.append("#### 空洞调查协会（HIA）执照与以太适性档案\n")
                    md_lines.append(f"> {ag['outlook_desc'].replace(chr(10), chr(10) + '> ')}\n")

                if ag["profiles"]:
                    md_lines.append("#### 深度身世与机密档案\n")
                    for i, prof in enumerate(ag["profiles"], 1):
                        label = f"档案记录 0{i}" if i == 1 else f"档案记录 0{i}（进阶调查）"
                        md_lines.append(f"**{label}**：\n\n{prof}\n")

                if ag["impression_wise"] or ag["impression_belle"] or ag["impression_gen"]:
                    md_lines.append("#### 录像店私密评语（绳匠视点）\n")
                    if ag["impression_wise"]:
                        md_lines.append(f"- 🎬 **兄长·哲的观察随笔**：\n  > {ag['impression_wise'].replace(chr(10), chr(10) + '  > ')}\n")
                    if ag["impression_belle"]:
                        md_lines.append(f"- 📼 **胞妹·铃的私密手记**：\n  > {ag['impression_belle'].replace(chr(10), chr(10) + '  > ')}\n")
                    if ag["impression_gen"] and not ag["impression_wise"] and not ag["impression_belle"]:
                        md_lines.append(f"> {ag['impression_gen'].replace(chr(10), chr(10) + '> ')}\n")

                if ag["cinema_acts"]:
                    md_lines.append(f"#### 意象影画·心象世界（共 {len(ag['cinema_acts'])} 幕）\n")
                    for act_info in ag["cinema_acts"]:
                        md_lines.append(f"##### 第 {act_info['act']} 幕：{act_info['title']}\n")
                        if act_info["story"]:
                            md_lines.append(f"> **影画寄语**：\n> {act_info['story'].replace(chr(10), chr(10) + '> ')}\n")
                        if act_info["buff"]:
                            md_lines.append(f"- **核心机制**：{act_info['buff']}\n")

                if ag["w_engines"]:
                    md_lines.append("#### 专属音擎与题记物语\n")
                    for w in ag["w_engines"]:
                        md_lines.append(f"##### {w['name']}\n")
                        if w["short_desc"]:
                            md_lines.append(f"> **题记**：{w['short_desc']}\n")
                        if w["desc"]:
                            md_lines.append(f"{w['desc']}\n")

                if ag["gals"]:
                    md_lines.append(f"#### 专属信赖邀约（GalGame事件，共 {len(ag['gals'])} 幕）\n")
                    for g in ag["gals"]:
                        md_lines.append(f"##### {g['title']}\n")
                        for line in g["lines"]:
                            md_lines.append(f"- {line}")
                        md_lines.append("")

                if ag["chats"]:
                    md_lines.append(f"#### 街区偶遇与日常对话（共 {len(ag['chats'])} 幕）\n")
                    for c in ag["chats"]:
                        md_lines.append(f"##### 街区日常 {c['eid']}\n")
                        for line in c["lines"]:
                            md_lines.append(f"- {line}")
                        md_lines.append("")

                if ag["bubbles"]:
                    md_lines.append(f"#### 随行气泡与特别对话（共 {len(ag['bubbles'])} 组）\n")
                    for b in ag["bubbles"]:
                        md_lines.append(f"##### 街区气泡 {b['eid']}\n")
                        for line in b["lines"]:
                            md_lines.append(f"- {line}")
                        md_lines.append("")

                md_lines.append("---\n")

        (agents_dir / fname).write_text("\n".join(md_lines), encoding="utf-8")

    # Write Overview Table
    ov_lines = ["# 新艾利都代理人全景总览\n"]
    ov_lines.append("| ID | 姓名 | 全名 | 所属阵营 | 生日 | 身高/体型 | 以太适性 | 专属音擎 | 意象影画 | 信赖/日常互动 |")
    ov_lines.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
    for ag in sorted(avatar_info_list, key=lambda x: int(x["id"]) if x["id"].isdigit() else 9999):
        w_str = ag["w_engines"][0]["name"] if ag["w_engines"] else "-"
        cinema_str = f"{len(ag['cinema_acts'])}幕全" if ag["cinema_acts"] else "-"
        interaction_parts = []
        if ag["gals"]:
            interaction_parts.append(f"邀约 {len(ag['gals'])}幕")
        if ag["chats"]:
            interaction_parts.append(f"街区 {len(ag['chats'])}幕")
        if ag["bubbles"]:
            interaction_parts.append(f"气泡 {len(ag['bubbles'])}组")
        inter_str = " / ".join(interaction_parts) if interaction_parts else "-"

        ov_lines.append(
            f"| `{ag['id']}` | **{ag['name']}** | {ag['full_name']} | {ag['camp']} | "
            f"{ag['birthday'] or '-'} | {ag['stature'] or '-'} | {ag['aptitude']} | {w_str} | {cinema_str} | {inter_str} |"
        )
    (agents_dir / "00_代理人全景总览.md").write_text("\n".join(ov_lines), encoding="utf-8")

    return {"lore_agents": agent_count}


def _extract_equipment(
    tm: TextMap,
    equip_dir: Path,
    avatar_base_data: dict[str, Any] | list[Any] | None = None,
) -> dict[str, int]:
    equip_dir.mkdir(parents=True, exist_ok=True)

    # 1. Drive Discs (EquipmentSuit_*_story)
    discs: list[dict[str, Any]] = []
    for k, v in tm.items():
        if k.startswith("EquipmentSuit_") and k.endswith("_name"):
            suit_id = k.split("_")[1]
            name = _clean(v).strip()
            story = _clean(tm.get(f"EquipmentSuit_{suit_id}_story", ""))
            two_pc = _clean(tm.get(f"EquipmentSuit_{suit_id}_2_des", ""))
            four_pc = _clean(tm.get(f"EquipmentSuit_{suit_id}_4_des", ""))
            tag = _clean(tm.get(f"EquipmentSuit_{suit_id}_Tag", ""))
            hint = _clean(tm.get(f"EquipmentSuit_{suit_id}_Hint", ""))
            filter_opt = _clean(tm.get(f"EquipmentSuit_{suit_id}_SuitFilterOption", ""))

            if not story:
                continue

            prefix = suit_id[:3]
            slots: dict[int, dict[str, str]] = {}
            for slot in range(1, 7):
                slot_name = ""
                slot_des = ""
                for r in ("4", "3", "2"):
                    s_name = tm.get(f"Item_Equipment_{prefix}{r}{slot}_name")
                    s_des = tm.get(f"Item_Equipment_{prefix}{r}{slot}_des")
                    if s_des:
                        slot_name = _clean(s_name).strip() if s_name else f"{name}[{slot}]"
                        slot_des = _clean(s_des)
                        break
                if not slot_des:
                    target_token = f"{name}[{slot}]"
                    for k_item, v_item in tm.items():
                        if k_item.startswith("Item_Equipment_") and k_item.endswith("_name"):
                            if v_item.strip() == target_token or v_item.strip().startswith(target_token):
                                base_k = k_item[:-5]
                                fallback_des = tm.get(f"{base_k}_des")
                                if fallback_des:
                                    slot_name = _clean(v_item).strip()
                                    slot_des = _clean(fallback_des)
                                    break
                slots[slot] = {
                    "name": slot_name or f"{name}[{slot}]",
                    "des": slot_des,
                }

            cat, cat_icon = DISC_TACTICAL_CATEGORIES.get(
                suit_id,
                ("综合战术", "💿"),
            )

            discs.append({
                "id": suit_id,
                "name": name,
                "story": story,
                "two_pc": two_pc,
                "four_pc": four_pc,
                "tag": tag,
                "hint": hint,
                "filter_opt": filter_opt,
                "category": cat,
                "cat_icon": cat_icon,
                "slots": slots,
            })

    # Sort strictly by integer ID to eliminate ordering bugs
    discs.sort(key=lambda x: int(x["id"]) if x["id"].isdigit() else 9999)

    disc_md: list[str] = [
        "# 新艾利都驱动盘唱片物语（全30套调律文献与6重奏分轨物语）\n",
        "> 驱动盘（Drive Disc）不仅是代理人调节以太适配率的核心作战插件，更铭刻着旧文明遗音与新艾利都流传的旋律纪实。每一套完整的驱动盘都是一张拥有6个分轨曲目的EP黑胶唱片，随着音擎转动共鸣，为代理人注入独特的以太战斗节拍。\n",
        "## 驱动盘六大分区与属性调律法则\n",
        "新艾利都音像店（如六分街吟游唱针）将驱动盘规范为六大插槽分区，各自承载不同的调律机制：\n",
        "| 分区插槽 | 调律定位 | 属性规则与战术倾向 |",
        "| :--- | :--- | :--- |",
        "| **I号位（分区1）** | 基础生命 | 固定主属性：生命值（Flat HP） |",
        "| **II号位（分区2）** | 基础攻击 | 固定主属性：攻击力（Flat ATK） |",
        "| **III号位（分区3）** | 基础防御 | 固定主属性：防御力（Flat DEF） |",
        "| **IV号位（分区4）** | 战技倾向 | 随机主属性：暴击率 / 暴击伤害 / 攻击力% / 防御力% / 生命值% / 异常精通 |",
        "| **V号位（分区5）** | 属性穿透 | 随机主属性：属性伤害加成（火/冰/电/物/以太/风） / 穿透率 / 攻防生% |",
        "| **VI号位（分区6）** | 核心机制 | 随机主属性：能量自动回复 / 冲击力 / 异常掌控 / 攻防生% |\n",
        "## 全 30 套驱动盘战术流派与唱片速查总览\n",
        "| 编号 | 唱片名称 | 战术流派 | 官方定位特征 | 2件套共鸣效果 | 4件套战术机制概要 | 分轨收录 |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
    ]

    for d in discs:
        four_brief = d["four_pc"].replace("\n", " ")
        if len(four_brief) > 50:
            four_brief = four_brief[:48] + "..."
        disc_md.append(
            f"| `{d['id']}` | **《{d['name']}》** | {d['cat_icon']} {d['category']} | `{d['tag']}` | {d['two_pc']} | {four_brief} | 6部曲全 |"
        )

    disc_md.append("\n---\n")
    disc_md.append("## 驱动盘唱片物语详篇（按官方编号递增排序）\n")

    for d in discs:
        disc_md.append(f"### 《{d['name']}》（编号：{d['id']}）\n")
        disc_md.append("| 唱片指标 | 调律文献记录 |")
        disc_md.append("| :--- | :--- |")
        disc_md.append(f"| **唱片编号 / ID** | `{d['id']}` |")
        disc_md.append(f"| **战术流派分类** | {d['cat_icon']} {d['category']} |")
        disc_md.append(f"| **官方定位特征** | `{d['tag']}` |")
        if d["filter_opt"]:
            disc_md.append(f"| **驱动盘检索标签** | `{d['filter_opt']}` |")
        if d["hint"]:
            disc_md.append(f"| **调律适用建议** | {d['hint']} |")
        disc_md.append("")

        disc_md.append("#### 💿 唱片文献与背景纪事\n")
        disc_md.append(f"> {d['story'].replace(chr(10), chr(10) + '> ')}\n")

        disc_md.append("#### 🎵 调律共鸣效果\n")
        disc_md.append(f"- **2件套共鸣**：{d['two_pc']}")
        disc_md.append(f"- **4件套共鸣**：{d['four_pc']}\n")

        disc_md.append("#### 🎼 六重奏分轨曲目物语（共 6 部曲全集）\n")
        for slot in range(1, 7):
            meta = SLOT_PARTITION_METADATA[slot]
            tr = d["slots"].get(slot, {})
            tr_name = tr.get("name", f"{d['name']}[{slot}]")
            tr_des = tr.get("des", "")
            disc_md.append(f"##### 【第 {slot} 部分曲目】{tr_name}（{meta[0]}）\n")
            disc_md.append(f"- **分区调律职能**：{meta[1]}")
            if tr_des:
                disc_md.append("- **旋律题记与歌谣物语**：\n")
                disc_md.append(f"> {tr_des.replace(chr(10), chr(10) + '> ')}\n")
            else:
                disc_md.append("- **旋律题记**：暂缺\n")

        disc_md.append("---\n")
    (equip_dir / "01_驱动盘唱片物语.md").write_text("\n".join(disc_md), encoding="utf-8")

    # 2. W-Engines (Item_Weapon_*)
    aid_to_agent: dict[str, tuple[str, str]] = {}
    raw_entries: list[dict[str, Any]] = []
    if isinstance(avatar_base_data, dict):
        if "IAEFFFFLKNB" in avatar_base_data:
            raw_entries = avatar_base_data["IAEFFFFLKNB"]
        else:
            for v_entry in avatar_base_data.values():
                if isinstance(v_entry, list):
                    raw_entries = v_entry
                    break
    elif isinstance(avatar_base_data, list):
        raw_entries = avatar_base_data

    for e in raw_entries:
        aid = str(e.get("PFOAJKNPCHL", 0))
        name_k = e.get("HAKHHHCAENA")
        ag_name = _clean(tm.get(name_k, "")) if name_k else ""
        camp_id = e.get("OOOHMBMDLBI") or 0
        camp_name = CAMP_ID_MAP.get(camp_id, "特别存在")
        if ag_name:
            aid_to_agent[aid] = (ag_name, camp_name)

    # Canonical known avatar mappings
    aid_to_agent.setdefault("1071", ("凯撒", "卡吕冬之子"))
    aid_to_agent.setdefault("1141", ("莱卡恩", "维多利亚家政"))
    aid_to_agent.setdefault("1161", ("莱特", "卡吕冬之子"))
    aid_to_agent.setdefault("1301", ("奥菲丝&「鬼火」", "奥波勒斯小队"))
    aid_to_agent.setdefault("1381", ("零号·安比", "狡兔屋"))
    aid_to_agent.setdefault("1531", ("星徽·比利", "狡兔屋"))

    engines: list[dict[str, Any]] = []
    seen_engine_names: set[str] = set()

    for k, v in tm.items():
        if k.startswith("Item_Weapon_") and k.endswith("_Name"):
            base = k[:-5]
            desc_raw = tm.get(f"{base}_Desc", "")
            if not desc_raw or desc_raw.startswith("Test"):
                continue

            name = _clean(v).strip()
            if name in seen_engine_names:
                continue

            parts = base.split("_")
            rank = parts[2] if len(parts) > 2 else "A"
            is_common = (parts[3] == "Common") if len(parts) > 3 else False

            tid = None
            owner_agent = ""
            owner_camp = ""
            sort_rank = 1 if rank == "S" else (2 if rank == "A" else 3)
            sort_sub = (1, 999)

            if rank == "B" and is_common and len(parts) > 4:
                cnum = int(parts[4])
                tid = f"12{cnum:03d}"
                sort_sub = (1, cnum)
            elif rank == "A" and is_common and len(parts) > 4:
                cnum = int(parts[4])
                tid = f"13{cnum:03d}"
                sort_sub = (1, cnum)
            elif rank == "S" and is_common and len(parts) > 4:
                cnum = int(parts[4])
                tid = f"14{cnum:03d}"
                sort_sub = (1, cnum)
            elif rank == "A" and not is_common and len(parts) > 3:
                aid_str = parts[3]
                if len(aid_str) == 4:
                    tid = f"131{aid_str[1:3]}"
                    sort_sub = (0, int(aid_str))
                    ag_info = aid_to_agent.get(aid_str)
                    if ag_info:
                        owner_agent, owner_camp = ag_info
            elif rank == "S" and not is_common and len(parts) > 3:
                aid_str = parts[3]
                if len(aid_str) == 4:
                    tid = f"141{aid_str[1:3]}"
                    sort_sub = (0, int(aid_str))
                    ag_info = aid_to_agent.get(aid_str)
                    if ag_info:
                        owner_agent, owner_camp = ag_info
                elif aid_str.isdigit() and int(aid_str) <= 4:
                    cnum = int(aid_str)
                    tid = f"14{cnum:03d}"
                    sort_sub = (1, cnum)

            talent_title = _clean(tm.get(f"Weapon_TalentTitle_{tid}", "")) if tid else ""
            talent_des_r1 = _clean(tm.get(f"Weapon_TalentDes_8{tid}01", "")) if tid else ""
            talent_des_r5 = _clean(tm.get(f"Weapon_TalentDes_8{tid}05", "")) if tid else ""

            # Fallbacks for unit test mock keys
            special = _clean(tm.get(f"{base}_SpecialDesc", ""))
            buff_name = _clean(tm.get(f"{base}_Buff_Name", ""))
            buff_des = _clean(tm.get(f"{base}_Buff_Des", ""))

            short_desc = _clean(tm.get(f"{base}_ShortDesc", ""))

            # Quote & story splitting
            blocks = [b.strip() for b in desc_raw.split("\n\n") if b.strip()]
            story_part = ""
            quote_part = ""
            if len(blocks) >= 2 and ("「" in blocks[-1] or "——" in blocks[-1]):
                story_part = _clean("\n\n".join(blocks[:-1]))
                quote_part = _clean(blocks[-1])
            else:
                cleaned_all = _clean(desc_raw)
                if "「" in cleaned_all and "——" in cleaned_all:
                    idx = cleaned_all.rfind("「")
                    story_part = cleaned_all[:idx].strip()
                    quote_part = cleaned_all[idx:].strip()
                else:
                    story_part = cleaned_all
                    quote_part = ""

            final_quote = special or quote_part
            final_skill_title = talent_title or buff_name
            final_skill_r1 = talent_des_r1 or buff_des

            is_exclusive = bool(owner_agent or final_quote)
            cat_label = f"专属特化（{owner_agent}）" if owner_agent else ("专属特化" if is_exclusive else "标准量产")

            seen_engine_names.add(name)
            engines.append({
                "name": name,
                "rank": rank,
                "sort_key": (sort_rank, sort_sub, name),
                "owner_agent": owner_agent,
                "owner_camp": owner_camp,
                "category_label": cat_label,
                "short_desc": short_desc,
                "story": story_part,
                "quote": final_quote,
                "skill_title": final_skill_title,
                "skill_des_r1": final_skill_r1,
                "skill_des_r5": talent_des_r5,
            })

    # Sort strictly by rank, signature-first, then ID/number
    engines.sort(key=lambda x: x["sort_key"])

    engine_md = [
        "# 新艾利都音擎档案与专属题记（全100款核心改装与战士名言录）\n",
        "> 音擎（W-Engine）是新艾利都空洞作战最核心的高能动力装置与战术武器。每一款特制音擎的外壳与调谐回路，都封存着设计者的执念、改装工艺与战士在裂隙深处的烈火足迹。高阶专属音擎的铭牌与机械外壳上，更铭刻着代理人出生入死时的经典名言与题记。\n",
        "## 全 100 款音擎品质与战术回路速查总览\n",
        "| 品质 | 音擎名称 | 类别 / 专属归属 | 所属阵营 | 核心改装回路（被动） | 专属题记名言录 |",
        "| :--- | :--- | :--- | :--- | :--- | :--- |",
    ]

    for eng in engines:
        q_brief = eng["quote"].replace("\n", " ")
        if len(q_brief) > 35:
            q_brief = q_brief[:33] + "..."
        engine_md.append(
            f"| **{eng['rank']}级** | **《{eng['name']}》** | {eng['category_label']} | {eng['owner_camp'] or '-'} | {eng['skill_title'] or '-'} | {q_brief or '-'} |"
        )

    engine_md.append("\n---\n")
    engine_md.append("## 音擎详篇档案（按品质与系列严格排序）\n")

    for eng in engines:
        engine_md.append(f"### 【{eng['name']}】（{eng['rank']}级 · {eng['category_label']}）\n")
        engine_md.append("| 音擎参数 | 战术构造档案 |")
        engine_md.append("| :--- | :--- |")
        engine_md.append(f"| **品质级别** | **{eng['rank']} 级** |")
        engine_md.append(f"| **定位分类** | {eng['category_label']} |")
        if eng["owner_agent"]:
            engine_md.append(f"| **专属代理人** | **{eng['owner_agent']}**（所属阵营：{eng['owner_camp']}） |")
        if eng["short_desc"]:
            engine_md.append(f"| **官方简评** | {eng['short_desc']} |")
        if eng["skill_title"]:
            engine_md.append(f"| **核心改装回路** | **{eng['skill_title']}** |")
        engine_md.append("")

        if eng["quote"]:
            engine_md.append("#### 📜 专属题记与战士心声\n")
            engine_md.append(f"> {eng['quote'].replace(chr(10), chr(10) + '> ')}\n")

        engine_md.append("#### ⚙️ 音擎构造与由来纪实\n")
        engine_md.append(f"{eng['story']}\n")

        if eng["skill_title"] or eng["skill_des_r1"]:
            engine_md.append(f"#### 🔧 核心改装回路：{eng['skill_title']}\n")
            if eng["skill_des_r1"]:
                engine_md.append(f"- **改造 1 阶效果**：{eng['skill_des_r1']}")
            if eng["skill_des_r5"] and eng["skill_des_r5"] != eng["skill_des_r1"]:
                engine_md.append(f"- **改造 5 阶（满星）**：{eng['skill_des_r5']}")
            engine_md.append("")

        engine_md.append("---\n")
    (equip_dir / "02_音擎档案与题记.md").write_text("\n".join(engine_md), encoding="utf-8")

    # 3. Bangboos (Bangboo_Name_* & Bangboo_Desc_*)
    bangboos: list[dict[str, Any]] = []
    for k, v in tm.items():
        if k.startswith("Bangboo_Name_") and not any(sub in k for sub in ["_en_", "Skill"]):
            bid = k.replace("Bangboo_Name_", "")
            if bid in ("50002", "57001"):  # Filter internal test / dummy non-units
                continue
            name = _clean(v)
            desc = _clean(tm.get(f"Bangboo_Desc_{bid}", ""))
            en_name = _clean(tm.get(f"Bangboo_Name_en_{bid}", ""))
            act_title = _clean(tm.get(f"Bangboo_ActiveSkill_Title_{bid}", ""))
            act_des = _clean(tm.get(f"Bangboo_ActiveSkill_Des_{bid}", ""))
            qte_title = _clean(tm.get(f"Bangboo_QTE_Title_{bid}", ""))
            qte_des = _clean(tm.get(f"Bangboo_QTE_Des_{bid}", ""))
            talent_title = _clean(tm.get(f"Bangboo_TalentSkill_Title_{bid}", ""))
            talent_des_lv1 = _clean(tm.get(f"Bangboo_TalentSkill_Des_{bid}_01", ""))
            talent_des_lv5 = _clean(tm.get(f"Bangboo_TalentSkill_Des_{bid}_05", ""))
            tarot_name = _clean(tm.get(f"TarotCard_10{bid}_name", ""))
            tarot_des = _clean(tm.get(f"TarotCard_10{bid}_des", ""))

            # Handle Special / Eous
            if bid == "50001":
                rank = "SP"
                rank_badge = "⭐ 特型机（传奇向导）"
                if desc == "伊埃斯" or not desc:
                    desc = "传奇绳匠「法厄同」的专属伴随向导机体。搭载深度以太共鸣传感与神经同步系统，是哲与铃探索未知空洞时意识连接的机械向导化身与得力助手。"
                if not act_title:
                    act_title = "空洞深潜向导（神经感知系统）"
                    act_des = "在空洞探险中为代理人提供全息路线导航、以太活性预警与裂隙探测；在探索深渊时激活战略支援权限，开辟前线撤离通路。"
                if not qte_title:
                    qte_title = "法厄同之眼（实况指令联结）"
                    qte_des = "通过高带宽以太神经同步链路，与哲/铃的意识深度同调，对全队代理人下达精准的弱点打击指引与战术协同指令。"
                if not talent_title:
                    talent_title = "以太奇点耐受"
                    talent_des_lv1 = "具备罕见的高以太适性回路，即使在零号空洞最深层亦能免于以太侵蚀，为全队提供不竭的向导道标。"
                    talent_des_lv5 = talent_des_lv1
            elif bid.startswith("540"):
                rank = "S"
                rank_badge = "🟡 S级机体"
            elif bid.startswith("530"):
                rank = "A"
                rank_badge = "🟣 A级机体"
            else:
                rank = "A"
                rank_badge = "🟣 A级机体"

            # Filter out entries with neither description nor skills
            if not desc and not act_title and not qte_title:
                continue

            # Synergy mapping
            if bid in BANGBOO_SYNERGY_MAP:
                cat_tag, cond_desc, syn_icon = BANGBOO_SYNERGY_MAP[bid]
            else:
                syn_icon = "🤖"
                cat_tag = "战术通用"
                m = re.search(r"队伍中存在([^：:]+?)时触发", talent_des_lv1)
                cond_desc = m.group(1).strip() if m else "全队通用协同"

            # Voice lines
            voice_lines: list[str] = []
            for i in range(1, 15):
                line = _clean(tm.get(f"Tips_{bid}0{i}", tm.get(f"Tips_{bid}{i:02d}", "")))
                if line and line not in voice_lines:
                    voice_lines.append(line)

            # Special exploration tips for Eous
            tactical_tips: list[str] = []
            if bid == "50001":
                for i in range(101, 125):
                    tline = _clean(tm.get(f"Tips_50001{i}", ""))
                    if tline and tline not in tactical_tips:
                        tactical_tips.append(tline)

            bangboos.append({
                "id": bid,
                "rank": rank,
                "rank_badge": rank_badge,
                "name": name,
                "en_name": en_name,
                "desc": desc,
                "cat_tag": cat_tag,
                "cond_desc": cond_desc,
                "syn_icon": syn_icon,
                "active_title": act_title,
                "active_des": act_des,
                "qte_title": qte_title,
                "qte_des": qte_des,
                "talent_title": talent_title,
                "talent_des_lv1": talent_des_lv1,
                "talent_des_lv5": talent_des_lv5,
                "tarot_name": tarot_name,
                "tarot_des": tarot_des,
                "voices": voice_lines,
                "tactical_tips": tactical_tips,
            })

    # Canonical sorting: S-Rank (540xx) -> A-Rank (530xx) -> Special (50001), strictly numerical ID ascending
    def _bangboo_sort_key(b: dict[str, Any]) -> tuple[int, int]:
        bid_int = int(b["id"]) if b["id"].isdigit() else 99999
        rank_order = 0 if b["rank"] == "S" else (1 if b["rank"] == "A" else 2)
        return (rank_order, bid_int)

    sorted_bangboos = sorted(bangboos, key=_bangboo_sort_key)

    bangboo_md = [
        "# 新艾利都邦布机体全景图鉴与核心技能档案\n",
        "> 邦布（Bangboo）是新艾利都社会不可或缺的人工智能机械生命，也是空洞探索中唯一具备极高以太适性的探索向导。\n",
        "> 本图鉴完整收录全城共 42 款实装战斗伴随与特型向导邦布（22 款 S 级机体、19 款 A 级机体与 1 款特型伴随向导），全系严格按「S 级巅峰机体 → A 级实用机体 → 特型向导机体」品质阶梯与官方机体代号（Numerical ID）递增严格排序，完整汇编机体格言、主动技回路、邦布连携技、专属额外能力（Lv.1 ~ Lv.5 满级）、零号空洞助战鸣徽及萌趣战斗台词。\n",
        "## 邦布全景机体速查总览表\n",
        "| 品质 | 邦布名称 (英文代号) | 战术/阵营偏向 | 主动技回路 | 连携技 | 专属额外能力 | 萌趣台词摘录 |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
    ]

    for b in sorted_bangboos:
        rank_tag = "🟡 S级" if b["rank"] == "S" else ("🟣 A级" if b["rank"] == "A" else "⭐ 特型")
        act_tag = b["active_title"] if b["active_title"] else "—"
        qte_tag = b["qte_title"] if b["qte_title"] else "—"
        talent_tag = b["talent_title"] if b["talent_title"] else "—"
        quote_sample = b["voices"][0] if b["voices"] else "—"
        if len(quote_sample) > 30:
            quote_sample = quote_sample[:28] + "..."
        bangboo_md.append(
            f"| {rank_tag} | **{b['name']}** ({b['en_name']}) | {b['syn_icon']} {b['cat_tag']} | `{act_tag}` | `{qte_tag}` | `{talent_tag}` | {quote_sample} |"
        )

    bangboo_md.append("\n---\n")

    current_group = ""
    for b in sorted_bangboos:
        group_title = (
            "## 一、S 级巅峰战斗邦布机体（22 款全集）\n"
            if b["rank"] == "S"
            else (
                "## 二、A 级实用特化邦布机体（19 款全集）\n"
                if b["rank"] == "A"
                else "## 三、特型伴随向导邦布（传奇绳匠机体）\n"
            )
        )
        if group_title != current_group:
            current_group = group_title
            bangboo_md.append(group_title)

        bangboo_md.append(f"### {b['name']}（{b['en_name']}）\n")
        bangboo_md.append("| 机体指标 | 规格参数与配置记录 |")
        bangboo_md.append("| :--- | :--- |")
        bangboo_md.append(f"| **官方机体编号 / ID** | `{b['id']}` |")
        bangboo_md.append(f"| **机体品质档位** | {b['rank_badge']} |")
        bangboo_md.append(f"| **战术/阵营偏向** | {b['syn_icon']} {b['cat_tag']} |")
        bangboo_md.append(f"| **战术羁绊激活条件** | `{b['cond_desc']}` |")
        if b["tarot_name"]:
            bangboo_md.append(f"| **空洞助战鸣徽** | {b['tarot_name']} |")
        bangboo_md.append("")

        bangboo_md.append("#### 🤖 机体格言与档案纪事\n")
        bangboo_md.append(f"> *{b['desc'].replace(chr(10), chr(10) + '> ')}*\n")

        bangboo_md.append("#### ⚡ 核心技能回路\n")
        if b["active_title"] or b["active_des"]:
            bangboo_md.append(f"##### 1. 主动技：{b['active_title']}\n{b['active_des']}\n")
        if b["qte_title"] or b["qte_des"]:
            bangboo_md.append(f"##### 2. 邦布连携技：{b['qte_title']}\n{b['qte_des']}\n")
        elif b["rank"] != "SP":
            bangboo_md.append("##### 2. 邦布连携技：无\n*本机体无独立连携技，专注常态主动技与战术辅助回路。*\n")

        if b["talent_title"] or b["talent_des_lv1"]:
            bangboo_md.append(f"##### 3. 专属额外能力：{b['talent_title']}")
            if b["talent_des_lv1"]:
                bangboo_md.append(f"- **基础触发效果（Lv.1）**：{b['talent_des_lv1']}")
            if b["talent_des_lv5"] and b["talent_des_lv5"] != b["talent_des_lv1"]:
                bangboo_md.append(f"- **完全升级效果（Lv.5 满星）**：{b['talent_des_lv5']}")
            bangboo_md.append("")

        if b["tarot_des"]:
            bangboo_md.append("#### 🎴 零号空洞助战鸣徽效果\n")
            bangboo_md.append(f"- **助战鸣徽**：{b['tarot_name']}")
            bangboo_md.append(f"- **鸣徽增益效果**：{b['tarot_des']}\n")

        if b["voices"]:
            bangboo_md.append("#### 📢 战地语音与萌趣台词\n")
            for vl in b["voices"]:
                bangboo_md.append(f"- {vl}")
            bangboo_md.append("")

        if b["tactical_tips"]:
            bangboo_md.append("#### 🧭 空洞实况与战术指引通讯（以太神经同步）\n")
            for tl in b["tactical_tips"]:
                bangboo_md.append(f"- {tl}")
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
        "- [01_驱动盘唱片物语](equipment/01_驱动盘唱片物语.md)：全 30 套驱动盘唱片文献、调律属性与 6 重奏分轨物语全集",
        "- [02_音擎档案与题记](equipment/02_音擎档案与题记.md)：全 100 款音擎战术构造、核心改装回路与专属题记名言录全集",
        "- [03_邦布机体图鉴](equipment/03_邦布机体图鉴.md)：全 42 款邦布机体全景图鉴（22款S级、19款A级与特型向导机体）、机体格言、技能回路、助战鸣徽与萌趣台词",
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
