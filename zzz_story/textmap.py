"""Load and merge TextMap files."""

from __future__ import annotations

import json
from pathlib import Path


class TextMap:
    def __init__(self, mapping: dict[str, str], language: str):
        self._mapping = mapping
        self.language = language

    def get(self, key: str, default: str = "") -> str:
        value = self._mapping.get(key, default)
        return value if isinstance(value, str) else default

    def __contains__(self, key: str) -> bool:
        return key in self._mapping

    def __len__(self) -> int:
        return len(self._mapping)

    def keys(self):
        return self._mapping.keys()

    def items(self):
        return self._mapping.items()


def _read(path: Path) -> dict[str, str]:
    def unique_pairs(pairs):
        mapping = {}
        for key, value in pairs:
            if key in mapping and mapping[key] != value:
                raise ValueError(f"{path}: conflicting TextMap values for {key!r}")
            mapping[key] = value
        return mapping

    with path.open("r", encoding="utf-8-sig") as handle:
        payload = json.load(handle, object_pairs_hook=unique_pairs)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} is not a JSON object")
    return {str(k): v for k, v in payload.items() if isinstance(v, str)}


def load_language_map(paths: dict[str, Path], language: str) -> dict[str, str]:
    """Load one language file without merging the CHS base table."""
    language = language.upper()
    if language == "CHS":
        base = paths.get("TextMap/TextMapTemplateTb.json")
        overwrite = paths.get("TextMap/TextMapOverwriteTemplateTb.json")
    else:
        base = paths.get(f"TextMap/TextMap_{language}TemplateTb.json")
        overwrite = paths.get(f"TextMap/TextMap_{language}OverwriteTemplateTb.json")
    merged: dict[str, str] = {}
    if base and base.exists():
        merged.update(_read(base))
    if overwrite and overwrite.exists():
        merged.update(_read(overwrite))
    return merged


def load_text_map(paths: dict[str, Path], language: str = "CHS") -> TextMap:
    language = language.upper()
    # Finish the fallback language before applying the requested language.
    # A CHS hotfix must never overwrite a translated base-table value.
    merged = load_language_map(paths, "CHS")
    if language != "CHS":
        translated = load_language_map(paths, language)
        if not translated:
            print(f"warning: no TextMap_{language} values; falling back to CHS")
        merged.update(translated)
    return TextMap(merged, language)
