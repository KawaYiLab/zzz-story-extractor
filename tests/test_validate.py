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
    records = [_line("A1", "Chapter240", "第三季 第4章")]
    issues = validate_records(records)
    assert [issue.code for issue in issues] == ["unknown-chapter"]
    assert issues[0].level == "warning"


def test_validate_output_reports_missing_directory(tmp_path):
    issues = validate_output(tmp_path / "missing")
    assert [issue.code for issue in issues] == ["missing-output"]
