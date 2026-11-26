"""Stream the archive's format-1 JSON bundle into a gzip file."""

import gzip
import json
from pathlib import Path
from typing import TextIO

MAX_UPLOAD_BYTES = 64 * 1024 * 1024
MAX_BUNDLE_BYTES = 512 * 1024 * 1024


def _write_member(output: TextIO, path: Path) -> None:
    # Each JSONL or Markdown file is one JSON string in the archive protocol.
    output.write('"')
    with path.open(encoding="utf-8") as source:
        while chunk := source.read(128 * 1024):
            output.write(json.dumps(chunk, ensure_ascii=False)[1:-1])
    output.write('"')


def write_bundle(corpus: Path, destination: Path) -> None:
    with gzip.open(destination, "wt", encoding="utf-8", newline="\n", compresslevel=6) as out:
        out.write('{"format":1,"manifest":')
        with (corpus / "manifest.json").open(encoding="utf-8") as manifest:
            json.dump(json.load(manifest), out, ensure_ascii=False, separators=(",", ":"))
        for name in ("story", "supplement", "extra"):
            out.write(f',"{name}":')
            path = corpus / f"{name}.jsonl"
            if name != "story" and not path.is_file():
                out.write("null")
            else:
                _write_member(out, path)
        out.write(',"lore":{')
        lore = corpus / "lore"
        members = sorted(p for p in lore.rglob("*") if p.is_file() and p.suffix in {".md", ".jsonl"})
        for index, path in enumerate(members):
            if index:
                out.write(",")
            out.write(json.dumps(path.relative_to(lore).as_posix(), ensure_ascii=False))
            out.write(":")
            _write_member(out, path)
        out.write("}}")
        out.flush()
        if out.buffer.tell() > MAX_BUNDLE_BYTES:
            raise ValueError("语料包解压后超过绳网后端的 512 MiB 导入上限")
    if destination.stat().st_size > MAX_UPLOAD_BYTES:
        raise ValueError("语料包超过绳网后端的 64 MiB 上传上限")
