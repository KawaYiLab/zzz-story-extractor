import json

from zzz_story.diff import diff_outputs, format_diff


def _write(directory, rows):
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "story.jsonl").open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _row(line_id, text, speaker="哲", chapter="Chapter230", order=1):
    return {
        "line_id": line_id,
        "chapter": chapter,
        "chapter_label": "第三季 第三章 她与她的隐秘往事",
        "text": text,
        "speaker": speaker,
        "line_type": "dialogue",
        "order": order,
    }


def test_diff_detects_added_removed_changed(tmp_path):
    old, new = tmp_path / "old", tmp_path / "new"
    _write(old, [_row("A", "旧台词"), _row("B", "保持原样"), _row("C", "被删掉的")])
    _write(new, [_row("A", "新台词"), _row("B", "保持原样"), _row("D", "新加的")])

    result = diff_outputs(old, new)

    assert (result.added, result.removed, result.changed) == (1, 1, 1)
    assert [chapter.token for chapter in result.chapters] == ["Chapter230"]
    text = format_diff(result)
    assert "合计：+1 新增，-1 删除，~1 修改" in text
    assert "「旧台词」 → 「新台词」" in text


def test_diff_detects_speaker_change(tmp_path):
    old, new = tmp_path / "old", tmp_path / "new"
    _write(old, [_row("A", "同一句台词", speaker="哲")])
    _write(new, [_row("A", "同一句台词", speaker="铃")])

    result = diff_outputs(old, new)

    assert (result.added, result.removed, result.changed) == (0, 0, 1)


def test_diff_reports_no_change_for_identical_outputs(tmp_path):
    old, new = tmp_path / "old", tmp_path / "new"
    rows = [_row("A", "台词"), _row("B", "另一句")]
    _write(old, rows)
    _write(new, rows)

    result = diff_outputs(old, new)

    assert result.chapters == []
    assert "没有变化" in format_diff(result)


def test_diff_orders_chapters_by_story_order(tmp_path):
    old, new = tmp_path / "old", tmp_path / "new"
    _write(old, [])
    _write(
        new,
        [
            _row("B", "第三章", chapter="Chapter230"),
            _row("A", "第一章", chapter="Chapter110"),
        ],
    )

    result = diff_outputs(old, new)

    assert [chapter.token for chapter in result.chapters] == ["Chapter110", "Chapter230"]
