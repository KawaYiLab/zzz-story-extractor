import json

from zzz_story.extract import extract
from zzz_story.fetch import REQUIRED_FILES


def _write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_extract_fixture(tmp_path, monkeypatch):
    data = tmp_path / "data"
    text_map = {
        "Main_GalGame_Chapter00_10000002_001": "你好",
        "Main_GalGame_Chapter00_10000002_002": "再见",
        "Main_GalGame_Chapter00_10000002_Name_001": "苏茜",
        "MainChat_Chapter01_001_01": "聊天内容",
        "Comic_abcdef": "漫画内容",
        "Title_10000002": "「测试场景」",
    }
    _write(data / "TextMap/TextMapTemplateTb.json", text_map)
    _write(data / "TextMap/TextMapOverwriteTemplateTb.json", {})
    _write(data / "TextMap/TextMap_ENTemplateTb.json", {})
    _write(data / "TextMap/TextMap_ENOverwriteTemplateTb.json", {})
    for rel in REQUIRED_FILES:
        path = data / rel
        if path.exists():
            continue
        if rel.endswith("PerformTemplateTb.json"):
            _write(path, {})
        elif rel.endswith("AvatarBaseTemplateTb.json"):
            _write(path, {"IAEFFFFLKNB": []})
        elif rel.endswith("VoiceData.json"):
            _write(path, {})
        else:
            _write(path, {})

    monkeypatch.setattr("zzz_story.extract.fetch_source_version", lambda: "3.2.0")
    out = tmp_path / "out"
    stats = extract(
        out_dir=out,
        data_dir=data,
        game_dir=tmp_path / "nogame",
        no_speakers=True,
        include_supplement=True,
        formats="jsonl,txt",
    )
    assert stats.total_lines == 3
    assert stats.supplement_lines == 1

    records = [
        json.loads(line)
        for line in (out / "story.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(records) == 3
    galgame = [record for record in records if record["family"] == "GalGame"]
    assert len(galgame) == 2
    assert galgame[0]["scene_speakers"] == ["苏茜"]
    assert galgame[0]["speaker"] is None
    assert galgame[0]["scene_act"] == 1
    assert galgame[0]["scene_title"] == "测试场景"
    story_txt = (out / "story.txt").read_text(encoding="utf-8")
    assert "## 第 1 幕：测试场景（出场：苏茜）" in story_txt
    assert (out / "supplement.jsonl").exists()
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["source_version"] == "3.2.0"
    coverage = json.loads((out / "coverage.json").read_text(encoding="utf-8"))
    assert coverage["total_lines"] == 3
