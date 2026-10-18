"""Command line interface."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .catalog import Catalog, find_catalog_block, map_story_assets, story_asset_paths
from .extract import extract
from .fetch import (
    DEFAULT_VERSION,
    detect_game_dir,
    ensure_data,
    read_game_version,
    read_json,
)
from .lore import extract_lore
from .textmap import load_text_map


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
    extract_parser.add_argument(
        "--no-lore",
        action="store_true",
        help="skip extracting worldbuilding lore (agents, equipment, interknot, cinema, etc.)",
    )
    extract_parser.add_argument("--limit", type=int, default=None, help="only process the first N line keys (debug)")

    lore_parser = sub.add_parser("extract-lore", help="extract only worldbuilding lore")
    lore_parser.add_argument("--lang", default="CHS", help="TextMap language (default: CHS)")
    lore_parser.add_argument("--out", type=Path, default=Path("out"), help="output directory")
    lore_parser.add_argument("--data-dir", type=Path, default=None, help="local ZenlessData clone")
    lore_parser.add_argument("--refresh", action="store_true", help="re-download ZenlessData files")

    doctor = sub.add_parser("doctor", help="check data, game and dependencies")
    doctor.add_argument("--data-dir", type=Path, default=None)
    doctor.add_argument("--game-dir", type=Path, default=None)
    doctor.add_argument("--refresh", action="store_true")
    return parser


def _doctor(args: argparse.Namespace) -> int:
    print(f"zzz-story {__version__}")
    ok = True

    for module in ("requests", "ooz", "xxhash", "cryptography"):
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


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "doctor":
        return _doctor(args)

    out = args.out
    if out == Path("out"):
        version = DEFAULT_VERSION
        out = Path("out") / f"zzz_story_{version}_chs"

    if args.command == "extract-lore":
        try:
            print("Loading data for lore extraction...")
            data_paths = ensure_data(lang=args.lang, refresh=args.refresh, data_dir=args.data_dir)
            text_map = load_text_map(data_paths, language=args.lang)
            avatar_path = data_paths.get("FileCfg/AvatarBaseTemplateTb.json")
            avatar_base = read_json(avatar_path) if avatar_path and avatar_path.exists() else None
            stats = extract_lore(text_map, avatar_base, out)
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
            protagonist=args.protagonist,
            formats=args.format,
            include_supplement=not args.no_supplement,
            dedupe=not args.no_dedupe,
            canonical_gender=not args.keep_branches,
            limit=args.limit,
            include_lore=not getattr(args, "no_lore", False),
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
