from zzz_story.chapters import chapter_info
from zzz_story.content import classify_key, coverage_report, parse_suffix
from zzz_story.extras import extract_extras, render_extra_txt
from zzz_story.keys import parse_key
from zzz_story.speakers import SpeakerIndex, SpeakerInfo, SpeakerStats
from zzz_story.textmap import TextMap


def test_generic_grammar_maps_categories_to_domains():
    cases = {
        "Activity_GalGame_SayItWithFlowers_10161201_001": ("activity", "activity.SayItWithFlowers", "GalGame"),
        "Side_Chat_ZenkovS1_226023006_01": ("side", "side.ZenkovS1", "Chat"),
        "Companion_GalGame_ChapterSeed_16510010_001": ("companion", "companion.ChapterSeed", "GalGame"),
        "Activity_Chat_MegaRobot_Chapter2_37960001_01": ("activity", "activity.MegaRobot_Chapter2", "Chat"),
        "InLevel_Chat_AbyssS2_49080024_01": ("hollow", "hollow.AbyssS2", "Chat"),
        "Activity_OngoingLevel_Summer_12345678_01": ("activity", "activity.Summer", "OngoingLevel"),
    }
    for key, (domain, group, family) in cases.items():
        parsed = classify_key(key)
        assert (parsed.domain, parsed.group, parsed.family, parsed.kind) == (domain, group, family, "line"), key


def test_legacy_layouts_are_classified():
    assert classify_key("GalGame_Chapter050_010_001").domain == "main"
    assert classify_key("GalGame_ChapterMana_01_01").group == "companion.ChapterMana"
    assert classify_key("GalGame_GoldenWeek_01_01").group == "activity.GoldenWeek"
    side = classify_key("SideChat_Chapter03_0002F_01")
    assert (side.domain, side.scene, side.variant, side.line_no) == ("side", "0002", "F", 1)
    assert classify_key("SideChat_Chapter03_0002F_00").kind == "name"
    assert classify_key("CompanionChat_ChapterBurnice_0001_01").domain == "companion"
    event = classify_key("AutoEvent100000_26")
    assert (event.domain, event.scene, event.line_no) == ("hollow", "100000", 26)
    assert classify_key("TL_C30_ChatPlus_01_01").domain == "main"
    assert classify_key("TL_ActivityDetectiveV2_ChatPlus_01_01").domain == "activity"


def test_covered_and_test_tables_are_not_extras():
    assert classify_key("Main_GalGame_Chapter110_1100001_001").domain == "main"
    assert classify_key("PartnerTalk_GalGame_Anby_01_01").domain == "lore"
    assert classify_key("CS_00_00_010").domain == "supplement"
    assert classify_key("Other_Chat_TestEmoji_30890004_01") is None
    assert classify_key("Other_Chat_ChatBubbleEmotionTest_30890004_01") is None
    assert classify_key("Item_1001057_des") is None


def test_parse_suffix_options_and_names():
    assert parse_suffix("05_Option1_01") == ("line", 5, (1, 1), None, True)
    # Replies after a choice are not choices themselves.
    assert parse_suffix("05_Option1_02F_Main") == ("line", 5, (1, 2), "F", False)
    assert parse_suffix("Name_01")[0] == "name"
    assert parse_suffix("Desc")[0] == "other"


def test_mainline_parser_accepts_season_one_cutscenes():
    parsed = parse_key("GalGame_Chapter050_010_001")
    assert (parsed.family, parsed.chapter_token, parsed.scene, parsed.line_no) == ("GalGame", "Chapter050", "010", 1)
    option = parse_key("GalGame_Chapter03_01_03_Option1_02F_Main")
    assert (option.kind, option.line_no, option.sub_no, option.variant) == ("line", 3, 102, "F")
    assert parse_key("GalGame_Chapter050_130_Name_01").kind == "name"
    assert parse_key("GalGame_ChapterMana_01_01") is None
    # Alias tokens share their chapter's slot instead of shifting later orders.
    assert chapter_info("Chapter010").order == chapter_info("Chapter01").order
    assert chapter_info("Chapter030").label == chapter_info("Chapter03").label


def test_coverage_report_flags_unknown_dialogue_families():
    report = coverage_report(TextMap({
        "Activity_Chat_Fest_30160093_01": "你好",
        "Brandnew_Story_12345678_01": "未登记的新键族",
        "Item_1001057_des": "道具",
    }, "CHS"))
    assert report["domains"]["activity"]["keys"] == 1
    assert [row["family"] for row in report["unclassified"]] == ["Brandnew"]


def _index(entries: dict[str, SpeakerInfo]) -> SpeakerIndex:
    return SpeakerIndex(entries, SpeakerStats())


