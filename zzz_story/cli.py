"""Command line interface."""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

import requests

from . import __version__
from .catalog import Catalog, find_catalog_block, find_resource_block, map_story_assets, story_asset_paths
from .diff import diff_outputs, format_diff
from .extract import extract, _cache_root
from .fetch import (
    DEFAULT_VERSION,
    detect_game_dir,
    ensure_data,
    read_game_version,
    read_json,
)
from .lore import extract_lore
from .speakers import build_speaker_index
from .textmap import load_text_map
from .upload import UploadError, build_bundle, encode_bundle, upload
from .validate import validate_output


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="zzz-story", description="Extract ZZZ main-story text.")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    extract_parser = sub.add_parser("extract", help="extract main-story text")
    extract_parser.add_argument("--lang", default="CHS", help="TextMap language (default: CHS)")
    extract_parser.add_argument("--out", type=Path, default=Path("out"), help="output directory")
    extract_parser.add_argument("--data-dir", type=Path, default=None, help="local ZenlessData clone")
    extract_parser.add_argument("--game-dir", type=Path, default=None, help="ZenlessZoneZero Game directory")
    extract_parser.add_argument("--refresh", action="store_true", help="re-download ZenlessData files")
    extract_parser.add_argument("--refresh-speakers", action="store_true", help="rebuild speaker cache")
    extract_parser.add_argument("--no-speakers", action="store_true", help="skip per-line speaker extraction")
    extract_parser.add_argument("--require-speakers", type=float, default=None, metavar="RATIO", help="fail if voice speaker coverage is below RATIO (0..1)")
    extract_parser.add_argument("--format", default="jsonl,txt", help="comma separated: jsonl,txt,csv")
    extract_parser.add_argument("--no-supplement", action="store_true", help="skip Comic/CS supplement text")
    extract_parser.add_argument("--no-dedupe", action="store_true", help="keep duplicate lines")
    extract_parser.add_argument(
        "--no-lore",
        action="store_true",
        help="skip extracting worldbuilding lore (agents, equipment, interknot, cinema, etc.)",
    )
    extract_parser.add_argument("--limit", type=int, default=None, help="only process the first N line keys (debug)")
    extract_parser.add_argument(
        "--keep-raw",
        action="store_true",
        help="always write raw_text, even when it equals the cleaned text (larger output)",
    )
    extract_parser.add_argument(
        "--only-chapter",
        default=None,
        metavar="TOKEN",
        help="only extract these chapters, comma separated (e.g. 230 or 210,220); use a separate --out",
    )
    extract_parser.add_argument(
        "--allow-issues",
        action="store_true",
        help="keep the output even if structural validation fails (see verify)",
    )
    extract_parser.add_argument(
        "--accuracy-first",
        action="store_true",
        help="保留所有候选台词，关闭分支/重复行删除和场景名单猜测；适合做完整性校对",
    )

    verify_parser = sub.add_parser("verify", help="validate a finished extraction output")
    verify_parser.add_argument("--out", type=Path, default=None, help="extraction output directory")

    diff_parser = sub.add_parser("diff", help="compare two extraction outputs line by line")
    diff_parser.add_argument("--old", type=Path, required=True, help="older output directory")
    diff_parser.add_argument("--new", type=Path, required=True, help="newer output directory")
    diff_parser.add_argument("--examples", type=int, default=3, help="example lines per chapter (0 = none)")

    lore_parser = sub.add_parser("extract-lore", help="extract only worldbuilding lore")
    lore_parser.add_argument("--lang", default="CHS", help="TextMap language (default: CHS)")
    lore_parser.add_argument("--out", type=Path, default=Path("out"), help="output directory")
    lore_parser.add_argument("--data-dir", type=Path, default=None, help="local ZenlessData clone")
    lore_parser.add_argument("--refresh", action="store_true", help="re-download ZenlessData files")
    lore_parser.add_argument("--game-dir", type=Path, default=None, help="local game resources for dialogue evidence")
    lore_parser.add_argument("--no-speakers", action="store_true", help="skip local dialogue evidence")
    lore_parser.add_argument("--accuracy-first", action="store_true", help="retain both dialogue routes")

    upload_parser = sub.add_parser(
        "upload",
        help="pack the extraction output and upload it to ik-server (story MCP corpus)",
        description="把提取结果打成语料包并上传到论坛后端（需要管理员账号）。密码从环境变量 IK_PASSWORD 读，不设则交互输入。",
    )
    upload_parser.add_argument("--out", type=Path, default=Path("out"), help="extraction output directory (same as extract --out)")
    upload_parser.add_argument("--server", default=os.environ.get("IK_SERVER"), help="server base URL, e.g. https://ik.tiwat.cn (env IK_SERVER)")
    upload_parser.add_argument("--account", default=os.environ.get("IK_ACCOUNT"), help="admin email or username (env IK_ACCOUNT)")
    upload_parser.add_argument("--token", default=os.environ.get("IK_TOKEN"), help="admin bearer token instead of account/password (env IK_TOKEN)")
    upload_parser.add_argument("--save", type=Path, default=None, help="also write the bundle (.json.gz) to this path")
    upload_parser.add_argument("--timeout", type=float, default=300.0, help="HTTP timeout in seconds")

    doctor = sub.add_parser("doctor", help="check data, game and dependencies")
    doctor.add_argument("--data-dir", type=Path, default=None)
    doctor.add_argument("--game-dir", type=Path, default=None)
    doctor.add_argument("--refresh", action="store_true")
    return parser


