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
        "Partner_OutlookDesc_1011": "空洞调查员-安比，具有良好的以太适性。",
        "Partner_ProfileDesc_1011": "档案记录01...",
        "Partner_ProfileDesc_1011_1": "档案记录02...",
        "Partner_Impression_m_1011": "说实话，我最好奇的是安比的歌单。",
        "Partner_Impression_f_1011": "安比经常来录像店借影片呢。",
        "Anbi_Talent_01_Title": "快充模式",
        "Anbi_Talent_01_Desc_02": "快充一分钟，战斗半小时！",
        "Anbi_Talent_01_Desc_01": "能量获得效率提升12%",
        "Chat_PartnerTalk_Anbi_0_1": "汉堡是最好吃的食物。",
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
        "EquipmentSuit_31000_SuitFilterOption": "啄木鸟电音-[暴击]",
        "Item_Equipment_31041_name": "啄木鸟电音[1]",
        "Item_Equipment_31041_des": "记录着《啄木鸟电音》第一部分曲目的驱动盘...",
        # Bangboo
        "Bangboo_Name_54004": "巴特勒",
        "Bangboo_Name_en_54004": "Butler",
        "Bangboo_Desc_54004": "完美的管家，完美的您。",
        "Bangboo_ActiveSkill_Title_54004": "茶歇时间",
        "Bangboo_ActiveSkill_Des_54004": "制作爱心茶点...",
        "Bangboo_QTE_Title_54004": "午后甜点",
        "Bangboo_QTE_Des_54004": "使用平底锅远程攻击...",
        "Bangboo_TalentSkill_Title_54004": "贴身管家",
        "Bangboo_TalentSkill_Des_54004_01": "队伍中存在2名或以上[维多利亚家政]阵营的角色时触发...",
        "Bangboo_TalentSkill_Des_54004_05": "队伍中存在2名或以上[维多利亚家政]阵营的角色时触发：完全升级...",
        "TarotCard_1054004_name": "[助战]巴特勒",
        "TarotCard_1054004_des": "全队能量自动回复提升7.5%...",
        "Tips_5400401": "嗯嗯呢~（请用下午茶~）",
        # Collectibles
        "CollectionName_3700109": "格莱特的恋人",
        "CollectionDesc_3700109": "根据格莱特保存的「真白君」影像资料制作。它不只是一座建筑质量堪忧的烂尾楼，还是掘进机的爱人——尽管它本人…本楼，对此缄默不言。",
        "CollectionName_3700119": "模型：德玛拉电池Ⅱ型",
        "CollectionDesc_3700119": "原型是一款重视储能效率的定制款音擎核心。<color=#575757>「武器就应该是危险的。」——安比，小心翼翼保养时的回答</color>",
        # Inter-Knot Quest & Forum Post
        "QuestName_10010001": "兔与绳",
        "QuestDesc_10010001": "狡兔屋的妮可冲进店里，说有紧急委托要找法厄同...",
        "QuestTarget_10010001": "与妮可交谈",
        "HollowClient_10010001": "妮可·德玛拉",
        "HollowAchivementName_1001000150": "这就是绳匠",
        "HollowAchivementDesc_1001000150": "首次揭露空洞新区域",
        "PostTitle_1001": "[灌水]以太适性自测结果是这个分数...",
        "Poster_1001": "lalala",
        "PostText_1001": "本人学生，高中还没毕业...",
        "PostScript_1001": "在线等挺急的",
        "Comment1_1001": "你该不是故意在秀吧...",
        "Commentator1_1001": "空洞旅人",
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
    assert stats["lore_collectibles"] == 2
    assert stats["lore_quests"] == 2
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
    assert (out_dir / "lore" / "equipment" / "04_收藏展架与风味展品.md").exists()
    assert (out_dir / "lore" / "interknot" / "01_委托人任务档案.md").exists()
    assert (out_dir / "lore" / "interknot" / "02_绳网私信与手机短信.md").exists()
    assert (out_dir / "lore" / "cinema" / "01_旧文明电影与影评.md").exists()
    assert (out_dir / "lore" / "glossary" / "01_空洞与以太规则.md").exists()
    assert (out_dir / "lore" / "street" / "01_街区路人与市井闲聊.md").exists()

    agent_doc = (out_dir / "lore" / "agents" / "01_狡兔屋.md").read_text(encoding="utf-8")
    assert "安比（安比·德玛拉）" in agent_doc
    assert "狡兔屋" in agent_doc
    assert "良好" in agent_doc
    assert "空洞调查协会（HIA）执照与以太适性档案" in agent_doc
    assert "档案记录 01" in agent_doc
    assert "兄长·哲的观察随笔" in agent_doc
    assert "胞妹·铃的私密手记" in agent_doc
    assert "快充模式" in agent_doc
    assert "德玛拉电池Ⅱ型" in agent_doc
    assert "汉堡是最好吃的食物。" in agent_doc

    disc_doc = (out_dir / "lore" / "equipment" / "01_驱动盘唱片物语.md").read_text(encoding="utf-8")
    assert "《啄木鸟电音》" in disc_doc
    assert "全 30 套驱动盘战术流派与唱片速查总览" in disc_doc
    assert "六重奏分轨曲目物语" in disc_doc
    assert "第 1 部分曲目" in disc_doc
    assert "记录着《啄木鸟电音》第一部分曲目的驱动盘..." in disc_doc

    engine_doc = (out_dir / "lore" / "equipment" / "02_音擎档案与题记.md").read_text(encoding="utf-8")
    assert "《德玛拉电池Ⅱ型》" in engine_doc
    assert "全 100 款音擎品质与战术回路速查总览" in engine_doc
    assert "以电为名的剑..." in engine_doc
    assert "电能爆发" in engine_doc

    bangboo_doc = (out_dir / "lore" / "equipment" / "03_邦布机体图鉴.md").read_text(encoding="utf-8")
    assert "邦布全景机体速查总览表" in bangboo_doc
    assert "巴特勒" in bangboo_doc
    assert "Butler" in bangboo_doc
    assert "茶歇时间" in bangboo_doc
    assert "午后甜点" in bangboo_doc
    assert "贴身管家" in bangboo_doc
    assert "维多利亚家政" in bangboo_doc
    assert "助战鸣徽" in bangboo_doc
    assert "嗯嗯呢~（请用下午茶~）" in bangboo_doc

    col_doc = (out_dir / "lore" / "equipment" / "04_收藏展架与风味展品.md").read_text(encoding="utf-8")
    assert "展架藏品风味速查总览表" in col_doc
    assert "格莱特的恋人" in col_doc
    assert "模型：德玛拉电池Ⅱ型" in col_doc
    assert "专属题记 / 纪念名言" in col_doc
    assert "「武器就应该是危险的。」——安比，小心翼翼保养时的回答" in col_doc

    knot_doc = (out_dir / "lore" / "interknot" / "01_委托人任务档案.md").read_text(encoding="utf-8")
    assert "绳网委托与求助全景速查总览表" in knot_doc
    assert "第一辑：绳网论坛求助与委托原帖" in knot_doc
    assert "以太适性自测结果" in knot_doc
    assert "lalala" in knot_doc
    assert "空洞旅人" in knot_doc
    assert "第二辑：空洞深潜与核心搜救委托" in knot_doc
    assert "兔与绳" in knot_doc
    assert "妮可·德玛拉" in knot_doc
    assert "这就是绳匠" in knot_doc



