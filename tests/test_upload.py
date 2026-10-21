import gzip
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from zzz_story.cli import main
from zzz_story.upload import BUNDLE_FORMAT, UploadError, build_bundle, encode_bundle, upload


def make_output(root: Path) -> Path:
    out = root / "zzz_story_3.2.0_chs"
    (out / "lore" / "agents").mkdir(parents=True)
    (out / "story.jsonl").write_text('{"chapter":"Chapter00","text":"你好"}\n', encoding="utf-8")
    (out / "supplement.jsonl").write_text('{"chapter":"Chapter00","text":"补充"}\n', encoding="utf-8")
    (out / "manifest.json").write_text(json.dumps({"source_version": "3.2.0"}), encoding="utf-8")
    (out / "lore" / "README.md").write_text("# 索引", encoding="utf-8")
    (out / "lore" / "agents" / "01_狡兔屋.md").write_text("### 安比", encoding="utf-8")
    (out / "story.txt").write_text("不上传", encoding="utf-8")
    return out


def test_build_bundle_reads_outputs(tmp_path):
    out = make_output(tmp_path)
    bundle = build_bundle(out)
    assert bundle["format"] == BUNDLE_FORMAT
    assert bundle["manifest"] == {"source_version": "3.2.0"}
    assert bundle["story"].startswith('{"chapter"')
    assert bundle["supplement"].endswith("\n")
    assert set(bundle["lore"]) == {"README.md", "agents/01_狡兔屋.md"}
    assert "story.txt" not in json.dumps(bundle, ensure_ascii=False)


def test_encode_is_deterministic_gzip_json(tmp_path):
    bundle = build_bundle(make_output(tmp_path))
    a, b = encode_bundle(bundle), encode_bundle(bundle)
    assert a == b, "同一份数据每次打包字节相同，服务端才能认出重复上传"
    assert json.loads(gzip.decompress(a)) == bundle


def test_missing_story_is_a_clear_error(tmp_path):
    with pytest.raises(UploadError, match="story.jsonl"):
        build_bundle(tmp_path)


def test_legacy_bundle_scales_all_chapter_orders_without_losing_interludes(tmp_path):
    out = make_output(tmp_path)
    story_rows = [
        {"chapter": "Chapter01", "chapter_order": 2, "text": "主线", "speaker_confidence": 0.5},
        {"chapter": "Chapter02", "chapter_order": 3, "text": "下一章"},
    ]
    supplement_rows = [
        {"chapter": "Chapter01", "chapter_order": 2.0, "text": "补充"},
        {"chapter": "Chapter015", "chapter_order": 2.5, "text": "间章"},
        {"chapter": "Chapter052", "chapter_order": 9.2, "text": "第五章补充"},
        {"chapter": "Chapter058", "chapter_order": 9.8, "text": "第五章尾声"},
        {"chapter": "CS_Unknown", "chapter_order": 900.0, "text": "其他过场"},
        {"chapter": "Comic", "chapter_order": 999, "text": "漫画"},
    ]
    for name, rows in (("story", story_rows), ("supplement", supplement_rows)):
        (out / f"{name}.jsonl").write_text(
            "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8"
        )
    manifest = {"source_version": "3.2.0", "chapters": [
        {"token": "Chapter01", "order": 2},
        {"token": "Chapter015", "order": 2.5},
        {"token": "Chapter02", "order": 3},
    ]}
    (out / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    original = {name: (out / name).read_bytes() for name in ("story.jsonl", "supplement.jsonl", "manifest.json")}

    bundle = build_bundle(out)
    story = [json.loads(line) for line in bundle["story"].splitlines()]
    supplement = [json.loads(line) for line in bundle["supplement"].splitlines()]
    assert [row["chapter_order"] for row in story] == [20, 30]
    assert [row["chapter_order"] for row in supplement] == [20, 25, 92, 98, 9000, 9990]
    assert all(type(row["chapter_order"]) is int for row in story + supplement)
    assert [chapter["order"] for chapter in bundle["manifest"]["chapters"]] == [20, 25, 30]
    for before, after in zip(story_rows + supplement_rows, story + supplement):
        assert {key: value for key, value in before.items() if key != "chapter_order"} == {
            key: value for key, value in after.items() if key != "chapter_order"
        }
    assert all((out / name).read_bytes() == raw for name, raw in original.items())
    assert encode_bundle(build_bundle(out)) == encode_bundle(bundle)


def test_integer_bundle_keeps_original_jsonl_bytes_and_other_floats(tmp_path):
    out = make_output(tmp_path)
    raw = '{ "chapter": "Chapter01", "chapter_order": 20, "speaker_confidence": 0.5, "text": "主线" }\n\n'
    (out / "story.jsonl").write_text(raw, encoding="utf-8")
    bundle = build_bundle(out)
    assert bundle["story"] == raw


def test_review_explicit_scale_rejects_fractional_new_orders(tmp_path):
    out = make_output(tmp_path)
    (out / "manifest.json").write_text(json.dumps({"chapter_order_scale":10}), encoding="utf-8")
    (out / "story.jsonl").write_text('{"chapter_order":20,"text":"甲"}\n', encoding="utf-8")
    (out / "supplement.jsonl").write_text('{"chapter_order":2.5,"text":"乙"}\n', encoding="utf-8")
    with pytest.raises(UploadError, match="chapter_order"):
        build_bundle(out)


@pytest.mark.parametrize("value", [9.25, True, None, "1.0", 2**63, float("inf"), float("nan")])
def test_invalid_chapter_order_is_reported_before_upload(tmp_path, value):
    out = make_output(tmp_path)
    row = {"chapter": "Chapter00", "chapter_order": value, "text": "补充"}
    (out / "supplement.jsonl").write_text("\n" + json.dumps(row) + "\n", encoding="utf-8")
    with pytest.raises(UploadError, match="supplement.jsonl 第 2 行 chapter_order"):
        build_bundle(out)


def test_cli_rejects_invalid_jsonl_before_prompting_for_password(tmp_path, monkeypatch, capsys):
    out = make_output(tmp_path)
    (out / "supplement.jsonl").write_text("\n{broken}\n", encoding="utf-8")
    def unexpected_prompt(*args):
        pytest.fail("invalid bundles must be rejected before login")
    monkeypatch.setattr("getpass.getpass", unexpected_prompt)
    assert main(["upload", "--out", str(out), "--server", "https://example.test", "--account", "boss"]) == 2
    assert "supplement.jsonl 第 2 行解析失败" in capsys.readouterr().err


class FakeServer:
    """Records requests; answers like ik-server's login / upload / logout."""

    def __init__(self, upload_status=201, upload_body=None):
        self.requests = []
        self.upload_status = upload_status
        self.upload_body = upload_body or {"id": "7", "sourceVersion": "3.2.0", "language": "CHS",
                                           "docs": 3, "lines": 5, "speakerCoverage": 0.5}
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _reply(self, status, body=None):
                payload = b"" if body is None else json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def _record(self):
                length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(length)
                outer.requests.append((self.command, self.path, dict(self.headers), body))
                return body

            def do_POST(self):
                body = self._record()
                if self.path == "/v1/auth/login":
                    login = json.loads(body)
                    if login == {"identifier": "boss", "password": "pw", "client": "app"}:
                        self._reply(200, {"token": "iks_test"})
                    else:
                        self._reply(401, {"code": "INVALID_CREDENTIALS", "detail": "账号或密码错误"})
                elif self.path == "/v1/auth/logout":
                    self._reply(204)
                else:
                    self._reply(404)

            def do_PUT(self):
                self._record()
                if self.headers.get("Authorization") != "Bearer iks_test":
                    self._reply(401, {"code": "UNAUTHORIZED", "detail": "请先登录"})
                else:
                    self._reply(outer.upload_status, outer.upload_body)

        self.httpd = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_port}"
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()


