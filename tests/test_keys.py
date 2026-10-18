from zzz_story.keys import parse_key


def test_galgame_line():
    parsed = parse_key("Main_GalGame_Chapter110_11100060_009_01")
    assert parsed is not None
    assert parsed.family == "GalGame"
    assert parsed.chapter_token == "Chapter110"
    assert parsed.scene == "11100060"
    assert parsed.kind == "line"
    assert parsed.line_no == 9
    assert parsed.sub_no == 1


def test_name_key():
    parsed = parse_key("Main_GalGame_Chapter110_11100060_Name_001")
    assert parsed is not None
    assert parsed.kind == "name"


def test_gender_suffix():
    parsed = parse_key("Main_GalGame_Chapter00_10000002_001F")
    assert parsed is not None
    assert parsed.line_no == 1
    assert parsed.variant == "F"


def test_mainchat():
    parsed = parse_key("MainChat_Chapter05_0069_25")
    assert parsed is not None
    assert parsed.family == "MainChat"
    assert parsed.scene == "0069"
    assert parsed.line_no == 25


def test_mainchat_inlevel():
    parsed = parse_key("MainChat_Chapter00_Inlevel_0002_Name01")
    assert parsed is not None
    assert parsed.scene == "Inlevel_0002"
    assert parsed.kind == "name"


def test_numeric_mainchat():
    parsed = parse_key("MainChat_2_0001_00")
    assert parsed is not None
    assert parsed.chapter_token == "2"
    assert parsed.scene == "0001"
    assert parsed.line_no == 0


def test_store_npc_ignored():
    assert parse_key("MainChat_StoreNPC_HIA_01_01") is None
