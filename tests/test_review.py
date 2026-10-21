import json

import pytest

from zzz_story.fetch import SOURCE_VERSION_CACHE, fetch_source_version
from zzz_story.speakers import CACHE_VERSION, SpeakerStats, _perform_speakers
from zzz_story.textmap import TextMap
from zzz_story.validate import validate_records
from zzz_story.writers import write_supplement_txt


def test_review_legacy_version_label_is_not_verified(tmp_path, monkeypatch):
    (tmp_path / SOURCE_VERSION_CACHE).write_text("9.9.9", encoding="utf-8")
    monkeypatch.setattr("zzz_story.fetch.requests.get", lambda *a, **k: pytest.fail("must not query latest version"))
    assert fetch_source_version(tmp_path) == "unknown"


def test_review_unfingerprinted_speaker_cache_is_rebuilt(tmp_path, monkeypatch):
    cache = tmp_path / "cache.json"
    cache.write_text(json.dumps({"version": CACHE_VERSION, "speakers": {}, "options": [], "stats": {}}))
    perform = tmp_path / "perform.json"
    perform.write_text("{}")
    def rebuilding(*args):
        raise RuntimeError("rebuilding")
    monkeypatch.setattr("zzz_story.speakers.find_catalog_block", rebuilding)
    with pytest.raises(RuntimeError, match="rebuilding"):
        _perform_speakers(TextMap({}, "CHS"), {}, perform, tmp_path, cache, False, SpeakerStats())


def test_review_supplement_ids_are_validated():
    main = [{"line_id":"same", "chapter":"Chapter00", "chapter_label":"序章"}]
    sup = [{"line_id":"same", "chapter":"Comic"}, {"chapter":"Comic"}]
    assert {i.code for i in validate_records(main, sup)} >= {"duplicate-line-id", "missing-line-id"}


def test_review_comics_have_individual_boundaries(tmp_path):
    path = tmp_path / "supplement.txt"
    write_supplement_txt([
        {"family":"Comic", "source_key":"Comic_a", "text":"甲片段", "context_status":"unlinked"},
        {"family":"Comic", "source_key":"Comic_b", "text":"乙片段", "context_status":"unlinked"},
    ], path)
    text = path.read_text(encoding="utf-8")
    assert "Comic_a" in text and "Comic_b" in text
    assert text.index("Comic_a") < text.index("甲片段") < text.index("Comic_b") < text.index("乙片段")


def test_review_integrity_checks_raw_text(tmp_path):
    from scripts.check_corpus_integrity import check
    output, audit = tmp_path / "out", tmp_path / "audit"
    for directory in (output, audit):
        directory.mkdir()
        (directory / "story.jsonl").write_text(json.dumps({"source_key":"k", "line_id":"id", "text":"same", "raw_text":"same", "chronology_status":"unknown"}) + "\n")
        (directory / "supplement.jsonl").write_text("")
        (directory / "discarded.jsonl").write_text("")
        (directory / "name_candidates.jsonl").write_text("")
        (directory / "manifest.json").write_text(json.dumps({"language":"CHS", "files":{"table":{"sha256":"abc"}}, "accuracy_first": directory == audit}))
    (output / "story.jsonl").write_text(json.dumps({"source_key":"k", "line_id":"id", "text":"same", "raw_text":"CORRUPTED", "chronology_status":"unknown"}))
    with pytest.raises(ValueError, match="原文"):
        check(output, audit)



def test_review_provenance_verifies_actual_input_files(tmp_path):
    from zzz_story.fetch import SOURCE_PROVENANCE, sha256_file
    table = tmp_path / "table.json"
    table.write_text("{}")
    provenance = {"commit":"a" * 40, "version":"3.2.0", "files":{"table.json":{"sha256":sha256_file(table)}}}
    (tmp_path / SOURCE_PROVENANCE).write_text(json.dumps(provenance))
    assert fetch_source_version(tmp_path) == "3.2.0"
    table.write_text('{"changed":true}')
    assert fetch_source_version(tmp_path) == "unknown"


