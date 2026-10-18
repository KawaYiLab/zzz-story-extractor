import json
from pathlib import Path

from zzz_story.lore import extract_lore
from zzz_story.textmap import TextMap


def test_extract_lore(tmp_path):
    text_map_data = {
        # Agent
        "Avatar_Female_Size02_Anby": "安比",
        "Avatar_Female_Size02_Anby_FullName": "安比·德玛拉",
        "PartnerCamp_Name_01": "狡兔屋",
        "Partner_Birthday_1011": "02/20",
        "Partner_Race_1011": "人族",
        "Partner_Stature_1011": "162cm",
        "Item_Avatar_1011_Des": "特写照片...",
        "Partner_ProfileDesc_1011": "档案记录01...",
        "Partner_ProfileDesc_1011_1": "档案记录02...",
        "Partner_Impression_1011": "伙伴评价...",
        "Item_Weapon_A_1011_Name": "德玛拉电池Ⅱ型",
        "Item_Weapon_A_1011_Desc": "音擎构造详情...",
        "Item_Weapon_A_1011_SpecialDesc": "以电为名的剑...",
        "Item_Weapon_A_1011_Buff_Name": "电能爆发",
        "Item_Weapon_A_1011_Buff_Des": "攻击力提升10%",
        # Drive Disc
        "EquipmentSuit_31000_name": "啄木鸟电音",
        "EquipmentSuit_31000_story": "火到出圈的驱动盘故事...",
        "EquipmentSuit_31000_2_des": "暴击率+8%",
        "EquipmentSuit_31000_4_des": "攻击力提升9%",
        "EquipmentSuit_31000_Tag": "暴击率提升",
        # Bangboo
        "Bangboo_Name_54004": "巴特勒",
        "Bangboo_Name_en_54004": "Butler",
        "Bangboo_Desc_54004": "完美的管家，完美的您。",
        "Bangboo_ActiveSkill_Title_54004": "茶歇时间",
        "Bangboo_ActiveSkill_Des_54004": "制作爱心茶点...",
        "Bangboo_QTE_Title_54004": "午后甜点",
        "Bangboo_QTE_Des_54004": "使用平底锅远程攻击...",
        "Tips_5400401": "嗯嗯呢~（请用下午茶~）",
        # Inter-Knot Quest
        "QuestName_10010001": "兔与绳",
        "QuestDesc_10010001": "狡兔屋的妮可冲进店里，说有紧急委托要找法厄同...",
        "QuestTarget_10010001": "与妮可交谈",
        # Message
        "Message_100700701": "绳匠，今天有空吗？",
        "Message_100700702": "野火镇的集市要开始了！",
        # Cinema
        "Cinema_CinemaConfig_01_Description": "流星雨过后的怪人与骑士特摄剧...",
        "Cinema_CinemaConfig_01_Tittle": "星徽骑士：另一位骑士",
        "Cinema_Comment_101_Content": "满分神作！",
        # Glossary
        "Tips_100001": "空洞内出现了紧急委托，请立刻前往以太探测系统！",
        "ChapterTipsMain_1000": "序章 生意×诡异×道义",
        "TarotCard_1001_name": "[出战]鲨牙布",
        "TarotCard_1001_story": "深海捕食者的鸣徽记忆...",
        # Street
        "PasserBy_BubbleStory_1001_01": "今天六分街的天气真好啊~",
    }

    tm = TextMap(text_map_data, "CHS")
    avatar_base = {
        "IAEFFFFLKNB": [
            {
                "PFOAJKNPCHL": 1011,
                "HAKHHHCAENA": "Avatar_Female_Size02_Anby",
                "JGHFBBCBBBA": "Avatar_Female_Size02_Anby_FullName",
                "FEKFJBFGANO": "anbi",
                "OOOHMBMDLBI": 1,
            }
        ]
    }

    out_dir = tmp_path / "out"
    stats = extract_lore(tm, avatar_base, out_dir)

    assert stats["lore_agents"] == 1
    assert stats["lore_discs"] == 1
    assert stats["lore_w_engines"] == 1
    assert stats["lore_bangboos"] == 1
    assert stats["lore_quests"] == 1
    assert stats["lore_messages"] == 2
    assert stats["lore_movies"] == 1
    assert stats["lore_movie_comments"] == 1
    assert stats["lore_tips"] == 1
    assert stats["lore_tarots"] == 1
    assert stats["lore_street_lines"] == 1

    # Verify generated markdown files exist
    assert (out_dir / "lore" / "README.md").exists()
    assert (out_dir / "lore" / "agents" / "00_代理人全景总览.md").exists()
    assert (out_dir / "lore" / "agents" / "01_狡兔屋.md").exists()
    assert (out_dir / "lore" / "equipment" / "01_驱动盘唱片物语.md").exists()
    assert (out_dir / "lore" / "equipment" / "02_音擎档案与题记.md").exists()
    assert (out_dir / "lore" / "equipment" / "03_邦布机体图鉴.md").exists()
    assert (out_dir / "lore" / "interknot" / "01_委托人任务档案.md").exists()
    assert (out_dir / "lore" / "interknot" / "02_绳网私信与手机短信.md").exists()
    assert (out_dir / "lore" / "cinema" / "01_旧文明电影与影评.md").exists()
    assert (out_dir / "lore" / "glossary" / "01_空洞与以太规则.md").exists()
    assert (out_dir / "lore" / "street" / "01_街区路人与市井闲聊.md").exists()

    agent_doc = (out_dir / "lore" / "agents" / "01_狡兔屋.md").read_text(encoding="utf-8")
    assert "安比（安比·德玛拉）" in agent_doc
    assert "狡兔屋" in agent_doc
    assert "档案记录01" in agent_doc
    assert "德玛拉电池Ⅱ型" in agent_doc
