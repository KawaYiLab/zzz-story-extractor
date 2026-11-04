from zzz_story.speakers import (
    SpeakerInfo,
    SpeakerStats,
    _recount_speaker_gaps,
    alias_from_source,
    canonical_text_id,
    normalize_name,
    resolve_alias,
)


def test_normalize_name_strips_separators_and_case():
    assert normalize_name("Student-Wise") == "studentwise"
    assert normalize_name("Sutando_Belle") == "sutandobelle"
    assert normalize_name("") == ""


def test_canonical_text_id_normalizes_chapter_numbers():
    assert canonical_text_id("Main_GalGame_Chapter01_10000002_001") == "galgame_chapter1_10000002_001"
    assert canonical_text_id("MainChat_Chapter001_Inlevel_0002") == "mainchat_chapter1_inlevel_0002"


def test_alias_from_source_reads_voice_paths_and_galgame_filenames():
    assert alias_from_source("VO_SutandoWise/Galgame_Chapter110_001") == "SutandoWise"
    assert alias_from_source("/VO_StudentWise/Voice_001") == "StudentWise"
    assert alias_from_source("Galgame_Chapter110_Hutao_001") == "Hutao"
    # Numeric middle segments are scene ids, not character aliases.
    assert alias_from_source("Galgame_Chapter110_11100060_001") is None


def test_resolve_alias_exact_prefix_and_suffix():
    aliases = {"wise": "哲", "nekomata": "猫又"}
    assert resolve_alias("Wise", aliases) == "哲"
    assert resolve_alias("StudentWise", aliases) == "哲"  # known prefix
    assert resolve_alias("WiseBlack", aliases) == "哲"  # known suffix


def test_resolve_alias_returns_none_when_ambiguous():
    aliases = {"sutandobelle": "佩洛伊斯铃", "sutandowise": "佩洛伊斯哲"}
    # Both candidates match, so guessing would be worse than staying silent.
    assert resolve_alias("Sutando", aliases) is None


def test_recount_speaker_gaps_ignores_resolved_and_unvoiced_lines():
    speakers = {
        "a": SpeakerInfo("哲", None, 1.0, "voice", True),
        "b": SpeakerInfo(None, "npcA", 0.0, "voice", True),
        "c": SpeakerInfo(None, None, 0.0, "voice", True),
        "d": SpeakerInfo(None, "npcB", 0.0, "voice", False),
    }
    stats = SpeakerStats(unresolved_aliases=99, ambiguous=99)
    _recount_speaker_gaps(speakers, stats)
    assert stats.unresolved_aliases == 1  # only b: voiced + alias, no speaker
    assert stats.ambiguous == 1  # only c: voiced, no alias


def test_exact_resource_key_wins_over_normalized_alias():
    from zzz_story.speakers import _index_from_speakers
    key = "Main_Chat_Chapter01_1_01"
    exact = SpeakerInfo("？？？", None, 0.95, "avatar")
    alias = SpeakerInfo("秘密身份", None, 1.0, "voice", True)
    for sources in ({key: exact, key[5:]: alias}, {key[5:]: alias, key: exact}):
        assert _index_from_speakers(sources, {key}, SpeakerStats()).lookup(key).speaker == "？？？"


def test_equal_evidence_conflict_is_not_resolved_alphabetically():
    from zzz_story.speakers import _index_from_speakers
    key = "Main_Chat_Chapter01_1_01"
    sources = {"Chat_Chapter1_1_01": SpeakerInfo("甲", None, 1.0, "voice", True),
               "Chat_Chapter001_1_01": SpeakerInfo("乙", None, 1.0, "voice", True)}
    info = _index_from_speakers(sources, {key}, SpeakerStats()).lookup(key)
    assert info.speaker is None and info.source == "conflict" and info.has_voice


def test_extra_chat_and_bubble_assets_are_included():
    from zzz_story.speakers import _exported_asset
    assert _exported_asset("Data/ScriptConfig/Perform/Data/Chat/Fest/Activity_Chat_Fest_700033.asset")
    assert _exported_asset("Data/ScriptConfig/Perform/Data/Bubble/Side/Side_Bubble_Zenkov_123456.asset")
    assert not _exported_asset("Data/ScriptConfig/Perform/Data/Chat/Test/Other_Chat_TestEmoji_30890004.asset")
