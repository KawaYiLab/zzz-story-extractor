import gzip
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from zzz_story.cli import main

LOGIN = "/v1/auth/login"
UPLOAD = "/v1/admin/story/corpus"
LOGOUT = "/v1/auth/logout"
RECEIPT = {"id": "42", "sourceVersion": "3.3.0", "active": True}


@pytest.fixture
def backend(monkeypatch):
    calls = []
    replies = {LOGIN: (200, {"token": "iks_session"}), UPLOAD: (201, RECEIPT), LOGOUT: (204, None)}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def respond(self):
            size = int(self.headers.get("Content-Length", 0))
            calls.append((self.command, self.path, self.headers, self.rfile.read(size)))
            status, value = replies[self.path]
            body = b"" if value is None else json.dumps(value).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        do_POST = do_PUT = respond

    with HTTPServer(("127.0.0.1", 0), Handler) as httpd:
        url = f"http://127.0.0.1:{httpd.server_port}"
        monkeypatch.setenv("IK_SERVER", url)
        monkeypatch.setenv("NO_PROXY", "127.0.0.1")
        for var in ("IK_ACCOUNT", "IK_PASSWORD", "IK_TOKEN"):
            monkeypatch.delenv(var, raising=False)
        thread = threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
        thread.start()
        try:
            yield url, calls, replies
        finally:
            httpd.shutdown()
            thread.join()


@pytest.fixture
def bundle(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "out/story-corpus.json.gz"
    path.parent.mkdir()
    data = {"format": 1, "manifest": {"source_version": "3.3.0"}, "story": '{"text":"哲与铃"}\n'}
    path.write_bytes(gzip.compress(json.dumps(data, ensure_ascii=False).encode(), mtime=42))
    return path


def test_upload_prompts_and_sends_the_exact_file(backend, bundle, monkeypatch, capsys):
    url, calls, _ = backend
    monkeypatch.setattr("builtins.input", lambda prompt: "admin@example.test")
    monkeypatch.setattr("getpass.getpass", lambda prompt: "private-password")
    data = bundle.read_bytes()
    assert main(["upload", "--server", url + "/"]) == 0
    assert [(m, p) for m, p, _, _ in calls] == [("POST", LOGIN), ("PUT", UPLOAD), ("POST", LOGOUT)]
    assert json.loads(calls[0][3]) == {"identifier": "admin@example.test", "password": "private-password", "client": "app"}
    assert calls[1][2]["Authorization"] == calls[2][2]["Authorization"] == "Bearer iks_session"
    assert calls[1][2]["Content-Type"] == "application/gzip"
    assert calls[1][3] == bundle.read_bytes() == data
    captured = capsys.readouterr()
    assert "语料已生效" in captured.out and "3.3.0" in captured.out and "42" in captured.out
    assert "private-password" not in captured.out + captured.err and "iks_session" not in captured.out + captured.err


def test_upload_with_existing_token_only_sends_the_bundle(backend, bundle, monkeypatch):
    _, calls, _ = backend
    monkeypatch.setenv("IK_TOKEN", "iks_existing")
    assert main(["upload"]) == 0
    assert [(m, p) for m, p, _, _ in calls] == [("PUT", UPLOAD)]
    assert calls[0][2]["Authorization"] == "Bearer iks_existing"
    assert calls[0][3] == bundle.read_bytes()


@pytest.mark.parametrize(("status", "body", "error"), [
    (403, {"detail": "需要管理员权限"}, "需要管理员权限"),
    (503, {"detail": "剧情库正在更新"}, "剧情库正在更新"),
    (202, {"id": "42"}, "HTTP 202"),
    (201, None, "回执"),
    (201, {**RECEIPT, "active": False}, "尚未确认"),
    (201, {"active": True}, "缺少语料版本信息"),
])
def test_unsuccessful_upload_reports_error_and_logs_out(backend, bundle, monkeypatch, capsys, status, body, error):
    _, calls, replies = backend
    replies[UPLOAD] = (status, body)
    monkeypatch.setenv("IK_ACCOUNT", "admin")
    monkeypatch.setenv("IK_PASSWORD", "private-password")
    assert main(["upload"]) != 0
    assert [p for _, p, _, _ in calls] == [LOGIN, UPLOAD, LOGOUT]
    captured = capsys.readouterr()
    assert error in captured.err and "语料已生效" not in captured.out


def test_login_failure_stops_before_upload(backend, bundle, monkeypatch, capsys):
    _, calls, replies = backend
    replies[LOGIN] = (401, {"detail": "账号或密码错误"})
    monkeypatch.setenv("IK_PASSWORD", "wrong-password")
    assert main(["upload", "--account", "admin"]) != 0
    assert [p for _, p, _, _ in calls] == [LOGIN]
    assert "账号或密码错误" in capsys.readouterr().err


def test_missing_bundle_stops_before_credentials_or_network(backend, tmp_path, monkeypatch, capsys):
    _, calls, _ = backend
    monkeypatch.chdir(tmp_path)
    assert main(["upload"]) != 0
    assert "一键提取.cmd" in capsys.readouterr().err
    assert calls == [] and not (tmp_path / "out").exists()
