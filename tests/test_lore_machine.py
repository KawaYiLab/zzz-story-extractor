import json

import pytest

from zzz_story.clean import clean_text
from zzz_story.lore import extract_lore
from zzz_story.message_config import MESSAGE_TABLES
from zzz_story.textmap import TextMap

# Includes the actual 3.3.0 same-name weapon conflict and SMS branch source.
VALUES = {
    "Avatar_Anby": "安比", "Partner_Birthday_1011": "02/20", "Partner_Stature_1011": "156",
    "Partner_ProfileDesc_1011": "<b>安比的档案</b>\n{M#哲的记录}{F#铃的记录}",
    "Chat_PartnerTalk_Anbi_2_4_7": "同文独立来源", "Chat_PartnerTalk_Anbi_2_5_7": "同文独立来源",
    "PartnerTalkBubble_Chapter1000_0001_01": "未关联代理人的气泡",
    "Item_Weapon_S_03_Name": "左轮转子", "Item_Weapon_S_03_Desc": "S-通用-03的临时描述",
    "Item_Weapon_S_Common_03_Name": "左轮转子",
    "Item_Weapon_S_Common_03_Desc": "仿造左轮外形制作的特型音擎，号称可装填六枚子弹形的浓缩以太电池。\n\n「这是独立的完整来源题记。」——使用者",
    "EquipmentSuit_31000_name": "啄木鸟电音", "EquipmentSuit_31000_story": "驱动盘的完整来源物语。",
    "EquipmentSuit_31000_2_des": "暴击率+8%", "Item_Equipment_31041_name": "啄木鸟电音[1]",
    "Item_Equipment_31041_des": "第一分轨的来源文本。",
    "Bangboo_Name_50001": "伊埃斯", "Bangboo_Desc_50001": "伊埃斯",
    "CollectionName_1": "纪念品", "CollectionDesc_1": "纪念品的完整来源说明。",
    "PostTitle_1001": "委托求助", "PostText_1001": "一位委托人的原始求助文本。",
    "QuestName_10010001": "真实任务名", "QuestDesc_10010001": "仅有背景而没有署名或行动目标的任务。",
    "Message_200312_17": "{M#一起出来玩吗}{F#想约你出来玩~}",
    "Message_Unusual": "不同配置上下文复用的来源",
    "Option01_100302": "马上来", "ItemTitle": "附件标题", "ItemBody": "{M#哲的附件}{F#铃的附件}",
    "SenderNote1_10001": "信托原文一", "SenderNote2_10001": "信托原文二", "SenderNote3_10001": "信托原文三",
    "Cinema_CinemaConfig_01_Tittle": "星徽骑士", "Cinema_CinemaConfig_01_Description": "电影原始梗概。",
    "Cinema_Comment_101_Name": "观众", "Cinema_Comment_101_Content": "星徽骑士的观众原始影评。",
    "Cinema_SpeakerName_610200001": "片中人物", "Cinema_DoubleDate_610200001": "影片的原始台词。",
    "MainStoryChapterNumber_1000": "序章", "MainStoryChapterName_1000": "第一幕原始标题",
    "LoadingTips_001": "空洞中的以太浓度影响所有进入其中的人类与机体。",
    "LoadingTips_002": "空洞中的以太浓度影响所有进入其中的人类与机体。",
    "Curse_1_name": "症状一", "Curse_1_story": "同文症状原始物语。", "Curse_2_name": "症状二", "Curse_2_story": "同文症状原始物语。",
    "TarotCard_10001_name": "[战救]古物", "TarotCard_10001_story": "古物的来源物语。",
    "PasserBy_Bubble_Street_01": "街头相同原句", "PasserBy_Bubble_Street_02": "街头相同原句",
}
AVATARS = [{"PFOAJKNPCHL": 1011, "HAKHHHCAENA": "Avatar_Anby", "FEKFJBFGANO": "anbi", "OOOHMBMDLBI": 1}]


