from zzz_story.content_audit import audit
from zzz_story.extract import _write_csv
from zzz_story.writers import write_chapter_files, write_jsonl, write_story_txt, write_supplement_txt


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
