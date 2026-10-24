from zzz_story import mhy1


def test_named_and_legacy_mhy_apis_preserve_file_bytes(monkeypatch):
    named = [("CAB-exact", b"serialized"), ("CAB-another", b"more data")]
    monkeypatch.setattr(mhy1, "unpack_mhy_named_file", lambda raw, offset: (named, len(raw)))
    raw = b"mhy1" + bytes(12)
    assert mhy1.unpack_mhy_file(raw, 0) == ([b"serialized", b"more data"], len(raw))
    assert mhy1.extract_mhy_named_files(raw) == named
    assert mhy1.extract_mhy_files(raw) == [b"serialized", b"more data"]