def make_fixture(output, protagonist="M", values=None):
    config_dir = output / "config"
    config_dir.mkdir(parents=True)
    payloads = [
        [{"PFOAJKNPCHL": 100301, "EGBBBFIINLO": 200312, "LDHNMACDKLH": "Message_200312_17",
          "NMIFFJEFBJI": 0, "HPKJODNLJOA": 0, "HBPLELJNAEA": 1},
         {"PFOAJKNPCHL": 100302, "EGBBBFIINLO": 200312, "FNOKFPDDECI": "Option01_100302"},
         {"PFOAJKNPCHL": 100303, "EGBBBFIINLO": 1003, "LDHNMACDKLH": "Message_Unusual"},
         {"PFOAJKNPCHL": 100304, "EGBBBFIINLO": 1004, "LDHNMACDKLH": "Message_Unusual"}],
        [], [], [{"HJOEBMMFOMB": 1, "AJEGPOBMPCG": "ItemTitle", "DOPCCNPLNAF": "ItemBody"}],
    ]
    paths = {}
    for name, data in zip(MESSAGE_TABLES, payloads):
        path = config_dir / name.rsplit("/", 1)[1]
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        paths[name] = path
    stats = extract_lore(TextMap(values or VALUES, "CHS"), AVATARS, output,
                         data_paths=paths, protagonist=protagonist)
    root = output / "lore"
    records = [json.loads(line) for line in (root / "documents.jsonl").read_text(encoding="utf-8").splitlines()]
    return root, stats, records[0], records[1:]


@pytest.mark.parametrize("protagonist", ["M", "F"])
def test_machine_lore_preserves_every_domain_source_and_audit_reference(tmp_path, protagonist):
    root, stats, header, docs = make_fixture(tmp_path, protagonist)
    assert header["protagonist"] == protagonist
    assert set(header["covered_source_files"]) == {p.relative_to(root).as_posix() for p in root.rglob("*.md")}
    assert {d["category"] for d in docs} == {"agents", "equipment", "interknot", "cinema", "glossary", "street"}
    assert all(d["items"] for d in docs)
    sources = {item["source_key"]: item for d in docs for item in d["items"] if item["kind"] == "source"}
    expected = {"Partner_ProfileDesc_1011", "Item_Weapon_S_03_Desc", "Item_Weapon_S_Common_03_Desc",
                "EquipmentSuit_31000_story", "Item_Equipment_31041_des", "Bangboo_Desc_50001",
                "CollectionDesc_1", "PostText_1001", "QuestDesc_10010001", "Cinema_Comment_101_Content",
                "Cinema_DoubleDate_610200001", "LoadingTips_001", "LoadingTips_002", "Curse_1_story",
                "Curse_2_story", "TarotCard_10001_story", "SenderNote1_10001", "SenderNote2_10001", "SenderNote3_10001"}
    assert expected <= sources.keys()
    for key, item in sources.items():
        assert (item["raw_text"] if item["raw_text"] is not None else item["text"]) == VALUES[key]
        ct = clean_text(VALUES[key], protagonist)
        assert item["text"] == ct.text and item["text_variants"] == ct.variants
        assert item["selected_variant"] == (protagonist if ct.variants else None)
    referenced = set()
    for doc in docs:
        for item in doc["items"]:
            if item["kind"] != "audit":
                continue
            rows = [json.loads(line) for line in (root / item["record_source"]).read_text(encoding="utf-8").splitlines()]
            if item["record_source"].endswith("message-item-audit.jsonl"):
                rows = [ref for row in rows for ref in row["references"]]
            row = next(row for row in rows if row["source_key"] == item["source_key"])
            assert row.get("retained") is not False and row["text"]
            assert row["raw_text"] == VALUES[item["source_key"]]
            referenced.add(item["source_key"])
    assert {"Chat_PartnerTalk_Anbi_2_4_7", "Chat_PartnerTalk_Anbi_2_5_7", "PartnerTalkBubble_Chapter1000_0001_01",
            "Message_200312_17", "Message_Unusual", "Option01_100302", "ItemBody",
            "PasserBy_Bubble_Street_01", "PasserBy_Bubble_Street_02"} <= referenced
    assert stats["lore_machine_documents"] == len(docs)