def test_upload_logs_in_uploads_and_logs_out(tmp_path):
    data = encode_bundle(build_bundle(make_output(tmp_path)))
    with FakeServer() as server:
        result = upload(server.url + "/", data, account="boss", password="pw")
    assert result["id"] == "7"
    methods = [(m, p) for m, p, _, _ in server.requests]
    assert methods == [("POST", "/v1/auth/login"), ("PUT", "/v1/admin/story/corpus"), ("POST", "/v1/auth/logout")]
    _, _, headers, body = server.requests[1]
    assert headers["Content-Type"] == "application/gzip"
    assert body == data
    assert server.requests[2][2]["Authorization"] == "Bearer iks_test"


def test_upload_errors_are_readable(tmp_path):
    data = encode_bundle(build_bundle(make_output(tmp_path)))
    with FakeServer() as server:
        with pytest.raises(UploadError, match="登录失败.*INVALID_CREDENTIALS"):
            upload(server.url, data, account="boss", password="wrong")
    bad = {"code": "STORY_BUNDLE_INVALID", "detail": "语料包不合格：story.jsonl 第 1 行解析失败"}
    with FakeServer(upload_status=400, upload_body=bad) as server:
        with pytest.raises(UploadError, match="STORY_BUNDLE_INVALID.*第 1 行"):
            upload(server.url, data, account="boss", password="pw")
        # 失败也要退出登录，不留下多余的会话。
        assert server.requests[-1][1] == "/v1/auth/logout"
    with FakeServer(upload_status=403, upload_body={"code": "FORBIDDEN", "detail": "需要管理员权限"}) as server:
        with pytest.raises(UploadError, match="需要管理员账号"):
            upload(server.url, data, account="boss", password="pw")


def test_token_skips_login(tmp_path):
    data = encode_bundle(build_bundle(make_output(tmp_path)))
    with FakeServer() as server:
        upload(server.url, data, token="iks_test")
    assert [p for _, p, _, _ in server.requests] == ["/v1/admin/story/corpus"]


def test_cli_upload_and_save(tmp_path, monkeypatch, capsys):
    out = make_output(tmp_path)
    saved = tmp_path / "bundle.json.gz"
    monkeypatch.setenv("IK_PASSWORD", "pw")
    with FakeServer() as server:
        code = main(["upload", "--out", str(out), "--server", server.url, "--account", "boss", "--save", str(saved)])
    assert code == 0
    assert saved.read_bytes() == encode_bundle(build_bundle(out))
    printed = capsys.readouterr().out
    assert "上传完成" in printed and "版本 id 7" in printed

    # 只保存不上传。
    assert main(["upload", "--out", str(out), "--save", str(saved)]) == 0
    # 没有服务器也没有 --save：报错退出。
    monkeypatch.delenv("IK_SERVER", raising=False)
    assert main(["upload", "--out", str(out)]) == 2