def test_review_refresh_failure_preserves_existing_dataset(tmp_path, monkeypatch):
    from zzz_story import fetch
    monkeypatch.setattr(fetch, "CACHE_ROOT", tmp_path)
    target = tmp_path / fetch.DEFAULT_VERSION
    for rel in fetch.REQUIRED_FILES:
        path = target / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("old")
    monkeypatch.setattr(fetch, "_upstream_snapshot", lambda: ("a" * 40, "3.3.0"))
    def failed(rel, destination, **kwargs):
        assert all("a" * 40 in base for base in kwargs["bases"])
        raise RuntimeError("failed download")
    monkeypatch.setattr(fetch, "download_file", failed)
    with pytest.raises(RuntimeError, match="failed download"):
        fetch.ensure_data(refresh=True)
    assert all((target / rel).read_text() == "old" for rel in fetch.REQUIRED_FILES)


def test_review_speaker_fingerprint_tracks_changed_inputs(tmp_path):
    from zzz_story.speakers import _speaker_fingerprint
    perform = tmp_path / "perform.json"
    perform.write_text("{}")
    blocks = tmp_path / "ZenlessZoneZero_Data/StreamingAssets/Blocks"
    blocks.mkdir(parents=True)
    block = blocks / "1.blk"
    block.write_bytes(b"old")
    text_map = TextMap({"name":"甲"}, "CHS")
    original = _speaker_fingerprint(text_map, {"alias":"甲"}, perform, tmp_path)
    assert original != _speaker_fingerprint(TextMap({"name":"乙"}, "CHS"), {"alias":"甲"}, perform, tmp_path)
    assert original != _speaker_fingerprint(text_map, {"alias":"乙"}, perform, tmp_path)
    block.write_bytes(b"changed")
    assert original != _speaker_fingerprint(text_map, {"alias":"甲"}, perform, tmp_path)

    updated = _speaker_fingerprint(text_map, {"alias":"甲"}, perform, tmp_path)
    patch = tmp_path / "ZenlessZoneZero_Data/Persistent/Blocks/1.blk"
    patch.parent.mkdir(parents=True)
    patch.write_bytes(b"patched")
    assert updated != _speaker_fingerprint(text_map, {"alias":"甲"}, perform, tmp_path)


def test_review_coverage_counts_only_retained_voiced_lines(tmp_path, monkeypatch):
    from zzz_story.fetch import REQUIRED_FILES
    from zzz_story.extract import extract
    from zzz_story.speakers import SpeakerIndex, SpeakerInfo
    data = tmp_path / "data"
    text_map = {"Main_GalGame_Chapter00_1_001":"相同台词", "Main_GalGame_Chapter00_1_002":"相同台词"}
    for rel in REQUIRED_FILES:
        path = data / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(text_map if rel == "TextMap/TextMapTemplateTb.json" else {}), encoding="utf-8")
    stats = SpeakerStats()
    index = SpeakerIndex({key: SpeakerInfo(name, name, 1.0, "voice", True) for key, name in zip(text_map, ("铃", "哲"))}, stats)
    monkeypatch.setattr("zzz_story.extract.build_speaker_index", lambda **kwargs: (index, stats))
    result = extract(out_dir=tmp_path / "out", data_dir=data, include_lore=False, include_supplement=False, formats="jsonl")
    assert result.total_lines == 1
    assert result.voice_linked == 1 and result.voice_speaker == 1


@pytest.mark.parametrize("args", [{"formats":"jsnol"}, {"formats":""}, {"limit":0}, {"limit":-1}, {"require_speakers":float("nan")}, {"require_speakers":1.1}])
def test_review_invalid_extract_args_fail_before_reading_data(tmp_path, args):
    from zzz_story.extract import extract
    with pytest.raises(ValueError):
        extract(out_dir=tmp_path / "out", data_dir=tmp_path / "missing", **args)
    assert not (tmp_path / "out").exists()


def test_review_partial_provenance_does_not_label_other_files(tmp_path):
    from zzz_story.fetch import SOURCE_PROVENANCE, sha256_file
    table = tmp_path / "table.json"
    table.write_text("{}")
    provenance = {"commit":"a" * 40, "version":"3.2.0", "files":{"table.json":{"sha256":sha256_file(table)}}}
    (tmp_path / SOURCE_PROVENANCE).write_text(json.dumps(provenance))
    assert fetch_source_version(tmp_path, required_files=["table.json", "unverified.json"]) == "unknown"
