from zzz_story.fetch import DEFAULT_VERSION, SOURCE_VERSION_CACHE, fetch_source_version


def test_source_version_uses_the_cached_value(tmp_path):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    (cache_dir / SOURCE_VERSION_CACHE).write_text("9.9.9\n", encoding="utf-8")
    # No network is touched when the cache file exists.
    assert fetch_source_version(cache_dir) == "9.9.9"


def test_source_version_falls_back_offline_without_caching(tmp_path, monkeypatch):
    def offline(*args, **kwargs):
        raise RuntimeError("offline")

    monkeypatch.setattr("zzz_story.fetch.requests.get", offline)
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    assert fetch_source_version(cache_dir, refresh=True) == DEFAULT_VERSION
    # A failed lookup must not be cached, or the stale default sticks forever.
    assert not (cache_dir / SOURCE_VERSION_CACHE).exists()
