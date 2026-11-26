"""Evidence-based route/copy filtering shared by all narrative domains."""

from __future__ import annotations


def referenced_sides(perform: dict | None, timeline: dict | None) -> set[str]:
    return {side for link in (perform, timeline) if link and not link.get("copy_of")
            for side in link.get("sides", [])}


def display_side(info, variant: str | None, protagonist: str | None = None) -> str | None:
    if info:
        sides = referenced_sides(info.perform, info.timeline)
        if len(sides) == 1:
            return next(iter(sides))
        if sides:
            return protagonist
    return variant or protagonist


def paired_route_order(male_sides: set[str], female_sides: set[str]) -> tuple[str, str] | None:
    """Resolve an already matched pair. Opposed resource references outrank a key or speaker."""
    if male_sides == {"F"} and female_sides == {"M"}:
        return "F", "M"
    if male_sides <= {"M"} and female_sides <= {"F"}:
        return "M", "F"
    return None

