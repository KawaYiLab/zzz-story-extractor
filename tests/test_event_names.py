from zzz_story.event_names import infer_event_names, normalize_tag
from zzz_story.extras import extract_extras
from zzz_story.textmap import TextMap


def group(text="", scenes=()):
    return {"scenes": set(scenes), "text": text}


def test_normalize_tag_drops_version_and_prefix():
    assert normalize_tag("ActivityHotPot_OB2.7") == "hotpot"
    assert normalize_tag("HotPot") == "hotpot"
    assert normalize_tag("MegaRobot_Chapter2") == "megarobot"
    assert normalize_tag("GoldenWeek_CB3") == "goldenweek"


def test_tiers_need_matching_title_strings():
    text_map = TextMap({
        "ActivityMainTitle_HotPot_OB2.7": "滚烫寻鲜记",
        "ActivityTabTitle_HotPot_OB2.7": "滚烫寻鲜记",
        "ActivityMainTitle_Summer_OB2.1": "仲夏游梦绮谭",
        "ActivityMainTitle_summer_OB3.1": "恰浪花逐夏而至",
        "SummerTideTreasure_ActivityTitle": "恰浪花逐夏而至",
        "ActivityJumpName_EndlessSummer_01": "推进「仲夏游梦绮谭」剧情内容",
        "ActivityMainTitle_ActivityCoop_OB2.5": "连携调查：神之迷宫",
        "ActivityMainTitle_YumAttack_OB2.0": "美味大作战",
        "ActivityMainTitle_BetaOB2.0_V2_A": "Beta测试任务-V2-",
    }, "CHS")
    groups = {
        "HotPot": group(),
        "Summer": group(),  # two different titles: ambiguous, left alone
        "SummerTideTreasure": group(),
        "EndlessSummer": group(),
        "TheDivineMaze": group("神之迷宫\n" * 5),
        "ActivityYum": group(scenes={"705493001", "705493002"}),
        "Lonely": group(scenes={"705493001"}),  # one scene is not enough
        "Chapter04": group(scenes={"705493001", "705493002"}),  # chapter-bound tables are skipped
    }
    quests = {70549: "美味大作战·其一"}
    names = infer_event_names(text_map, groups, quests)
    assert {tag: (n.name, n.source) for tag, n in names.items()} == {
        "HotPot": ("滚烫寻鲜记", "title"),
        "SummerTideTreasure": ("恰浪花逐夏而至", "tagged"),
        "EndlessSummer": ("仲夏游梦绮谭", "jump"),
        "TheDivineMaze": ("连携调查：神之迷宫", "mention"),
        "ActivityYum": ("美味大作战", "quest"),
    }


def test_mentions_need_a_clear_lead_and_duplicates_keep_tags():
    text_map = TextMap({
        "ActivityMainTitle_Cinema_OB2.0": "缘于引力的邂逅",
        "ActivityMainTitle_GoldenWeek_CB3": "沙罗黄金周",
    }, "CHS")
    groups = {
        "Cinema": group(),
        "ActivityCinema": group(),
        "GoldenWeekStory": group("沙罗黄金周\n" * 6),
        "EndlessSummer": group("沙罗黄金周\n" * 3),  # mentioned, but not the leader
    }
    names = infer_event_names(text_map, groups)
    assert names["Cinema"].name == "缘于引力的邂逅（Cinema）"
    assert names["ActivityCinema"].name == "缘于引力的邂逅（ActivityCinema）"
    assert "EndlessSummer" not in names
    assert "GoldenWeekStory" not in names  # 6 vs 3 is below the required lead


def test_extract_extras_labels_groups_with_event_names():
    text_map = TextMap({
        "ActivityMainTitle_HotPot_OB2.7": "滚烫寻鲜记",
        "Activity_Chat_HotPot_30160093_01": "开锅了！",
        "Activity_Chat_Unknown_30160094_01": "没有标题",
        "Side_Chat_Chapter03_226023006_01": "支线",
    }, "CHS")
    records, _, stats = extract_extras(text_map)
    labels = {row["chapter"]: (row["chapter_label"], row.get("group_name_source")) for row in records}
    assert labels == {
        "activity.HotPot": ("活动剧情 · 滚烫寻鲜记", "title"),
        "activity.Unknown": ("活动剧情 · Unknown", None),
        "side.Chapter03": ("支线委托 · 第一季 第三章", None),
    }
    assert stats.named_groups == 1
    assert stats.group_names["activity.HotPot"]["evidence"] == "ActivityMainTitle_HotPot_OB2.7"
