import json

import pytest

from zzz_story.extract import (
    DEFAULT_COSTUME_PREFIXES,
    _assign_line_ids,
    _assign_supplement_ids,
    _cache_root,
    _collapse_gender_pairs,
    _dedupe_records,
    _galgame_scene_positions,
    _filter_branch_lines,
    _mark_unattributed_scenes,
    _normalize_speaker,
    _protagonist_side,
    _record_raw_text,
    _scene_metadata,
    _speaker_identity,
    _unknown_costume_forms,
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
    stats = extract(
        out_dir=out,
        data_dir=data,
        game_dir=tmp_path / "nogame",
        no_speakers=True,
        include_supplement=True,
        formats="jsonl,txt",
    )
    assert stats.total_lines == 6
    assert stats.options_count == 2
    assert stats.supplement_lines == 4

    records = [
        json.loads(line)
        for line in (out / "story.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(records) == 6
    galgame = [record for record in records if record["family"] == "GalGame"]
    assert len(galgame) == 5
    assert galgame[0]["scene_speakers"] == ["苏茜"]
    assert galgame[0]["speaker"] is None
    assert galgame[0]["scene_act"] == 1
    assert galgame[0]["scene_title"] == "测试场景"
    assert galgame[0]["quest_name"] == "测试任务"
    # The archive places scene 9000001 after 10000002 despite its smaller id.
    assert galgame[-1]["scene"] == "9000001"
    assert galgame[-1]["text"] == "后来场景台词"
    assert galgame[-1]["quest_name"] == "任务二"
    story_txt = (out / "story.txt").read_text(encoding="utf-8")
    assert "### 任务：测试任务" in story_txt
    assert "### 任务：任务二" in story_txt
    assert story_txt.index("你好") < story_txt.index("后来场景台词")
    assert "## 第 1 幕：测试场景（出场：苏茜）" in story_txt
    assert "> 选项 1：选项分支一" in story_txt
    assert "> 选项 2：选项分支二" in story_txt

    assert (out / "supplement.jsonl").exists()
    supp_txt = (out / "supplement.txt").read_text(encoding="utf-8")
    assert "### 序章" in supp_txt
    assert "#### 过场 01" in supp_txt
    assert "过场台词一" in supp_txt
    assert "妹妹，可以开始吗？" in supp_txt
    assert "哥哥，可以开始吗？" not in supp_txt  # male-only: Belle's version dropped

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
    coverage = json.loads((out / "coverage.json").read_text(encoding="utf-8"))
    assert coverage["total_lines"] == 6
    assert coverage["options_count"] == 2
    # Keyed by chapter token, not label: labels are not unique across chapters.
    assert coverage["by_chapter"] == {"Chapter00": 5, "Chapter01": 1}
    assert coverage["validation"]["errors"] == 0
    # Plain fixture lines clean to themselves, so raw_text is omitted.
    assert all(record["raw_text"] is None for record in records)
    assert coverage["raw_text_omitted"] == 6
    assert manifest["ordering"]["chronology_status"] == "unknown"
    assert manifest["quality"]["unlinked_comic_lines"] == 1
    assert galgame[0]["order_source"] == "archive_table"
    assert galgame[0]["archive_order"] == 0
    assert galgame[0]["quest_id"] == 9901
    discarded = [json.loads(line) for line in (out / "discarded.jsonl").read_text(encoding="utf-8").splitlines()]
    assert {row["source_key"] for row in discarded} == {
        "CS_00_01_020", "CS_00_01_030",
        "Main_GalGame_Chapter00_10000002_002F", "Main_GalGame_Chapter00_10000002_Name_001F",
    }
    assert manifest["counts"]["discarded_lines"] == 3
    assert manifest["counts"]["discarded_names"] == 1
    assert all(row["raw_text"] and row["paired_source_key"] for row in discarded)
    assert all(not any(key.startswith("_discard") or key == "_paired_source_key" for key in row) for row in records + supplements)
    # Stable ids: chapter token only, no chapter_order prefix.
    assert all(record["line_id"].startswith(("CH00_", "CH01_")) for record in records)
    # The manifest must not leak the local game path.
    assert "\\" not in manifest["game_dir"] and "/" not in manifest["game_dir"]

    # --only-chapter keeps just the requested chapter; lore is skipped.
    partial = tmp_path / "partial"
    partial_stats = extract(
        out_dir=partial,
        data_dir=data,
        game_dir=tmp_path / "nogame",
        no_speakers=True,
        include_supplement=True,
        formats="jsonl,txt",
        include_lore=False,
        only_chapters={"01"},
    )
    assert partial_stats.total_lines == 1
    partial_manifest = json.loads((partial / "manifest.json").read_text(encoding="utf-8"))
    assert partial_manifest["chapter_filter"] == ["Chapter01"]
    assert partial_manifest["chapters"][0]["token"] == "Chapter01"

    # Accuracy-first mode keeps both branch candidates and raw source text so
    # a reviewer can decide what belongs in a curated male-only corpus.
    accurate = tmp_path / "accurate"
    accurate_stats = extract(
        out_dir=accurate,
        data_dir=data,
        game_dir=tmp_path / "nogame",
        no_speakers=True,
        include_supplement=True,
        formats="jsonl",
        include_lore=False,
        accuracy_first=True,
    )
    assert accurate_stats.branch_filtered == 0
    assert accurate_stats.gender_pair_filtered == 0
    assert accurate_stats.deduped == 0
    accurate_manifest = json.loads((accurate / "manifest.json").read_text(encoding="utf-8"))
    assert accurate_manifest["accuracy_first"] is True
    assert accurate_manifest["protagonist"] == "mixed"
    assert (accurate / "discarded.jsonl").read_text(encoding="utf-8") == ""
    accurate_records = [
        json.loads(line)
        for line in (accurate / "story.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert all(record["raw_text"] is not None for record in accurate_records)

    limited = tmp_path / "limited"
    extract(out_dir=limited, data_dir=data, game_dir=tmp_path / "nogame", no_speakers=True,
            include_supplement=False, include_lore=False, formats="jsonl", limit=1)
    assert (limited / "discarded.jsonl").read_text(encoding="utf-8") == ""

    with pytest.raises(SystemExit):
        extract(
            out_dir=tmp_path / "empty",
            data_dir=data,
            game_dir=tmp_path / "nogame",
            no_speakers=True,
            include_supplement=False,
            include_lore=False,
            only_chapters={"999"},
        )


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


def test_filters_keep_reviewable_removal_evidence():
    records = [_rec(1, "准备好了吗，铃？", "妮可"), _rec(2, "准备好了吗，哲？", "妮可")]
    for i, row in enumerate(records):
        row["source_key"] = f"key_{i}"
    kept, count = _filter_branch_lines(records)
    assert count == 1
    removed = next(row for row in records if row not in kept)
    assert removed["_discard_reason"] == "gender_address"
    assert removed["_paired_source_key"] == "key_1"

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


def test_review_branch_filter_preserves_semantic_differences():
    for records in (
        [_rec(1, "师妹，我们不能打开这扇门。", "仪玄"), _rec(2, "师弟，我们能打开这扇门。", "仪玄")],
        [_rec(1, "哥哥，今天不去空洞了。", "小孩"), _rec(2, "今天不去空洞了。", "邻居")],
        [_rec(1, "铃，你会游泳吗？", "仪玄"), _rec(2, "哲，你会游泳吗？", "妮可")],
    ):
        kept, count = _filter_branch_lines(records)
        assert count == 0
        assert kept == records


def test_review_gender_pairs_preserve_negation():
    records = [_rec(1, "我们不能打开这扇门。", "铃"), _rec(2, "我们能打开这扇门。", "哲")]
    assert _collapse_gender_pairs(records, "M") == (records, 0)


def test_review_dedupe_preserves_props_and_real_repetition():
    records = [_rec(1, "叮咚。", "门铃"), _rec(2, "叮咚。", None)]
    assert _dedupe_records(records, "M") == (records, 0)
    records = [_rec(1, "……", "仪玄"), _rec(2, "……", "仪玄")]
    assert _dedupe_records(records, "M") == (records, 0)


def test_dedupe_keeps_npc_repeats():
    records = [
        _rec(1, "……", "叶瞬光"),
        _rec(2, "怎么了？", "铃"),
        _rec(3, "没事。", "仪玄"),
        _rec(4, "……", "叶瞬光"),
    ]
    kept, dropped = _dedupe_records(records, "F")
    assert dropped == 0
    assert len(kept) == 4


def test_dedupe_drops_protagonist_copies():
    records = [
        _rec(1, "出发吧。", "铃"),
        _rec(2, "出发吧。", "哲"),
        _rec(3, "好的。", None),
        _rec(4, "好的。", "学生铃"),
    ]
    kept, dropped = _dedupe_records(records, "F")
    assert dropped == 1
    assert [(r["line_no"], r["speaker"]) for r in kept] == [(1, "铃"), (3, None), (4, "学生铃")]


def test_dedupe_drops_copied_branch_block():
    records = [
        _rec(1, "你来了。", "仪玄"),
        _rec(2, "先坐下吧。", "仪玄"),
        _rec(3, "好。", "铃"),
        _rec(4, "你来了。", "仪玄"),
        _rec(5, "先坐下吧。", "仪玄"),
        _rec(6, "好。", "哲"),
    ]
    kept, dropped = _dedupe_records(records, "F")
    assert dropped == 1
    assert [r["line_no"] for r in kept] == [1, 2, 3, 4, 5]


def test_branch_filter_needs_counterpart():
    records = [
        _rec(1, "师妹，快来这边！", "橘福福"),
        _rec(15, "师弟，快来这边！", "橘福福"),
        _rec(20, "引壶师弟，掩护师父！", "橘福福"),
    ]
    kept, dropped = _filter_branch_lines(records)
    assert dropped == 1
    assert [r["line_no"] for r in kept] == [15, 20]


def test_branch_filter_sibling_pairs():
    records = [
        _rec(1, "铃，我查过了，Fairy 确实筛出了有效的委托。", "哲"),
        _rec(2, "哥哥…我查了一下，Fairy 确实筛出了一些委托。", None),
        _rec(3, "铃，你顺便去了解下情况吧。", None),
        _rec(4, "哥哥，你顺便去了解下情况吧。", None),
        _rec(5, "哥哥，吃饭了。", "铃"),
    ]
    kept, dropped = _filter_branch_lines(records)
    # Rephrased and unattributed lines cannot establish a branch pair.
    assert [r["line_no"] for r in kept] == [1, 2, 3, 4, 5]


def test_branch_filter_scoped_to_scene():
    # Two scenes: the pair lives in scene 2 while scene 1 lines sit at the
    # same group-local positions; only the paired Belle line may drop.
    records = [
        _rec(1, "今天拉面店不营业吗？", None, scene="0001"),
        _rec(2, "稍等，我还没说完！", "苏茜", scene="0001"),
        _rec(1, "师妹，快来这边！", "橘福福", scene="0002"),
        _rec(2, "师弟，快来这边！", "橘福福", scene="0002"),
    ]
    kept, dropped = _filter_branch_lines(records)
    assert dropped == 1
    assert [r["text"] for r in kept] == ["今天拉面店不营业吗？", "稍等，我还没说完！", "师弟，快来这边！"]


def test_branch_filter_bare_name_vocative():
    records = [
        _rec(1, "铃，你会游泳吗？", "仪玄"),
        _rec(2, "哲，你会游泳吗？", "仪玄"),
    ]
    kept, dropped = _filter_branch_lines(records)
    assert dropped == 1
    assert kept[0]["text"] == "哲，你会游泳吗？"


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


def test_gender_pair_collapses_costume_forms():
    records = [
        _rec(1, "我记起来了，船长也说过这件事。", "道士铃"),
        _rec(2, "我记起来了，船长也说过这件事。", "道士哲"),
    ]
    kept, dropped = _collapse_gender_pairs(records, "M")
    assert dropped == 1
    assert [record["speaker"] for record in kept] == ["道士哲"]


def test_gender_pair_collapses_sutando_forms():
    # 佩洛伊斯铃 is the game's own "stand-in Belle" form, not a prop.
    records = [
        _rec(1, "……", "佩洛伊斯铃"),
        _rec(2, "……", "佩洛伊斯哲"),
    ]
    kept, dropped = _collapse_gender_pairs(records, "M")
    assert dropped == 1
    assert [record["speaker"] for record in kept] == ["佩洛伊斯哲"]


def test_gender_pair_keeps_distinct_sibling_lines():
    records = [
        _rec(1, "哥哥，我先去工坊了。", "学生铃"),
        _rec(2, "师父让我们在观里等消息。", "学生哲"),
    ]
    kept, dropped = _collapse_gender_pairs(records, "M")
    assert dropped == 0
    assert len(kept) == 2


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


def test_unknown_costume_forms_only_reports_pairs():
    records = [
        {"speaker": "幼年哲"},
        {"speaker": "幼年铃"},
        {"speaker": "门铃"},
        {"speaker": "哲"},
    ]
    assert _unknown_costume_forms(records, DEFAULT_COSTUME_PREFIXES) == {
        "幼年哲": 1,
        "幼年铃": 1,
    }


def test_gender_pair_collapses_with_a_derived_costume_set():
    records = [
        _rec(1, "走吧，师父在等我们。", "幼年铃"),
        _rec(2, "走吧，师父在等我们。", "幼年哲"),
    ]
    kept, dropped = _collapse_gender_pairs(records, "M", frozenset({"幼年"}))
    assert dropped == 1
    assert [record["speaker"] for record in kept] == ["幼年哲"]


def test_raw_text_is_kept_only_when_cleaning_changed_it():
    assert _record_raw_text("你好", "你好", keep_raw=False) is None
    assert _record_raw_text("<b>你好</b>", "你好", keep_raw=False) == "<b>你好</b>"
    assert _record_raw_text("你好", "你好", keep_raw=True) == "你好"


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
    with pytest.raises(FileExistsError, match="已有提取产物"):
        extract(out_dir=out, data_dir=tmp_path / "missing", no_speakers=True, include_supplement=False)
    assert (out / "supplement.jsonl").read_text(encoding="utf-8") == "old"
    assert not (out / "manifest.json").exists()
