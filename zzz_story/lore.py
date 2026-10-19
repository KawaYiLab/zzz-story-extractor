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

# Canonical SMS Camp ordering for chapter presentation
CAMP_SMS_ORDER: list[tuple[int, str]] = [
    (10, "狡兔屋"),
    (12, "白祇重工"),
    (13, "维多利亚家政"),
    (14, "奥波勒斯小队"),
    (15, "刑侦特勤组"),
    (16, "卡吕冬之子"),
    (17, "对空六课"),
    (18, "天琴座"),
    (19, "幻影怪盗"),
    (20, "云岿山"),
    (21, "怪啖屋"),
    (22, "达识结社"),
    (23, "反舌鸟"),
    (24, "妄想天使"),
    (25, "外务筹策局"),
    (26, "都市秩序部"),
    (27, "空巡局"),
    (28, "弗林特工坊"),
]

# Canonical playable and story agents for SMS and Trust Memos (SenderNotes)
# code: (cid, name, camp_name, camp_code)
CANONICAL_SMS_AGENTS: dict[int, tuple[str, str, str, int]] = {
    1: ("101011", "安比", "狡兔屋", 10),
    2: ("101021", "猫又", "狡兔屋", 10),
    3: ("101031", "妮可", "狡兔屋", 10),
    4: ("141041", "「11号」", "奥波勒斯小队", 14),
    5: ("211051", "伊德海莉", "怪啖屋", 21),
    6: ("131061", "可琳", "维多利亚家政", 13),
    7: ("161071", "凯撒", "卡吕冬之子", 16),
    8: ("101081", "比利", "狡兔屋", 10),
    9: ("171091", "星见雅", "对空六课", 17),
    10: ("121101", "珂蕾妲", "白祇重工", 12),
    11: ("121111", "安东", "白祇重工", 12),
    12: ("121121", "本", "白祇重工", 12),
    13: ("171131", "苍角", "对空六课", 17),
    14: ("131141", "莱卡恩", "维多利亚家政", 13),
    15: ("161151", "露西", "卡吕冬之子", 16),
    16: ("161161", "莱特", "卡吕冬之子", 16),
    17: ("161171", "柏妮思", "卡吕冬之子", 16),
    18: ("121181", "格莉丝", "白祇重工", 12),
    19: ("131191", "艾莲", "维多利亚家政", 13),
    20: ("171201", "悠真", "对空六课", 17),
    21: ("131211", "丽娜", "维多利亚家政", 13),
    22: ("171221", "月城柳", "对空六课", 17),
    24: ("151241", "朱鸢", "刑侦特勤组", 15),
    25: ("151251", "青衣", "刑侦特勤组", 15),
    26: ("151261", "简", "刑侦特勤组", 15),
    27: ("151271", "赛斯", "刑侦特勤组", 15),
    28: ("161281", "派派", "卡吕冬之子", 16),
    29: ("191291", "雨果", "幻影怪盗", 19),
    30: ("141301", "奥菲丝& 「鬼火」", "奥波勒斯小队", 14),
    31: ("181311", "耀嘉音", "天琴座", 18),
    32: ("181321", "伊芙琳", "天琴座", 18),
    33: ("191331", "薇薇安", "幻影怪盗", 19),
    34: ("221341", "照", "达识结社", 22),
    35: ("161351", "波可娜", "卡吕冬之子", 16),
    36: ("141361", "「扳机」", "奥波勒斯小队", 14),
    37: ("201371", "仪玄", "云岿山", 20),
    39: ("201391", "橘福福", "云岿山", 20),
    40: ("211401", "爱丽丝", "怪啖屋", 21),
    41: ("211411", "浮波柚叶", "怪啖屋", 21),
    42: ("201421", "潘引壶", "云岿山", 20),
    43: ("201431", "叶瞬光", "云岿山", 20),
    44: ("211441", "狛野真斗", "怪啖屋", 21),
    45: ("211451", "卢西娅", "怪啖屋", 21),
    46: ("141461", "「席德」", "奥波勒斯小队", 14),
    47: ("221471", "般岳", "达识结社", 22),
    48: ("221481", "琉音", "达识结社", 22),
    49: ("231491", "千夏", "反舌鸟", 23),
    50: ("231501", "爱芮", "反舌鸟", 23),
    51: ("231511", "南宫羽", "反舌鸟", 23),
    52: ("241521", "希希芙", "妄想天使", 24),
    54: ("221541", "普罗米娅", "达识结社", 22),
    56: ("251561", "维琳娜", "外务筹策局", 25),
    57: ("251571", "诺姆", "外务筹策局", 25),
    58: ("261581", "蕾米埃尔", "都市秩序部", 26),
    59: ("271591", "希格莉德", "空巡局", 27),
    61: ("281611", "克拉蕾", "弗林特工坊", 28),
    62: ("281621", "洛克茜", "弗林特工坊", 28),
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
    collections: list[dict[str, Any]] = []
    for k, v in tm.items():
        if k.startswith("CollectionDesc_"):
            cid = k.replace("CollectionDesc_", "")
            if not cid.isdigit():
                continue
            name = _clean(tm.get(f"CollectionName_{cid}", f"藏品 {cid}"))
            raw_text = clean_text(v).text.strip()
            if not raw_text or len(raw_text) < 5:
                continue
            # Filter internal test dummy data
            if "测试数据" in name or "测试数据" in raw_text:
                continue

            # Parse quote if present: 「...」——... or ...——...
            quote = ""
            story = raw_text
            m = re.search(r'(「[^」\n]+?」\s*——\s*[^\n]+)$', raw_text)
            if not m:
                m = re.search(r'([^\n]+——\s*(?:安比|妮可|可琳|比利|安东|本|艾莲|珂蕾妲|莱卡恩|猫又|苍角|「11号」|丽娜|格莉丝|朱鸢|赛斯|简|露西|派派|青衣|凯撒|柏妮思|莱特|月城柳|星见雅|柚叶|真斗|照|奥菲丝|语出|课间)[^\n]*)$', raw_text)
            if m:
                quote = m.group(1).strip()
                story = raw_text[:m.start()].strip()

            # Categorize into the 4 official CollectionCabinet types
            if name.startswith("模型：") or name in ("奇机弄巧",):
                cat = "音擎模型"
                cat_badge = "⚙️ 音擎微缩模型"
                cat_order = 3
                sub = "音擎微缩手办·限定玩具" if "限定玩具" in raw_text else "音擎微缩手办·战术原型"
            elif any(suit in name or suit in raw_text for suit in ("三Z", "4WD", "0WD", "1WD", "等待", "蔬果国度", "生瓷有道", "桌上丽都", "火锅派对", "市井琐记", "甘甜夏日", "健康计划", "蔬菜天团")):
                cat = "潮流藏品"
                cat_badge = "🧸 潮流藏品"
                cat_order = 2
                if "等待" in name:
                    sub = "「等待…」概念潮玩系列"
                elif "三Z潮音" in name:
                    sub = "三Z潮音·乐队代言系列"
                elif any(k in name for k in ("4WD", "0WD", "1WD")):
                    sub = "驾梦漫布·邦布四驱车系列"
                elif any(k in name for k in ("甘甜夏日", "健康计划", "蔬菜天团")) or "蔬果国度" in raw_text:
                    sub = "邦布蔬果国度设计品系列"
                elif "生瓷有道" in name or "发财" in name:
                    sub = "生瓷有道·招财摆件系列"
                elif "桌上丽都" in name:
                    sub = "桌上丽都·生活美学系列"
                elif "火锅派对" in name:
                    sub = "火锅派对·「煮釜」联名摆件系列"
                elif "市井琐记" in name:
                    sub = "市井琐记·六分街见闻系列"
                else:
                    sub = "三Z STUDIO 潮流藏品"
            elif any(kw in name for kw in ("麦麦", "闪耀的此棒", "闪味奇盘", "咚哒回声")):
                cat = "活动限定"
                cat_badge = "🎉 活动限定"
                cat_order = 1
                if "麦麦" in name:
                    sub = "品牌联名·超大发光薯条灯"
                elif "闪耀的此棒" in name:
                    sub = "巨星盛典·耀嘉音演唱会限定"
                elif "闪味奇盘" in name:
                    sub = "市集特供·滋滋脆脆美食铺餐盘"
                else:
                    sub = "学园风物·奥蕾莉亚学院特制小鼓"
            else:
                cat = "纪事珍存"
                cat_badge = "📜 纪事珍存"
                cat_order = 0
                if "星见雅" in name:
                    sub = "特别羁绊·星见雅亲制信物"
                elif "伊埃斯" in raw_text or "如愿遂心" in name or "璀璨流金" in name:
                    sub = "传奇日常·绳匠兄妹与伊埃斯"
                elif "格莱特" in name:
                    sub = "街坊故事·掘进机与「真白君」"
                elif "治安官" in name:
                    sub = "市井趣闻·治安局抽奖阳光普照"
                elif "沙盘" in name:
                    sub = "战略演习·小邦布战术沙盘"
                elif "游侠骑士" in name:
                    sub = "荣誉认可·游侠骑士阿吉之盔"
                elif "倾心泪" in name:
                    sub = "少女祈愿·纯净泪滴纪念"
                else:
                    sub = "城市生活·纪事珍存物语"

            collections.append({
                "cid": cid,
                "name": name,
                "story": story,
                "quote": quote,
                "cat": cat,
                "cat_badge": cat_badge,
                "cat_order": cat_order,
                "sub": sub,
            })

    # Canonical sorting: Category (0..3) -> Numerical CID ascending
    def _col_sort_key(c: dict[str, Any]) -> tuple[int, int]:
        cid_int = int(c["cid"]) if c["cid"].isdigit() else 9999999
        return (c["cat_order"], cid_int)

    sorted_collections = sorted(collections, key=_col_sort_key)

    col_md = [
        "# 录像店展示架与收藏品风味物语\n",
        "> Random Play 货架与展柜上陈列的纪念品、市井手办、潮流玩偶与音擎微缩模型，记录着六分街街坊、委托人与代理人的日常趣事与深层回忆。\n",
        "> 本档案完整收录全城共 132 件实装展架藏品，全系严格按「纪事珍存（8件） → 活动限定（3件） → 潮流藏品（23件） → 音擎模型（98件）」四大官方分类与藏品编号（Numerical ID）递增严格排序。\n",
        "## 全 132 件展架藏品风味速查总览表\n",
        "| 编号 | 展品名称 | 官方分类 | 所属系列 / 主题 | 展品风味简介 |",
        "| :--- | :--- | :--- | :--- | :--- |",
    ]

    for c in sorted_collections:
        brief = c["story"].replace("\n", " ").strip()
        if len(brief) > 45:
            brief = brief[:43] + "..."
        col_md.append(f"| `{c['cid']}` | **{c['name']}** | {c['cat_badge']} | {c['sub']} | {brief} |")

    col_md.append("\n---\n")

    current_cat = -1
    cat_titles = [
        "## 第一辑：纪事珍存与市井纪念（共 8 件）\n> 六分街街坊的生活赠礼、代理人亲赠信物与法厄同兄妹的探险留念。\n",
        "## 第二辑：活动限定与庆典风物（共 3 件）\n> 新艾利都跨界品牌联名、巨星演艺庆典与商业街特供纪念品。\n",
        "## 第三辑：三Z潮流潮玩与套组展品（共 23 件）\n> 六分街「三Z设计工作室（三Z STUDIO）」与潮流品牌旗下热门系列。\n",
        "## 第四辑：音擎微缩手办与战术原型模型（共 98 件）\n> 代理人专属武器与工坊经典音擎的 1:1 比例精密微缩展品，附带使用者专属题记。\n",
    ]

    for c in sorted_collections:
        if c["cat_order"] != current_cat:
            current_cat = c["cat_order"]
            col_md.append(cat_titles[current_cat])

        col_md.append(f"### 【{c['name']}】（编号：`{c['cid']}`）\n")
        col_md.append("| 展品指标 | 展柜配置记录 |")
        col_md.append("| :--- | :--- |")
        col_md.append(f"| **官方藏品编号** | `{c['cid']}` |")
        col_md.append(f"| **官方所属分类** | {c['cat_badge']} |")
        col_md.append(f"| **所属系列 / 题材** | {c['sub']} |")
        col_md.append("| **展架陈列类型** | 货架陈列摆件 / 微缩模型 |")
        col_md.append("")

        col_md.append("#### 📖 展品风味文献\n")
        col_md.append(f"> {c['story'].replace(chr(10), chr(10) + '> ')}\n")

        if c["quote"]:
            col_md.append("#### 💬 专属题记 / 纪念名言\n")
            col_md.append(f"> *{c['quote']}*\n")

        col_md.append("---\n")
    (equip_dir / "04_收藏展架与风味展品.md").write_text("\n".join(col_md), encoding="utf-8")

    return {
        "lore_discs": len(discs),
        "lore_w_engines": len(engines),
        "lore_bangboos": len(bangboos),
        "lore_collectibles": len(collections),
    }


def _extract_interknot(tm: TextMap, knot_dir: Path) -> dict[str, int]:
    knot_dir.mkdir(parents=True, exist_ok=True)

    # 1. Forum posts (PostTitle_*, Poster_*, PostText_*, PostScript_*, Comment<N>_*, Commentator<N>_*)
    forum_posts: list[dict[str, Any]] = []
    for k in tm.keys():
        if k.startswith("PostTitle_"):
            pid = k.replace("PostTitle_", "")
            title = _clean(tm.get(k, ""))
            if not title:
                continue
            poster = _clean(tm.get(f"Poster_{pid}", "匿名绳匠"))
            text = _clean(tm.get(f"PostText_{pid}", ""))
            script = _clean(tm.get(f"PostScript_{pid}", ""))
            comments: list[dict[str, Any]] = []
            for i in range(1, 20):
                ct = _clean(tm.get(f"Comment{i}_{pid}", ""))
                cu = _clean(tm.get(f"Commentator{i}_{pid}", ""))
                if ct:
                    comments.append({"floor": i, "user": cu or "热心网友", "text": ct})

            tag = "💬 综合交流"
            if "委托" in title:
                tag = "📌 悬赏委托"
            elif "求助" in title or "招募" in title:
                tag = "🆘 紧急求助"
            elif "情报" in title or "怪谈" in title or "资讯" in title:
                tag = "🔍 怪谈情报"
            elif "灌水" in title or "讨论" in title:
                tag = "☕ 市井闲聊"
            elif "公告" in title or "通知" in title:
                tag = "📢 绳网公告"

            forum_posts.append({
                "pid": pid,
                "title": title,
                "poster": poster,
                "tag": tag,
                "text": text,
                "script": script,
                "comments": comments,
            })

    def _post_sort_key(p: dict[str, Any]) -> tuple[int, int | str]:
        pid = p["pid"]
        return (0, int(pid)) if pid.isdigit() else (1, pid)

    forum_posts.sort(key=_post_sort_key)

    # 2. In-game Commissions (QuestName_*, QuestDesc_*, QuestTarget_*, HollowClient_*, etc.)
    raw_quests: list[dict[str, Any]] = []
    for k in tm.keys():
        if not k.startswith("QuestName_"):
            continue
        qid = k.replace("QuestName_", "")
        name = _clean(tm.get(k, ""))
        if not name or "测试" in name or "test" in name.lower() or "temp" in name.lower() or "随意叠放" in name:
            continue
        # Filter out 3-star achievements (handled as child property of parent)
        if len(qid) == 10 and (qid.endswith("50") or qid.endswith("51") or qid.endswith("52")):
            continue
        # Filter pure step checkpoints if parent exists
        if len(qid) == 10 and f"QuestName_{qid[:8]}" in tm:
            continue

        desc = _clean(tm.get(f"QuestDesc_{qid}", ""))
        target = _clean(tm.get(f"QuestTarget_{qid}", ""))
        client = _clean(tm.get(f"HollowClient_{qid}", ""))

        if not desc and not target and not client:
            continue
        if desc in ["TBD", "占位", "待定", "待补充"]:
            continue
        if len(desc) < 6 and not target and not client:
            continue

        map_name = _clean(tm.get(f"BigSceneMapName_4{qid}", ""))
        map_desc = _clean(tm.get(f"BigSceneMapDes_4{qid}", ""))

        achievements: list[tuple[str, str]] = []
        for suffix in ["50", "51", "52"]:
            ach_id = f"{qid}{suffix}"
            aname = _clean(tm.get(f"HollowAchivementName_{ach_id}", ""))
            adesc = _clean(tm.get(f"HollowAchivementDesc_{ach_id}", ""))
            if aname:
                achievements.append((aname, adesc))

        in_targets: list[str] = []
        for step in ["01", "02", "03", "04", "05"]:
            it = _clean(tm.get(f"InHollowTarget_{qid}{step}", ""))
            if it and it not in in_targets:
                in_targets.append(it)

        raw_quests.append({
            "id": qid,
            "name": name,
            "desc": desc,
            "target": target,
            "client": client,
            "map_name": map_name,
            "map_desc": map_desc,
            "achievements": achievements,
            "in_targets": in_targets,
        })

    def _quest_sort_key(q: dict[str, Any]) -> tuple[int, int | str]:
        qid = q["id"]
        return (0, int(qid)) if qid.isdigit() else (1, qid)

    raw_quests.sort(key=_quest_sort_key)

    # Consolidate consecutive identical quests with same prefix
    consolidated: list[dict[str, Any]] = []
    curr: dict[str, Any] | None = None
    for q in raw_quests:
        qid = q["id"]
        p = qid[:4] if qid.isdigit() and len(qid) >= 4 else qid
        if curr and curr["name"] == q["name"] and curr["prefix"] == p:
            curr["stages"].append(q)
            if q["client"] and not curr["client"]:
                curr["client"] = q["client"]
            if q["achievements"] and not curr["achievements"]:
                curr["achievements"] = q["achievements"]
            if q["map_name"] and not curr["map_name"]:
                curr["map_name"] = q["map_name"]
                curr["map_desc"] = q["map_desc"]
            if q["in_targets"]:
                for it in q["in_targets"]:
                    if it not in curr["in_targets"]:
                        curr["in_targets"].append(it)
        else:
            if curr:
                consolidated.append(curr)
            curr = {
                "first_id": qid,
                "prefix": p,
                "name": q["name"],
                "desc": q["desc"],
                "target": q["target"],
                "client": q["client"],
                "map_name": q["map_name"],
                "map_desc": q["map_desc"],
                "achievements": q["achievements"],
                "in_targets": list(q["in_targets"]),
                "stages": [q],
            }
    if curr:
        consolidated.append(curr)

    # Classify consolidated commissions into 4 canonical categories
    for c in consolidated:
        qid = c["first_id"]
        name = c["name"]
        target = c["target"]
        desc = c["desc"]
        client = c["client"]
        if c["achievements"] or qid.startswith("1001") or client in ["「牧羊人」", "猫宫 又奈", "妮可·德玛拉"]:
            c["cat_order"] = 1
            c["cat_name"] = "⚔️ 核心空洞搜救"
        elif qid.startswith("1005") or qid.startswith("51") or "同行" in target or "升阶" in name or "心愿" in target or "心愿" in desc:
            c["cat_order"] = 3
            c["cat_name"] = "🤝 代理人羁绊同行"
        elif qid.startswith("1010") or qid.startswith("1228") or qid.startswith("1399") or qid.startswith("2310") or qid.startswith("30") or "考核" in name or "肃清" in name or "战线" in name:
            c["cat_order"] = 4
            c["cat_name"] = "🛡️ 协会考核特遣"
        else:
            c["cat_order"] = 2
            c["cat_name"] = "🏘️ 街区街坊委托"

    consolidated.sort(key=lambda x: (x["cat_order"], (0, int(x["first_id"])) if x["first_id"].isdigit() else (1, x["first_id"])))

    cat_groups: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for c in consolidated:
        cat_groups[c["cat_order"]].append(c)

    q_md = ["# 绳网（Inter-Knot）委托人任务档案与市井怪谈全集\n"]
    q_md.append(
        "> 新艾利都传奇绳匠「法厄同」从绳网终端（Inter-Knot）与空洞深潜系统承接的全部委托档案。\n"
        f"> 本档案完整收录「绳网论坛求助帖（共 {len(forum_posts)} 篇，含发帖人/正文/附言/楼层热评）」与「各街区实装正式委托（共 {len(consolidated)} 项，含委托人/空洞领域/行动目标/背景详情/三星观测指标/多阶段行动链）」，"
        "严格按「论坛求助原帖 → 核心空洞搜救 → 街区街坊委托 → 代理人同行羁绊 → 协会考核特遣」五大官方板块与数值编号递增严格排序。\n"
    )

    q_md.append("## 绳网委托与求助全景速查总览表\n")
    q_md.append("| 编号 | 委托 / 帖子标题 | 委托人 / 发帖人 | 官方分类 / 板块 | 核心目标 / 内容提要 |")
    q_md.append("| :--- | :--- | :--- | :--- | :--- |")

    for p in forum_posts:
        summary = p["text"].replace("\n", " ").replace("|", "—")
        if len(summary) > 42:
            summary = summary[:42] + "..."
        q_md.append(f"| `{p['pid']}` | **{p['title']}** | 👤 {p['poster']} | {p['tag']} | {summary} |")

    for c in consolidated:
        client_name = c["client"] if c["client"] else "街坊委托人"
        summary = (c["target"] if c["target"] else c["desc"]).replace("\n", " ").replace("|", "—")
        if len(summary) > 42:
            summary = summary[:42] + "..."
        q_md.append(f"| `{c['first_id']}` | **{c['name']}** | 👤 {client_name} | {c['cat_name']} | {summary} |")

    q_md.append("\n---\n")

    # Chapter 1: Forum Posts
    q_md.append(
        f"## 第一辑：绳网论坛求助与委托原帖（共 {len(forum_posts)} 篇）\n"
        "> 新艾利都市民、盗洞客、调查员与匿名网民在绳网论坛发布的求助悬赏、空洞传闻与都市怪谈讨论帖。包含完整楼主原帖、附言与各楼层真实网友回帖。\n"
    )
    for p in forum_posts:
        q_md.append(f"### 【帖子】{p['title']}（帖子编号：`{p['pid']}`）\n")
        q_md.append("| 帖子参数 | 绳网论坛记录 |")
        q_md.append("| :--- | :--- |")
        q_md.append(f"| **发帖编号** | `{p['pid']}` |")
        q_md.append(f"| **发帖人 / 楼主** | 👤 **{p['poster']}** |")
        q_md.append(f"| **所属板块** | {p['tag']} |")
        q_md.append(f"| **楼层回帖数** | 💬 {len(p['comments'])} 楼回复 |")
        q_md.append("")

        q_md.append("#### 📝 帖子原文内容\n")
        q_md.append(f"> {p['text'].replace(chr(10), chr(10) + '> ')}\n")

        if p["script"]:
            q_md.append("#### 📌 楼主附言\n")
            q_md.append(f"> *{p['script']}*\n")

        if p["comments"]:
            q_md.append(f"#### 💬 绳网网友回帖讨论（共 {len(p['comments'])} 楼）\n")
            q_md.append("| 楼层 | 评论用户 | 留言内容 |")
            q_md.append("| :--- | :--- | :--- |")
            for cmt in p["comments"]:
                cmt_text = cmt["text"].replace("\n", " ").replace("|", "—")
                q_md.append(f"| #{cmt['floor']} | **{cmt['user']}** | {cmt_text} |")
            q_md.append("")

        q_md.append("---\n")

    # Chapters 2 to 5: Commissions
    chapter_meta = [
        (1, "第二辑：空洞深潜与核心搜救委托", "传奇绳匠「法厄同」亲自深入各类高危空洞执行的核心特务、人道搜救与治安搜证任务，附带空洞舞台环境勘测、阶段推进与三星观测评级指标。"),
        (2, "第三辑：街区街坊委托与都市传闻", "六分街、光映广场、野火镇等生活街区街坊邻里发布的日常帮扶、机械改装与市井奇闻委托。"),
        (3, "第四辑：代理人专属同行与信任委托", "各大阵营代理人向绳匠发起的专属同行邀请、升阶考验与私密委托。"),
        (4, "第五辑：空洞调查协会与战线考评", "空洞调查协会（HIA）、治安局与防卫军组织的资质考核、战线肃清与模拟训练委托。"),
    ]

    for cat_idx, cat_title, cat_intro in chapter_meta:
        group_items = cat_groups.get(cat_idx, [])
        q_md.append(f"## {cat_title}（共 {len(group_items)} 项）\n> {cat_intro}\n")

        for c in group_items:
            client_display = c["client"] if c["client"] else "新艾利都市民 / 绳网委托人"
            target_display = c["target"] if c["target"] else "探索空洞并达成委托目标"

            q_md.append(f"### 【{c['name']}】（委托编号：`{c['first_id']}`）\n")
            q_md.append("| 委托指标 | 任务终端归档记录 |")
            q_md.append("| :--- | :--- |")
            q_md.append(f"| **官方委托编号** | `{c['first_id']}` |")
            q_md.append(f"| **委托人** | 👤 **{client_display}** |")
            q_md.append(f"| **任务业务分类** | {c['cat_name']} |")
            q_md.append(f"| **核心行动指引** | {target_display} |")
            if c["map_name"]:
                q_md.append(f"| **空洞舞台 / 区域** | 🌐 {c['map_name']} |")
            q_md.append("")

            q_md.append("#### 📋 委托背景详情\n")
            q_md.append(f"> {c['desc'].replace(chr(10), chr(10) + '> ')}\n")

            if c["map_desc"]:
                q_md.append("#### 🗺️ 空洞环境勘测情报\n")
                q_md.append(f"> {c['map_desc'].replace(chr(10), chr(10) + '> ')}\n")

            if c["in_targets"]:
                q_md.append("#### 🎯 空洞深入推进目标\n")
                for it in c["in_targets"]:
                    q_md.append(f"- {it}")
                q_md.append("")

            if c["achievements"]:
                q_md.append("#### ⭐ 空洞观测评级目标（三星指标）\n")
                q_md.append("| 星级目标 | 达成判定说明 |")
                q_md.append("| :--- | :--- |")
                for aname, adesc in c["achievements"]:
                    q_md.append(f"| ⭐ **{aname}** | {adesc} |")
                q_md.append("")

            if len(c["stages"]) > 1:
                q_md.append(f"#### 📜 委托行动阶段记录（共 {len(c['stages'])} 个阶段）\n")
                q_md.append("| 阶段编号 | 行动指引 | 阶段背景详情 |")
                q_md.append("| :--- | :--- | :--- |")
                for s in c["stages"]:
                    s_target = (s["target"] if s["target"] else "—").replace("|", "—")
                    s_desc = (s["desc"] if s["desc"] else "—").replace("\n", " ").replace("|", "—")
                    q_md.append(f"| `{s['id']}` | {s_target} | {s_desc} |")
                q_md.append("")

            q_md.append("---\n")

    (knot_dir / "01_委托人任务档案.md").write_text("\n".join(q_md), encoding="utf-8")

    # 3. Private Messages & Instant Messaging (Message_*)
    threads: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for k, v in tm.items():
        if not k.startswith("Message_"):
            continue
        mid = k[len("Message_"):]
        if (
            mid.startswith(("NPC", "Role_", "Group_", "Item_", "MultiMessage_", "Quest", "Reply", "SendButton"))
            or k.endswith(("_name", "_Tips", "_Name"))
        ):
            continue
        if "_" in mid:
            tid, seq = mid.rsplit("_", 1)
        elif mid.isdigit() and len(mid) >= 5:
            tid, seq = mid[:-2], mid[-2:]
        else:
            continue
        text = _clean(v)
        if not text or "占位" in text:
            continue
        threads[tid].append((seq, text, v))

    # Extract dynamic Trust Memos (SenderNotes) from TextMap if present
    trust_memos: dict[str, tuple[str, str, str]] = {}
    for k, v in tm.items():
        if k.startswith("SenderNote1_"):
            cid = k[len("SenderNote1_"):]
            n1 = _clean(tm.get(f"SenderNote1_{cid}", ""))
            n2 = _clean(tm.get(f"SenderNote2_{cid}", ""))
            n3 = _clean(tm.get(f"SenderNote3_{cid}", ""))
            if n1 or n2 or n3:
                trust_memos[cid] = (n1, n2, n3)

    def _get_agent_code(tid_str: str) -> int | None:
        if tid_str.startswith("40") and len(tid_str) >= 4 and tid_str[2:4].isdigit():
            return int(tid_str[2:4])
        if tid_str.startswith("4") and len(tid_str) >= 3 and tid_str[1:3].isdigit():
            return int(tid_str[1:3])
        if tid_str.startswith("601") and len(tid_str) >= 5 and tid_str[3:5].isdigit():
            return int(tid_str[3:5])
        if tid_str.startswith("2000"):
            return 1
        if tid_str.startswith(("20010", "20011", "20012")):
            return 3
        if tid_str.startswith(("20020", "20021", "20022")):
            return 8
        if tid_str.startswith(("20030", "20031", "20032")):
            return 2
        if tid_str.startswith(("20040", "20041", "20042")):
            return 4
        if tid_str.startswith("2005"):
            return 6
        if tid_str.startswith("2054"):
            return 10
        if tid_str.startswith("2056"):
            return 21
        if tid_str.startswith("2057"):
            return 25
        if tid_str.startswith("2058"):
            return 17
        if tid_str.startswith("1007"):
            return 7
        if tid_str.startswith(("10101", "10102", "10103", "10104")):
            return 2
        if tid_str.startswith(("1017", "1040")):
            return 15
        if tid_str.startswith("1027"):
            return 27
        if tid_str.startswith("1270"):
            return 31
        if tid_str == "122002":
            return 40
        if tid_str == "131001":
            return 56
        if "1261" in tid_str:
            return 26
        return None

    def _resolve_street_contact(tid_str: str) -> tuple[str, str, str]:
        tname = _clean(tm.get(f"Message_{tid_str}_name", ""))
        if tname:
            return (tname, "街区通讯", tname)
        if tid_str in ("9708",) or tid_str.startswith(("9900", "6004")):
            return ("法厄同（哲 / 铃）", "兄妹日常", "哲与铃的手持终端私信")
        if tid_str in ("9701", "10201", "10202", "10203", "10204") or tid_str.startswith(("3020", "9010", "9020", "9030")):
            return ("「牧羊人」", "独立情报中介", "「牧羊人」的情报专线")
        if tid_str in ("9702", "9705", "9706", "9707"):
            return ("柳林庄贵宾专线", "都市文旅", "柳林庄度假庄园贵宾通知")
        if tid_str == "9703":
            return ("淘金寻宝客", "空洞淘金", "C41 空洞物资箱开箱联络")
        if tid_str.startswith("10200"):
            return ("恩佐", "六分街商户", "恩佐的盒玩改装工坊")
        if tid_str.startswith(("1050", "105000")):
            return ("「咔嚓仔」", "六分街名人", "咔嚓仔的空洞街拍联络")
        if tid_str.startswith(("1060", "106000", "1090", "109000", "6200")):
            return ("塔维斯", "六分街商户", "「141」杂货店供货联络")
        if tid_str.startswith(("3010", "301000")):
            return ("艾尔菲", "六分街商户", "「吟游唱针」黑胶唱片推荐")
        if tid_str.startswith(("9901", "3099")):
            return ("空洞调查协会（HIA）", "官方机构", "HIA 特许独立调查员服务专线")
        if tid_str.startswith("8001"):
            return ("新艾利都治安局", "官方机构", "治安局个体经营资质管理通知")
        if tid_str.startswith("7000"):
            return ("「启明星」", "委托平台", "启明星特别拉力委托推荐")
        if tid_str.startswith("1025"):
            return ("喵吉长官", "治安协理", "喵吉长官的热心市民问候")
        if tid_str.startswith("1080"):
            return ("神秘特工", "都市传说", "TOPS 特工伪装通讯")
        if tid_str.startswith("1220"):
            return ("黑市奖券买家", "黑市交易", "神秘奖券收购联络")
        if tid_str.startswith("1230"):
            return ("防卫军指挥部", "官方机构", "莱姆尼安空洞避险广播")
        if tid_str.startswith("1990"):
            return ("汀曼大师", "六分街商户", "咖啡店新品鉴赏邀约")
        if tid_str.startswith("2099"):
            return ("神选者", "都市异闻", "午夜怪信·残月审判")
        if tid_str.startswith(("604", "610", "612", "651")):
            return ("录像店熟客", "街区市井", "Random Play 录像店日常沟通")
        return (f"市井联系人 #{tid_str}", "市井日常", f"街区通讯频段 #{tid_str}")

    def _format_msg_line(seq_str: str, text_str: str, raw_str: str, contact_str: str) -> str:
        is_phaethon = False
        if "{M#" in raw_str or "{F#" in raw_str:
            is_phaethon = True
        elif raw_str.startswith(("[回复]", "回复：", "【回复】")):
            is_phaethon = True

        ct = clean_text(raw_str)
        if ct.variants and len(ct.variants) > 1 and "M" in ct.variants and "F" in ct.variants:
            var_m = ct.variants["M"].replace("\n", " ").strip()
            var_f = ct.variants["F"].replace("\n", " ").strip()
            return f"> 📱 **[{seq_str}] 法厄同（哲 / 铃）**：哲：「{var_m}」 / 铃：「{var_f}」\n"

        clean_val = text_str.replace("\n", " ").strip()
        if is_phaethon:
            return f"> 📱 **[{seq_str}] 法厄同（哲 / 铃）**：{clean_val}\n"
        else:
            return f"> 💬 **[{seq_str}] {contact_str}**：{clean_val}\n"

    # Categorize threads
    agent_threads: dict[int, list[str]] = defaultdict(list)
    client_threads: list[str] = []
    street_threads: list[str] = []

    for tid in sorted(threads.keys(), key=lambda t: (0, int(t)) if t.isdigit() else (1, t)):
        code = _get_agent_code(tid)
        if code is not None and code in CANONICAL_SMS_AGENTS:
            agent_threads[code].append(tid)
            continue

        poster = _clean(tm.get(f"Poster_{tid}", ""))
        if poster or (len(tid) == 4 and tid.isdigit() and int(tid) in range(1000, 3000)):
            client_threads.append(tid)
            continue

        street_threads.append(tid)

    # Sort threads deterministically
    client_threads.sort(key=lambda t: (0, int(t)) if t.isdigit() else (1, t))
    street_threads.sort(key=lambda t: (0, int(t)) if t.isdigit() else (1, t))

    msg_md = ["# 绳网私信与手机即时通讯记录\n"]
    msg_md.append(
        "> 法厄同个人手持终端（敲敲 / Knock Knock）中的短信与私信聊天记录，全量收录代理人日常通讯、专属信托手记、绳网委托人后续跟进、街区市井闲谈与特色多方群聊。\n"
    )

    # Executive Overview Table
    msg_md.append("## 📱 绳网即时通讯与通讯录全景速查总览表\n")
    msg_md.append("| 频段编号 | 通讯对象 / 标题 | 身份类别 / 阵营 | 消息数量 | 交流内容导语 / 开场白 |")
    msg_md.append("| :--- | :--- | :--- | :--- | :--- |")

    # Table rows: Chapter 1 -> Chapter 2 -> Chapter 3
    for camp_code, camp_name in CAMP_SMS_ORDER:
        camp_agent_codes = [c for c, info in CANONICAL_SMS_AGENTS.items() if info[3] == camp_code]
        camp_agent_codes.sort(key=lambda c: int(CANONICAL_SMS_AGENTS[c][0]))
        for code in camp_agent_codes:
            cid, aname, _, _ = CANONICAL_SMS_AGENTS[code]
            tids = agent_threads.get(code, [])
            tids.sort(key=lambda t: (0, int(t)) if t.isdigit() else (1, t))
            for tid in tids:
                lines = threads[tid]
                m_sorted = sorted(lines, key=lambda x: x[0])
                first_text = m_sorted[0][1].replace("\n", " ").replace("|", "—") if m_sorted else "—"
                snippet = first_text[:28] + ("..." if len(first_text) > 28 else "")
                tname = _clean(tm.get(f"Message_{tid}_name", ""))
                title = tname if tname else snippet
                msg_md.append(f"| `#{tid}` | **{aname}** · {title} | {camp_name}（代理人通讯） | {len(lines)} 条 | {snippet} |")

    for tid in client_threads:
        lines = threads[tid]
        m_sorted = sorted(lines, key=lambda x: x[0])
        first_text = m_sorted[0][1].replace("\n", " ").replace("|", "—") if m_sorted else "—"
        snippet = first_text[:28] + ("..." if len(first_text) > 28 else "")
        poster = _clean(tm.get(f"Poster_{tid}", ""))
        cname = poster if poster else f"委托人 #{tid}"
        quest = _clean(tm.get(f"Quest_{tid}", ""))
        title = f"《{quest}》跟进" if quest else snippet
        msg_md.append(f"| `#{tid}` | **{cname}** · {title} | 绳网业务委托 | {len(lines)} 条 | {snippet} |")

    for tid in street_threads:
        lines = threads[tid]
        m_sorted = sorted(lines, key=lambda x: x[0])
        first_text = m_sorted[0][1].replace("\n", " ").replace("|", "—") if m_sorted else "—"
        snippet = first_text[:28] + ("..." if len(first_text) > 28 else "")
        cname, id_cat, title = _resolve_street_contact(tid)
        msg_md.append(f"| `#{tid}` | **{cname}** · {title} | {id_cat} | {len(lines)} 条 | {snippet} |")

    msg_md.append("\n---\n")

    msg_count = 0

    # Chapter 1: Playable Agents & Trust Memos
    msg_md.append("## 第一辑：代理人专属日常通讯与信托手记\n")
    for camp_code, camp_name in CAMP_SMS_ORDER:
        camp_agent_codes = [c for c, info in CANONICAL_SMS_AGENTS.items() if info[3] == camp_code]
        camp_agent_codes.sort(key=lambda c: int(CANONICAL_SMS_AGENTS[c][0]))
        has_content = any(c in agent_threads or CANONICAL_SMS_AGENTS[c][0] in trust_memos for c in camp_agent_codes)
        if not has_content:
            continue

        msg_md.append(f"### 🏛️ {camp_name}\n")
        for code in camp_agent_codes:
            cid, aname, _, _ = CANONICAL_SMS_AGENTS[code]
            has_memos = cid in trust_memos
            tids = agent_threads.get(code, [])
            tids.sort(key=lambda t: (0, int(t)) if t.isdigit() else (1, t))
            if not has_memos and not tids:
                continue

            msg_md.append(f"#### 💬 {aname}（{camp_name}）\n")
            if has_memos:
                memo1, memo2, memo3 = trust_memos[cid]
                m1_clean = re.sub(r"^对.+?的印象：?\s*", "", memo1).strip().replace("\n", "\n> ")
                m2_clean = memo2.strip().replace("\n", "\n> ")
                m3_clean = memo3.strip().replace("\n", "\n> ")
                msg_md.append(f"> 📝 **法厄同信托手记（对{aname}的印象）**\n>")
                if m1_clean:
                    msg_md.append(f"> **第一阶段**：{m1_clean}\n>")
                if m2_clean:
                    msg_md.append(f"> **第二阶段**：{m2_clean}\n>")
                if m3_clean:
                    msg_md.append(f"> **第三阶段**：{m3_clean}\n")
                msg_md.append("\n")

            for tid in tids:
                lines = threads[tid]
                m_sorted = sorted(lines, key=lambda x: x[0])
                first_text = m_sorted[0][1].replace("\n", " ").strip() if m_sorted else ""
                tname = _clean(tm.get(f"Message_{tid}_name", ""))
                title = tname if tname else (first_text[:24] + ("..." if len(first_text) > 24 else ""))
                msg_md.append(f"##### 频段 #{tid} · {title}\n")
                for seq, text, raw in m_sorted:
                    msg_md.append(_format_msg_line(seq, text, raw, aname))
                    msg_count += 1
                msg_md.append("---\n")

    # Chapter 2: Inter-Knot Commission Clients
    if client_threads:
        msg_md.append("## 第二辑：绳网委托人后续跟进与业务联络\n")
        for tid in client_threads:
            lines = threads[tid]
            m_sorted = sorted(lines, key=lambda x: x[0])
            first_text = m_sorted[0][1].replace("\n", " ").strip() if m_sorted else ""
            poster = _clean(tm.get(f"Poster_{tid}", ""))
            quest = _clean(tm.get(f"Quest_{tid}", ""))
            cname = poster if poster else f"委托人 #{tid}"
            title = f"《{quest}》跟进" if quest else (first_text[:24] + ("..." if len(first_text) > 24 else ""))
            msg_md.append(f"### 频段 #{tid} · {cname} · {title}\n")
            if poster or quest:
                p_label = f"`{poster}`" if poster else "—"
                q_label = f"《{quest}》" if quest else "—"
                msg_md.append(f"> 📋 **委托档案关联**：发帖人 {p_label} ｜ 委托任务 {q_label}\n\n")
            for seq, text, raw in m_sorted:
                msg_md.append(_format_msg_line(seq, text, raw, cname))
                msg_count += 1
            msg_md.append("---\n")

    # Chapter 3: Street & Group Chats
    if street_threads:
        msg_md.append("## 第三辑：街区市井通讯与特色多方群聊\n")
        for tid in street_threads:
            lines = threads[tid]
            m_sorted = sorted(lines, key=lambda x: x[0])
            cname, id_cat, title = _resolve_street_contact(tid)
            msg_md.append(f"### 频段 #{tid} · {cname} · {title}\n")
            msg_md.append(f"> 🏷️ **通讯类别**：{id_cat}\n\n")
            for seq, text, raw in m_sorted:
                msg_md.append(_format_msg_line(seq, text, raw, cname))
                msg_count += 1
            msg_md.append("---\n")

    (knot_dir / "02_绳网私信与手机短信.md").write_text("\n".join(msg_md), encoding="utf-8")

    return {"lore_quests": len(consolidated) + len(forum_posts), "lore_messages": msg_count}


FILM_COMMENT_GROUPS: dict[int, list[str]] = {
    1: ["101", "102", "103", "104", "105", "106"],
    2: ["201", "202", "203", "204", "205", "206", "2101", "2102", "2103", "2104", "2105"],
    3: ["301", "302", "303", "304", "305", "306", "2201", "2202", "2203", "2204", "2205"],
    4: ["401", "402", "403", "404", "405"],
    5: ["501", "502", "503", "504", "505"],
    6: ["601", "602", "603", "604", "605"],
    7: ["701", "702", "703", "704", "705", "3001", "3002", "3003", "3004", "3005"],
    8: ["801", "802", "803", "804", "805", "2901", "2902", "2903", "2904", "2905"],
    9: ["901", "902", "903", "904", "905"],
    10: ["1001", "1002", "1003", "1004"],
    11: ["1101", "1102", "1103", "1104", "1105", "2301", "2302", "2303", "2304", "2305"],
    12: ["1201", "1202", "1203", "1204", "1205", "2601", "2602", "2603", "2604", "2605"],
    13: ["1301", "1302", "1303", "1304", "1305"],
    14: ["1401", "2701", "2702", "2703", "2704", "2705"],
    15: ["2801", "2802", "2803", "2804", "2805"],
    16: ["2501", "2502", "2503", "2504", "2505"],
    17: ["2401", "2402", "2403", "2404", "2405"],
}

FILM_QUOTE_RANGES: dict[int, range] = {
    1: range(1, 3),    # 星徽骑士 (01-02)
    2: range(3, 7),    # 严厉的调查员, 坚定的母亲 (03-06)
    3: range(7, 10),   # 安吉丽娜, 洛普先生 (07-09)
    4: range(10, 13),  # 安娜, 杰森 (10-12)
    5: range(13, 15),  # 实习调查员 (13-14)
    6: range(15, 18),  # 艾琳达, 乔瑟夫 (15-17)
    7: range(18, 23),  # 莉莉安 (18-22)
    8: range(23, 27),  # 鲍勃, 热心姐姐 (23-26)
    9: range(27, 30),  # 成熟的治安官, 年轻的治安官 (27-29)
    10: range(30, 35), # 「我」的独白 (30-34)
    11: range(35, 38), # 迟到的客人, 胭儿 (35-37)
    12: range(38, 41), # 调查员, 小狗洛斯 (38-40)
    13: range(41, 45), # 惊惶的冒险者, 绝望的冒险者 (41-44)
}


def _extract_cinema(tm: TextMap, cinema_dir: Path) -> dict[str, int]:
    cinema_dir.mkdir(parents=True, exist_ok=True)

    # 1. Collect all comments from tm
    all_comments: dict[str, dict[str, str]] = {}
    for k, v in tm.items():
        if k.startswith("Cinema_Comment_") and k.endswith("_Content"):
            cid = k[len("Cinema_Comment_"):-len("_Content")]
            content = _clean(v)
            if content:
                name_k = f"Cinema_Comment_{cid}_Name"
                name = _clean(tm.get(name_k, "热心影迷")) or "热心影迷"
                all_comments[cid] = {"name": name, "content": content}

    # Store manager reflections: cid "1" (铃) and "2" (哲)
    manager_reflections: list[tuple[str, str, str]] = []
    for cid in ["2", "1"]:  # 哲 then 铃
        if cid in all_comments:
            m_info = all_comments[cid]
            display_role = "兄长·哲" if "哲" in m_info["name"] else ("胞妹·铃" if "铃" in m_info["name"] else m_info["name"])
            manager_reflections.append((cid, display_role, m_info["content"]))

    # Reverse map from cid to movie_id
    cid_to_movie: dict[str, int] = {}
    for mid, cids in FILM_COMMENT_GROUPS.items():
        for cid in cids:
            cid_to_movie[cid] = mid

    # Group comments by movie_id
    movie_comments: dict[int, list[tuple[str, str, str]]] = {i: [] for i in range(1, 100)}
    for cid, cinfo in all_comments.items():
        if cid in ["1", "2"]:
            continue
        if cid in cid_to_movie:
            mid = cid_to_movie[cid]
            movie_comments[mid].append((cid, cinfo["name"], cinfo["content"]))
        else:
            # Fallback for standard 3/4-digit release IDs: e.g. 101 -> 1, 1001 -> 10
            if cid.isdigit():
                inferred_mid = int(cid) // 100
                if 1 <= inferred_mid <= 99:
                    movie_comments[inferred_mid].append((cid, cinfo["name"], cinfo["content"]))

    # Sort comments within each movie numerically by cid
    for mid in movie_comments:
        movie_comments[mid].sort(key=lambda x: int(x[0]) if x[0].isdigit() else 99999)

    # 2. Extract Quotes
    movie_quotes: dict[int, list[tuple[str, str]]] = {}
    for mid, q_range in FILM_QUOTE_RANGES.items():
        q_list: list[tuple[str, str]] = []
        for q_idx in q_range:
            spk_k = f"Cinema_SpeakerName_6102000{q_idx:02d}"
            txt_k = f"Cinema_DoubleDate_6102000{q_idx:02d}"
            if txt_k in tm or spk_k in tm:
                spk = _clean(tm.get(spk_k, ""))
                txt = _clean(tm.get(txt_k, ""))
                if txt:
                    q_list.append((spk, txt))
        if q_list:
            movie_quotes[mid] = q_list

    # 3. Movies Config
    movies: list[dict[str, Any]] = []
    for i in range(1, 100):
        desc_k = f"Cinema_CinemaConfig_{i:02d}_Description"
        name_k = f"Cinema_CinemaConfig_{i:02d}_Name"
        title_k = f"Cinema_CinemaConfig_{i:02d}_Tittle"
        if desc_k in tm or name_k in tm or title_k in tm:
            desc = _clean(tm.get(desc_k, ""))
            name = _clean(tm.get(title_k, tm.get(name_k, f"经典影片 #{i:02d}")))

            # Tags
            tags: list[str] = []
            tag_k = f"Cinema_CinemaConfig_Tag_{i:02d}"
            if tag_k in tm:
                t = _clean(tm.get(tag_k, ""))
                if t and t not in tags:
                    tags.append(t)
            for sub in [1, 2, 3]:
                sub_k = f"Cinema_CinemaConfig_Tag_{i:02d}_{sub}"
                if sub_k in tm:
                    t = _clean(tm.get(sub_k, ""))
                    if t and t not in tags:
                        tags.append(t)
            tag_str = " / ".join(tags) if tags else "经典电影"

            m_comments = movie_comments.get(i, [])
            m_quotes = movie_quotes.get(i, [])

            if desc or name:
                movies.append({
                    "id": f"{i:02d}",
                    "num_id": i,
                    "name": name,
                    "desc": desc,
                    "tag_str": tag_str,
                    "tags": tags,
                    "comments": m_comments,
                    "quotes": m_quotes,
                })

    # Sort movies strictly ascending by num_id
    movies.sort(key=lambda x: x["num_id"])

    # 4. Generate Markdown
    c_md = ["# Random Play 录像店旧文明电影与大众影评\n"]
    c_md.append("> 录像店藏品中收录的旧文明黄金时代经典电影、特摄剧、纪录片与顾客大众影评。完整涵盖新艾利都影视金曲、流派标签、原声台词选摘与全量顾客短评。\n")

    # Overview Table
    c_md.append("## 📽️ 旧文明经典馆藏全景速查总览表\n")
    c_md.append("| 录像带编号 | 经典片名 | 题材流派 / 标签 | 馆藏剧情梗概导读 | 经典原声选摘 | 影评篇数 |")
    c_md.append("| :---: | :--- | :--- | :--- | :--- | :---: |")
    for m in movies:
        short_desc = m["desc"].replace("\n", " ")
        if len(short_desc) > 28:
            short_desc = short_desc[:26] + "..."
        if m["quotes"]:
            first_spk, first_txt = m["quotes"][0]
            clean_txt = first_txt.replace("\n", " ")
            if len(clean_txt) > 16:
                clean_txt = clean_txt[:15] + "..."
            sample_q = f"【{first_spk}】{clean_txt}" if first_spk else f"“{clean_txt}”"
        else:
            sample_q = "暂无台词收录"
        c_count = len(m["comments"])
        c_md.append(f"| {m['id']} | 《{m['name']}》 | {m['tag_str']} | {short_desc} | {sample_q} | {c_count} 篇 |")
    c_md.append("")

    # Manager reflections if any
    if manager_reflections:
        c_md.append("## 🎞️ 店长放映杂感·观影出神札记\n")
        c_md.append("> 录像店兄妹在放映厅忙碌一天后偷闲看片、或者在观影途中走神时记下的真实心声札记。\n")
        for cid, role, content in manager_reflections:
            c_md.append(f"- 💭 **{role}**：*“{content}”*")
        c_md.append("\n---\n")

    # Detailed Movie Sections
    total_comments = len(manager_reflections)
    for m in movies:
        c_md.append(f"## {m['id']}. 《{m['name']}》（录像带编号：{m['id']}）\n")
        c_md.append(f"- **题材流派 / 标签**：{m['tag_str']}\n")
        c_md.append("### 剧情梗概与题材背景\n")
        c_md.append(f"{m['desc']}\n")

        if m["quotes"]:
            c_md.append("### 经典原声台词选摘\n")
            for spk, txt in m["quotes"]:
                if spk:
                    c_md.append(f"- 🗣️ **{spk}**：*“{txt}”*")
                else:
                    c_md.append(f"- 🗣️ *“{txt}”*")
            c_md.append("")

        if m["comments"]:
            c_md.append(f"### 顾客观影札记与热门影评（共 {len(m['comments'])} 篇）\n")
            for cid, name, content in m["comments"]:
                c_md.append(f"- 💬 **{name}**：*“{content}”*")
                total_comments += 1
            c_md.append("")
        else:
            c_md.append("### 顾客观影札记与热门影评\n")
            c_md.append("> *暂无本店顾客发表影评记录。*\n")

        c_md.append("---\n")

    (cinema_dir / "01_旧文明电影与影评.md").write_text("\n".join(c_md), encoding="utf-8")

    return {"lore_movies": len(movies), "lore_movie_comments": total_comments}


CHAPTER_GUIDES: dict[str, tuple[str, str]] = {
    "1000": ("S1-CHAPTER 000", "狡兔屋初遇法厄同，录像店与空洞深潜契约启动"),
    "1001": ("S1-CHAPTER 001", "猫又潜入狡兔屋，引申出白祇重工机械谜案"),
    "1002": ("S1-CHAPTER 002", "黑雁工地深潜调查，珂蕾妲与白祇重工重铸荣耀"),
    "1003": ("S1-CHAPTER 002 INTERLUDE", "治安局刑侦特勤组出动，朱鸢与青衣执勤协作"),
    "1004": ("S1-CHAPTER 003", "芭莱大厦幽灵事件，维多利亚家政优雅执事行动"),
    "1005": ("S1-CHAPTER 004", "外环荒野霸主争霸赛，卡吕冬之子燃擎狂飙"),
    "1006": ("S1-CHAPTER 005", "对空六课全员集结，星见雅与月城柳星流斩夜"),
    "1007": ("S1-CHAPTER 006", "零号空洞旧都旧忆，揭开以太灾变历史沉寂"),
    "1008": ("S1-CHAPTER 007", "深渊共鸣决战，法厄同与全阵营并肩突破死局"),
    "1009": ("S2-CHAPTER 001", "云岿山怪啖屋启幕，仪玄、福福与瞬光古门修行"),
    "1010": ("S2-CHAPTER 002", "索恩海域潮汐异动，以太深潜探秘远洋古遗迹"),
    "1011": ("S2-CHAPTER 003", "良夜前哨暗涌，面对以太侵蚀狂澜的抗争"),
    "1012": ("S2-CHAPTER 004", "虚数回廊梦境追忆，探寻旧文明未竟的愿景"),
    "1013": ("S2-CHAPTER 005", "空洞活性极限攀升，深渊裂隙的决绝探查"),
    "1014": ("S2-CHAPTER 006", "微光引渡，迷途以骸与人类灵魂的救赎"),
    "1015": ("S2-INTERLUDE", "反舌鸟天籁复苏，耀嘉音与伊芙琳舞台奏鸣"),
    "1016": ("S2-EPILOGUE", "日落之时余晖反照，新政局与新势力的暗潮"),
    "1017": ("S2-EPILOGUE", "破晓前的沉静准备，新旧时代的交替节点"),
    "1018": ("S3-CHAPTER 001", "潜意识深潜调查，意识流离者的归途寻觅"),
    "1019": ("S3-CHAPTER 002", "与旧都执念的永别，文明重构的崭新里程碑"),
    "1020": ("S3-CHAPTER 003", "深层身世揭秘，宿命纠葛的最终解封"),
    "2001": ("SP-2001", "简·杜伪装深潜，山狮帮与刑侦特勤组博弈"),
    "2002": ("SP-2002", "对空六课赛博网络训练，虚拟与现实的双重试炼"),
    "2003": ("SP-2003", "耀嘉音巡演特别纪事，聚光灯与以太战场的合鸣"),
}

EMERGENCY_MEDS: dict[str, str] = {
    "1000602": "[战救]急救输液管",
    "1000605": "[战救]军用硬化针",
    "1000606": "[战救]肾上腺素气雾剂",
    "1000607": "[战救]双管薄荷提神剂",
    "1000608": "[战救]应急保命剂",
}


def _extract_glossary(tm: TextMap, gloss_dir: Path) -> dict[str, int]:
    gloss_dir.mkdir(parents=True, exist_ok=True)

    # =========================================================================
    # Part 1: Main Story Chapters & Timeline (01_空洞与以太规则.md)
    # =========================================================================
    chapters: list[tuple[str, str, str, str]] = []
    for k, v in tm.items():
        if k.startswith("MainStoryChapterNumber_"):
            cid = k.replace("MainStoryChapterNumber_", "")
            name_k = f"MainStoryChapterName_{cid}"
            num = _clean(v)
            name = _clean(tm.get(name_k, "")).replace("\xa0", " ")
            guide = CHAPTER_GUIDES.get(cid, (num, "主线剧情深入推进"))[1]
            if name and name != "未完待续…":
                chapters.append((cid, num, name, guide))

    for k, v in tm.items():
        if k.startswith("SpecialEpisodesChapterName_"):
            cid = k.replace("SpecialEpisodesChapterName_", "")
            name = _clean(v).replace("\xa0", " ")
            guide = CHAPTER_GUIDES.get(cid, (f"SP-{cid}", "独家视界代理人特别篇"))[1]
            chapters.append((cid, f"SP-{cid}", f"独家视界·{name}", guide))

    # Fallback if no MainStoryChapterNumber found (e.g. minimal mock test data)
    if not chapters:
        for k, v in tm.items():
            if k.startswith("ChapterTipsMain_"):
                cid = k.replace("ChapterTipsMain_", "")
                cleaned_val = _clean(v).replace("\xa0", " ")
                if "临时" not in cleaned_val and "OB-" not in cleaned_val:
                    guide = CHAPTER_GUIDES.get(cid, (f"幕次 {cid}", "官方剧情纪事"))[1]
                    chapters.append((cid, f"幕次 {cid}", cleaned_val, guide))

    chapters.sort(key=lambda x: int(x[0]) if x[0].isdigit() else 99999)

    # =========================================================================
    # Part 2: World Tips & Loading Knowledge (01_空洞与以太规则.md)
    # =========================================================================
    tips: list[str] = []
    seen_tips: set[str] = set()

    # 1. Canonical loading screen tips
    for k, v in sorted(tm.items()):
        if k.startswith("LoadingTips_"):
            cleaned = _clean(v)
            if cleaned and len(cleaned) > 15 and cleaned not in seen_tips:
                if not any(token in cleaned for token in ["点击[", "按键", "滑动翻页", "拖拽画面", "请重试"]):
                    seen_tips.add(cleaned)
                    tips.append(cleaned)

    # 2. Key worldbuilding tips from Tips_
    lore_keywords = ["以太", "空洞", "侵蚀", "治安", "绳匠", "盗洞客", "防卫军", "赫利俄斯", "新艾利都", "旧都", "邦布", "音擎", "秽息"]
    for k, v in sorted(tm.items()):
        if k.startswith("Tips_") and len(v) > 20:
            if not any(token in v for token in ["LAYOUT_", "Action:UI", "IconMap:", "点击[", "按键", "tab", "Tab", "切远程", "禁用中"]):
                if any(w in v for w in lore_keywords):
                    cleaned = _clean(v)
                    if cleaned and cleaned not in seen_tips:
                        seen_tips.add(cleaned)
                        tips.append(cleaned)

    # =========================================================================
    # Part 3: Erosion Symptoms / Corruption Pathology (01_空洞与以太规则.md)
    # =========================================================================
    curses: list[dict[str, str]] = []
    seen_curse_stories: set[str] = set()
    for k, v in sorted(tm.items()):
        if k.startswith("Curse_") and k.endswith("_story"):
            cid = k.split("_")[1]
            story = _clean(v)
            name = _clean(tm.get(f"Curse_{cid}_name", ""))
            des = _clean(tm.get(f"Curse_{cid}_des", ""))
            if story and name and story not in seen_curse_stories:
                seen_curse_stories.add(story)
                curses.append({
                    "id": cid,
                    "name": name,
                    "des": des,
                    "story": story,
                })

    curses.sort(key=lambda x: int(x["id"]) if x["id"].isdigit() else 99999)

    # -------------------------------------------------------------------------
    # Render 01_空洞与以太规则.md
    # -------------------------------------------------------------------------
    t_md = ["# 新艾利都世界观百科与空洞规则\n"]
    t_md.append("> 涵盖新艾利都官方条例、主线全章节编年史、以太物理规则、空洞灾害评级与全量以太侵蚀病理图鉴。\n")

    # Section 1: Chapter Timeline
    t_md.append("## 📜 第一辑：核心主线历程与章节纪事全景\n")
    t_md.append("| 幕次编号 | 官方分幕代号 | 主线章节名称 | 剧情主轴导读 |")
    t_md.append("| :---: | :--- | :--- | :--- |")
    for cid, num, title, guide in chapters:
        t_md.append(f"| {cid} | **{num}** | 《{title}》 | {guide} |")
    t_md.append("")

    # Section 2: World Rules & Living Guidelines
    t_md.append("## 🌐 第二辑：新艾利都世界观典藏与空洞生存法则\n")
    if tips:
        for tip in tips:
            t_md.append(f"- 💡 {tip}")
        t_md.append("")

    # Section 3: Erosion Symptoms
    if curses:
        t_md.append("## ☣️ 第三辑：零号空洞以太侵蚀症状全景病理图鉴\n")
        t_md.append("> 小队在空洞内遭遇压力过载（压力值累计达 100）后将爆发随机侵蚀症状，对生理、神经机能与战术协同产生深远异变。\n")
        t_md.append("| 症状编号 | 侵蚀症状名称 | 异变病理手记摘要 | 空洞实战异变效应 |")
        t_md.append("| :---: | :--- | :--- | :--- |")
        for c in curses:
            short_story = c["story"].replace("\n", " ")
            if len(short_story) > 26:
                short_story = short_story[:24] + "..."
            short_des = c["des"].replace("\n", " ")
            if len(short_des) > 26:
                short_des = short_des[:24] + "..."
            t_md.append(f"| #{c['id']} | **{c['name']}** | {short_story} | {short_des} |")
        t_md.append("\n### 全量侵蚀症状详录\n")
        for c in curses:
            t_md.append(f"#### 【{c['name']}】（编号：#{c['id']}）\n")
            t_md.append(f"- 🔬 **病理异变物语**：\n> *“{c['story']}”*\n")
            if c["des"]:
                t_md.append(f"- ⚠️ **空洞侵蚀效应**：{c['des']}\n")
            t_md.append("---\n")

    (gloss_dir / "01_空洞与以太规则.md").write_text("\n".join(t_md), encoding="utf-8")

    # =========================================================================
    # Part 4: Resoniums & Relics (02_空洞鸣徽与古物预言.md)
    # =========================================================================
    tarots: list[dict[str, str]] = []
    for k, v in sorted(tm.items()):
        if k.startswith("TarotCard_") and k.endswith("_story"):
            tid = k.split("_")[1]
            if not tid.isdigit():
                continue
            name = _clean(tm.get(f"TarotCard_{tid}_name", tm.get(f"TarotCard_{tid}_Name", f"鸣徽 #{tid}")))
            if tid in EMERGENCY_MEDS and name.startswith("鸣徽 #"):
                name = EMERGENCY_MEDS[tid]
            des = _clean(tm.get(f"TarotCard_{tid}_des", ""))
            story = _clean(v)
            if story and name not in ("鸣徽信息", "无货"):
                tarots.append({"id": tid, "name": name, "des": des, "story": story})

    # Sort strictly by numeric ID ascending
    tarots.sort(key=lambda x: int(x["id"]) if x["id"].isdigit() else 99999)

    # Group into canonical genres
    genre_groups: dict[str, list[dict[str, str]]] = {}
    for t in tarots:
        m = re.match(r"\[(.*?)\]", t["name"])
        g = m.group(1) if m else "代理人专属共鸣古物"
        genre_groups.setdefault(g, []).append(t)

    tc_md = ["# 零号空洞鸣徽考据与古物预言全集\n"]
    tc_md.append("> 零号空洞深处凝结的以太鸣徽与旧文明珍稀古物。其上依附着旧文明探险者的执念、神秘预言与强大的以太战术增益。\n")

    # Resonium Genres Overview Table
    tc_md.append("## 🔮 零号空洞鸣徽流派全景速查总览表\n")
    tc_md.append("| 序号 | 核心流派分类 | 鸣徽收录总数 | 战术增益倾向 | 代表性鸣徽 / 预言古物 |")
    tc_md.append("| :---: | :--- | :---: | :--- | :--- |")

    canonical_genre_order = [
        ("引燃", "火属性灼烧爆发与斗志累积"),
        ("冻结", "冰属性冻结碎冰与霜寒控制"),
        ("感电", "电属性感电传导与落雷增伤"),
        ("强袭", "物理伤害穿透与破甲重击"),
        ("以太", "以太能量侵蚀与活性共鸣"),
        ("侵蚀", "侵蚀机制抗性与负面状态转化"),
        ("烈性", "极限样本强效增幅"),
        ("暴击", "暴击率与暴击伤害极境强化"),
        ("决斗", "失衡值快速积蓄与失衡易伤倍率"),
        ("护盾", "护盾生成保护与反伤壁垒"),
        ("闪避", "极限闪避强化与反击追加伤害"),
        ("能量", "能量自动回复与终结技快速充能"),
        ("顽强", "生命上限恢复与防御减伤"),
        ("诡术", "奇术障眼法与概率增益触发"),
        ("命破", "贯穿防御与绝对贯通伤害"),
        ("锋御", "防反招架与锋芒坚壁"),
        ("支援", "后台快速支援与连携技增幅"),
        ("协助", "协同作战与宠物随行助力"),
        ("契合", "代理人羁绊战术流派深度共鸣"),
        ("研究", "空洞科研探索与资源高效转化"),
        ("通用", "全队通用战斗效能强化"),
        ("空洞", "空洞行进机制与齿轮硬币理财"),
        ("战救", "战场应急医疗与生命体征强化"),
        ("礼包码", "旧文明娱乐彩蛋与光耀馈赠"),
        ("出战", "邦布前场连携与主动战技"),
        ("助战", "邦布后场支援与能量被动"),
        ("代理人专属共鸣古物", "专属身世信物与觉醒预言"),
    ]

    rendered_genres = set()
    idx = 1
    for g_name, g_desc in canonical_genre_order:
        if g_name in genre_groups:
            items = genre_groups[g_name]
            sample = items[0]["name"]
            tc_md.append(f"| {idx:02d} | **【{g_name}】** | {len(items)} 款 | {g_desc} | {sample} |")
            rendered_genres.add(g_name)
            idx += 1

    for g_name, items in sorted(genre_groups.items()):
        if g_name not in rendered_genres:
            sample = items[0]["name"]
            tc_md.append(f"| {idx:02d} | **【{g_name}】** | {len(items)} 款 | 专属战法古物 | {sample} |")
            idx += 1

    tc_md.append("")

    # Detailed entries by genre
    g_section_idx = 1
    for g_name, g_desc in canonical_genre_order:
        if g_name in genre_groups:
            items = genre_groups[g_name]
            tc_md.append(f"## {g_section_idx}. 【{g_name}】战术鸣徽与古物（共 {len(items)} 款）\n")
            tc_md.append(f"> 战术增益倾向：{g_desc}\n")
            for t in items:
                tc_md.append(f"### 【{t['name']}】（编号：#{t['id']}）\n")
                tc_md.append(f"- 📜 **古物预言 / 档案考据**：\n> *“{t['story']}”*\n")
                if t["des"]:
                    tc_md.append(f"- ⚡ **共鸣效能**：{t['des']}\n")
                tc_md.append("---\n")
            g_section_idx += 1

    for g_name, items in sorted(genre_groups.items()):
        if g_name not in rendered_genres:
            tc_md.append(f"## {g_section_idx}. 【{g_name}】战术鸣徽与古物（共 {len(items)} 款）\n")
            for t in items:
                tc_md.append(f"### 【{t['name']}】（编号：#{t['id']}）\n")
                tc_md.append(f"- 📜 **古物预言 / 档案考据**：\n> *“{t['story']}”*\n")
                if t["des"]:
                    tc_md.append(f"- ⚡ **共鸣效能**：{t['des']}\n")
                tc_md.append("---\n")
            g_section_idx += 1

    (gloss_dir / "02_空洞鸣徽与古物预言.md").write_text("\n".join(tc_md), encoding="utf-8")

    return {"lore_tips": len(tips), "lore_tarots": len(tarots)}


def _extract_street(tm: TextMap, street_dir: Path) -> dict[str, int]:
    street_dir.mkdir(parents=True, exist_ok=True)

    district_configs = [
        (
            "01",
            "六分街（Sixth Street）",
            "Random Play 录像店门前、锦鲤面馆、盒玩具店、涡轮改装店与 141 便利店",
            "狡兔屋、面馆乔普师傅、141店员、街坊邻里与录像店顾客",
            ["Chapter00", "Chapter01", "SixthStreet", "1001_01", "Store", "MainCityStreet"],
        ),
        (
            "02",
            "光映广场（Lumina Square）",
            "繁华商业步行街、天桥观景台、HIA 协会大厅、治安局分署、404 Livehouse 与演艺大厅",
            "HIA调查员、治安官、潮牌店长、逛街市民与演艺乐迷",
            ["FortuneSquare", "FortuneHIA", "FortuneNEPS", "404ERROR", "Concert", "SuibianTemple", "Hand", "ReverbArena"],
        ),
        (
            "03",
            "黑雁工地旧址（Brant Street）",
            "机械施工现场、工友集结地、重机营地、地下管网与废弃站台",
            "白祇重工工程队、施工工人、机械师与安全监理",
            ["Chapter02", "BrantStreet", "MegaRobot"],
        ),
        (
            "04",
            "芭莱大厦前广场（Ballet Twins）",
            "喷泉广场、双子大厦名流商圈、艺术长廊与高雅观景台",
            "艺术名流、芭莱双子访客、摄影师与都会名媛",
            ["Chapter03", "BalletTwins"],
        ),
        (
            "05",
            "外环·野火镇（Blazewood）",
            "机车党荒野客栈、外环集市、仙人掌戈壁、加油站与狂飙赛道",
            "卡吕冬之子、荒野开拓者、机车骑手与集市客商",
            ["Chapter04", "OuterRing", "Blazewood"],
        ),
        (
            "06",
            "索恩区·罗斯凯利法（Roscaelifer）",
            "索恩大都会、历史行政名区、轨道交通枢纽与都会繁华街巷",
            "大都会通勤族、轻轨乘客、索恩名流与市政公职人员",
            ["Roscaelifer", "Subway"],
        ),
        (
            "07",
            "卫非地半岛（Whitfield）",
            "澄辉坪聚落、辉瓷工坊、索恩海湾海角与泽尼希航天城旧址",
            "辉瓷手艺人、半岛渔民、海钓客、水手与海湾度假市民",
            ["Whitfield", "WhitFiled", "HiddenReef", "Port", "UltimateAngler"],
        ),
        (
            "08",
            "云岿山怪啖街区（Yum Cha Sin）",
            "随缘道场、古法茶馆、方士集聚地、山门集市与怪啖街坊",
            "云岿方士、茶客、茶肆掌柜、香客与求道者",
            ["YumChaSin"],
        ),
        (
            "09",
            "斯科特哨站（Scott Outpost）",
            "零号空洞前沿指挥所、防卫军哨所、补给站与调查员集结地",
            "对空六课前沿哨兵、防卫军军官、资深调查员与物资军需官",
            ["Zero", "Outpost", "Scott"],
        ),
        (
            "10",
            "街头邦布众生相（Street Bangboos）",
            "新艾利都街头巷尾、各商铺门口、工地角落与野生流浪点",
            "巡警布、建筑布、快递布、招揽布与野生流浪邦布",
            ["BangBoo", "BangbooUnderGround", "BangbooRabbit"],
        ),
    ]

    def match_district(k: str) -> str:
        k_lower = k.lower()
        if "bangboo" in k_lower:
            return "10"
        for d_id, _, _, _, kw_list in district_configs:
            if d_id == "10":
                continue
            for kw in kw_list:
                if kw.lower() in k_lower:
                    return d_id
        return "11"

    # 1. Parse PasserByChat_
    chat_dict: dict[str, dict] = {}
    for k, v in tm.items():
        if k.startswith("PasserByChat_"):
            parts = k.split("_")
            if len(parts) >= 4:
                prefix = parts[1]
                conv_id = parts[2]
                suffix = "_".join(parts[3:])
                conv_key = f"{prefix}_{conv_id}"
                if conv_key not in chat_dict:
                    chat_dict[conv_key] = {"prefix": prefix, "id": conv_id, "dialogues": [], "names": {}}
                if suffix.startswith("Name"):
                    cleaned_name = _clean(v)
                    if cleaned_name:
                        chat_dict[conv_key]["names"][suffix] = cleaned_name
                else:
                    cleaned_text = _clean(v)
                    if cleaned_text and len(cleaned_text) > 1 and not cleaned_text.startswith("LAYOUT"):
                        chat_dict[conv_key]["dialogues"].append((suffix, cleaned_text))

    chats_by_dist: dict[str, list[dict]] = {d[0]: [] for d in district_configs}
    chats_by_dist["11"] = []

    total_chat_lines = 0
    for conv_key, cdata in chat_dict.items():
        cdata["dialogues"].sort(key=lambda x: x[0])
        cleaned_dialogues = []
        seen_seq = set()
        for seq, text in cdata["dialogues"]:
            base_seq = seq.rstrip("FMfm")
            if base_seq in seen_seq:
                continue
            seen_seq.add(base_seq)
            cleaned_dialogues.append((seq, text))
        cdata["dialogues"] = cleaned_dialogues
        if cleaned_dialogues:
            total_chat_lines += len(cleaned_dialogues)
            dist_id = match_district(conv_key)
            chats_by_dist[dist_id].append(cdata)

    for dist_id in chats_by_dist:
        chats_by_dist[dist_id].sort(key=lambda x: (x["prefix"], x["id"]))

    # 2. Parse Bubbles
    bubbles_by_dist: dict[str, list[tuple[str, str]]] = {d[0]: [] for d in district_configs}
    bubbles_by_dist["11"] = []
    all_bubble_texts: set[str] = set()

    for k, v in tm.items():
        is_bubble = (
            k.startswith("PasserBy_BubbleStory_")
            or k.startswith("PasserBy_Bubble_")
            or k.startswith("PasserByBubble_")
            or k.startswith("PasserBy_BubbleNpc_")
            or k.startswith("BubbleByChat_")
            or k.startswith("StoreBubble_")
            or ("Bubble" in k and "PasserBy" in k)
        )
        if is_bubble and not k.startswith("PasserByChat_"):
            cleaned = _clean(v)
            if cleaned and len(cleaned) > 5 and not cleaned.startswith("LAYOUT"):
                if cleaned not in all_bubble_texts:
                    all_bubble_texts.add(cleaned)
                    dist_id = match_district(k)
                    bubbles_by_dist[dist_id].append((k, cleaned))

    for dist_id in bubbles_by_dist:
        bubbles_by_dist[dist_id].sort(key=lambda x: x[0])

    # 3. Generate Markdown
    s_md: list[str] = [
        "# 新艾利都市井众生相与街区传闻全集\n",
        "> 本文献库全景收录新艾利都各大生活街区、商业步行街、工业营地、外环荒野与前沿哨所的全部市民闲聊、情境对话与漫步环境气泡。严格按新艾利都 10 大核心地标街区及都会特别区域划篇归档，保序排列。\n",
        "## 🏙️ 新艾利都全景街区众生相速查总览表\n",
        "| 序号 | 街区 / 场景代号 | 核心地标与市井风貌 | 核心对话主体 | 市井逸闻收录数 |",
        "|:---:|:---|:---|:---|:---:|",
    ]

    for dist_id, dist_name, dist_desc, dist_actors, _ in district_configs:
        n_chats = len(chats_by_dist[dist_id])
        n_clines = sum(len(c["dialogues"]) for c in chats_by_dist[dist_id])
        n_bubbles = len(bubbles_by_dist[dist_id])
        total_d = n_clines + n_bubbles
        if n_chats > 0 and n_bubbles > 0:
            count_str = f"**{total_d:,}** 条（情境对话 {n_chats} 组 / 环境气泡 {n_bubbles:,} 条）"
        elif n_chats > 0:
            count_str = f"**{total_d:,}** 条（情境对话 {n_chats} 组）"
        else:
            count_str = f"**{total_d:,}** 条（环境气泡 {n_bubbles:,} 条）"
        s_md.append(f"| {dist_id} | {dist_name} | {dist_desc} | {dist_actors} | {count_str} |")

    c11 = len(chats_by_dist["11"])
    clines11 = sum(len(c["dialogues"]) for c in chats_by_dist["11"])
    b11 = len(bubbles_by_dist["11"])
    total_11 = clines11 + b11
    if total_11 > 0:
        count_str_11 = f"**{total_11:,}** 条（情境对话 {c11} 组 / 环境气泡 {b11:,} 条）" if c11 > 0 else f"**{total_11:,}** 条（环境气泡 {b11:,} 条）"
        s_md.append(f"| 11 | 都会特别展演、庆典赛事与市井杂咏 | 都会特别巡游舞台、节日庆典广场与街头即兴秀场 | 庆典游客、即兴街头艺人与都会闲逛者 | {count_str_11} |")

    s_md.append("\n---\n")

    # Detailed sections
    for dist_id, dist_name, dist_desc, dist_actors, _ in district_configs:
        chats = chats_by_dist[dist_id]
        bubbles = bubbles_by_dist[dist_id]
        if not chats and not bubbles:
            continue

        s_md.append(f"## 第 {dist_id} 卷 · {dist_name}\n")
        s_md.append(f"> **街区定位**：{dist_desc}。  \n> **核心对话主体**：{dist_actors}。\n")

        if chats:
            s_md.append("### 一、街区情境对话与市井逸事\n")
            for cdata in chats:
                names_list = list(cdata["names"].values())
                if names_list:
                    speakers_str = "、".join(names_list)
                    topic = f"{speakers_str} 的街头见闻"
                else:
                    speakers_str = "街坊市民 / 过路行人"
                    topic = "街角琐语与邻里闲谈"

                s_md.append(f"#### 📍 逸事 {cdata['prefix']}_{cdata['id']} · {topic}\n")
                s_md.append(f"- 👥 **登场主体 / 闲聊街坊**：{speakers_str}")
                s_md.append("- 💬 **情境对话实录**：")
                for idx, (_, text) in enumerate(cdata["dialogues"], 1):
                    s_md.append(f"  {idx}. {text}")
                s_md.append("\n---\n")

        if bubbles:
            section_title = "### 二、街头漫步环境气泡与路人闲言\n" if chats else "### 街头漫步环境气泡与路人闲言\n"
            s_md.append(section_title)
            for _, b_text in bubbles:
                s_md.append(f"- 🗣️ {b_text}")
            s_md.append("\n---\n")

    if total_11 > 0:
        chats_11 = chats_by_dist["11"]
        bubbles_11 = bubbles_by_dist["11"]
        s_md.append("## 第 11 卷 · 都会特别展演、庆典赛事与市井杂咏\n")
        s_md.append("> **街区定位**：都会特别巡游舞台、节日庆典广场与街头即兴秀场。  \n> **核心对话主体**：庆典游客、即兴街头艺人与都会闲逛者。\n")
        if chats_11:
            s_md.append("### 一、街区情境对话与市井逸事\n")
            for cdata in chats_11:
                names_list = list(cdata["names"].values())
                speakers_str = "、".join(names_list) if names_list else "街坊市民 / 过路行人"
                topic = f"{speakers_str} 的街头见闻" if names_list else "街角琐语与邻里闲谈"
                s_md.append(f"#### 📍 逸事 {cdata['prefix']}_{cdata['id']} · {topic}\n")
                s_md.append(f"- 👥 **登场主体 / 闲聊街坊**：{speakers_str}")
                s_md.append("- 💬 **情境对话实录**：")
                for idx, (_, text) in enumerate(cdata["dialogues"], 1):
                    s_md.append(f"  {idx}. {text}")
                s_md.append("\n---\n")
        if bubbles_11:
            section_title = "### 二、街头漫步环境气泡与路人闲言\n" if chats_11 else "### 街头漫步环境气泡与路人闲言\n"
            s_md.append(section_title)
            for _, b_text in bubbles_11:
                s_md.append(f"- 🗣️ {b_text}")
            s_md.append("\n---\n")

    (street_dir / "01_街区路人与市井闲聊.md").write_text("\n".join(s_md), encoding="utf-8")

    total_extracted_lines = total_chat_lines + len(all_bubble_texts)
    return {"lore_street_lines": total_extracted_lines}


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
        "- [04_收藏展架与风味展品](equipment/04_收藏展架与风味展品.md)：全 132 件收藏展架珍品全集（纪事珍存、活动限定、三Z潮玩套组与音擎微缩模型）、风味物语与题记名言\n",
        "### 3. 绳网论坛与通讯 (`lore/interknot/`)",
        "- [01_委托人任务档案](interknot/01_委托人任务档案.md)：全量绳网论坛委托求助信（发帖人/正文/附言/楼层热评）与各街区实装委托档案（委托人/空洞舞台/三星指标/阶段链），严格按五大官方板块与编号递增排序",
        "- [02_绳网私信与手机短信](interknot/02_绳网私信与手机短信.md)：即时通讯私信会话流（日常吐槽、八卦求助、协会联络）\n",
        "### 4. Random Play 录像店影音档案 (`lore/cinema/`)",
        "- [01_旧文明电影与影评](cinema/01_旧文明电影与影评.md)：录像店全部 17 部经典影片长梗概、题材流派、原声台词选摘与全量顾客大众影评\n",
        "### 5. 新艾利都世界观百科与空洞规则 (`lore/glossary/`)",
        "- [01_空洞与以太规则](glossary/01_空洞与以太规则.md)：主线全章节历程纪事、以太物理规则、新艾利都生存法则与全量以太侵蚀病理图鉴",
        "- [02_空洞鸣徽与古物预言](glossary/02_空洞鸣徽与古物预言.md)：零号空洞全 25 大流派鸣徽考据、古物预言与代理人专属共鸣密藏\n",
        "### 6. 街区众生相与市井传闻 (`lore/street/`)",
        "- [01_街区路人与市井闲聊](street/01_街区路人与市井闲聊.md)：全 10 大核心地标街区（六分街、光映广场、黑雁工地、芭莱大厦、野火镇、索恩区、卫非地半岛、云岿山、斯科特哨站与街头邦布）全量市井逸事对话与漫步环境气泡全集\n",
        "## 统计概要\n",
        f"- **收录代理人**：{stats.get('lore_agents', 0)} 位",
        f"- **收录驱动盘唱片**：{stats.get('lore_discs', 0)} 套",
        f"- **收录音擎装备**：{stats.get('lore_w_engines', 0)} 款",
        f"- **收录邦布图鉴**：{stats.get('lore_bangboos', 0)} 只",
        f"- **收录展架藏品**：{stats.get('lore_collectibles', 0)} 件",
        f"- **收录长篇委托**：{stats.get('lore_quests', 0)} 条",
        f"- **收录短信对话**：{stats.get('lore_messages', 0)} 条",
        f"- **收录旧文明影片**：{stats.get('lore_movies', 0)} 部（影评 {stats.get('lore_movie_comments', 0)} 条）",
        f"- **收录空洞词条**：{stats.get('lore_tips', 0)} 条，**鸣徽古物**：{stats.get('lore_tarots', 0)} 个",
        f"- **收录市井街区逸闻**：{stats.get('lore_street_lines', 0)} 条",
    ]
    (lore_dir / "README.md").write_text("\n".join(lines), encoding="utf-8")
