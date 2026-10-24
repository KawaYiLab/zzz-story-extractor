import json

from zzz_story.speakers import SpeakerIndex, SpeakerInfo, SpeakerStats
from zzz_story.street_dialogue import extract_street, street_source
from zzz_story.textmap import TextMap


def test_street_distinct_sources_short_lines_names_and_gender_variants(tmp_path):
    values = {
        "PasserByChat_Chapter00_001_Name01": "路人甲",
        "PasserByChat_Chapter00_001_01": "嗯",
        "PasserByChat_Chapter00_001_01F": "好",
        "PasserBy_Bubble_Street_10_01": "相同台词",
        "PasserBy_Bubble_Street_11_01": "相同台词",
        "PasserBy_Chat_Street_12_01": "新格式对白",
        "StoreChat_Street_13_01": "店员对白",
        "PasserBy_Chat_1300503150": "经过一番努力…小邦布站了起来！",
        "PasserBy_Chat_Street_14_EventName_01": "事件标题不是对白",
        "PasserBy_Chat_Street_14_InteractName": "交互按钮不是对白",
    }
    stats = extract_street(TextMap(values, "CHS"), tmp_path)
    rows = [json.loads(line) for line in (tmp_path / "dialogue-audit.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 7 == stats["lore_street_lines"]
    assert {r["source_key"] for r in rows} == set(values) - {
        "PasserByChat_Chapter00_001_Name01", "PasserBy_Chat_Street_14_EventName_01", "PasserBy_Chat_Street_14_InteractName"}
    metadata = [json.loads(line) for line in (tmp_path / "metadata-audit.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(metadata) == 3
    assert all(r["raw_text"] == values[r["source_key"]] for r in rows)
    assert all(r["speaker"] is None for r in rows)
    assert all(r["retained"] for r in rows)
    doc = (tmp_path / "01_街区路人与市井闲聊.md").read_text(encoding="utf-8")
    assert "姓名表候选：路人甲" in doc
    assert doc.count("相同台词") == 2
    assert "事件标题不是对白" not in doc and "交互按钮不是对白" not in doc
    assert "（未标注）嗯" in doc and "（未标注）好" in doc


def test_street_resource_names_and_verified_routes_preserve_audit(tmp_path):
    male, female = "PasserBy_Chat_Street_1_01", "PasserBy_Chat_Street_1_02"
    values = {male: "你好", female: "您好"}
    base = {"explicit_gender": True, "sides": ["M"], "paired_key": female}
    index = SpeakerIndex({male: SpeakerInfo("店员", None, .98, "perform", perform=base),
                          female: SpeakerInfo("店员", None, .98, "perform", perform={**base, "sides": ["F"], "paired_key": male})}, SpeakerStats())
    for accuracy in (False, True):
        directory = tmp_path / str(accuracy)
        stats = extract_street(TextMap(values, "CHS"), directory, speaker_index=index, accuracy_first=accuracy)
        rows = [json.loads(line) for line in (directory / "dialogue-audit.jsonl").read_text(encoding="utf-8").splitlines()]
        assert len(rows) == 2
        assert stats["lore_street_lines"] == (2 if accuracy else 1)
        assert all(r["speaker"] == "店员" and r["speaker_status"] == "resolved" for r in rows)
        assert rows[1]["retained"] == accuracy
        assert rows[1]["paired_source_key"] == (None if accuracy else male)


def test_street_legacy_bubble_passerby_families_are_preserved(tmp_path):
    # Fixed 3.3.0 source keys/texts that the legacy substring rule covered.
    values = {
        "Bubble_PasserBy_23001_01": "总感觉最近的物资摆放有点乱。",
        "Activity_Bubble_PasserBy21Spring_40160112_01": "不想试一试海上射击吗？",
        "Enclave_Bubble_PasserByWhitFiled_40170015_01": "早，今天要用什么点心开启新一天呢？",
    }
    # Name/title suffixes stay metadata in each restored family.
    metadata = {
        "Bubble_PasserBy_23001_Name01": "工人",
        "Activity_Bubble_PasserBy21Spring_40160112_EventName_01": "海上射击",
        "Enclave_Bubble_PasserByWhitFiled_40170015_InteractName": "点心摊",
    }
    stats = extract_street(TextMap(values | metadata, "CHS"), tmp_path)
    rows = [json.loads(line) for line in (tmp_path / "dialogue-audit.jsonl").read_text(encoding="utf-8").splitlines()]
    meta_rows = [json.loads(line) for line in (tmp_path / "metadata-audit.jsonl").read_text(encoding="utf-8").splitlines()]
    assert stats["lore_street_candidates"] == stats["lore_street_lines"] == 3
    assert {r["source_key"]: r["raw_text"] for r in rows} == values
    assert {r["source_key"]: r["raw_text"] for r in meta_rows} == metadata
    assert {r["family"] for r in rows} == {
        "Bubble_PasserBy", "Activity_Bubble_PasserBy21Spring", "Enclave_Bubble_PasserByWhitFiled"}
    assert all(r["retained"] and r["speaker"] is None for r in rows)
    doc = (tmp_path / "01_街区路人与市井闲聊.md").read_text(encoding="utf-8")
    assert all(text in doc and key in doc for key, text in values.items())
    assert "姓名表候选：工人" in doc
    assert all(street_source(key) is None for key in metadata)


def test_restored_street_families_do_not_merge_matching_scene_ids(tmp_path):
    male = "Bubble_PasserBy_40160112_01"
    female = "Activity_Bubble_PasserBy21Spring_40160112_01F"
    values = {male: "相同台词", female: "相同台词"}
    base = {"explicit_gender": True, "sides": ["M"], "paired_key": female}
    index = SpeakerIndex({male: SpeakerInfo("工人", None, .98, "perform", perform=base),
                          female: SpeakerInfo("工人", None, .98, "perform", perform={**base, "sides": ["F"], "paired_key": male})}, SpeakerStats())
    stats = extract_street(TextMap(values, "CHS"), tmp_path, speaker_index=index)
    rows = [json.loads(line) for line in (tmp_path / "dialogue-audit.jsonl").read_text(encoding="utf-8").splitlines()]
    assert stats["lore_street_lines"] == 2
    assert len({r["family"] for r in rows}) == 2
    assert len({r["scene"] for r in rows}) == 1
    assert all(r["retained"] and r["paired_source_key"] is None for r in rows)
