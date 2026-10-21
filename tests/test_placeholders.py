import json

from zzz_story.extract import extract
from zzz_story.fetch import REQUIRED_FILES
from zzz_story.narrative import annotate_content
from zzz_story.speakers import SpeakerIndex, SpeakerInfo, SpeakerStats
from zzz_story.validate import validate_records
from zzz_story.writers import write_story_txt


KEY = "Main_GalGame_Chapter240_124000034_001"
TEXT = "过渡到蕾米埃尔回忆之前和艾尔妲在在零号空洞前的对话。"


def row():
    return {"source_key": KEY, "text": TEXT, "raw_text": None, "speaker": "安比",
            "speaker_id": "安比", "speaker_alias": "NameKey", "speaker_source": "perform",
            "speaker_confidence": .98, "scene_speakers": ["安比"], "line_type": "dialogue",
            "line_id": "CH240_GalGame_124000034_0001", "chapter": "Chapter240",
            "chapter_label": "第三季 第四章 重返天空的旅程", "family": "GalGame",
            "scene": "124000034", "scene_act": 34, "has_voice": False}


def test_reviewed_outline_keeps_source_but_removes_actual_attribution(tmp_path):
    record = row()
    annotate_content([record])
    assert record["text"] == TEXT and record["source_key"] == KEY
    assert record["source_attribution"]["speaker"] == "安比"
    assert record["source_attribution"]["speaker_alias"] == "NameKey"
    assert record["speaker"] is None and record["scene_speakers"] == []
    assert record["speaker_status"] == "not_applicable"
    assert record["content_evidence"]["playback_status"] == "unverified"
    annotate_content([record])  # repeated review preserves the original name
    assert record["source_attribution"]["speaker"] == "安比"
    path = tmp_path / "story.txt"
    write_story_txt([record], path)
    text = path.read_text(encoding="utf-8")
    assert "剧情占位说明" in text and TEXT in text
    assert "【安比】" not in text and "出场：安比" not in text
    assert not validate_records([record])


def test_changed_source_and_regular_anby_dialogue_are_not_reclassified():
    changed = {**row(), "text": "安比说：接下来，我们去会客室。"}
    unrelated = {**row(), "source_key": "Main_GalGame_Chapter240_124000035_001"}
    annotate_content([changed, unrelated])
    assert all(r["speaker"] == "安比" and "content_status" not in r for r in (changed, unrelated))


def test_placeholder_validation_catches_legacy_attribution():
    assert "unclassified-placeholder" in {issue.code for issue in validate_records([row()])}
    bad = {**row(), "content_status": "reviewed_placeholder"}
    assert "placeholder-attribution" in {issue.code for issue in validate_records([bad])}


def test_extraction_exports_same_placeholder_in_both_modes(tmp_path, monkeypatch):
    data = tmp_path / "data"
    for rel in REQUIRED_FILES:
        path = data / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {KEY: TEXT, "Main_GalGame_Chapter240_124000034_Name_001": "安比"} if rel == "TextMap/TextMapTemplateTb.json" else {}
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    stats = SpeakerStats()
    index = SpeakerIndex({KEY: SpeakerInfo("安比", "NameKey", .98, "perform", True,
                                         perform={"avatars": ["NameKey"], "voice_keys": ["voice"], "occurrences": []})}, stats)
    monkeypatch.setattr("zzz_story.extract.build_speaker_index", lambda **kwargs: (index, stats))
    for accurate in (False, True):
        out = tmp_path / str(accurate)
        extract(out_dir=out, data_dir=data, include_lore=False, include_supplement=False,
                formats="jsonl,txt,csv", accuracy_first=accurate)
        records = [json.loads(line) for line in (out / "story.jsonl").read_text(encoding="utf-8").splitlines()]
        assert len(records) == 1 and records[0]["speaker"] is None
        assert records[0]["has_voice"] is True  # linkage remains evidence, not proof of an actual voice
        assert records[0]["source_attribution"]["speaker"] == "安比"
        assert records[0]["line_type"] == "placeholder"
        assert json.loads((out / "placeholder-records.jsonl").read_text(encoding="utf-8")) == records[0]
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["reviewed_placeholder_lines"] == 1
        assert manifest["validation"]["errors"] == 0
        from zzz_story.content_audit import export_errors
        assert not export_errors(out, records, [])
