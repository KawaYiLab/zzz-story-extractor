"""Publish the extracted gzip bundle to the InterKnot story archive."""

import getpass
import os
from pathlib import Path

import requests

DEFAULT_SERVER = "https://ik.tiwat.cn"


def _reply(response: requests.Response, action: str, statuses: tuple[int, ...]) -> dict:
    try:
        body = response.json()
    except ValueError:
        body = None
    if response.status_code not in statuses:
        detail = (body.get("detail") or body.get("title") or body.get("code")) if isinstance(body, dict) else None
        raise RuntimeError(f"{action}返回 HTTP {response.status_code}" + (f"：{detail}" if detail else ""))
    if not isinstance(body, dict):
        raise RuntimeError(f"无法读取后端的{action}回执。")
    return body


def _login(session: requests.Session, server: str, account: str | None) -> str:
    try:
        account = account or input("绳网管理员邮箱或用户名：").strip()
        if not account:
            raise RuntimeError("请输入绳网管理员邮箱或用户名。")
        password = os.environ.get("IK_PASSWORD") or getpass.getpass("绳网管理员密码：")
    except EOFError:
        raise RuntimeError("需要管理员账号和密码，也可以设置 IK_TOKEN 后重试。") from None
    response = session.post(
        server + "/v1/auth/login", json={"identifier": account, "password": password, "client": "app"},
        timeout=30, allow_redirects=False,
    )
    token = _reply(response, "登录", (200,)).get("token")
    if not isinstance(token, str) or not token:
        raise RuntimeError("登录回执缺少会话令牌。")
    return token


def upload_bundle(path: Path, server: str, *, account: str | None, token: str | None) -> None:
    if not path.is_file():
        raise RuntimeError(f"找不到 {path}，请先运行「一键提取.cmd」。")
    server = server.rstrip("/")
    print(f"准备将 {path.name} 上传到 {server}", flush=True)
    with path.open("rb") as data, requests.Session() as session:
        session.headers["User-Agent"] = "zzz-story-extractor/upload"
        owns_session = not token
        if owns_session:
            token = _login(session, server, account)
        session.headers["Authorization"] = f"Bearer {token}"
        try:
            print("正在上传，等待绳网后端校验语料并建立索引……", flush=True)
            response = session.put(
                server + "/v1/admin/story/corpus", data=data, headers={"Content-Type": "application/gzip"},
                timeout=(10, 300), allow_redirects=False,
            )
            receipt = _reply(response, "上传", (200, 201))
            if receipt.get("active") is not True:
                raise RuntimeError("后端尚未确认这份语料已生效。")
            if not receipt.get("id") or not receipt.get("sourceVersion"):
                raise RuntimeError("后端回执缺少语料版本信息。")
            print(f"语料已生效。游戏版本 {receipt['sourceVersion']}，语料版本 ID {receipt['id']}。", flush=True)
        finally:
            if owns_session:
                try:
                    session.post(server + "/v1/auth/logout", timeout=30, allow_redirects=False)
                except requests.RequestException:
                    pass
