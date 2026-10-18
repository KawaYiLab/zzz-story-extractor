"""MCP server for querying the extracted ZZZ main-story text.

The tool surface intentionally mirrors the Akasha story MCP:
books / catalog / search / read / skill.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

from mcp.server import MCPServer

from .db import (
    build_database,
    connect,
    list_documents,
    list_scenes,
    read_document,
    resolve_document,
    search_lines,
)

WORLDS = {"zzz", "nap", "绝区零", "zenless"}
WORLD_LABEL = "绝区零"


def _world_ok(world: str) -> bool:
    return (world or "").strip().lower() in WORLDS


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def _snippet(text: str, keyword: str, radius: int = 42) -> str:
    index = text.lower().find(keyword.lower())
    if index < 0:
        return text[: radius * 2] + ("…" if len(text) > radius * 2 else "")
    start = max(0, index - radius)
    end = min(len(text), index + len(keyword) + radius)
    prefix = "…" if start else ""
    suffix = "…" if end < len(text) else ""
    return prefix + text[start:end].replace("\n", " ") + suffix


def _format_documents(rows: list[sqlite3.Row], title: str) -> str:
    if not rows:
        return f"[{title}]\n没有找到匹配的章节。"
    lines = [f"[{title}]", f"命中 {len(rows)} 个章节："]
    for row in rows:
        lines.append(
            f"- {row['label']} | {row['chapter']} | {row['doc_id']} | "
            f"{row['line_count']} 行 / {row['scene_count']} 场景"
        )
    return "\n".join(lines)


def _format_scenes(doc: sqlite3.Row, rows: list[sqlite3.Row]) -> str:
    lines = [
        "[zzz_catalog]",
        f"章节：{doc['label']}（{doc['chapter']}）",
        f"文档：{doc['doc_id']}，共 {doc['line_count']} 行 / {doc['scene_count']} 场景",
    ]
    for row in rows:
        speakers = json.loads(row["speakers"] or "[]")
        cast = "、".join(speakers) if speakers else "未标注"
        lines.append(
            f"- 场景 {row['scene']} | {row['family']} | {row['line_count']} 行 | 出场：{cast}"
        )
    return "\n".join(lines)


def _read_markdown(conn: sqlite3.Connection, doc: sqlite3.Row, offset: int, limit: int) -> str:
    document, rows, total = read_document(conn, doc["doc_id"], offset, limit)
    if not document:
        return f"未找到文档：{doc['doc_id']}"
    speakers_by_scene = {
        (row["scene"], row["family"]): json.loads(row["speakers"] or "[]")
        for row in conn.execute(
            "SELECT scene, family, speakers FROM scenes WHERE doc_id = ?", (doc["doc_id"],)
        ).fetchall()
    }
    lines = [
        f"# {document['label']}（{document['chapter']}）",
        f"doc_id: {document['doc_id']} | 总行数: {total} | 本次 offset={offset}, limit={limit}",
    ]
    current_scene = None
    for row in rows:
        scene_key = (row["scene"], row["family"])
        if scene_key != current_scene:
            current_scene = scene_key
            cast = "、".join(speakers_by_scene.get(scene_key, [])) or "未标注"
            lines.append("")
            lines.append(f"## 场景 {row['scene']}（{row['family']}；出场：{cast}）")
        speaker = row["speaker"] or "未标注"
        text = (row["text"] or "").replace("\n", " / ")
        lines.append(f"L{int(row['line_index']):04d} 【{speaker}】{text}")

    text = "\n".join(lines)
    if len(text) > 30_000:
        text = text[:30_000] + "\n\n[内容超过 30000 字符，请增大 offset 继续读取]"
    next_offset = offset + len(rows)
    if next_offset <= total:
        text += f"\n\n[nextOffset={next_offset}]"
    return text


def create_server(db_path: Path) -> MCPServer:
    if not Path(db_path).exists():
        raise FileNotFoundError(f"database not found: {db_path}")
    db_path = Path(db_path)

    server = MCPServer(
        name="zzz-story",
        title="绝区零主线剧情知识库",
        version="0.2.0",
        instructions=(
            "绝区零主线剧情只读检索服务。先用 zzz_search 检索关键词，"
            "再用 zzz_read 按 doc_id 读取章节原文；zzz_books/zzz_catalog 用于枚举章节和场景。"
            "回答剧情、角色关系、台词出处时请引用 doc_id 与 L 行号。"
        ),
    )

    def open_db() -> sqlite3.Connection:
        return connect(db_path)

    @server.tool(description="按章节标题或章节 token 检索绝区零主线文档，返回章节 doc_id、行数和场景数。")
    def zzz_books(
        world: str = "zzz",
        keyword: str = "",
        maxResults: int = 100,
        includeSupplement: bool = False,
    ) -> str:
        if not _world_ok(world):
            return f"本服务只包含绝区零（zzz）文本，不支持 world={world!r}。"
        max_results = _clamp(maxResults, 1, 200)
        with closing(open_db()) as conn:
            rows = list_documents(conn, keyword, max_results, includeSupplement)
            return _format_documents(rows, f"zzz_books keyword={keyword!r}")

    @server.tool(description="查看绝区零章节/场景目录；传 chapter 或 pathHash 时列出该章场景。")
    def zzz_catalog(
        world: str = "zzz",
        keyword: str = "",
        chapter: str = "",
        maxResults: int = 100,
        includeSupplement: bool = False,
    ) -> str:
        if not _world_ok(world):
            return f"本服务只包含绝区零（zzz）文本，不支持 world={world!r}。"
        max_results = _clamp(maxResults, 1, 200)
        with closing(open_db()) as conn:
            if chapter:
                doc = resolve_document(conn, chapter)
                if not doc:
                    return f"未找到章节：{chapter}"
                return _format_scenes(doc, list_scenes(conn, doc["doc_id"], max_results))
            rows = list_documents(conn, keyword, max_results, includeSupplement)
            return _format_documents(rows, f"zzz_catalog keyword={keyword!r}")

    @server.tool(description="在绝区零主线全文中检索关键词；返回场景、行号、说话人和命中片段。可用 pathHash 限定到某一章。")
    def zzz_search(
        world: str = "zzz",
        keyword: str = "",
        pathHash: str = "",
        maxResults: int = 10,
        includeSupplement: bool = False,
    ) -> str:
        if not _world_ok(world):
            return f"本服务只包含绝区零（zzz）文本，不支持 world={world!r}。"
        keyword = (keyword or "").strip()
        if not keyword:
            return "请提供 keyword。"
        max_docs = _clamp(maxResults, 1, 50)
        with closing(open_db()) as conn:
            doc_id = None
            if pathHash:
                doc = resolve_document(conn, pathHash)
                if not doc:
                    return f"未找到文档/章节：{pathHash}"
                doc_id = doc["doc_id"]
            hits = search_lines(
                conn,
                keyword,
                doc_id=doc_id,
                max_hits=max_docs * 8,
                include_supplement=includeSupplement,
            )
            if not hits:
                docs = list_documents(conn, keyword, max_docs, includeSupplement)
                if docs:
                    return (
                        f"[zzz_search] 未找到与 {keyword!r} 匹配的台词，"
                        "但在章节标题中找到：\n"
                        + _format_documents(docs, f"zzz_search keyword={keyword!r}")
                    )
                return f"[zzz_search] 未找到与 {keyword!r} 匹配的主线文本。"

            grouped: dict[tuple[str, str, str], list] = {}
            labels: dict[str, str] = {}
            for hit in hits:
                key = (hit.doc_id, hit.scene, hit.family)
                grouped.setdefault(key, []).append(hit)
                labels[hit.doc_id] = hit.label

            lines = [f"[zzz_search] keyword={keyword!r}，命中 {len(hits)} 行，{len(grouped)} 个场景"]
            for (doc_id, scene, family), scene_hits in list(grouped.items())[:max_docs]:
                lines.append("")
                lines.append(f"## {labels.get(doc_id, doc_id)} | 场景 {scene}（{family}）")
                lines.append(f"doc_id: {doc_id}（可用 zzz_read 读取整章）")
                for hit in scene_hits[:3]:
                    speaker = hit.speaker or "未标注"
                    lines.append(
                        f"- L{hit.line_index:04d} 【{speaker}】{_snippet(hit.text, keyword)}"
                    )
            return "\n".join(lines)

    @server.tool(description="按 doc_id / 章节 token / 章节标题读取绝区零主线章节原文；offset 从 1 开始，默认 30 行。")
    def zzz_read(
        world: str = "zzz",
        pathHash: str = "",
        offset: int = 1,
        limit: int = 30,
    ) -> str:
        if not _world_ok(world):
            return f"本服务只包含绝区零（zzz）文本，不支持 world={world!r}。"
        if not pathHash:
            return "请提供 pathHash（来自 zzz_search / zzz_books / zzz_catalog 的 doc_id）。"
        with closing(open_db()) as conn:
            doc = resolve_document(conn, pathHash)
            if not doc:
                return f"未找到文档/章节：{pathHash}"
            return _read_markdown(conn, doc, max(1, offset), _clamp(limit, 1, 200))

    @server.tool(description="获取绝区零剧情检索/讲述/细读的使用指引；mode 可选 search、storytelling、subtext。")
    def zzz_skill(world: str = "zzz", mode: str = "search") -> str:
        if not _world_ok(world):
            return f"本服务只包含绝区零（zzz）文本，不支持 world={world!r}。"
        mode = (mode or "search").strip().lower()
        guides = {
            "search": (
                "【检索】先用角色名、章节名、地点名、组织名或台词短句调用 zzz_search；"
                "拿到 doc_id 后用 zzz_read 读取上下文。引用时给出 doc_id 和 L 行号。"
            ),
            "storytelling": (
                "【讲述】先用 zzz_search 找到关键场景，再用 zzz_read 读完整章节；"
                "按章节时间线讲述，区分对白、旁白和玩家选项，不要补写游戏没有的设定。"
            ),
            "subtext": (
                "【细读】先用 zzz_search 定位反复出现的词或角色，再用 zzz_read 读取相邻章节；"
                "分析说话人、语气和前后文，引用具体 L 行号作为证据。"
            ),
        }
        return guides.get(mode, "mode 可选：search、storytelling、subtext。")

    @server.resource("zzz://catalog", description="绝区零主线章节目录")
    def zzz_catalog_resource() -> str:
        with closing(open_db()) as conn:
            return _format_documents(
                list_documents(conn, "", 200, include_supplement=True), "zzz://catalog"
            )

    return server


def run_mcp(
    db_path: Path,
    transport: str = "stdio",
    host: str = "127.0.0.1",
    port: int = 8765,
    path: str = "/mcp",
) -> None:
    server = create_server(Path(db_path))
    if transport == "stdio":
        server.run(transport="stdio")
    elif transport == "streamable-http":
        sys.stderr.write(
            f"zzz-story MCP listening on http://{host}:{port}{path}\n"
        )
        sys.stderr.flush()
        server.run(
            transport="streamable-http",
            host=host,
            port=port,
            streamable_http_path=path,
        )
    elif transport == "sse":
        server.run(transport="sse", host=host, port=port)
    else:
        raise ValueError(f"unsupported transport: {transport}")


def build_db_from_outputs(
    jsonl_path: Path,
    db_path: Path,
    supplement_path: Path | None = None,
):
    return build_database(jsonl_path, db_path, supplement_path)
