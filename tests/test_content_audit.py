from zzz_story.content_audit import audit
from zzz_story.extract import _write_csv
from zzz_story.writers import (
    write_chapter_files,
    write_jsonl,
    write_story_txt,
    write_supplement_txt,
    write_text,
)


def fixture(output):
    rows = [{"source_key": str(n), "line_id": str(n), "chapter": "Chapter210", "chapter_label": "Chapter210",
             "chapter_order": 210, "scene": "1", "scene_act": 1, "speaker": "NPC", "text": "same text",
             "raw_text": "same text", "line_type": "dialogue", "family": "GalGame", "scene_speakers": ["NPC"],
             "text_variants": None} for n in (1, 2)]
    write_jsonl(rows, output / "story.jsonl")
    write_story_txt(rows, output / "story.txt")
    write_chapter_files(rows, output / "chapters")
    write_supplement_txt([], output / "supplement.txt")
    _write_csv(rows, output / "story.csv")
    return rows


def test_full_audit_checks_exports_without_deleting_repeated_text(tmp_path):
    rows = fixture(tmp_path)
    result = audit(tmp_path)
    assert not result["export_errors"]
    assert result["summary"]["adjacent_equal_pairs"] == 1
    assert result["summary"]["text_anomalies"] == 0
    assert result["repeated_pairs"][0]["status"] == "no_structured_evidence"
    assert result["summary"]["main_lines"] == len(rows)


def test_audit_detects_stale_text_csv_and_chapter_exports(tmp_path):
    fixture(tmp_path)
    (tmp_path / "story.txt").write_text("stale", encoding="utf-8")
    (tmp_path / "story.csv").write_text("source_key,text\nwrong,stale\n", encoding="utf-8")
    (tmp_path / "chapters" / "stale.txt").write_text("stale", encoding="utf-8")
    result = audit(tmp_path)
    assert "story.txt differs from JSONL rendering" in result["export_errors"]
    assert "CSV record count differs" in result["export_errors"]
    assert "chapter file inventory differs" in result["export_errors"]


def test_audit_covers_extra_exports_and_anomalies(tmp_path):
    from zzz_story.extras import render_extra_txt
    fixture(tmp_path)
    rows = [{"source_key": "extra", "line_id": "EX_extra", "chapter": "activity.Fest", "domain": "activity",
             "chapter_label": "活动", "family": "Chat", "scene": "1", "text": "残留{M#标记}", "line_type": "unknown"}]
    write_jsonl(rows, tmp_path / "extra.jsonl")
    write_text(tmp_path / "extra.txt", render_extra_txt(rows))
    result = audit(tmp_path)
    assert result["summary"]["extra_lines"] == 1
    assert result["summary"]["text_anomalies"] == 1
    assert not result["export_errors"]
    (tmp_path / "extra.txt").write_text("stale", encoding="utf-8")
    assert "extra.txt differs from JSONL rendering" in audit(tmp_path)["export_errors"]


def test_repeated_passages_find_blocks_without_merging_options_or_scenes():
    from zzz_story.content_audit import repeated_passages
    texts = ["这是重复段落的第一句话。", "这是重复段落的第二句话。", "这是重复段落的第三句话。"]
    rows = [{"source_key": str(n), "chapter": "activity.Fest", "family": "Chat", "scene": "1",
             "text": text, "speaker": "NPC", "line_type": "dialogue"} for n, text in enumerate(texts * 2)]
    result = repeated_passages(rows)
    assert result[0]["source_keys"] == [["0", "1", "2"], ["3", "4", "5"]]
    assert len(rows) == 6
    rows[3]["line_type"] = "option"
    assert repeated_passages(rows) == []
    rows[3]["line_type"] = "dialogue"
    for row in rows[3:]:
        row["scene"] = "2"
    assert repeated_passages(rows) == []