def _doctor(args: argparse.Namespace) -> int:
    print(f"zzz-story {__version__}")
    ok = True

    for module in ("requests", "ooz", "xxhash", "cryptography", "UnityPy"):
        try:
            __import__(module)
            print(f"  dependency {module}: ok")
        except Exception as exc:  # noqa: BLE001
            ok = False
            print(f"  dependency {module}: FAILED ({exc})")

    try:
        data_paths = ensure_data(lang="CHS", refresh=args.refresh, data_dir=args.data_dir)
        print("  TextMap/FileCfg: ok")
    except Exception as exc:  # noqa: BLE001
        print(f"  TextMap/FileCfg: FAILED ({exc})")
        return 2

    game_dir = detect_game_dir(args.game_dir)
    if not game_dir:
        print("  game directory: NOT FOUND (speakers unavailable)")
        print("  use --game-dir to point at 'ZenlessZoneZero Game'")
        return 0 if ok else 2

    print(f"  game directory: {game_dir}")
    print(f"  game version: {read_game_version(game_dir) or 'unknown'}")
    try:
        catalog_path = find_catalog_block(game_dir)
        catalog = Catalog.from_path(catalog_path)
        perform = read_json(data_paths["FileCfg/PerformTemplateTb.json"])
        assets = story_asset_paths(perform)
        by_block, matched = map_story_assets(catalog, assets)
        existing = [block for block in by_block if find_resource_block(game_dir, block)]
        print(f"  catalog: {catalog_path.name} ({catalog_path.stat().st_size / 1e6:.1f} MB)")
        print(f"  perform assets: {len(assets)} paths, {matched} matched, {len(existing)} blocks")
        if not existing:
            ok = False
            print("  perform blocks: FAILED")
    except Exception as exc:  # noqa: BLE001
        ok = False
        print(f"  perform resources: FAILED ({exc})")

    return 0 if ok else 2


def _upload(args: argparse.Namespace, out: Path) -> int:
    try:
        bundle = build_bundle(out)
        data = encode_bundle(bundle)
        print(f"语料包：{out}（{len(data) / 1e6:.1f} MB，设定 {len(bundle['lore'])} 个文件）")
        if args.save:
            args.save.parent.mkdir(parents=True, exist_ok=True)
            args.save.write_bytes(data)
            print(f"  已保存到 {args.save}")
        if not args.server:
            if args.save:
                return 0
            print("error: 需要 --server（或环境变量 IK_SERVER）", file=sys.stderr)
            return 2
        password = None
        if not args.token:
            if not args.account:
                print("error: 需要 --account（或 IK_ACCOUNT），或者用 --token", file=sys.stderr)
                return 2
            password = os.environ.get("IK_PASSWORD") or getpass.getpass(f"{args.account} 的密码：")
        print(f"上传到 {args.server} …")
        result = upload(
            args.server,
            data,
            account=args.account,
            password=password,
            token=args.token,
            timeout=args.timeout,
        )
    except UploadError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except requests.RequestException as exc:
        print(f"error: 连接 {args.server} 失败：{exc}", file=sys.stderr)
        return 2
    print("上传完成，已生效：")
    print(f"  版本 id {result.get('id')} · 数据 {result.get('sourceVersion')} {result.get('language')}")
    print(f"  {result.get('docs')} 篇 · {result.get('lines')} 行 · 说话人覆盖 {float(result.get('speakerCoverage') or 0):.0%}")
    return 0


