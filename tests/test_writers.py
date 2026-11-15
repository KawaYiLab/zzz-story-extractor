import json

import pytest

from zzz_story.writers import _atomic_write_text, write_jsonl


@pytest.mark.parametrize("records", [[], [{"text": "中文与😀\n下一行", "value": None}, {"text": "后一句"}]])
def test_jsonl_stream_matches_previous_bytes_and_order(tmp_path, records):
    baseline = tmp_path / "baseline.jsonl"
    lines = [json.dumps(record, ensure_ascii=False, separators=(",", ":")) for record in records]
    _atomic_write_text(baseline, "\n".join(lines) + ("\n" if lines else ""))
    target = tmp_path / "nested" / "output.jsonl"

    assert write_jsonl(iter(records), target) == len(records)
    assert target.read_bytes() == baseline.read_bytes()
    assert not target.with_suffix(".jsonl.tmp").exists()


@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize("failure", ["iterator", "serialization", "replace"])
def test_failed_jsonl_write_preserves_target_and_removes_temp(tmp_path, monkeypatch, existing, failure):
    target = tmp_path / "output.jsonl"
    if existing:
        target.write_bytes(b"previous complete output\n")

    def records():
        yield {"text": "first line"}
        if failure == "iterator":
            raise RuntimeError("source failed")
        yield {"value": object()} if failure == "serialization" else {"text": "second line"}

    if failure == "replace":
        def fail_replace(self, other):
            raise OSError("replace failed")

        monkeypatch.setattr(type(target), "replace", fail_replace)
    expected = {"iterator": RuntimeError, "serialization": TypeError, "replace": OSError}[failure]
    with pytest.raises(expected):
        write_jsonl(records(), target)

    assert not target.with_suffix(".jsonl.tmp").exists()
    if existing:
        assert target.read_bytes() == b"previous complete output\n"
    else:
        assert not target.exists()
