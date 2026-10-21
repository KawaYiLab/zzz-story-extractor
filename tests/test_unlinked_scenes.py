from copy import deepcopy

import pytest

from zzz_story.writers import write_chapter_files, write_story_txt


def unlinked_rows():
    return [
        {"chapter": "Chapter240", "chapter_label": "Chapter240", "chapter_order": 290,
         "family": "GalGame", "scene": "124000036", "scene_act": 36,
         "scene_speakers": ["铃", "哲", "Fairy"], "speaker": None,
         "speaker_gap_reason": "no_structured_reference", "line_type": "unknown",
         "source_key": f"Main_GalGame_Chapter240_124000036_{index:03}",
         "text": text}
        for index, text in enumerate(["找到终端了吗？", "找到终端了吗？", "铃，看看这里。", "哲，看看这里。"], 1)
    ]


def test_unlinked_names_and_versions_are_presented_as_candidates(tmp_path):
    rows = unlinked_rows()
    before = deepcopy(rows)
    story = tmp_path / "story.txt"
    write_story_txt(rows, story)
    chapters = write_chapter_files(rows, tmp_path / "chapters")
    for path in [story, *chapters]:
        text = path.read_text(encoding="utf-8")
        assert "第 36 幕（姓名表：铃、哲、Fairy）" in text
        assert "出场：" not in text and "剧情占位说明" not in text
        assert "说话人未关联；分支、播放及先后未核实" in text
        assert text.count("（未标注）找到终端了吗？") == 2
        assert text.index("铃，看看这里。") < text.index("哲，看看这里。")
    assert rows == before  # presentation must not rewrite names, text or source IDs


@pytest.mark.parametrize("evidence", [
    {"speaker": "Fairy", "line_type": "dialogue", "speaker_gap_reason": None},
    {"perform": {"occurrences": [{"node_type": "GalBubbleStoryNode"}]}},
    {"timeline": {"source": "clip"}},
])
def test_name_table_notice_does_not_hide_existing_scene_evidence(tmp_path, evidence):
    rows = unlinked_rows()
    rows[-1].update(evidence)
    # A separate family using the same scene number must retain its own status.
    unlinked_other_family = {**unlinked_rows()[0], "family": "Chat", "scene_act": 37}
    write_story_txt(rows + [unlinked_other_family], tmp_path / "story.txt")
    text = (tmp_path / "story.txt").read_text(encoding="utf-8")
    first, second = text.split("## 第 37 幕", 1)
    assert "说话人未关联；分支、播放及先后未核实" not in first
    assert "姓名表：" in second
    assert text.count("说话人未关联；分支、播放及先后未核实") == 1
