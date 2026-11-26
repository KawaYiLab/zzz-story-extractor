import gzip
import json

import pytest

from zzz_story import bundle


def test_gzip_members_preserve_text_across_chunks_and_check_backend_limits(tmp_path, monkeypatch):
    # Put JSON escapes and a multibyte character on a streaming boundary.
    story = "字" * (128 * 1024 - 1) + '"\\\t\n'
    (tmp_path / "manifest.json").write_text("{}", encoding="utf-8")
    (tmp_path / "story.jsonl").write_text(story, encoding="utf-8")
    output = tmp_path / "corpus.gz"
    bundle.write_bundle(tmp_path, output)
    raw = gzip.decompress(output.read_bytes())
    assert json.loads(raw)["story"] == story
    with monkeypatch.context() as patch:
        patch.setattr(bundle, "MAX_BUNDLE_BYTES", len(raw) - 1)
        with pytest.raises(ValueError, match="512 MiB"):
            bundle.write_bundle(tmp_path, output)
    monkeypatch.setattr(bundle, "MAX_UPLOAD_BYTES", output.stat().st_size - 1)
    with pytest.raises(ValueError, match="64 MiB"):
        bundle.write_bundle(tmp_path, output)