def test_extract_extras_groups_attributes_and_preserves_unproven_repetitions():
    text_map = TextMap({
        "Activity_GalGame_Fest_10161201_001": "欢迎光临。",
        "Activity_GalGame_Fest_10161201_002": "{M#哥哥}{F#妹妹}，来了啊。",
        "Activity_GalGame_Fest_10161201_002F": "妹妹，来了啊。",
        "Activity_GalGame_Fest_10161201_003": "欢迎光临。",
        "Activity_GalGame_Fest_10161201_004": "欢迎光临。",
        "Activity_GalGame_Fest_10161201_Name_01": "店员",
        "Side_Chat_Zenkov_226023006_01": "达米安？",
        "AutoEvent100000_29": "安比：「…绳匠，我建议不要靠近那伙人。」",
        "GalGame_ChapterMana_01_05_Option1_01": "原来是这个意思。",
        "Other_Chat_TestEmoji_30890004_01": "测试",
    }, "CHS")
    speakers = _index({"Activity_GalGame_Fest_10161201_001": SpeakerInfo("店员", None, 1.0, "voice", True)})
    records, discarded, stats = extract_extras(text_map, speaker_index=speakers)

    keys = [row["source_key"] for row in records]
    assert keys == [
        "Activity_GalGame_Fest_10161201_001",
        "Activity_GalGame_Fest_10161201_002",
        "Activity_GalGame_Fest_10161201_003",
        "Activity_GalGame_Fest_10161201_004",
        "Side_Chat_Zenkov_226023006_01",
        "GalGame_ChapterMana_01_05_Option1_01",
        "AutoEvent100000_29",
    ]
    first = records[0]
    assert (first["domain"], first["chapter"], first["speaker"], first["line_type"]) == (
        "activity", "activity.Fest", "店员", "dialogue")
    assert first["scene_speakers"] == ["店员"]
    assert records[1]["text"] == "哥哥，来了啊。"
    assert records[5]["line_type"] == "option"
    assert (records[6]["speaker"], records[6]["speaker_source"]) == ("安比", "inline")
    assert {row["reason"] for row in discarded} == {"explicit_gender_variant"}
    assert stats.by_domain == {"activity": 4, "side": 1, "companion": 1, "hollow": 1}
    orders = [row["chapter_order"] for row in records]
    assert orders == sorted(orders) and orders[0] >= 1_000_000
    assert [row["order"] for row in records] == list(range(1, 8))

    text = render_extra_txt(records)
    assert "## 活动剧情" in text and "店员：欢迎光临。" in text and "> 选项：原来是这个意思。" in text


def test_accuracy_first_keeps_gender_copies_and_duplicates():
    text_map = TextMap({
        "Side_Chat_Zenkov_226023006_01": "好。",
        "Side_Chat_Zenkov_226023006_01F": "好。",
        "Side_Chat_Zenkov_226023006_02": "好。",
    }, "CHS")
    records, discarded, _ = extract_extras(text_map, accuracy_first=True)
    assert len(records) == 3 and discarded == []


def test_extra_structured_routes_remove_nonadjacent_alternatives_with_full_evidence():
    prefix = "Activity_Chat_Fest_10161201_"
    tm = TextMap({prefix + "01": "女主路线", prefix + "02": "中间的公共台词", prefix + "03": "男主路线"}, "CHS")
    def info(side, peer):
        return SpeakerInfo("店员", None, 0.98, "perform", perform={
            "explicit_gender": True, "sides": [side], "paired_key": prefix + peer,
            "assets": ["fixture.asset"], "occurrences": [],
        })
    speakers = _index({prefix + "01": info("F", "03"), prefix + "03": info("M", "01")})
    records, discarded, stats = extract_extras(tm, speaker_index=speakers)
    assert [r["source_key"] for r in records] == [prefix + "02", prefix + "03"]
    assert discarded[0]["reason"] == "perform_gender_route"
    assert discarded[0]["paired_source_key"] == prefix + "03"
    assert discarded[0]["raw_text"] == "女主路线"
    assert discarded[0]["perform"]["assets"] == ["fixture.asset"]
    assert records[-1]["perform"]["sides"] == ["M"] and stats.structured_filtered == 1
    all_rows, removed, _ = extract_extras(tm, speaker_index=speakers, accuracy_first=True)
    assert len(all_rows) == 3 and not removed
    assert all(r["raw_text"] == tm.get(r["source_key"]) for r in all_rows)


def test_extra_gender_variant_survives_empty_base_and_renders_own_gender():
    key = "Side_Chat_Fest_226023006_01"
    tm = TextMap({key: "<color=red></color>", key + "F": "{M#哥哥}{F#姐姐}，你好"}, "CHS")
    rows, removed, _ = extract_extras(tm)
    assert len(rows) == 1 and not removed
    all_rows, removed, _ = extract_extras(tm, accuracy_first=True)
    assert all_rows[0]["text"] == "姐姐，你好" and not removed
    assert all_rows[0]["raw_text"] == tm.get(key + "F")


def test_extra_equal_options_unknown_speakers_and_repeated_dialogue_survive():
    prefix = "Activity_Chat_Fest_10161201_"
    tm = TextMap({prefix + "01": "好。", prefix + "02": "好。", prefix + "03": "好。"}, "CHS")
    index = SpeakerIndex({prefix + "02": SpeakerInfo("NPC", None, 1, "perform"),
                          prefix + "03": SpeakerInfo("NPC", None, 1, "perform")}, SpeakerStats(), {prefix + "01"})
    rows, removed, _ = extract_extras(tm, speaker_index=index)
    assert [r["line_type"] for r in rows] == ["option", "dialogue", "dialogue"]
    assert not removed


def test_extra_display_names_render_gender_and_preserve_hidden_identity():
    prefix = "Side_Chat_Fest_226023006_"
    tm = TextMap({prefix + "01": "甲", prefix + "01F": "乙", prefix + "02": "丙"}, "CHS")
    index = _index({prefix + "01": SpeakerInfo("{M#哲}{F#铃}", None, 1, "perform"),
                    prefix + "01F": SpeakerInfo("{M#哲}{F#铃}", None, 1, "perform"),
                    prefix + "02": SpeakerInfo("？？？", None, 1, "perform")})
    rows, _, _ = extract_extras(tm, speaker_index=index, accuracy_first=True)
    assert [r["speaker"] for r in rows] == ["哲", "铃", "？？？"]
