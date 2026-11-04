import json

import pytest

from zzz_story.textmap import load_language_map, load_text_map


def tables(tmp_path, values):
    paths = {}
    for name, value in values.items():
        path = tmp_path / name
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8-sig")
        paths["TextMap/" + name] = path
    return paths


def test_translation_takes_priority_over_chinese_hotfix(tmp_path):
    paths = tables(tmp_path, {
        "TextMapTemplateTb.json": {"k": "中文旧文", "fallback": "原文", "empty": "原文"},
        "TextMapOverwriteTemplateTb.json": {"k": "中文新文", "fallback": "修订"},
        "TextMap_ENTemplateTb.json": {"k": "English", "empty": "", "override": "old"},
        "TextMap_ENOverwriteTemplateTb.json": {"override": "new"},
    })
    result = load_text_map(paths, "en")
    assert dict(result.items()) == {"k": "English", "fallback": "修订", "empty": "", "override": "new"}
    assert load_text_map(paths).get("k") == "中文新文"
    assert "fallback" not in load_language_map(paths, "EN")


def test_conflicting_source_keys_are_not_silently_overwritten(tmp_path):
    path = tmp_path / "table.json"
    path.write_text('{"line": "yes", "line": "no"}', encoding="utf-8")
    with pytest.raises(ValueError, match="conflicting TextMap values.*line"):
        load_text_map({"TextMap/TextMapTemplateTb.json": path})


def test_identical_source_keys_do_not_duplicate_output(tmp_path):
    path = tmp_path / "table.json"
    path.write_text('{"line": "yes", "line": "yes"}', encoding="utf-8")
    assert list(load_text_map({"TextMap/TextMapTemplateTb.json": path}).items()) == [("line", "yes")]
