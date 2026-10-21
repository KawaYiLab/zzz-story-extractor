from zzz_story.chapters import (
    CHAPTER_ORDER_SCALE,
    ORDERED_TOKENS,
    chapter_info,
    label_for,
    parse_season_chapter,
    season_chapter_token,
    sort_key,
)
from zzz_story.extract import CS_SPECIAL_CHAPTERS, cs_chapter


def test_season_chapter_token_matches_3_2_0_numbering():
    assert season_chapter_token(2, 1) == "110"
    assert season_chapter_token(2, 5) == "150"
    assert season_chapter_token(3, 1) == "210"
    assert season_chapter_token(3, 4) == "240"


def test_parse_season_chapter_only_accepts_compact_form():
    assert parse_season_chapter("21") == (2, 1)
    assert parse_season_chapter("34") == (3, 4)
    # Season 1 supplement keys are irregular and stay in the explicit table.
    assert parse_season_chapter("05.2") is None
    assert parse_season_chapter("028") is None
    assert parse_season_chapter("") is None


def test_known_chapters_keep_their_season_labels():
    assert label_for("Chapter110") == "第二季 第一章 云霞同归处"
    assert label_for("Chapter210") == "第三季 第一章 某个梦游者的自白"
    assert chapter_info("Chapter110").known
    assert label_for("Chapter240") == "第三季 第四章 重返天空的旅程"
    assert chapter_info("Chapter240").known
    assert not chapter_info("Chapter250").known


def test_order_increases_across_seasons():
    assert sort_key("Chapter110") < sort_key("Chapter210") < sort_key("Chapter240")


def test_cs_prefixes_resolve_to_their_own_season():
    # Regression: CS_21 used to map to Chapter210 (season 3) instead of 110.
    assert cs_chapter("21")[0] == "Chapter110"
    assert cs_chapter("23")[0] == "Chapter130"
    assert cs_chapter("25")[0] == "Chapter150"
    assert cs_chapter("31")[0] == "Chapter210"
    assert cs_chapter("34")[0] == "Chapter240"


def test_cs_labels_come_from_the_chapter_table():
    for token in ("21", "22", "23", "24", "25", "26", "29"):
        chapter, label, order = cs_chapter(token)
        assert label == chapter_info(chapter).label
        assert order == chapter_info(chapter).order


def test_cs_specials_never_point_at_season_two_or_later():
    for token, (chapter, _label, _order) in CS_SPECIAL_CHAPTERS.items():
        assert not chapter.startswith("Chapter2"), token
        assert not chapter.startswith("Chapter3"), token


def test_chapter_orders_are_integers_and_leave_room_for_interludes():
    for token in ORDERED_TOKENS + ["240", "Other"]:
        assert type(chapter_info(f"Chapter{token}").order) is int
    for token in list(CS_SPECIAL_CHAPTERS) + ["21", "31", "Unknown"]:
        assert type(cs_chapter(token)[2]) is int
    for before, interlude, after in (
        ("01", "01.5", "02"),
        ("02.5", "028", "03"),
        ("03", "03.5", "04"),
        ("04", "04.5", "05"),
        ("05", "05.2", "05.5"),
        ("05.2", "05.5", "05.8"),
    ):
        assert cs_chapter(before)[2] < cs_chapter(interlude)[2] < cs_chapter(after)[2]
    for token in ("00", "01", "02", "03", "04", "05"):
        chapter, _label, order = cs_chapter(token)
        assert order == chapter_info(chapter).order
    assert cs_chapter("05.8")[2] < chapter_info("Chapter06").order
    assert cs_chapter("Unknown")[2] < 999 * CHAPTER_ORDER_SCALE
