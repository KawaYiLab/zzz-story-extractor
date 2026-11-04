from zzz_story.validate import validate_output, validate_records


def _line(line_id, chapter, label, text="台词"):
    return {"line_id": line_id, "chapter": chapter, "chapter_label": label, "text": text}


def test_clean_output_has_no_issues():
    records = [_line("A1", "Chapter210", "第三季 第一章 某个梦游者的自白")]
    supplements = [{"line_id": "S1", "chapter": "Chapter210", "chapter_label": "第三季 第一章 某个梦游者的自白"}]
    assert validate_records(records, supplements) == []


def test_duplicate_line_id_is_an_error():
    records = [
        _line("A1", "Chapter210", "第三季 第一章 某个梦游者的自白"),
        _line("A1", "Chapter210", "第三季 第一章 某个梦游者的自白"),
    ]
    issues = validate_records(records)
    assert [issue.code for issue in issues] == ["duplicate-line-id"]
    assert issues[0].level == "error"


def test_supplement_shadowing_another_season_is_an_error():
    records = [_line("A1", "Chapter210", "第三季 第一章 某个梦游者的自白")]
    supplements = [{"line_id": "S1", "chapter": "Chapter210", "chapter_label": "第二季 第一章 云霞同归处"}]
    issues = validate_records(records, supplements)
    assert [issue.code for issue in issues] == ["supplement-chapter-shadow"]
    assert "Chapter210" in issues[0].message


def test_empty_story_is_an_error():
    assert [issue.code for issue in validate_records([])] == ["empty-story"]


def test_unknown_chapter_is_only_a_warning():
    records = [_line("A1", "Chapter250", "第三季 第5章")]
    issues = validate_records(records)
    assert [issue.code for issue in issues] == ["unknown-chapter"]
    assert issues[0].level == "warning"


def test_validate_output_reports_missing_directory(tmp_path):
    issues = validate_output(tmp_path / "missing")
    assert [issue.code for issue in issues] == ["missing-output"]


def test_validate_extras_and_discard_references():
    story = [{**_line("s", "Chapter210", "第三季"), "source_key": "s"}]
    extra = [{"source_key": "e", "line_id": "e", "chapter": "activity.Fest", "text": "正文"}]
    removed = [{"source_key": "old", "paired_source_key": "e", "raw_text": "旧文", "reason": "copy"}]
    assert validate_records(story, extras=extra, discarded=removed) == []
    extra[0]["line_id"] = "s"
    extra[0]["text"] = ""
    removed[0]["paired_source_key"] = "missing"
    assert {i.code for i in validate_records(story, extras=extra, discarded=removed)} == {
        "duplicate-line-id", "empty-text", "discard-pair"}


def test_validate_rejects_retained_and_discarded_overlap():
    story = [{**_line("s", "Chapter210", "第三季"), "source_key": "s"}]
    removed = [{"source_key": "s", "paired_source_key": "s", "raw_text": "台词", "reason": "copy"}]
    assert "discard-overlap" in {i.code for i in validate_records(story, discarded=removed)}
