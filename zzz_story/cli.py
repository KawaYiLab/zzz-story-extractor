"""Build the corpus consumed by the InterKnot story archive."""

import argparse
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import requests

from .bundle import write_bundle
from .extract import extract
from .upload import DEFAULT_SERVER, upload_bundle


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="zzz-story", description="默认提取绳网剧情档案库语料。")
    upload = parser.add_subparsers(dest="command").add_parser("upload", help="上传已有的语料包")
    upload.add_argument("--server", default=os.environ.get("IK_SERVER") or DEFAULT_SERVER, help="绳网后端地址")
    upload.add_argument("--account", default=os.environ.get("IK_ACCOUNT"), help="管理员邮箱或用户名")
    upload.add_argument("--token", default=os.environ.get("IK_TOKEN"), help="管理员会话令牌")
    args = parser.parse_args(argv)
    destination = Path("out/story-corpus.json.gz").resolve()
    if args.command == "upload":
        try:
            upload_bundle(destination, args.server, account=args.account, token=args.token)
        except requests.RequestException as exc:
            print(f"未收到绳网后端的确认（{type(exc).__name__}）。请检查网络和后端地址后重试。", file=sys.stderr)
            return 1
        except (OSError, RuntimeError) as exc:
            print(f"上传未完成：{exc}", file=sys.stderr)
            return 1
        return 0
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(dir=destination.parent, prefix=".extract-") as temporary:
            work = Path(temporary)
            extract(out_dir=work)
            staged = work / destination.name
            print("正在打包绳网剧情语料……", flush=True)
            write_bundle(work, staged)
            staged.replace(destination)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"提取失败：{exc}", file=sys.stderr)
        return 1
    print(f"提取完成。语料包位于 {destination}")
    return 0
