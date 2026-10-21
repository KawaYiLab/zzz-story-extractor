"""Chapter labels and ordering.

The token map is deliberately data-driven: unknown tokens are kept and get a
derived label instead of being dropped.  The labels below are the 3.3.0 main
story order and can be edited when a new version adds chapters.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache


# Explicit order also acts as the tie-breaker for tokens that share a chapter.
ORDERED_TOKENS: list[str] = [
    "000", "00",
    "01",
    "02",
    "025",
    "03",
    "04", "040",
    "050", "05",
    "06", "060",
    "07", "070",
    "08", "09", "090",
    "110", "120", "130", "140", "150", "160", "170", "180", "190",
    "210", "220", "230", "240",
]

LABELS: dict[str, str] = {
    "000": "序章",
    "00": "序章",
    "01": "第一季 第一章",
    "02": "第一季 第二章",
    "025": "第一季 第二章间章",
    "03": "第一季 第三章",
    "04": "第一季 第四章",
    "040": "第一季 第四章",
    "050": "第一季 第五章",
    "05": "第一季 第五章",
    "06": "第一季 尾音",
    "060": "第一季 尾音 上",
    "07": "第一季 尾音",
    "070": "第一季 尾音 下",
    "08": "第二季 序章",
    "09": "第二季 序章",
    "090": "第二季 序章",
    "110": "第二季 第一章 云霞同归处",
    "120": "第二季 第二章 迟吟的浪涌",
    "130": "第二季 第三章 不要温和地走入那良夜",
    "140": "第二季 第四章 可曾记得梦",
    "150": "第二季 第五章 将临未抵的深渊",
    "160": "第二季 第六章 微光引灯时",
    "170": "第二季 间章 旧梦的安可曲",
    "180": "第二季 尾音 新·艾利都日落时 上",
    "190": "第二季 尾音 新·艾利都日落时 下",
    "210": "第三季 第一章 某个梦游者的自白",
    "220": "第三季 第二章 漫长的告别",
    "230": "第三季 第三章 她与她的隐秘往事",
    "240": "第三季 第四章 重返天空的旅程",
}

# Leave integer slots between chapters for supplement-only interludes.  The
# server's chapter_order is i64, so fractional positions must not reach JSONL.
CHAPTER_ORDER_SCALE = 10
_INDEX = {token: i * CHAPTER_ORDER_SCALE for i, token in enumerate(ORDERED_TOKENS)}
_CHAPTER_RE = re.compile(r"^Chapter(?P<short>.+)$", re.IGNORECASE)
_SEASON_CHAPTER_RE = re.compile(r"^([1-9])(\d)$")


@dataclass(frozen=True)
class ChapterInfo:
    token: str
    short: str
    order: int
    label: str
    known: bool


@lru_cache(maxsize=512)
def short_token(token: str) -> str:
    match = _CHAPTER_RE.match(token or "")
    return match.group("short") if match else (token or "")


@lru_cache(maxsize=512)
def chapter_info(token: str) -> ChapterInfo:
    short = short_token(token)
    if short in _INDEX:
        return ChapterInfo(token, short, _INDEX[short], LABELS[short], True)

    # Best-effort derivation for future chapters. Examples: 250 -> S3 ch5
    # (3-digit tokens: first digit is the zero-based season), 300 -> S4 ch0.
    derived = _derive(short)
    return ChapterInfo(token, short, (10_000 + derived[0]) * CHAPTER_ORDER_SCALE, derived[1], False)


def _derive(short: str) -> tuple[int, str]:
    if re.fullmatch(r"\d{3}", short):
        season = int(short[0]) + 1
        chapter = int(short[1:]) // 10
        if chapter <= 0:
            return (season * 100 + chapter, f"第{season}季 序章")
        return (season * 100 + chapter, f"第{season}季 第{chapter}章")
    if re.fullmatch(r"\d{2}", short):
        chapter = int(short)
        return (100 + chapter, f"第一季 第{chapter}章")
    if re.fullmatch(r"\d+", short):
        return (900 + int(short), f"第{short}章")
    return (9_000, short or "未分章")


def sort_key(token: str) -> tuple[int, str]:
    info = chapter_info(token)
    return (info.order, info.short)


def label_for(token: str) -> str:
    return chapter_info(token).label


def season_chapter_token(season: int, chapter: int) -> str:
    """Main-story token for ``第<season>季 第<chapter>章``.

    The 3.2.0 numbering makes the hundreds digit mean "season - 1", so
    2.1 -> 110, 3.1 -> 210 and 3.4 -> 240. ``_derive`` is the exact
    inverse of this function; keep the two in sync.
    """
    if season < 1 or chapter < 0:
        raise ValueError(f"invalid season/chapter: {season}.{chapter}")
    return f"{(season - 1) * 100 + chapter * 10:03d}"


def parse_season_chapter(token: str) -> tuple[int, int] | None:
    """Parse a ``"21"`` / ``"34"`` style supplement prefix into (season, chapter).

    Season 1 supplement keys are irregular (``01.5``, ``028``, ``05.2``) and
    have no season digit, so they return ``None`` and stay in an explicit table.
    """
    match = _SEASON_CHAPTER_RE.fullmatch(token or "")
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))
