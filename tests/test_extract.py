import json

import pytest

from zzz_story.extract import (
    DEFAULT_COSTUME_PREFIXES,
    _assign_line_ids,
    _assign_supplement_ids,
    _cache_root,
    _galgame_scene_positions,
    _mark_unattributed_scenes,
    _normalize_speaker,
    _protagonist_side,
    _scene_metadata,
    _speaker_identity,
    costume_prefixes,
    extract,
)
from zzz_story.fetch import REQUIRED_FILES


def _write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_extract_fixture(tmp_path, monkeypatch):
    data = tmp_path / "data"
    text_map = {
        "Main_GalGame_Chapter00_10000002_001": "你好",
        "Main_GalGame_Chapter00_10000002_002": "再见",
        "Main_GalGame_Chapter00_10000002_002F": "再见",
        "Main_GalGame_Chapter00_9000001_001": "后来场景台词",
        "QuestName_9901": "测试任务",
        "QuestName_9902": "任务二",
        "Main_GalGame_Chapter00_10000002_Option1_03": "选项分支一",
        "Main_GalGame_Chapter00_10000002_Option2_04": "选项分支二",
        "Main_GalGame_Chapter00_10000002_Name_001": "苏茜",
        "Main_GalGame_Chapter00_10000002_Name_001F": "铃",
        "MainChat_Chapter01_001_01": "聊天内容",
        "Comic_abcdef": "漫画内容",
        "Title_10000002": "「测试场景」",
        "Intro_10000002": "{F#铃}{M#哲}和苏茜在测试场景见面。",
        "Intro_9000001": "gal跳过内容",
        "CS_00_01_010": "过场台词一",
        "CS_00_01_020": "过场台词一",
        "CS_00_01_030": "哥哥，可以开始吗？",
        "CS_00_01_040": "妹妹，可以开始吗？",
        "CS_21_01_010": "第二季第一章过场",
    }
    _write(data / "TextMap/TextMapTemplateTb.json", text_map)
    _write(data / "TextMap/TextMapOverwriteTemplateTb.json", {})
    _write(data / "TextMap/TextMap_ENTemplateTb.json", {})
    _write(data / "TextMap/TextMap_ENOverwriteTemplateTb.json", {})
    # Archive order deliberately contradicts numeric order: 10000002 first.
    _write(data / "FileCfg/ArchivePerformTemplateTb.json", {"IAEFFFFLKNB": [
        {"PFOAJKNPCHL": 990101, "JFHCIJHJLOH": 10000002},
        {"PFOAJKNPCHL": 990201, "JFHCIJHJLOH": 9000001},
    ]})
    # 梗概只按 Perform 资源文件名里的剧情族和场景号配；策划的占位说明不算梗概。
    _write(data / "FileCfg/PerformTemplateTb.json", {"IAEFFFFLKNB": [
        {"PFOAJKNPCHL": 10000002, "BCGIEODKGDG": "Intro_10000002",
         "BCKKFAEFDPP": "Data/ScriptConfig/Perform/Data/GalGame/Chapter00/Main_GalGame_Chapter00_10000002.asset"},
        {"PFOAJKNPCHL": 9000001, "BCGIEODKGDG": "Intro_9000001",
         "BCKKFAEFDPP": "Data/ScriptConfig/Perform/Data/GalGame/Chapter00/Main_GalGame_Chapter00_9000001.asset"},
    ]})
    _write(data / "FileCfg/QuestConfigTemplateTb.json", {"IAEFFFFLKNB": [
        {"ODCODEPMLGG": 9901, "ANCOBODLNIK": "QuestName_9901"},
        {"ODCODEPMLGG": 9902, "ANCOBODLNIK": "QuestName_9902"},
    ]})
    for rel in REQUIRED_FILES:
        path = data / rel
        if path.exists():
            continue
        if rel.endswith("PerformTemplateTb.json"):
            _write(path, {})
        elif rel.endswith("AvatarBaseTemplateTb.json"):
            _write(path, {"IAEFFFFLKNB": []})
        elif rel.endswith("VoiceData.json"):
            _write(path, {})
        else:
            _write(path, {})

    monkeypatch.setattr("zzz_story.extract.fetch_source_version", lambda *args, **kwargs: "3.2.0")
    out = tmp_path / "out"
    stats = extract(out_dir=out, data_dir=data, game_dir=tmp_path / "nogame")
    assert stats.total_lines == 7
    assert stats.options_count == 2
    assert stats.supplement_lines == 6

    records = [
        json.loads(line)
        for line in (out / "story.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(records) == 7
    galgame = [record for record in records if record["family"] == "GalGame"]
    assert len(galgame) == 6
    assert galgame[0]["scene_speakers"] == ["苏茜", "铃"]
    assert galgame[0].get("speaker") is None
    assert galgame[0]["scene_act"] == 1
    assert galgame[0]["scene_title"] == "测试场景"
    assert galgame[0]["scene_intro"] == "哲视角：哲和苏茜在测试场景见面。 / 铃视角：铃和苏茜在测试场景见面。"
    assert galgame[-1].get("scene_intro") is None
    assert galgame[0]["quest_name"] == "测试任务"
    # The archive places scene 9000001 after 10000002 despite its smaller id.
    assert galgame[-1]["scene"] == "9000001"
    assert galgame[-1]["text"] == "后来场景台词"
    assert galgame[-1]["quest_name"] == "任务二"
    supplements = [
        json.loads(line)
        for line in (out / "supplement.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert all(type(row["chapter_order"]) is int for row in records + supplements)
    assert all(
        row["chapter_order"] == records[0]["chapter_order"]
        for row in supplements if row["chapter"] == records[0]["chapter"]
    )
    season_two = [row for row in supplements if row["source_key"].startswith("CS_21_")]
    assert len(season_two) == 1
    # CS_21 is season 2 chapter 1, i.e. Chapter110 -- not Chapter210 (season 3).
    assert season_two[0]["chapter"] == "Chapter110"
    assert season_two[0]["chapter_label"] == "第二季 第一章 云霞同归处"

    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["source_version"] == "3.2.0"
    assert manifest["validation"]["errors"] == 0
    chapters = {row["token"]: row for row in manifest["chapters"]}
    assert all(type(row["order"]) is int for row in chapters.values())
    assert chapters["Chapter110"]["supplement_lines"] == 1
    assert chapters["Chapter110"]["order"] > chapters["Chapter00"]["order"]
    assert stats.by_chapter == {"Chapter00": 6, "Chapter01": 1}
    assert all(record.get("raw_text") is None for record in records)
    assert manifest["ordering"]["chronology_status"] == "unknown"
    assert manifest["quality"]["unlinked_comic_lines"] == 1
    assert galgame[0]["order_source"] == "archive_table"
    assert galgame[0]["archive_order"] == 0
    assert galgame[0]["quest_id"] == 9901
    assert {row["text"] for row in supplements} >= {"哥哥，可以开始吗？", "妹妹，可以开始吗？"}
    # Stable ids: chapter token only, no chapter_order prefix.
    assert all(record["line_id"].startswith(("CH00_", "CH01_")) for record in records)
    # The manifest must not leak the local game path.
    assert "\\" not in manifest["game_dir"] and "/" not in manifest["game_dir"]



def test_cache_root_isolated_for_custom_dataset(tmp_path):
    default = _cache_root(None, "CHS")
    custom = _cache_root(tmp_path, "CHS")
    english = _cache_root(None, "EN")
    assert custom != default
    assert english != default
    assert _cache_root(tmp_path, "CHS") == custom


def test_supplement_ids_survive_insertion():
    old = [{"source_key": "Comic_b"}, {"source_key": "CS_21_01_010"}]
    _assign_supplement_ids(old)
    new = [{"source_key": "Comic_a"}] + [dict(row) for row in old]
    _assign_supplement_ids(new)
    assert [row["line_id"] for row in new[1:]] == [row["line_id"] for row in old]


def _rec(line_no, text, speaker=None, scene="1", family="GalGame", line_type="dialogue"):
    return {
        "chapter": "Chapter110",
        "scene": scene,
        "family": family,
        "variant": None,
        "line_no": line_no,
        "sub_no": None,
        "speaker": speaker,
        "text": text,
        "line_type": line_type,
    }


def test_normalize_speaker():
    assert _normalize_speaker("{M#铃}{F#哲}", "F") == "哲"
    assert _normalize_speaker("{M#铃}{F#哲}", "M") == "铃"
    assert _normalize_speaker("Youkai", "F") == "幻祟"
    assert _normalize_speaker("Fairy", "F") == "Fairy"
    assert _normalize_speaker("", "F") is None


def test_unattributed_scene_is_unknown():
    records = [
        _rec(1, "台词", None, scene="a", line_type="narration"),
        _rec(1, "旁白", None, scene="b", line_type="narration"),
        _rec(2, "台词", "铃", scene="b"),
    ]
    _mark_unattributed_scenes(records)
    assert [r["line_type"] for r in records] == ["unknown", "narration", "dialogue"]

def test_galgame_scene_positions_archive_order():
    scenes = ["11100010", "11100015", "11100020", "11100165", "11100170", "11120010", "99999999"]
    scene_order = {
        "11100010": (0, 1),
        "11100020": (1, 1),
        "11100170": (2, 2),
        "11100165": (3, 2),
        "11120010": (4, 3),
    }
    positions = _galgame_scene_positions(scenes, scene_order)
    ordered = sorted(scenes, key=lambda scene: positions[scene])
    assert ordered == [
        "11100010",
        "11100015",  # unarchived, slots between numeric neighbours
        "11100020",
        "11100170",  # archive order beats numeric order
        "11100165",
        "11120010",  # mid-chapter per archive, not at the end
        "99999999",  # beyond all archived scenes stays last
    ]


def test_ongoing_tips_speakers(tmp_path):
    from zzz_story.speakers import ongoing_tips_speakers

    tips_path = tmp_path / "FileCfg" / "OngoingTipsConfigTemplateTb.json"
    _write(
        tips_path,
        {
            "IAEFFFFLKNB": [
                {
                    "FGAHJLHNEDB": "Main_OngoingLevel_Chapter110_110809072_01",
                    "BLOGJEGIBOH": "Name_Test",
                    "PFOBGIIIICG": "OngoingLevel_Chapter110_TaoistBelle_110809071_001",
                    "CIBKAFBOGCI": "",
                },
                {
                    "FGAHJLHNEDB": "Main_OngoingLevel_Chapter110_110809072_02",
                    "BLOGJEGIBOH": "",
                    "PFOBGIIIICG": "OngoingLevel_Chapter110_PanYinhu_110809072_001",
                },
                {
                    "FGAHJLHNEDB": "Main_OngoingLevel_Chapter110_110809072_03",
                    "BLOGJEGIBOH": "Name_Option",
                    "PFOBGIIIICG": "",
                },
                {"FGAHJLHNEDB": "Tips_72030001", "BLOGJEGIBOH": "Avatar_X"},
            ]
        },
    )

    class FakeMap:
        def get(self, key, default=""):
            return {"Name_Test": "潘引壶", "Name_Option": "选项"}.get(key, default)

    data_paths = {"FileCfg/OngoingTipsConfigTemplateTb.json": tips_path}
    result = ongoing_tips_speakers(data_paths, FakeMap(), {"panyinhu": "潘引壶"}, "F")
    assert result["Main_OngoingLevel_Chapter110_110809072_01"] == ("潘引壶", None)
    assert result["Main_OngoingLevel_Chapter110_110809072_02"] == ("潘引壶", "PanYinhu")
    assert "Main_OngoingLevel_Chapter110_110809072_03" not in result  # 选项 is not a speaker
    assert "Tips_72030001" not in result  # not a main-story key

    no_file = ongoing_tips_speakers({}, FakeMap(), {}, "F")
    assert no_file == {}


def test_protagonist_side_covers_costumes_but_not_props():
    assert _protagonist_side("哲") == "M"
    assert _protagonist_side("铃") == "F"
    # Every form in the game's GalNPC<Form>Belle / <Form>Wise table.
    for prefix in ("玩家", "学生", "道士", "泳装", "佩洛伊斯"):
        assert _protagonist_side(prefix + "哲") == "M"
        assert _protagonist_side(prefix + "铃") == "F"
    # A doorbell is not the female protagonist.
    assert _protagonist_side("门铃") is None
    assert _protagonist_side(None) is None


def test_costume_prefixes_come_from_the_textmap():
    text_map = {
        "GalNPCBelle": "铃",
        "GalNPCSutandoBelle": "佩洛伊斯铃",
        "GalNPCStudentBelle": "学生铃",
        "GalNPCPlayerBelle": "玩家铃",
        "GalNPCBelleEvelyn": "铃&伊芙琳",
    }
    assert costume_prefixes(text_map) == frozenset({"佩洛伊斯", "学生", "玩家"})


def test_costume_prefixes_fall_back_when_keys_are_missing():
    assert costume_prefixes({}) == DEFAULT_COSTUME_PREFIXES


def test_protagonist_side_accepts_a_new_costume_form():
    assert _protagonist_side("幼年哲", frozenset({"幼年"})) == "M"
    assert _protagonist_side("幼年铃", frozenset({"幼年"})) == "F"
    # Without the derived set the form stays unknown.
    assert _protagonist_side("幼年哲") is None


def test_line_id_does_not_depend_on_chapter_order():
    records = [_rec(1, "你好", "仪玄")]
    records[0]["chapter"] = "Chapter110"
    records[0]["chapter_order"] = 17
    _assign_line_ids(records)
    first = records[0]["line_id"]
    # Simulate inserting a chapter earlier in the table: the order shifts,
    # the id must not.
    records[0]["chapter_order"] = 42
    _assign_line_ids(records)
    assert records[0]["line_id"] == first
    assert first.startswith("CH110_GalGame_")


def test_scene_metadata_never_claims_chronology():
    assert _scene_metadata("GalGame", "123000001", {"123000001": (0, 0)}) == {
        "order_source": "archive_table", "chronology_status": "unknown",
        "archive_order": 0, "quest_id": None, "quest_source": None,
    }
    assert _scene_metadata("Chat", "123000001", {"123000001": (0, 9901)})["quest_id"] is None


def test_identity_only_merges_known_forms():
    assert _speaker_identity("道士哲", DEFAULT_COSTUME_PREFIXES) == ("哲", "道士")
    assert _speaker_identity("林德薇恩「中挽昼」", DEFAULT_COSTUME_PREFIXES) == ("林德薇恩", "中挽昼")
    assert _speaker_identity("零号·安比", DEFAULT_COSTUME_PREFIXES) == ("零号·安比", None)
    assert _speaker_identity("门铃", DEFAULT_COSTUME_PREFIXES) == ("门铃", None)


def test_review_reused_output_is_rejected_before_any_writes(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / "supplement.jsonl").write_text("old", encoding="utf-8")
    with pytest.raises(FileExistsError, match="工作目录须为空"):
        extract(out_dir=out, data_dir=tmp_path / "missing")
    assert (out / "supplement.jsonl").read_text(encoding="utf-8") == "old"
    assert not (out / "manifest.json").exists()


def test_empty_variant_keeps_nonempty_peer_regardless_of_input_order(tmp_path):
    data = tmp_path / "data"
    prefix = "Main_GalGame_Chapter00_10000002_"
    # JSON insertion order deliberately visits the female key before its peer.
    tm = {prefix + "01F": "女主独立文本", prefix + "02": "另一个文本", prefix + "01": "男主文本",
          prefix + "03F": "", prefix + "03": "非空文本"}
    for rel in REQUIRED_FILES:
        _write(data / rel, tm if rel == "TextMap/TextMapTemplateTb.json" else {})
    full = tmp_path / "full"
    extract(out_dir=full, data_dir=data, game_dir=tmp_path / "no-game")
    rows = [json.loads(line) for line in (full / "story.jsonl").read_text(encoding="utf-8").splitlines()]
    assert {row["source_key"]: row["text"] for row in rows} == {key: text for key, text in tm.items() if text}
