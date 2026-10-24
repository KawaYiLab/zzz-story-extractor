"""Source identities for agent interactions, independent of speaker attribution."""

from __future__ import annotations

import re
from dataclasses import dataclass

PARTNER_DIALOGUE_PREFIXES = (
    "PartnerTalk_", "Chat_PartnerTalk_", "PartnerTalkChat_",
    "PartnerTalkBubble_", "PartnerDate_",
)

_LINE = re.compile(r"^(?:\d+(?:_\d+)*|Option\d+_\d+|Bubble\d+|NPC\d+)(?:_?([MF]))?$", re.IGNORECASE)


@dataclass(frozen=True)
class PartnerDialogue:
    scope: str
    family: str
    agent_tag: str | None
    event: str
    sequence: str
    variant: str | None

    @property
    def group(self) -> tuple[str, str, str, str | None]:
        return self.scope, self.family, self.event, self.agent_tag


def parse_partner_dialogue(key: str) -> PartnerDialogue | None:
    """Keep nested event IDs and source families; name tables are metadata."""
    if not key.startswith(PARTNER_DIALOGUE_PREFIXES):
        return None
    if any(re.fullmatch(r"(?:Name|Nametag)\d*[MF]?", part, re.IGNORECASE) for part in key.split("_")):
        return None
    if key.startswith("Chat_PartnerTalk_"):
        scope, family, rest = "Chat_PartnerTalk", "Chat", key[len("Chat_PartnerTalk_"):]
    elif key.startswith("PartnerTalkChat_"):
        scope, family, rest = "PartnerTalkChat", "Chat", key[len("PartnerTalkChat_"):]
    elif key.startswith("PartnerTalkBubble_"):
        scope, family, rest = "PartnerTalkBubble", "Bubble", key[len("PartnerTalkBubble_"):]
    else:
        scope, rest = key.split("_", 1)
        if "_" not in rest:
            return None
        family, rest = rest.split("_", 1)
    parts = rest.split("_")
    tag = None
    if parts and not parts[0].isdigit():
        tag = parts.pop(0)
    if family == "GalGame" and len(parts) >= 2:
        event, suffix = parts[0], "_".join(parts[1:])
        match = _LINE.fullmatch(suffix)
        if not match:
            return None
        variant = match.group(1).upper() if match.group(1) else None
        return PartnerDialogue(scope, family, tag, event, suffix, variant)
    # Only the final token (plus an explicit M/F suffix) is a line number.
    # Earlier numeric tokens belong to the encounter, not a merged sequence.
    suffix = parts[-1] if parts else ""
    if suffix in {"M", "F"} and len(parts) >= 2:
        suffix = parts[-2] + "_" + suffix
        parts = parts[:-2]
    elif parts:
        parts = parts[:-1]
    match = _LINE.fullmatch(suffix)
    if not match:
        return None
    event = "_".join(parts)
    if not event:
        # Standalone narrative snippets have no encounter metadata.
        event = "source:" + suffix
    variant = match.group(1).upper() if match.group(1) else None
    return PartnerDialogue(scope, family, tag, event, suffix, variant)


def sequence_order(token: str) -> tuple:
    return tuple(int(value) for value in re.findall(r"\d+", token)), token
