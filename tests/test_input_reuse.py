import json
from collections import Counter

import pytest

from zzz_story import extract as extraction
from zzz_story import extras, speakers
from zzz_story.fetch import REQUIRED_FILES


def test_extract_reuses_loaded_inputs_and_extra_candidates(tmp_path, monkeypatch):
    data = tmp_path / "data"
    values = {
        "Main_GalGame_Chapter00_10000002_001": "主线台词",
        "Activity_Chat_Fest_700033_01": "活动台词",
        "Comic_abcdef": "漫画台词",
    }
    for rel in REQUIRED_FILES:
        path = data / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = values if rel == "TextMap/TextMapTemplateTb.json" else {"IAEFFFFLKNB": []}
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(extraction, "detect_game_dir", lambda path: path)
    monkeypatch.setattr(extraction, "fetch_source_version", lambda *args, **kwargs: "3.3.0")

    reads = Counter()
    loaded = {}
    original_read = extraction.read_json

    def read_json(path):
        reads[path] += 1
        loaded[path] = original_read(path)
        return loaded[path]

    monkeypatch.setattr(extraction, "read_json", read_json)
    original_language_map = extraction.load_language_map
    languages = []

    def load_language_map(paths, language):
        languages.append(language)
        return original_language_map(paths, language)

    monkeypatch.setattr(extraction, "load_language_map", load_language_map)

    def unexpected_language_load(*args, **kwargs):
        pytest.fail("speaker resolver reloaded the already supplied English map")

    monkeypatch.setattr(speakers, "load_language_map", unexpected_language_load)

    def perform_speakers(text_map, aliases, perform_path, game_dir, cache_path, refresh, stats, loader):
        assert loader(perform_path) is loaded[perform_path]
        return {}, set()

    monkeypatch.setattr(speakers, "_perform_speakers", perform_speakers)

    def comic_context(game_dir, perform, cache_path, **kwargs):
        assert perform is loaded[data / "FileCfg/PerformTemplateTb.json"]
        return {"links": {}, "errors": {}, "stats": {}}

    monkeypatch.setattr(extraction, "scan_comic_context", comic_context)

    def lore(text_map, avatar, out, **kwargs):
        assert avatar is loaded[data / "FileCfg/AvatarBaseTemplateTb.json"]
        return {}

    monkeypatch.setattr(extraction, "extract_lore", lore)
    classify_calls = []
    original_candidates = extraction.extra_candidate_keys

    def candidates(text_map):
        classify_calls.append(True)
        return original_candidates(text_map)

    def unexpected_candidates(*args, **kwargs):
        pytest.fail("extra extraction repeated candidate classification")

    monkeypatch.setattr(extraction, "extra_candidate_keys", candidates)
    monkeypatch.setattr(extras, "candidate_keys", unexpected_candidates)
    out = tmp_path / "out"
    stats = extraction.extract(out_dir=out, data_dir=data, game_dir=tmp_path / "game", formats="jsonl")

    assert stats.total_lines == 1
    assert languages == ["EN"]
    assert len(classify_calls) == 1
    for rel in ("FileCfg/AvatarBaseTemplateTb.json", "FileCfg/PerformTemplateTb.json",
                "FileCfg/OngoingTipsConfigTemplateTb.json"):
        assert reads[data / rel] == 1
    assert json.loads((out / "extra.jsonl").read_text(encoding="utf-8"))["text"] == "活动台词"