def _parse_chapter_filter(value: str | None) -> set[str] | None:
    if not value:
        return None
    tokens = {part.strip() for part in value.split(",") if part.strip()}
    return tokens or None


def _diff(args: argparse.Namespace) -> int:
    for path in (args.old, args.new):
        if not (path / "story.jsonl").exists():
            print(f"error: {path} 里没有 story.jsonl", file=sys.stderr)
            return 2
    print(format_diff(diff_outputs(args.old, args.new, examples=args.examples)))
    return 0


def _verify(out: Path) -> int:
    if not out.exists():
        print(f"error: 找不到输出目录 {out}", file=sys.stderr)
        return 2
    issues = validate_output(out)
    if not issues:
        print(f"OK: {out} 通过校验")
        return 0
    for issue in issues:
        print(issue)
    errors = sum(1 for issue in issues if issue.level == "error")
    print(f"{len(issues)} issue(s), {errors} error(s)")
    return 1 if errors else 0


def main(argv: list[str] | None = None) -> int:
    # Chinese logs are unreadable when piped on a GBK Windows console unless
    # stdout is pinned to UTF-8 (the files themselves are always UTF-8).
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:  # noqa: BLE001 - best effort only
            pass

    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "doctor":
        return _doctor(args)

    if args.command == "verify":
        return _verify(args.out or Path("out") / f"zzz_story_{DEFAULT_VERSION}_chs")

    if args.command == "diff":
        return _diff(args)

    out = args.out
    if out == Path("out"):
        version = DEFAULT_VERSION
        out = Path("out") / f"zzz_story_{version}_chs"

    if args.command == "upload":
        return _upload(args, out)

    if args.command == "extract-lore":
        try:
            print("Loading data for lore extraction...")
            data_paths = ensure_data(lang=args.lang, refresh=args.refresh, data_dir=args.data_dir)
            text_map = load_text_map(data_paths, language=args.lang)
            avatar_path = data_paths.get("FileCfg/AvatarBaseTemplateTb.json")
            avatar_base = read_json(avatar_path) if avatar_path and avatar_path.exists() else None
            speaker_index, _ = build_speaker_index(
                text_map=text_map,
                text_keys={key for key in text_map.keys() if key.startswith(("PartnerTalk_", "Chat_PartnerTalk_"))},
                data_paths=data_paths, game_dir=detect_game_dir(args.game_dir),
                cache_path=_cache_root(args.data_dir, args.lang) / "speakers_cache.json",
                no_speakers=args.no_speakers,
            )
            stats = extract_lore(text_map, avatar_base, out, speaker_index=speaker_index, accuracy_first=args.accuracy_first)
            print("")
            print("Worldbuilding lore extraction completed successfully!")
            print(f"  agents: {stats.get('lore_agents', 0)}")
            print(f"  drive disc suits: {stats.get('lore_discs', 0)}")
            print(f"  w-engines: {stats.get('lore_w_engines', 0)}")
            print(f"  bangboos: {stats.get('lore_bangboos', 0)}")
            print(f"  collectibles: {stats.get('lore_collectibles', 0)}")
            print(f"  inter-knot quests: {stats.get('lore_quests', 0)}")
            print(f"  inter-knot messages: {stats.get('lore_messages', 0)}")
            print(f"  cinema movies: {stats.get('lore_movies', 0)} (reviews: {stats.get('lore_movie_comments', 0)})")
            print(f"  world tips: {stats.get('lore_tips', 0)}, tarot relics: {stats.get('lore_tarots', 0)}")
            print(f"  output: {out / 'lore'}")
            return 0
        except Exception as exc:  # noqa: BLE001
            print(f"error: {exc}", file=sys.stderr)
            return 2

    try:
        extract(
            out_dir=out,
            lang=args.lang,
            data_dir=args.data_dir,
            game_dir=args.game_dir,
            refresh=args.refresh,
            refresh_speakers=args.refresh_speakers,
            no_speakers=args.no_speakers,
            require_speakers=args.require_speakers,
            formats=args.format,
            include_supplement=not args.no_supplement,
            dedupe=not args.no_dedupe,
            limit=args.limit,
            include_lore=not getattr(args, "no_lore", False),
            strict=not getattr(args, "allow_issues", False),
            keep_raw=getattr(args, "keep_raw", False),
            only_chapters=_parse_chapter_filter(getattr(args, "only_chapter", None)),
            accuracy_first=getattr(args, "accuracy_first", False),
        )
    except SystemExit as exc:
        print(exc)
        return 3
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
