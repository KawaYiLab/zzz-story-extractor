"""Command line interface."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .catalog import Catalog, find_catalog_block, map_story_assets, story_asset_paths
from .db import build_database
from .extract import extract
from .fetch import (
    DEFAULT_VERSION,
    detect_game_dir,
    ensure_data,
    read_game_version,
    read_json,
)
from .mcp_server import run_mcp


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
    extract_parser.add_argument("--protagonist", choices=["M", "F", "BOTH"], default="F", help="protagonist variant (default: F)")
    extract_parser.add_argument("--format", default="jsonl,txt", help="comma separated: jsonl,txt,csv")
    extract_parser.add_argument("--no-supplement", action="store_true", help="skip Comic/CS supplement text")
    extract_parser.add_argument("--no-dedupe", action="store_true", help="keep duplicate lines")
    extract_parser.add_argument(
        "--keep-branches",
        action="store_true",
        help="keep both male/female protagonist branches instead of canonicalizing",
    )
    extract_parser.add_argument("--limit", type=int, default=None, help="only process the first N line keys (debug)")

    build_db = sub.add_parser("build-db", help="build the SQLite index used by the MCP server")
    build_db.add_argument(
        "--jsonl",
        type=Path,
        default=Path("out/zzz_story_3.2.0_chs/story.jsonl"),
        help="main story JSONL",
    )
    build_db.add_argument(
        "--supplement",
        type=Path,
        default=Path("out/zzz_story_3.2.0_chs/supplement.jsonl"),
        help="optional supplement JSONL",
    )
    build_db.add_argument("--no-supplement", action="store_true")
    build_db.add_argument(
        "--db",
        type=Path,
        default=Path("out/zzz_story_3.2.0_chs/story.sqlite"),
        help="SQLite output",
    )

    mcp_parser = sub.add_parser("mcp", help="run the read-only story MCP server")
    mcp_parser.add_argument(
        "--db",
        type=Path,
        default=Path("out/zzz_story_3.2.0_chs/story.sqlite"),
        help="SQLite index",
    )
    mcp_parser.add_argument("--transport", choices=["stdio", "streamable-http", "sse"], default="stdio")
    mcp_parser.add_argument("--host", default="127.0.0.1")
    mcp_parser.add_argument("--port", type=int, default=8765)
    mcp_parser.add_argument("--path", default="/mcp")

    doctor = sub.add_parser("doctor", help="check data, game and dependencies")
    doctor.add_argument("--data-dir", type=Path, default=None)
    doctor.add_argument("--game-dir", type=Path, default=None)
    doctor.add_argument("--refresh", action="store_true")
    return parser


def _doctor(args: argparse.Namespace) -> int:
    print(f"zzz-story {__version__}")
    ok = True

    for module in ("requests", "ooz", "xxhash", "cryptography", "mcp"):
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
        existing = [block for block in by_block if (game_dir / "ZenlessZoneZero_Data" / "StreamingAssets" / "Blocks" / f"{block}.blk").exists()]
        print(f"  catalog: {catalog_path.name} ({catalog_path.stat().st_size / 1e6:.1f} MB)")
        print(f"  perform assets: {len(assets)} paths, {matched} matched, {len(existing)} blocks")
        if not existing:
            ok = False
            print("  perform blocks: FAILED")
    except Exception as exc:  # noqa: BLE001
        ok = False
        print(f"  perform resources: FAILED ({exc})")

    return 0 if ok else 2


def _build_db(args: argparse.Namespace) -> int:
    supplement = None if args.no_supplement else args.supplement
    stats = build_database(args.jsonl, args.db, supplement)
    print(f"database: {args.db}")
    print(f"  documents: {stats.documents}")
    print(f"  scenes: {stats.scenes}")
    print(f"  lines: {stats.lines}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "doctor":
        return _doctor(args)
    if args.command == "build-db":
        return _build_db(args)
    if args.command == "mcp":
        try:
            run_mcp(
                db_path=args.db,
                transport=args.transport,
                host=args.host,
                port=args.port,
                path=args.path,
            )
        except FileNotFoundError as exc:
            print(f"error: {exc}", file=sys.stderr)
            print("run: zzz-story build-db", file=sys.stderr)
            return 2
        return 0

    out = args.out
    if out == Path("out"):
        version = DEFAULT_VERSION
        out = Path("out") / f"zzz_story_{version}_chs"

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
            protagonist=args.protagonist,
            formats=args.format,
            include_supplement=not args.no_supplement,
            dedupe=not args.no_dedupe,
            canonical_gender=not args.keep_branches,
            limit=args.limit,
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
