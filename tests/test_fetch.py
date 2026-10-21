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
