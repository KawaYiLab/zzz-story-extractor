"""Content registry: which TextMap key families carry narrative and where they go.

TextMap dialogue keys mostly follow one grammar::

    {Category}_{Kind}_{Tag}_{Scene}_{Line...}
    Activity_GalGame_SayItWithFlowers_10161201_001
    Side_Chat_ZenkovS1_226023006_01
    Companion_GalGame_ChapterSeed_16510010_001

plus a handful of older layouts (``GalGame_Chapter050_010_001``,
``SideChat_Chapter03_0002F_01``, ``AutoEvent100000_26`` ...).  The registry
below is the single place that maps those layouts to a content *domain*:

- ``main``: handled by the mainline pipeline (``extract.py`` / ``keys.py``)
- ``lore``: handled by ``lore.py`` (agent profiles, street NPCs, Inter-Knot)
- ``activity`` / ``side`` / ``companion`` / ``hollow`` / ``other`` / ``legacy``:
  extracted by ``extras.py`` into ``extra.jsonl``

Anything that looks like dialogue but matches no rule is reported by
:func:`coverage_report` so new versions cannot silently add unextracted text.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from .partner_dialogue import PARTNER_DIALOGUE_PREFIXES
from .street_dialogue import STREET_DIALOGUE_PREFIXES

# Order is also the catalog order of the extra domains.
DOMAIN_LABELS: dict[str, str] = {
    "activity": "活动剧情",
    "side": "支线委托",
    "companion": "代理人故事",
    "hollow": "空洞事件",
    "other": "其他剧情",
    "legacy": "旧版文本",
}
EXTRA_DOMAINS = tuple(DOMAIN_LABELS)

# Dialogue kinds as they appear in the second key segment.  Values reuse the
# mainline family names so readers and the server label them consistently.
KINDS = {
    "GalGame": "GalGame",
    "Chat": "Chat",
    "ChatPlus": "ChatPlus",
    "ChatAudio": "ChatAudio",
    "Bubble": "Bubble",
    "BubbleStory": "BubbleStory",
}
_ONGOING_RE = re.compile(r"^Ongoing[A-Za-z]*$")

# Categories of the generic grammar and the domain each one feeds.
CATEGORY_DOMAINS: dict[str, str] = {
    "Activity": "activity",
    "Side": "side",
    "Companion": "companion",
    "InLevel": "hollow",
    "Other": "other",
    "Store": "other",
    "Enclave": "other",
    # Already covered elsewhere; listed so the coverage report counts them.
    "Main": "main",
    "PartnerTalk": "lore",
    "PasserBy": "lore",
}

# Season-1 cutscenes predate the ``Main_`` prefix.  Only numeric chapter tokens
# are mainline; ``GalGame_ChapterMana`` etc. are agent stories.
LEGACY_MAIN_GALGAME_RE = re.compile(r"^GalGame_Chapter(\d+)_")

# Tags that are developer test tables, not shipped content.
_TEST_TAG_RE = re.compile(r"(?:^|[^a-z])test|emotiontest|testemoji", re.IGNORECASE)

_GENERIC_RE = re.compile(
    r"^(?P<cat>[A-Za-z]+)_(?P<kind>[A-Za-z]+)(?:_(?P<tag>.+?))?_(?P<scene>\d{2,})_(?P<suffix>.+)$"
)
_LEGACY_GALGAME_RE = re.compile(r"^GalGame_(?P<tag>[A-Za-z][^_]*)_(?P<scene>\d+)_(?P<suffix>.+)$")
_PREFIX_CHAT_RE = re.compile(
    r"^(?P<prefix>(?:Side|PhotoSide|Companion|Activity|Store|Other|Enclave|PartnerTalk|PasserBy)(?:Chat|Bubble))_(?P<tag>[^_]+)_(?P<rest>.+)$"
)
_AUTO_EVENT_RE = re.compile(r"^AutoEvent(?P<scene>\d+)_(?P<suffix>\d+)$")
_LEGACY_LOWER_RE = re.compile(r"^Galgame_(?P<tag>[^_]+)_(?P<scene>\d+)_(?P<suffix>.+)$")
_LEGACY_CHAT_RE = re.compile(r"^Chat_(?P<tag>Chapter[^_]+)_(?P<scene>[^_]+)_(?P<suffix>.+)$")
_PREFIX_CHAT_DOMAINS = {
    "Side": "side",
    "PhotoSide": "side",
    "Companion": "companion",
    "Activity": "activity",
    "Store": "other",
    "Other": "other",
    "Enclave": "other",
    "PartnerTalk": "lore",
    "PasserBy": "lore",
}
# Timeline subtitles: ``TL_C30_ChatPlus`` belongs to the mainline timeline
# reader (timeline.py); ``TL_Activity*`` and ``TL_PartnerDate`` do not.
_TIMELINE_RE = re.compile(r"^TL_(?P<tag>[^_]+)_(?P<kind>[A-Za-z]+)_(?P<scene>\d+)_(?P<suffix>.+)$")
# Families lore.py extracts (partner talks and dates, street and store NPCs).
# Checked before every other rule so no key is written to two outputs.
LORE_PREFIXES = PARTNER_DIALOGUE_PREFIXES + STREET_DIALOGUE_PREFIXES
# Families another output already covers, so the report does not flag them.
_COVERED_PREFIXES = {
    "CS_": "supplement",
    "Comic_": "supplement",
    "Message_": "lore",
    "Cinema_": "lore",
    "Chat_PartnerTalk_": "lore",
}

# A key "looks like dialogue" when it ends in a scene/line number pair.  Used
# only to find families the registry does not know yet.
_DIALOGUE_SHAPE_RE = re.compile(r"_\d{2,}_\d+[MF]?$")


@dataclass(frozen=True)
class ContentKey:
    key: str
    domain: str
    family: str
    tag: str
    scene: str
    kind: str  # line | name | other
    line_no: int = 0
    sub_no: tuple[int, ...] = ()
    variant: str | None = None
    option: bool = False

    @property
    def group(self) -> str:
        """Stable group id, e.g. ``activity.SayItWithFlowers``."""
        return f"{self.domain}.{self.tag or self.family}"


_NUM_RE = re.compile(r"\d+")


def parse_suffix(suffix: str) -> tuple[str, int, tuple[int, ...], str | None, bool]:
    """Parse line suffixes such as ``001``, ``05_Option1_02F_Main``, ``0002F_01``.

    Returns ``(kind, line_no, sub_numbers, variant, option)``.
    """
    if re.search(r"(?:^|_)(?:Name|name)(?:_|\d|[MF]?$)", suffix):
        variant = "F" if re.search(r"\d+F$", suffix) else None
        return ("name", 0, (), variant, False)
    core = re.sub(r"_Main$", "", suffix)
    if not re.fullmatch(r"(?:\d+[MF]?|Option\d+[MF]?)(?:_(?:\d+[MF]?|Option\d+[MF]?))*", core, re.IGNORECASE):
        return ("other", 0, (), None, False)
    numbers = [int(n) for n in _NUM_RE.findall(core)]
    if not numbers:
        return ("other", 0, (), None, False)
    variant_match = re.search(r"\d([MF])$", core)
    variant = variant_match.group(1) if variant_match else None
    # ``OptionN_01`` is the choice itself; ``OptionN_02``+ are the replies
    # that follow it, so only the first entry (or a bare ``OptionN``) counts.
    option = bool(re.search(r"Option\d+(?:[MF])?(?:_0*1[MF]?)?$", core, re.IGNORECASE))
    return ("line", numbers[0], tuple(numbers[1:]), variant, option)


def _kind(raw: str) -> str | None:
    if raw in KINDS:
        return KINDS[raw]
    if _ONGOING_RE.match(raw):
        return raw
    return None


def classify_key(key: str) -> ContentKey | None:
    """Classify one TextMap key, or ``None`` when it is not narrative text."""
    if key.startswith(LORE_PREFIXES):
        return ContentKey(key, "lore", "Lore", "", "", "other")
    if key.startswith(("Main_", "MainChat_")):
        return ContentKey(key, "main", "Main", "", "", "other")

    match = LEGACY_MAIN_GALGAME_RE.match(key)
    if match:
        return ContentKey(key, "main", "GalGame", f"Chapter{match.group(1)}", "", "other")

    match = _GENERIC_RE.match(key)
    if match and match["cat"] in CATEGORY_DOMAINS and _kind(match["kind"]):
        domain = CATEGORY_DOMAINS[match["cat"]]
        tag = match["tag"]
        if domain in {"main", "lore"}:
            return ContentKey(key, domain, _kind(match["kind"]) or "", tag or "", match["scene"], "other")
        tag = tag or match["cat"]
        if _TEST_TAG_RE.search(tag):
            return None
        kind, line_no, sub, variant, option = parse_suffix(match["suffix"])
        return ContentKey(key, domain, _kind(match["kind"]) or "", tag, match["scene"], kind, line_no, sub, variant, option)

    match = _LEGACY_GALGAME_RE.match(key)
    if match:
        tag = match["tag"]
        if _TEST_TAG_RE.search(tag):
            return None
        # GalGame_ChapterMana / ChapterQingyi: agent stories.  Other tags
        # (GoldenWeek, Special2VirtualRevenge ...) are limited-time events.
        domain = "companion" if tag.startswith("Chapter") else "activity"
        kind, line_no, sub, variant, option = parse_suffix(match["suffix"])
        return ContentKey(key, domain, "GalGame", tag, match["scene"], kind, line_no, sub, variant, option)

    for prefix, domain in _COVERED_PREFIXES.items():
        if key.startswith(prefix):
            return ContentKey(key, domain, prefix.rstrip("_"), "", "", "other")

    match = _TIMELINE_RE.match(key)
    if match:
        tag = match["tag"]
        if re.fullmatch(r"C\d+", tag) or tag.startswith(("Csr", "Cs", "QTE", "TL")):
            return ContentKey(key, "main", "ChatPlus", tag, "", "other")
        domain = "companion" if tag.startswith("PartnerDate") else "activity"
        kind, line_no, sub, variant, option = parse_suffix(match["suffix"])
        return ContentKey(key, domain, _kind(match["kind"]) or "ChatPlus", tag, match["scene"], kind, line_no, sub, variant, option)

    match = _PREFIX_CHAT_RE.match(key)
    if match:
        prefix = match["prefix"]
        family = "Bubble" if prefix.endswith("Bubble") else "Chat"
        domain = _PREFIX_CHAT_DOMAINS[prefix[: -len(family)]]
        tag = match["tag"]
        if domain == "lore":
            return ContentKey(key, domain, family, tag, "", "other")
        if _TEST_TAG_RE.search(tag):
            return None
        rest = match["rest"]
        if rest.startswith("Inlevel_"):
            rest = rest[len("Inlevel_"):]
        scene, _, suffix = rest.partition("_")
        if not suffix:
            scene, suffix = "0", scene
        # SideChat_Chapter03_0002F_01: the F marks the female scene copy.
        variant = None
        scene_match = re.fullmatch(r"(\d+)([MF])", scene)
        if scene_match:
            scene, variant = scene_match.group(1), scene_match.group(2)
        kind, line_no, sub, line_variant, option = parse_suffix(suffix)
        if kind == "line" and line_no == 0 and not sub:
            # ``_00`` rows of SideChat hold the speaker of the conversation.
            kind = "name"
        return ContentKey(key, domain, family, tag, scene, kind, line_no, sub, line_variant or variant, option)

    match = _AUTO_EVENT_RE.match(key)
    if match:
        return ContentKey(key, "hollow", "AutoEvent", "AutoEvent", match["scene"], "line", int(match["suffix"]))

    match = _LEGACY_LOWER_RE.match(key)
    if match and not _TEST_TAG_RE.search(match["tag"]):
        kind, line_no, sub, variant, option = parse_suffix(match["suffix"])
        return ContentKey(key, "legacy", "GalGame", f"Galgame{match['tag']}", match["scene"], kind, line_no, sub, variant, option)

    match = _LEGACY_CHAT_RE.match(key)
    if match:
        kind, line_no, sub, variant, option = parse_suffix(match["suffix"])
        return ContentKey(key, "legacy", "Chat", f"Chat{match['tag']}", match["scene"], kind, line_no, sub, variant, option)
    return None


def _family_of(key: str) -> str:
    parts = key.split("_")
    head = re.sub(r"\d.*$", "", parts[0]) or parts[0]
    if len(parts) > 1 and _kind(parts[1]):
        return f"{head}_{parts[1]}"
    return head


def coverage_report(text_map) -> dict:
    """Count narrative-looking keys per domain and list unknown families.

    ``unclassified`` holds key families whose shape resembles dialogue but no
    registry rule matched; review them whenever the game version changes.
    """
    domains: Counter[str] = Counter()
    domain_chars: Counter[str] = Counter()
    unknown: Counter[str] = Counter()
    unknown_chars: Counter[str] = Counter()
    examples: dict[str, str] = {}
    for key, value in text_map.items():
        parsed = classify_key(key)
        size = len(value) if isinstance(value, str) else 0
        if parsed is not None:
            domains[parsed.domain] += 1
            domain_chars[parsed.domain] += size
            continue
        if _DIALOGUE_SHAPE_RE.search(key):
            family = _family_of(key)
            unknown[family] += 1
            unknown_chars[family] += size
            examples.setdefault(family, key)
    return {
        "domains": {name: {"keys": domains[name], "chars": domain_chars[name]} for name in sorted(domains)},
        "unclassified": [
            {"family": family, "keys": count, "chars": unknown_chars[family], "example": examples[family]}
            for family, count in sorted(unknown.items(), key=lambda item: -unknown_chars[item[0]])
        ],
    }
