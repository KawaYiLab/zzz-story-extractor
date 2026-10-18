"""Build a read-only SQLite index from story.jsonl for the MCP server."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


SCHEMA = """
CREATE TABLE documents (
    doc_id TEXT PRIMARY KEY,
    chapter TEXT UNIQUE NOT NULL,
    label TEXT NOT NULL,
    chapter_order INTEGER NOT NULL,
    line_count INTEGER NOT NULL DEFAULT 0,
    scene_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE scenes (
    scene_key TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL,
    chapter TEXT NOT NULL,
    scene TEXT NOT NULL,
    family TEXT NOT NULL,
    line_count INTEGER NOT NULL DEFAULT 0,
    speakers TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id TEXT NOT NULL,
    chapter TEXT NOT NULL,
    scene TEXT NOT NULL,
    family TEXT NOT NULL,
    line_index INTEGER NOT NULL,
    line_no INTEGER NOT NULL,
    speaker TEXT,
    speaker_alias TEXT,
    text TEXT NOT NULL,
    source_key TEXT NOT NULL,
    line_type TEXT NOT NULL,
    order_index INTEGER NOT NULL
);

CREATE INDEX idx_lines_doc ON lines(doc_id, line_index);
CREATE INDEX idx_lines_scene ON lines(doc_id, scene, family);
CREATE INDEX idx_lines_speaker ON lines(speaker);
CREATE INDEX idx_scenes_doc ON scenes(doc_id);
"""


def doc_id_for(chapter: str) -> str:
    return "doc_" + hashlib.sha1((chapter or "unknown").encode("utf-8")).hexdigest()[:12]


@dataclass
class BuildStats:
    documents: int = 0
    scenes: int = 0
    lines: int = 0


def build_database(jsonl_path: Path, db_path: Path, supplement_path: Path | None = None) -> BuildStats:
    if not jsonl_path.exists():
        raise FileNotFoundError(f"story.jsonl not found: {jsonl_path}")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    stats = BuildStats()
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    conn.execute("PRAGMA synchronous = OFF")
    conn.execute("PRAGMA journal_mode = MEMORY")

    documents: dict[str, dict] = {}
    scenes: dict[str, dict] = {}
    line_index: dict[str, int] = {}

    def ingest(path: Path, supplement: bool = False) -> None:
        nonlocal stats
        with path.open("r", encoding="utf-8") as handle:
            for raw in handle:
                raw = raw.strip()
                if not raw:
                    continue
                record = json.loads(raw)
                chapter = str(record.get("chapter") or ("补充" if supplement else "未分章"))
                if supplement:
                    chapter = "补充"
                doc_id = doc_id_for(chapter)
                label = str(record.get("chapter_label") or chapter)
                document = documents.setdefault(
                    doc_id,
                    {
                        "doc_id": doc_id,
                        "chapter": chapter,
                        "label": label,
                        "chapter_order": int(record.get("chapter_order") or 9999),
                    },
                )
                document["chapter_order"] = min(document["chapter_order"], int(record.get("chapter_order") or 9999))
                line_index[doc_id] = line_index.get(doc_id, 0) + 1
                index = line_index[doc_id]
                speaker = record.get("speaker")
                speakers = record.get("scene_speakers") or []
                scene_key = f"{doc_id}:{record.get('family')}:{record.get('scene')}"
                scene = scenes.setdefault(
                    scene_key,
                    {
                        "scene_key": scene_key,
                        "doc_id": doc_id,
                        "chapter": chapter,
                        "scene": str(record.get("scene") or ""),
                        "family": str(record.get("family") or ""),
                        "line_count": 0,
                        "speakers": [],
                    },
                )
                scene["line_count"] += 1
                for name in speakers:
                    if name and name not in scene["speakers"]:
                        scene["speakers"].append(name)
                conn.execute(
                    "INSERT INTO lines(doc_id, chapter, scene, family, line_index, line_no, speaker, "
                    "speaker_alias, text, source_key, line_type, order_index) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        doc_id,
                        chapter,
                        str(record.get("scene") or ""),
                        str(record.get("family") or ""),
                        index,
                        int(record.get("line_no") or 0),
                        speaker,
                        record.get("speaker_alias"),
                        str(record.get("text") or ""),
                        str(record.get("source_key") or ""),
                        str(record.get("line_type") or "unknown"),
                        int(record.get("order") or index),
                    ),
                )
                stats.lines += 1

    ingest(jsonl_path)
    if supplement_path and supplement_path.exists():
        ingest(supplement_path, supplement=True)

    for doc_id, document in documents.items():
        line_count = line_index.get(doc_id, 0)
        scene_count = sum(1 for scene in scenes.values() if scene["doc_id"] == doc_id)
        conn.execute(
            "INSERT INTO documents(doc_id, chapter, label, chapter_order, line_count, scene_count) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                doc_id,
                document["chapter"],
                document["label"],
                document["chapter_order"],
                line_count,
                scene_count,
            ),
        )
        stats.documents += 1

    for scene in scenes.values():
        conn.execute(
            "INSERT INTO scenes(scene_key, doc_id, chapter, scene, family, line_count, speakers) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                scene["scene_key"],
                scene["doc_id"],
                scene["chapter"],
                scene["scene"],
                scene["family"],
                scene["line_count"],
                json.dumps(scene["speakers"], ensure_ascii=False),
            ),
        )
        stats.scenes += 1

    conn.commit()
    conn.close()
    return stats


def connect(db_path: Path) -> sqlite3.Connection:
    if not db_path.exists():
        raise FileNotFoundError(f"database not found: {db_path}")
    uri = db_path.resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def resolve_document(conn: sqlite3.Connection, reference: str) -> sqlite3.Row | None:
    reference = (reference or "").strip()
    if not reference:
        return None
    row = conn.execute("SELECT * FROM documents WHERE doc_id = ?", (reference,)).fetchone()
    if row:
        return row
    row = conn.execute("SELECT * FROM documents WHERE chapter = ?", (reference,)).fetchone()
    if row:
        return row
    row = conn.execute(
        "SELECT * FROM documents WHERE label = ? ORDER BY chapter_order LIMIT 1", (reference,)
    ).fetchone()
    if row:
        return row
    row = conn.execute(
        "SELECT DISTINCT d.* FROM documents d JOIN scenes s ON s.doc_id = d.doc_id "
        "WHERE s.scene = ? ORDER BY d.chapter_order LIMIT 1",
        (reference,),
    ).fetchone()
    return row


def list_documents(
    conn: sqlite3.Connection,
    keyword: str = "",
    max_results: int = 100,
    include_supplement: bool = False,
) -> list[sqlite3.Row]:
    keyword = (keyword or "").strip()
    clauses = [] if include_supplement else ["chapter != '补充'"]
    args: list = []
    if keyword:
        pattern = f"%{keyword}%"
        clauses.append("(chapter LIKE ? OR label LIKE ?)")
        args.extend([pattern, pattern])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    args.append(max_results)
    return conn.execute(
        f"SELECT * FROM documents {where} ORDER BY chapter_order LIMIT ?", args
    ).fetchall()


def list_scenes(conn: sqlite3.Connection, doc_id: str, max_results: int = 200) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM scenes WHERE doc_id = ? ORDER BY rowid LIMIT ?", (doc_id, max_results)
    ).fetchall()


def read_document(
    conn: sqlite3.Connection, doc_id: str, offset: int = 1, limit: int = 30
) -> tuple[sqlite3.Row | None, list[sqlite3.Row], int]:
    document = conn.execute("SELECT * FROM documents WHERE doc_id = ?", (doc_id,)).fetchone()
    if not document:
        return None, [], 0
    offset = max(1, offset)
    rows = conn.execute(
        "SELECT * FROM lines WHERE doc_id = ? ORDER BY line_index LIMIT ? OFFSET ?",
        (doc_id, limit, offset - 1),
    ).fetchall()
    return document, rows, int(document["line_count"])


@dataclass
class SearchHit:
    doc_id: str
    chapter: str
    label: str
    scene: str
    family: str
    line_index: int
    line_no: int
    speaker: str | None
    text: str
    source_key: str


def search_lines(
    conn: sqlite3.Connection,
    keyword: str,
    doc_id: str | None = None,
    max_hits: int = 30,
    include_supplement: bool = False,
) -> list[SearchHit]:
    keyword = (keyword or "").strip()
    if not keyword:
        return []
    pattern = f"%{keyword}%"
    sql = (
        "SELECT l.*, d.label FROM lines l JOIN documents d ON d.doc_id = l.doc_id "
        "WHERE (l.text LIKE ? OR l.speaker LIKE ?)"
    )
    args: list = [pattern, pattern]
    if doc_id:
        sql += " AND l.doc_id = ?"
        args.append(doc_id)
    elif not include_supplement:
        sql += " AND l.chapter != '补充'"
    sql += " ORDER BY l.doc_id, l.line_index LIMIT ?"
    args.append(max_hits)
    rows = conn.execute(sql, args).fetchall()
    return [
        SearchHit(
            doc_id=row["doc_id"],
            chapter=row["chapter"],
            label=row["label"],
            scene=row["scene"],
            family=row["family"],
            line_index=int(row["line_index"]),
            line_no=int(row["line_no"]),
            speaker=row["speaker"],
            text=row["text"],
            source_key=row["source_key"],
        )
        for row in rows
    ]
