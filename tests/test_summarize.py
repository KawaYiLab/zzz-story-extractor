import json

import pytest

from zzz_story import summarize as S
from zzz_story.upload import build_bundle


def _write_output(out):
    rows = [
        {"chapter": "Chapter240", "chapter_label": "测试章", "family": "GalGame", "scene": "1",
         "scene_title": "开场", "scene_intro": "诺姆向哲介绍芯片计划。", "speaker": "诺姆", "text": "芯片计划开始！"},
        {"chapter": "Chapter240", "chapter_label": "测试章", "family": "GalGame", "scene": "1",
         "scene_title": "开场", "speaker": None, "text": "（研究室里很安静）"},
        {"chapter": "Chapter240", "chapter_label": "测试章", "family": "GalGame", "scene": "2",
         "scene_title": "试验", "speaker": "维克托", "scene_speakers": ["维克托", "诺姆"], "text": "嗯呢？"},
    ]
    out.mkdir(parents=True, exist_ok=True)
    (out / "story.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
                                     encoding="utf-8")
    (out / "extra.jsonl").write_text(json.dumps(
        {"chapter": "side.RAB", "chapter_label": "支线", "family": "GalGame", "scene": "100000006",
         "speaker": "安比", "text": "无关的支线。"}, ensure_ascii=False) + "\n", encoding="utf-8")


def _reply(payload):
    return {"choices": [{"message": {"content": "```json\n" + json.dumps(payload, ensure_ascii=False) + "\n```"}}]}


def test_units_number_scenes_and_carry_game_outlines(tmp_path):
    _write_output(tmp_path)
    units = S.load_units(tmp_path)
    assert [(u.source, u.chapter, len(u.scenes)) for u in units] == [("story", "Chapter240", 2), ("extra", "side.RAB", 1)]
    text = S.render(units[0].scenes, 1)
    assert "## S1 开场\n游戏梗概：诺姆向哲介绍芯片计划。\n诺姆：芯片计划开始！\n？：（研究室里很安静）" in text
    assert "## S2 试验" in text
    assert S.load_units(tmp_path, {"side.RAB"})[0].chapter == "side.RAB"


def test_long_units_split_on_scene_boundaries():
    scenes = [S.Scene("GalGame", str(i), f"场景{i}", None, [(None, "字" * 40)]) for i in range(1, 6)]
    parts = S.chunks(scenes, limit=100)
    assert [(start, len(run)) for start, run in parts] == [(1, 2), (3, 2), (5, 1)]


def test_paragraphs_without_citations_or_with_stray_names_are_dropped(tmp_path):
    _write_output(tmp_path)
    unit = S.load_units(tmp_path)[0]
    names = S.known_names(S.load_units(tmp_path))

    def post(body):
        return _reply({
            "summary": [
                {"text": "诺姆向哲介绍了芯片计划。", "scenes": ["S1"]},
                {"text": "维克托参加了试验。", "scenes": ["S2"]},
                {"text": "安比也来帮忙。", "scenes": ["S2"]},  # 安比不在 S2 里
                {"text": "没有出处的一段。", "scenes": []},
            ],
            "scene_synopses": [
                {"scene": "S1", "text": "已有游戏梗概，不补。"},
                {"scene": "S2", "text": "维克托试用了芯片。"},
            ],
        })

    result = S.summarize_unit(unit, post, "m", names)
    assert [p["text"] for p in result["summary"]] == ["诺姆向哲介绍了芯片计划。", "维克托参加了试验。"]
    assert result["summary"][0]["scenes"] == [{"family": "GalGame", "scene": "1"}]
    assert result["scene_synopses"] == [{"family": "GalGame", "scene": "2", "text": "维克托试用了芯片。"}]
    assert {d["reason"] for d in result["dropped"]} == {"name_not_in_cited_scenes", "no_citation"}


def test_run_caches_units_and_stops_on_quota_without_marking_done(tmp_path):
    _write_output(tmp_path)
    calls = []

    def post(body):
        calls.append(body["messages"][1]["content"])
        if len(calls) == 2:
            raise S.StopGeneration("402 Insufficient Balance")
        return _reply({"summary": [{"text": "诺姆介绍芯片计划。", "scenes": ["S1"]}], "scene_synopses": []})

    stats = S.run(tmp_path, post, "m", log=lambda _: None)
    assert stats["generated"] == 1 and stats["stopped"].startswith("402")
    rows = [json.loads(line) for line in (tmp_path / "summaries.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [r["chapter"] for r in rows] == ["Chapter240"]
    assert rows[0]["model"] == "m" and rows[0]["prompt_version"] == S.PROMPT_VERSION
    assert "dropped" not in rows[0]

    # 续跑：做完的单元走缓存，只补停下来的那个。
    calls.clear()
    stats = S.run(tmp_path, lambda body: (calls.append(1), _reply({"summary": [], "scene_synopses": []}))[1],
                  "m", log=lambda _: None)
    assert stats["cached"] == 1 and stats["generated"] == 1 and len(calls) == 1
    bundle = build_bundle(tmp_path)
    assert bundle["summaries"].count("unit_summary") == 2


def test_quota_errors_stop_instead_of_retrying(monkeypatch):
    class Response:
        status_code = 402
        text = "Insufficient Balance"

    monkeypatch.setattr("requests.post", lambda *a, **k: Response())
    with pytest.raises(S.StopGeneration):
        S.http_post("https://example.invalid/v1", "k")({"model": "m"})
