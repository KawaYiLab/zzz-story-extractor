from zzz_story.fetch import SOURCE_VERSION_CACHE, fetch_source_version


def test_source_version_uses_the_cached_value_only_as_an_unverified_hint(tmp_path):
    (tmp_path / SOURCE_VERSION_CACHE).write_text("9.9.9\n", encoding="utf-8")
    assert fetch_source_version(tmp_path) == "unknown"


def test_source_version_is_unknown_offline_without_provenance(tmp_path, monkeypatch):
    def offline(*args, **kwargs):
        raise RuntimeError("offline")
    monkeypatch.setattr("zzz_story.fetch.requests.get", offline)
    assert fetch_source_version(tmp_path, refresh=True) == "unknown"
    assert not (tmp_path / SOURCE_VERSION_CACHE).exists()


def test_one_click_reuses_matching_snapshot_and_recovers_damaged_cache(tmp_path, monkeypatch):
    from zzz_story import fetch

    monkeypatch.setattr(fetch, "CACHE_ROOT", tmp_path)
    monkeypatch.setattr(fetch, "REQUIRED_FILES", ["table.json"])
    requests = []

    def snapshot():
        requests.append(True)
        return "a" * 40, "3.3.0"

    def download(rel, destination, **kwargs):
        destination.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(fetch, "_upstream_snapshot", snapshot)
    monkeypatch.setattr(fetch, "download_file", download)
    table = fetch.ensure_data(game_version="CNPRODWin3.3.0")["table.json"]
    fetch.ensure_data(game_version="CNPRODWin3.3.0")
    assert len(requests) == 1
    table.write_text("broken", encoding="utf-8")
    fetch.ensure_data(game_version="CNPRODWin3.3.0")
    assert len(requests) == 2 and table.read_text(encoding="utf-8") == "{}"
    fetch.ensure_data(game_version="CNPRODWin3.4.0")
    assert len(requests) == 3
