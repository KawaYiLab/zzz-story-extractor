import json

from zzz_story.extract import (
    _dedupe_records,
    _galgame_scene_positions,
    _filter_branch_lines,
    _mark_unattributed_scenes,
    _normalize_speaker,
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
        "Main_GalGame_Chapter00_9000001_001": "后来场景台词",
        "QuestName_9901": "测试任务",
        "QuestName_9902": "任务二",
        "Main_GalGame_Chapter00_10000002_Option1_03": "选项分支一",
        "Main_GalGame_Chapter00_10000002_Option2_04": "选项分支二",
        "Main_GalGame_Chapter00_10000002_Name_001": "苏茜",
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

    monkeypatch.setattr("zzz_story.extract.fetch_source_version", lambda: "3.2.0")
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
    season_two = [row for row in supplements if row["source_key"].startswith("CS_21_")]
    assert len(season_two) == 1
    # CS_21 is season 2 chapter 1, i.e. Chapter110 -- not Chapter210 (season 3).
    assert season_two[0]["chapter"] == "Chapter110"
    assert season_two[0]["chapter_label"] == "第二季 第一章 云霞同归处"

    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["source_version"] == "3.2.0"
    assert manifest["validation"]["errors"] == 0
    chapters = {row["token"]: row for row in manifest["chapters"]}
    assert chapters["Chapter110"]["supplement_lines"] == 1
    assert chapters["Chapter110"]["order"] > chapters["Chapter00"]["order"]
    coverage = json.loads((out / "coverage.json").read_text(encoding="utf-8"))
    assert coverage["total_lines"] == 6
    assert coverage["options_count"] == 2
    # Keyed by chapter token, not label: labels are not unique across chapters.
    assert coverage["by_chapter"] == {"Chapter00": 5, "Chapter01": 1}
    assert coverage["validation"]["errors"] == 0

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
    assert dropped == 2
    assert [(r["line_no"], r["speaker"]) for r in kept] == [(1, "铃"), (4, "学生铃")]


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
    assert dropped == 3
    assert [r["line_no"] for r in kept] == [1, 2, 3]


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
    # 哲 speaking is always kept; 哥哥 twins are the female branch and drop;
    # the surviving 铃 line keeps its only twin gone, so it stays; Belle's
    # unpaired NPC line stays too.
    assert [r["line_no"] for r in kept] == [1, 3, 5]


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
