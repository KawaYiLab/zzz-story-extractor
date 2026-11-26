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
from .clean import clean_text, dialogue_readings
from .content import DOMAIN_LABELS, EXTRA_DOMAINS, ContentKey, classify_key
from .dedupe import display_side
from .event_names import EventName, infer_event_names
from .keys import natural_scene_key, source_gender_pairs
from .narrative import annotate_attribution

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
# Domains whose source tags name an event; others keep their tag or chapter.
NAMED_DOMAINS = ("activity", "side")
# Groups are numbered inside each domain; this keeps domains apart and away
# from mainline chapter orders when the server sorts groups.
DOMAIN_ORDER_BASE = 1_000_000
_INLINE_SPEAKER_RE = re.compile(r"^(?P<name>[^\s：:「」“”()（）]{1,12})[：:]\s*「(?P<text>.+)」$", re.S)
_NAME_IGNORE = {"选项", "玩家选项", "旁白", "？？？", "???"}


@dataclass
class ExtraStats:
    candidate_keys: int = 0
    name_keys: int = 0
    lines: int = 0
    speaker_lines: int = 0
    named_groups: int = 0
    group_names: dict[str, dict] = field(default_factory=dict)
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


def group_label(domain: str, tag: str, name: EventName | None = None) -> str:
    """Readable group label: inferred event name, chapter label, else the tag."""
    prefix = DOMAIN_LABELS.get(domain, domain)
    if name is not None:
        return f"{prefix} · {name.name}"
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
    scene_order: dict[str, tuple[int, int]] | None = None,
    quest_names: dict[int, str] | None = None,
    domains: Iterable[str] = EXTRA_DOMAINS,
    candidates: list[ContentKey] | None = None,
) -> tuple[list[dict], ExtraStats]:
    """Return ``(records, stats)`` for the selected extra domains.

    ``candidates`` may reuse ``candidate_keys(text_map, domains)`` from the
    caller's speaker-input preparation; no second classification is needed.
    """
    stats = ExtraStats()
    scene_order = scene_order or {}
    quest_names = quest_names or {}
    names: dict[tuple[str, str, str], list[str]] = {}
    pending = []
    if candidates is None:
        candidates = candidate_keys(text_map, domains)
    pairs = source_gender_pairs({p.key: p.variant for p in candidates}, text_map, speaker_index)

    for parsed in candidates:
        stats.candidate_keys += 1
        raw = text_map.get(parsed.key)
        if not raw:
            continue
        info = speaker_index.lookup(parsed.key) if speaker_index else None
        route = pairs[parsed.key][1] if parsed.key in pairs else display_side(info, parsed.variant)
        cleaned = clean_text(raw, route or "M")
        if not cleaned.text:
            continue
        if parsed.kind == "name":
            stats.name_keys += 1
            bucket = names.setdefault((parsed.group, parsed.family, parsed.scene), [])
            for _, name, _ in dialogue_readings(cleaned, None, route):
                if name not in bucket and name not in _NAME_IGNORE:
                    bucket.append(name)
            continue
        for side, text, speaker in dialogue_readings(cleaned, info.speaker if info else None, route):
            pending.append((parsed, text, raw, cleaned.variants, side, speaker))

    # Infer per domain so tags are matched bare (``ZenkovS1``, not ``side.ZenkovS1``).
    sources: dict[str, dict[str, dict]] = {}
    for parsed, text, *_ in pending:
        if parsed.domain in NAMED_DOMAINS:
            tag = parsed.group.split(".", 1)[1]
            group = sources.setdefault(parsed.domain, {}).setdefault(tag, {"scenes": set(), "text": []})
            group["scenes"].add(parsed.scene)
            group["text"].append(text)
    event_names: dict[str, EventName] = {}
    for domain, groups in sources.items():
        joined = {tag: {"scenes": row["scenes"], "text": "\n".join(row["text"])} for tag, row in groups.items()}
        for tag, name in infer_event_names(text_map, joined, quest_names).items():
            event_names[f"{domain}.{tag}"] = name
    stats.named_groups = len(event_names)
    stats.group_names = {
        group: {"name": name.name, "source": name.source, "evidence": name.evidence}
        for group, name in sorted(event_names.items())
    }

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
    seen_keys = set()
    for parsed, text, raw, variants, gender, speaker in pending:
        if parsed.group not in group_orders:
            index = domain_groups.get(parsed.domain, 0)
            domain_groups[parsed.domain] = index + 1
            group_orders[parsed.group] = (
                DOMAIN_ORDER_BASE * (EXTRA_DOMAINS.index(parsed.domain) + 1) + index * 10
            )
        info = speaker_index.lookup(parsed.key) if speaker_index is not None else None
        if speaker in {"选项", "玩家选项", "旁白"}:
            speaker = None
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
            "line_id": "EX_" + parsed.key + (":F" if parsed.key in seen_keys else ""),
            "domain": parsed.domain,
            "chapter": parsed.group,
            "chapter_label": group_label(parsed.domain, tag, event_names.get(parsed.group)),
            "group_name_source": event_names[parsed.group].source if parsed.group in event_names else None,
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
            "selected_variant": gender,
            "source_key": parsed.key,
            "line_type": line_type,
            "scene_speakers": list(names.get((parsed.group, parsed.family, parsed.scene), [])),
            "order_source": "source_key",
            "chronology_status": "unknown",
            "context_status": "source_key_only",
            "order": 0,
        }
        if info:
            record["speaker_confidence"] = info.confidence
            if info.perform:
                record["perform"] = info.perform
                record["context_status"] = "resource_linked"
            if info.timeline:
                record["timeline"] = info.timeline
                record["context_status"] = "resource_linked"
        records.append(record)
        seen_keys.add(parsed.key)

    annotate_attribution(records)

    for index, record in enumerate(records, 1):
        record["order"] = index
        # 100k+ rows: leave empty optional fields out; readers treat them as absent.
        for name in [name for name, value in record.items() if value is None or value is False or value == []]:
            del record[name]
        stats.lines += 1
        stats.speaker_lines += bool(record.get("speaker"))
        stats.by_domain[record["domain"]] = stats.by_domain.get(record["domain"], 0) + 1
        stats.groups[record["chapter"]] = stats.groups.get(record["chapter"], 0) + 1
    return records, stats
