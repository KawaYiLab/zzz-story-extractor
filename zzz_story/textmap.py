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
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
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
    merged: dict[str, str] = {}
    base = paths.get("TextMap/TextMapTemplateTb.json")
    if base:
        merged.update(_read(base))

    if language != "CHS":
        stem = language
        lang_base = paths.get(f"TextMap/TextMap_{stem}TemplateTb.json")
        if lang_base and lang_base.exists():
            merged.update(_read(lang_base))
        else:
            print(f"warning: no TextMap_{stem} file; falling back to CHS")

    overwrite = paths.get("TextMap/TextMapOverwriteTemplateTb.json")
    if overwrite and overwrite.exists():
        merged.update(_read(overwrite))

    if language != "CHS":
        stem = language
        lang_overwrite = paths.get(f"TextMap/TextMap_{stem}OverwriteTemplateTb.json")
        if lang_overwrite and lang_overwrite.exists():
            merged.update(_read(lang_overwrite))

    return TextMap(merged, language)
