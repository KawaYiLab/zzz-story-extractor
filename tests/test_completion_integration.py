import json

from zzz_story.extract import extract
from zzz_story.fetch import REQUIRED_FILES
from zzz_story.speakers import SpeakerIndex, SpeakerInfo, SpeakerStats


def test_completion_source_audit_and_lore_speaker_inputs(tmp_path, monkeypatch):
    data = tmp_path / "data"
    base = "Main_BubbleStory_Chapter170_417001009_01"
    empty = "Main_Chat_Chapter02_30200076_08"
    partner = "PartnerTalkChat_Partner1011_1001_01"
    street = "PasserBy_Chat_Street_1002_01"
    values = {base: "{M#哲}{F#铃}", base + "_Gender": "{F#铃}{M#哲}", empty: "",
              "Avatar_Anby": "安比", partner: "新格式互动", street: "新格式街头对白"}
    for rel in REQUIRED_FILES:
        path = data / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {}
        if rel == "TextMap/TextMapTemplateTb.json":
            payload = values
        elif rel == "FileCfg/AvatarBaseTemplateTb.json":
            payload = {"IAEFFFFLKNB": [{"PFOAJKNPCHL": 1011, "HAKHHHCAENA": "Avatar_Anby",
                                       "FEKFJBFGANO": "anbi", "OOOHMBMDLBI": 1}]}
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr("zzz_story.extract.fetch_source_version", lambda *args, **kwargs: "3.3.0")

    def speaker_index(**kwargs):
        assert {base, partner, street} <= kwargs["text_keys"]
        return SpeakerIndex({partner: SpeakerInfo("安比", None, .98, "perform"),
                             street: SpeakerInfo("店员", None, .98, "perform")}, SpeakerStats()), SpeakerStats()

    monkeypatch.setattr("zzz_story.extract.build_speaker_index", speaker_index)
    out = tmp_path / "out"
    extract(out_dir=out, data_dir=data, game_dir=tmp_path / "no-game", formats="jsonl,txt,csv")
    story = [json.loads(s) for s in (out / "story.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(story) == 1 and story[0]["source_key"] == base
    assert story[0]["line_id"] == "CH170_BubbleStory_417001009_0001"
    assert story[0]["source_variants"][0]["status"] == "equivalent_source_variant"
    variants = [json.loads(s) for s in (out / "source-variants.jsonl").read_text(encoding="utf-8").splitlines()]
    assert variants == story[0]["source_variants"]
    gaps = [json.loads(s) for s in (out / "source-gaps.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [r["source_key"] for r in gaps] == [empty] and gaps[0]["english_status"] == "absent"
    partner_rows = [json.loads(s) for s in (out / "lore/agents/dialogue-audit.jsonl").read_text(encoding="utf-8").splitlines()]
    assert partner_rows[0]["speaker"] == "安比"
    street_rows = [json.loads(s) for s in (out / "lore/street/dialogue-audit.jsonl").read_text(encoding="utf-8").splitlines()]
    assert street_rows[0]["speaker"] == "店员"


def test_comic_context_is_rendered_without_changing_source_identity(tmp_path, monkeypatch):
    from zzz_story.supplement_context import annotate_supplement_context
    from zzz_story.writers import write_supplement_txt

    key = "Comic_" + "a" * 32
    rows = [{"source_key": key, "line_id": "SUP_" + key, "family": "Comic", "scene": "a" * 32,
             "context_status": "unlinked", "text": "先把事情说清楚。"}]
    context = {"links": {key: [{"comic": "C00_01", "asset": "Comic/C00_01.asset", "timeline_path_id": 1,
                                "display_name": "妮可", "marker_time": 1.5}]}}
    annotate_supplement_context(rows, context)
    path = tmp_path / "supplement.txt"
    write_supplement_txt(rows, path)
    text = path.read_text(encoding="utf-8")
    assert "漫画资源：C00_01" in text and "【妮可】先把事情说清楚。" in text
    assert rows[0]["line_id"] == "SUP_" + key and rows[0]["scene"] == "a" * 32
