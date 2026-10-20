from zzz_story.chapters import (
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
    assert not chapter_info("Chapter240").known


def test_order_increases_across_seasons():
    assert sort_key("Chapter110") < sort_key("Chapter210") < sort_key("Chapter240")


def test_cs_prefixes_resolve_to_their_own_season():
    # Regression: CS_21 used to map to Chapter210 (season 3) instead of 110.
    assert cs_chapter("21")[0] == "Chapter110"
    assert cs_chapter("23")[0] == "Chapter130"
    assert cs_chapter("25")[0] == "Chapter150"
    assert cs_chapter("31")[0] == "Chapter210"


def test_cs_labels_come_from_the_chapter_table():
    for token in ("21", "22", "23", "24", "25", "26", "29"):
        chapter, label, order = cs_chapter(token)
        assert label == chapter_info(chapter).label
        assert order == chapter_info(chapter).order


def test_cs_specials_never_point_at_season_two_or_later():
    for token, (chapter, _label, _order) in CS_SPECIAL_CHAPTERS.items():
        assert not chapter.startswith("Chapter2"), token
        assert not chapter.startswith("Chapter3"), token
