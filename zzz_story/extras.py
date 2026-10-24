"""Non-mainline narrative: activities, side quests, agent stories, hollow events.

These texts use the same TextMap dialogue grammar as the mainline (see
``content.py``) but are not part of ``story.jsonl``.  They are written to
``extra.jsonl`` with the same record fields the server already reads for
story lines, plus ``domain``.  Grouping is by source tag (one activity, one
agent story, one side-quest table); scene order inside a group is the
source-key order, and no playback chronology is claimed.

Speakers come from the shared speaker index when local game resources are
available, from inline ``名字：「…」`` text (hollow events), and otherwise stay
empty.  Name tables (``_Name`` keys) are kept as ``scene_speakers`` only.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

from .chapters import chapter_info
from .clean import clean_text
from .content import DOMAIN_LABELS, EXTRA_DOMAINS, ContentKey, classify_key
from .keys import natural_scene_key

# Within a group, keep families in the mainline reading order.
_FAMILY_ORDER = {
    "GalGame": 0,
    "Chat": 1,
    "ChatAudio": 2,
    "ChatPlus": 3,
    "BubbleStory": 4,
    "Bubble": 5,
    "AutoEvent": 6,
}
# Groups are numbered inside each domain; this keeps domains apart and away
# from mainline chapter orders when the server sorts groups.
DOMAIN_ORDER_BASE = 1_000_000
_INLINE_SPEAKER_RE = re.compile(r"^(?P<name>[^\s：:「」“”()（）]{1,12})[：:]\s*「(?P<text>.+)」$", re.S)
_NAME_IGNORE = {"选项", "玩家选项", "旁白", "？？？", "???"}
_F_SUFFIX_RE = re.compile(r"(\d)F((?:_Main)?)$")
_F_SCENE_RE = re.compile(r"_(\d+)F_")


@dataclass
class ExtraStats:
    candidate_keys: int = 0
    name_keys: int = 0
    lines: int = 0
    speaker_lines: int = 0
    gender_copies: int = 0
    adjacent_duplicates: int = 0
    by_domain: dict[str, int] = field(default_factory=dict)
    groups: dict[str, int] = field(default_factory=dict)


def candidate_keys(text_map, domains: Iterable[str] = EXTRA_DOMAINS) -> list[ContentKey]:
    wanted = set(domains)
    out = []
    for key in text_map.keys():
        parsed = classify_key(key)
        if parsed is not None and parsed.domain in wanted and parsed.kind in {"line", "name"}:
            out.append(parsed)
    return out


def _male_twin(key: str, text_map) -> str | None:
    """Return the base key a female-protagonist copy duplicates, if present."""
    for pattern, repl in ((_F_SUFFIX_RE, r"\1\2"), (_F_SCENE_RE, r"_\1_")):
        twin = pattern.sub(repl, key, count=1)
        if twin != key and twin in text_map:
            return twin
    return None


def group_label(domain: str, tag: str) -> str:
    """Readable group label; chapter-bound side tables reuse chapter labels."""
    prefix = DOMAIN_LABELS.get(domain, domain)
    match = re.fullmatch(r"Chapter(\d+)", tag)
    if match:
        info = chapter_info(tag)
        if info.known:
            return f"{prefix} · {info.label}"
    return f"{prefix} · {tag}"


def extract_extras(
    text_map,
    *,
    speaker_index=None,
    accuracy_first: bool = False,
    dedupe: bool = True,
    scene_order: dict[str, tuple[int, int]] | None = None,
    quest_names: dict[int, str] | None = None,
    domains: Iterable[str] = EXTRA_DOMAINS,
) -> tuple[list[dict], list[dict], ExtraStats]:
    """Return ``(records, discarded, stats)`` for the selected extra domains."""
    stats = ExtraStats()
    scene_order = scene_order or {}
    quest_names = quest_names or {}
    names: dict[tuple[str, str, str], list[str]] = {}
    pending: list[tuple[ContentKey, str, str, dict | None]] = []
    discarded: list[dict] = []
    clean_cache: dict[str, tuple[str, dict | None]] = {}

    for parsed in candidate_keys(text_map, domains):
        stats.candidate_keys += 1
        raw = text_map.get(parsed.key)
        if not raw:
            continue
        cleaned = clean_cache.get(raw)
        if cleaned is None:
            result = clean_text(raw, "M")
            cleaned = clean_cache[raw] = (result.text, result.variants)
        text, variants = cleaned
        if not text:
            continue
        if parsed.kind == "name":
            stats.name_keys += 1
            bucket = names.setdefault((parsed.group, parsed.family, parsed.scene), [])
            if text not in bucket and text not in _NAME_IGNORE:
                bucket.append(text)
            continue
        if not accuracy_first and parsed.variant == "F":
            twin = _male_twin(parsed.key, text_map)
            if twin is not None:
                stats.gender_copies += 1
                discarded.append(_discard(parsed, text, raw, "explicit_gender_variant", twin))
                continue
        pending.append((parsed, text, raw, variants))

    pending.sort(
        key=lambda item: (
            EXTRA_DOMAINS.index(item[0].domain),
            item[0].group.lower(),
            _FAMILY_ORDER.get(item[0].family, 9),
            item[0].family,
            natural_scene_key(item[0].scene),
            item[0].line_no,
            item[0].sub_no,
            item[0].variant or "",
            item[0].key,
        )
    )

    group_orders: dict[str, int] = {}
    domain_groups: dict[str, int] = {}
    records: list[dict] = []
    for parsed, text, raw, variants in pending:
        if parsed.group not in group_orders:
            index = domain_groups.get(parsed.domain, 0)
            domain_groups[parsed.domain] = index + 1
            group_orders[parsed.group] = (
                DOMAIN_ORDER_BASE * (EXTRA_DOMAINS.index(parsed.domain) + 1) + index * 10
            )
        info = speaker_index.lookup(parsed.key) if speaker_index is not None else None
        speaker = info.speaker if info and info.speaker not in _NAME_IGNORE else None
        speaker_source = info.source if speaker else "none"
        inline = _INLINE_SPEAKER_RE.match(text) if not speaker else None
        if inline and inline["name"] not in _NAME_IGNORE:
            speaker = inline["name"]
            speaker_source = "inline"
        option = parsed.option or bool(speaker_index is not None and speaker_index.is_option(parsed.key))
        if option:
            line_type, speaker, speaker_source = "option", None, "none"
        elif speaker:
            line_type = "dialogue"
        else:
            line_type = "unknown"
        quest_name = None
        archived = scene_order.get(parsed.scene)
        if archived and archived[1]:
            quest_name = quest_names.get(archived[1])
        tag = parsed.tag or parsed.family
        record = {
            "line_id": "EX_" + parsed.key,
            "domain": parsed.domain,
            "chapter": parsed.group,
            "chapter_label": group_label(parsed.domain, tag),
            "chapter_order": group_orders[parsed.group],
            "scene": parsed.scene,
            "scene_title": None,
            "quest_name": quest_name,
            "family": parsed.family,
            "line_no": parsed.line_no,
            "sub_no": list(parsed.sub_no) or None,
            "variant": parsed.variant,
            "speaker": speaker,
            "speaker_source": speaker_source,
            "has_voice": bool(info and info.has_voice),
            "text": text,
            "raw_text": raw if raw != text else None,
            "text_variants": variants,
            "source_key": parsed.key,
            "line_type": line_type,
            "scene_speakers": list(names.get((parsed.group, parsed.family, parsed.scene), [])),
            "order_source": "source_key",
            "chronology_status": "unknown",
            "context_status": "source_key_only",
            "order": 0,
        }
        if dedupe and not accuracy_first and records:
            previous = records[-1]
            if (
                previous["source_key"] != record["source_key"]
                and previous["chapter"] == record["chapter"]
                and previous["family"] == record["family"]
                and previous["scene"] == record["scene"]
                and previous["text"] == record["text"]
                and previous["speaker"] == record["speaker"]
            ):
                stats.adjacent_duplicates += 1
                discarded.append(_discard(parsed, text, raw, "adjacent_duplicate", previous["source_key"]))
                continue
        records.append(record)

    for index, record in enumerate(records, 1):
        record["order"] = index
        # 100k+ rows: leave empty optional fields out; readers treat them as absent.
        for name in [name for name, value in record.items() if value is None or value is False or value == []]:
            del record[name]
        stats.lines += 1
        stats.speaker_lines += bool(record.get("speaker"))
        stats.by_domain[record["domain"]] = stats.by_domain.get(record["domain"], 0) + 1
        stats.groups[record["chapter"]] = stats.groups.get(record["chapter"], 0) + 1
    return records, discarded, stats


def _discard(parsed: ContentKey, text: str, raw: str, reason: str, paired: str) -> dict:
    return {
        "source_key": parsed.key,
        "domain": parsed.domain,
        "chapter": parsed.group,
        "scene": parsed.scene,
        "family": parsed.family,
        "text": text,
        "raw_text": raw,
        "reason": reason,
        "paired_source_key": paired,
    }


def render_extra_txt(records: list[dict]) -> str:
    chunks = [
        "# 绝区零活动、支线与代理人剧情",
        "",
        "按来源表分组；场景按来源键编号排列，不代表游戏内播放先后。",
    ]
    current_domain = current_group = current_scene = None
    for record in records:
        if record["domain"] != current_domain:
            current_domain = record["domain"]
            current_group = None
            chunks.extend(["", f"## {DOMAIN_LABELS.get(current_domain, current_domain)}"])
        if record["chapter"] != current_group:
            current_group = record["chapter"]
            current_scene = None
            chunks.extend(["", f"### {record['chapter_label']}"])
        scene_key = (record["family"], record["scene"])
        if scene_key != current_scene:
            current_scene = scene_key
            title = record.get("quest_name") or f"{record['family']} {record['scene']}"
            chunks.extend(["", f"#### {title}"])
            if record.get("scene_speakers"):
                chunks.append(f"（姓名表：{'、'.join(record['scene_speakers'])}；不代表逐句署名）")
            chunks.append("")
        text = record["text"]
        if record.get("line_type") == "option":
            chunks.append(f"> 选项：{text}")
        elif record.get("speaker") and record.get("speaker_source") != "inline":
            chunks.append(f"{record['speaker']}：{text}")
        else:
            chunks.append(text)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(chunks).strip()) + "\n"
