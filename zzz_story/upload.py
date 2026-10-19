"""Pack an extraction output directory and upload it to the InterKnot server (ik-server).

The server keeps the uploaded bundle in its database and serves it to story-summarization AIs
through MCP (``POST /v1/story/mcp``). See ikserver-rs ``deploy/README.md``.

Bundle format (must match ``ik_story::corpus::Bundle`` on the server)::

    {"format": 1, "manifest": {...}, "story": "<story.jsonl>",
     "supplement": "<supplement.jsonl>", "lore": {"agents/01_xxx.md": "..."}}

gzip-compressed JSON, sent as ``PUT /v1/admin/story/corpus`` with an admin bearer token.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

import requests

BUNDLE_FORMAT = 1
UPLOAD_PATH = "/v1/admin/story/corpus"
LOGIN_PATH = "/v1/auth/login"
LOGOUT_PATH = "/v1/auth/logout"
USER_AGENT = "zzz-story-extractor/upload"


class UploadError(RuntimeError):
    """Login or upload failed; the message is meant for the user."""


def build_bundle(out_dir: Path) -> dict[str, Any]:
    """Read story.jsonl (required), supplement.jsonl, manifest.json and lore/**/*.md."""
    story = out_dir / "story.jsonl"
    if not story.is_file():
        raise UploadError(f"{out_dir} 里没有 story.jsonl，先运行 `python -m zzz_story extract`")
    bundle: dict[str, Any] = {
        "format": BUNDLE_FORMAT,
        "manifest": None,
        "story": story.read_text(encoding="utf-8"),
        "supplement": None,
        "lore": {},
    }
    manifest = out_dir / "manifest.json"
    if manifest.is_file():
        bundle["manifest"] = json.loads(manifest.read_text(encoding="utf-8"))
    supplement = out_dir / "supplement.jsonl"
    if supplement.is_file():
        bundle["supplement"] = supplement.read_text(encoding="utf-8")
    lore_dir = out_dir / "lore"
    if lore_dir.is_dir():
        for path in sorted(lore_dir.rglob("*.md")):
            bundle["lore"][path.relative_to(lore_dir).as_posix()] = path.read_text(encoding="utf-8")
    return bundle


def encode_bundle(bundle: dict[str, Any]) -> bytes:
    raw = json.dumps(bundle, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    # mtime=0: the same data always produces the same bytes, so the server can recognize re-uploads.
    return gzip.compress(raw, compresslevel=9, mtime=0)


def _problem(response: requests.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return f"HTTP {response.status_code}: {response.text[:200]}"
    code = body.get("code", "")
    detail = body.get("detail") or body.get("title") or ""
    return f"HTTP {response.status_code} {code}: {detail}".strip()


def login(session: requests.Session, server: str, account: str, password: str, timeout: float) -> str:
    response = session.post(
        server + LOGIN_PATH,
        json={"identifier": account, "password": password, "client": "app"},
        timeout=timeout,
    )
    if response.status_code != 200:
        raise UploadError(f"登录失败：{_problem(response)}")
    token = response.json().get("token")
    if not token:
        raise UploadError("登录成功但服务器没有返回令牌")
    return token


def upload(
    server: str,
    data: bytes,
    *,
    account: str | None = None,
    password: str | None = None,
    token: str | None = None,
    timeout: float = 300.0,
) -> dict[str, Any]:
    """Upload a gzip bundle. Logs in with account/password unless a bearer token is given;
    a session created here is logged out afterwards."""
    server = server.rstrip("/")
    with requests.Session() as session:
        session.headers["User-Agent"] = USER_AGENT
        own_session = token is None
        if own_session:
            if not account or password is None:
                raise UploadError("需要管理员账号与密码（或 --token）")
            token = login(session, server, account, password, timeout)
        try:
            response = session.put(
                server + UPLOAD_PATH,
                data=data,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/gzip"},
                timeout=timeout,
            )
            if response.status_code == 403:
                raise UploadError(f"没有权限：需要管理员账号（{_problem(response)}）")
            if response.status_code == 413:
                raise UploadError("语料包超过服务器的正文上限，检查 nginx 的 client_max_body_size")
            if response.status_code not in (200, 201):
                raise UploadError(f"上传失败：{_problem(response)}")
            return response.json()
        finally:
            if own_session:
                try:
                    session.post(
                        server + LOGOUT_PATH,
                        headers={"Authorization": f"Bearer {token}"},
                        timeout=30,
                    )
                except requests.RequestException:
                    pass
