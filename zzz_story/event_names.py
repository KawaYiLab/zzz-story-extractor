"""Chinese display names for activity and side-quest groups.

Dialogue keys carry an internal tag (``SayItWithFlowers``) while the game UI
names the event elsewhere (``ActivityMainTitle_ActivityFlower_OB1.7`` =
花语未明之言).  No public table links the two, so names are inferred from
evidence tiers that each have to agree with an existing title string.  A
group without such evidence keeps its internal tag; nothing is guessed.

Tiers, strongest first:

``title``    ``ActivityMainTitle_<tag>`` / ``ActivityTabTitle_<tag>`` with one value
``tagged``   ``<tag>_ActivityTitle`` or ``Activity<tag>…_ActivityName``
``jump``     ``ActivityJumpName_<tag>_*`` reading 推进「X」剧情
``quest``    the common quest-name prefix of the group's scenes equals a title
``mention``  a title quoted in the group's own dialogue far more than elsewhere
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass

_TITLE_KEY_RE = re.compile(r"^Activity(?:Main|Tab)Title_(?P<name>.+)$")
_TAGGED_KEY_RE = re.compile(r"^(?P<name>.+?)(?:MainPage_Text)?_Activity(?:Title|Name)$")
_JUMP_KEY_RE = re.compile(r"^ActivityJumpName_(?P<name>[^_]+)_\d+$")
_JUMP_TEXT_RE = re.compile(r"推进「(?P<title>[^」]{2,16})」(?:的)?(?:剧情|故事)")
_MARKUP_RE = re.compile(r"<[^>]+>")
_TEST_TITLE_RE = re.compile(r"Beta|测试|\{|\d{2}")
_QUEST_SPLIT_RE = re.compile(r"[·•]")
_TITLE_SPLIT_RE = re.compile(r"[·•：:]")
# The ``mention`` tier needs this many quotes and this lead over any other group.
MIN_MENTIONS = 4
MENTION_LEAD = 3
# The ``quest`` tier needs this many scenes agreeing on one prefix.
MIN_QUEST_SCENES = 2
# Side tables bound to a main chapter are labelled by that chapter instead.
_CHAPTER_TAG_RE = re.compile(r"^Chapter\d+$")


@dataclass(frozen=True)
class EventName:
    name: str
    source: str  # tier name
    evidence: str  # TextMap key or quest name the name came from


def normalize_tag(tag: str) -> str:
    """``ActivityHotPot_OB2.7`` / ``HotPot`` / ``MegaRobot_Chapter2`` -> ``hotpot`` ..."""
    value = re.sub(r"_Chapter\d+$", "", tag)
    value = value.lower()
    value = re.sub(r"_?(?:ob|cb)\d+(?:\.\d+)?(?:_\w+)?$", "", value)
    value = re.sub(r"^activity", "", value)
    return re.sub(r"[^a-z0-9]", "", value)


def _clean_title(value: str) -> str:
    return _MARKUP_RE.sub("", value).strip()


def _titles(text_map) -> dict[str, list[tuple[str, str]]]:
    """Normalized internal name -> [(title, key)] from activity title keys."""
    out: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for key, value in text_map.items():
        match = _TITLE_KEY_RE.match(key)
        if not match or not isinstance(value, str):
            continue
        title = _clean_title(value)
        if title and not _TEST_TITLE_RE.search(key + title):
            out[normalize_tag(match["name"])].append((title, key))
    return out


def _bare(value: str) -> str:
    return value.strip(" 「」『』!！")


def _title_parts(titles: set[str]) -> dict[str, str]:
    """Unambiguous fragments -> full title: 神之迷宫 -> 连携调查：神之迷宫."""
    owners: dict[str, set[str]] = defaultdict(set)
    for title in titles:
        for part in {title, *_TITLE_SPLIT_RE.split(title)}:
            part = _bare(part)
            if len(part) >= 3:
                owners[part].add(title)
    return {part: next(iter(full)) for part, full in owners.items() if len(full) == 1}


def infer_event_names(
    text_map,
    groups: dict[str, dict],
    quest_names: dict[int, str] | None = None,
) -> dict[str, EventName]:
    """Infer names for ``groups``: tag -> ``{"scenes": set[str], "text": str}``."""
    quest_names = quest_names or {}
    titles = _titles(text_map)
    parts = _title_parts({title for rows in titles.values() for title, _ in rows})
    tagged: dict[str, tuple[str, str]] = {}
    jumps: dict[str, tuple[str, str]] = {}
    for key, value in text_map.items():
        if not isinstance(value, str):
            continue
        match = _TAGGED_KEY_RE.match(key)
        if match and _clean_title(value):
            tagged.setdefault(normalize_tag(match["name"]), (_clean_title(value), key))
        match = _JUMP_KEY_RE.match(key)
        if match:
            text = _JUMP_TEXT_RE.search(value)
            if text:
                jumps.setdefault(normalize_tag(match["name"]), (text["title"], key))

    mentions = _mentions(groups, parts)
    names: dict[str, EventName] = {}
    for tag, group in groups.items():
        if _CHAPTER_TAG_RE.match(tag):
            continue
        norm = normalize_tag(tag)
        values = {title for title, _ in titles.get(norm, [])}
        if len(values) == 1:
            title, key = titles[norm][0]
            names[tag] = EventName(title, "title", key)
            continue
        if norm in tagged:
            names[tag] = EventName(tagged[norm][0], "tagged", tagged[norm][1])
            continue
        if norm in jumps:
            names[tag] = EventName(jumps[norm][0], "jump", jumps[norm][1])
            continue
        quest = _quest_prefix(group["scenes"], quest_names)
        if quest and _bare(quest[0]) in parts:
            names[tag] = EventName(parts[_bare(quest[0])], "quest", quest[1])
            continue
        if tag in mentions:
            part = mentions[tag]
            names[tag] = EventName(parts[part], "mention", part)
    return _disambiguate(names)


def _disambiguate(names: dict[str, EventName]) -> dict[str, EventName]:
    """Two groups with one inferred name keep their tags visible."""
    owners = Counter(name.name for name in names.values())
    return {
        tag: name if owners[name.name] == 1 else EventName(f"{name.name}（{tag}）", name.source, name.evidence)
        for tag, name in names.items()
    }


def _quest_prefix(scenes: set[str], quest_names: dict[int, str]) -> tuple[str, str] | None:
    """Most common ``X`` of ``X·其一`` quest names reached from scene ids."""
    prefixes: Counter[str] = Counter()  # one count per scene
    example: dict[str, str] = {}
    for scene in scenes:
        if not scene.isdigit():
            continue
        value = int(scene)
        for divisor in (10000, 1000, 100):
            name = quest_names.get(value // divisor)
            if name:
                prefix = _QUEST_SPLIT_RE.split(name, 1)[0].strip()
                prefixes[prefix] += 1
                example.setdefault(prefix, name)
                break
    if not prefixes:
        return None
    prefix, count = prefixes.most_common(1)[0]
    if count < MIN_QUEST_SCENES:
        return None
    return prefix, example[prefix]


def _mentions(groups: dict[str, dict], titles) -> dict[str, str]:
    """Title fragments quoted in one group's dialogue clearly more than elsewhere."""
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    for tag, group in groups.items():
        text = group["text"]
        for title in titles:
            if len(title) >= 3 and title in text:
                counts[title][tag] = text.count(title)
    best: dict[str, tuple[tuple[int, int], str]] = {}
    for title, per_group in counts.items():
        ranked = per_group.most_common(2)
        tag, top = ranked[0]
        runner_up = ranked[1][1] if len(ranked) > 1 else 0
        if top < MIN_MENTIONS or top < MENTION_LEAD * runner_up:
            continue
        score = (top, len(title))
        if tag not in best or score > best[tag][0]:
            best[tag] = (score, title)
    return {tag: title for tag, (_, title) in best.items()}