def test_machine_lore_does_not_turn_display_defaults_or_summaries_into_source_text(tmp_path):
    root, _, _, docs = make_fixture(tmp_path)
    body = "\n".join(i["text"] for d in docs for i in d["items"] if i["kind"] == "source")
    assert "烈火足迹" not in body
    assert "新艾利都市民 / 绳网委托人" not in body
    assert "探索空洞并达成委托目标" not in body
    assert "深度以太共鸣传感与神经同步系统" not in body
    assert "男主路线：" not in body
    weapon_docs = [d for d in docs if d["doc_id"].startswith("lore:equipment:weapon:")]
    assert len(weapon_docs) == 2 and {d["title"] for d in weapon_docs} == {"左轮转子"}
    assert "完整来源题记" in body
    rendered = (root / "equipment/02_音擎档案与题记.md").read_text(encoding="utf-8")
    assert "S-通用-03的临时描述" in rendered and "仿造左轮外形制作的特型音擎" in rendered
    movie = next(d for d in docs if d["doc_id"] == "lore:cinema:movie:1")
    assert {i["source_key"] for i in movie["items"]} >= {"Cinema_CinemaConfig_01_Tittle", "Cinema_Comment_101_Content"}
    agent = next(d for d in docs if d["doc_id"] == "lore:agents:agent:1011")
    height = next(f for f in agent["profile"]["facts"] if f["field"] == "height")
    assert height["value"] == "156"  # Generated cm display is not substituted into the source fact.
    assert agent["items"][height["item_index"]]["source_key"] == "Partner_Stature_1011"


def test_source_document_ids_and_retained_occurrences_survive_input_reordering(tmp_path):
    _, _, _, first = make_fixture(tmp_path / "first")
    _, _, _, second = make_fixture(tmp_path / "second", values=dict(reversed(list(VALUES.items()))))
    def normalize(docs):
        return {d["doc_id"]: {(i["kind"], i["source_key"]) for i in d["items"]} for d in docs}
    assert normalize(first) == normalize(second)
    occurrences = [d for d in first if any(i["source_key"] == "Message_Unusual" for i in d["items"])]
    assert {d["entity_id"] for d in occurrences} == {"1003", "1004"}


def test_filtered_empty_post_cannot_capture_later_trust_or_contact_sources(tmp_path):
    values = {"PostTitle_99": "", "SenderNote1_1234": "秘密信托原文",
              "Message_1234_01": "短信原文", "Message_1234_name": "联系人原文"}
    _, _, _, docs = make_fixture(tmp_path, values=values)
    assert all(d["doc_id"] != "lore:interknot:post:99" for d in docs)
    holders = [d for d in docs if any(i["source_key"] == "SenderNote1_1234" for i in d["items"])]
    assert [d["doc_id"] for d in holders] == ["lore:interknot:trust:1234"]


def test_unassigned_interactions_with_equal_event_numbers_keep_their_full_source_context(tmp_path):
    values = {"Avatar_Anby": "安比", "PartnerTalk_Chat_UnknownA_1001_01": "甲事件原文",
              "PartnerTalk_Chat_UnknownB_1001_01": "乙事件原文"}
    _, _, _, docs = make_fixture(tmp_path, values=values)
    interactions = [d for d in docs if d["doc_id"].startswith("lore:agents:interaction:")]
    assert len(interactions) == 2
    assert len({i["scene_id"] for d in interactions for i in d["items"]}) == 2
    assert all(len(d["items"]) == 1 for d in interactions)


@pytest.mark.parametrize("probe_description", [None, "<b></b>"])
def test_disc_slot_probes_cannot_capture_names_of_unadopted_candidates(tmp_path, probe_description):
    values = {"EquipmentSuit_31000_name": "唱片甲", "EquipmentSuit_31000_story": "唱片甲原文故事",
              "Item_Equipment_31041_name": "唱片乙[1]", "Item_Equipment_99941_name": "唱片甲[1]",
              "Item_Equipment_99941_des": "唱片甲第一轨真实题记"}
    if probe_description is not None:
        values["Item_Equipment_31041_des"] = probe_description
    _, _, _, docs = make_fixture(tmp_path, values=values)
    disc = next(d for d in docs if d["doc_id"] == "lore:equipment:disc:31000")
    keys = {i["source_key"] for i in disc["items"]}
    assert "Item_Equipment_31041_name" not in keys
    assert {"Item_Equipment_99941_name", "Item_Equipment_99941_des"} <= keys


def test_mindscape_cinema_sources_are_not_exported_as_trust_dialogue(tmp_path):
    values = {**VALUES, "Anbi_Talent_01_Title": "快充模式",
              "Anbi_Talent_01_Desc_02": "快充一分钟，战斗半小时！",
              "Anbi_Talent_01_Desc_01": "能量获得效率提升12%"}
    _, _, _, docs = make_fixture(tmp_path, values=values)
    agent = next(d for d in docs if d["doc_id"] == "lore:agents:agent:1011")
    mindscape = [i for i in agent["items"] if "_Talent_" in i["source_key"]]
    assert len(mindscape) == 3
    assert {i["section_kind"] for i in mindscape} == {"other"}
