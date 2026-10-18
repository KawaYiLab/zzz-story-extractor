import json

from zzz_story.db import (
    build_database,
    connect,
    list_documents,
    read_document,
    resolve_document,
    search_lines,
)


def test_build_and_query(tmp_path):
    jsonl = tmp_path / "story.jsonl"
    records = [
        {
            "chapter": "Chapter110",
            "chapter_label": "第二季 第一章",
            "chapter_order": 17,
            "scene": "11100060",
            "family": "GalGame",
            "line_no": 1,
            "speaker": "橘福福",
            "text": "师父久等了",
            "source_key": "k1",
            "line_type": "dialogue",
            "scene_speakers": ["橘福福", "铃", "哲"],
            "order": 1,
        },
        {
            "chapter": "Chapter110",
            "chapter_label": "第二季 第一章",
            "chapter_order": 17,
            "scene": "11100060",
            "family": "GalGame",
            "line_no": 2,
            "speaker": "仪玄",
            "text": "我联系徒弟了",
            "source_key": "k2",
            "line_type": "dialogue",
            "scene_speakers": ["橘福福", "铃", "哲"],
            "order": 2,
        },
        {
            "chapter": "Chapter01",
            "chapter_label": "第一季 第一章",
            "chapter_order": 2,
            "scene": "101",
            "family": "Chat",
            "line_no": 1,
            "speaker": None,
            "text": "随便看看",
            "source_key": "k3",
            "line_type": "unknown",
            "scene_speakers": [],
            "order": 3,
        },
    ]
    jsonl.write_text(
        "\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n",
        encoding="utf-8",
    )
    db = tmp_path / "story.sqlite"
    stats = build_database(jsonl, db)
    assert stats.documents == 2
    assert stats.scenes == 2
    assert stats.lines == 3

    conn = connect(db)
    docs = list_documents(conn)
    assert len(docs) == 2
    doc = resolve_document(conn, "Chapter110")
    assert doc is not None
    document, rows, total = read_document(conn, doc["doc_id"], 1, 1)
    assert document["label"] == "第二季 第一章"
    assert total == 2
    assert len(rows) == 1
    assert rows[0]["speaker"] == "橘福福"

    hits = search_lines(conn, "徒弟")
    assert len(hits) == 1
    assert hits[0].speaker == "仪玄"
    conn.close()
