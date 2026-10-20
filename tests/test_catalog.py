from zzz_story.catalog import Catalog, map_story_assets, story_asset_paths
from zzz_story.speakers import (
    alias_from_source,
    canonical_text_id,
    normalize_name,
    resolve_alias,
)

import struct
import xxhash

from zzz_story.perform import (
    avatar_links_from_cab,
    dialogue_links_from_cab,
    option_keys_from_cab,
    scan_cab,
)


def test_alias_from_source():
    assert alias_from_source("GalGame_Chapter00_Susie_002_002") == "Susie"
    assert alias_from_source("Galgame_Chapter0_Wise_72") == "Wise"
    assert alias_from_source("VO_Galgame/Ver1_0/VO_Anbi/GalGame_Chapter00_001") == "Anbi"
    assert alias_from_source("GalGame_ChapterMana_08_02") is None


def test_resolve_alias():
    aliases = {
        "hugovlad": "雨果",
        "wise": "哲",
        "sunbringer": "挽昼",
        "lindvein": "林德薇恩",
    }
    assert resolve_alias("Hugo", aliases) == "雨果"
    assert resolve_alias("StudentWise", aliases) == "哲"
    assert resolve_alias("LindveinSkin01", aliases) == "林德薇恩"
    assert resolve_alias("Unknown", aliases) is None


def test_normalize_and_canonical():
    assert normalize_name("Ye Shunguang") == "yeshunguang"
    assert canonical_text_id("Main_GalGame_Chapter110_11100060_001") == (
        "galgame_chapter110_11100060_001"
    )


def test_story_asset_paths():
    payload = {
        "a": "Data/ScriptConfig/Perform/Data/GalGame/Chapter00/x.asset",
        "b": ["Data/ScriptConfig/Perform/Data/Chat/Chapter01/y.asset"],
        "c": "Data/ScriptConfig/Perform/Data/Activity/z.asset",
    }
    found = story_asset_paths(payload)
    assert len(found) == 2
    assert any("GalGame" in path for path in found)
    assert any("Chat" in path for path in found)


def test_catalog_mapping():
    path = "Data/ScriptConfig/Perform/Data/GalGame/Chapter00/test.asset"
    asset_hash = xxhash.xxh64(("assets/napresources/" + path).lower().encode()).intdigest()
    asset_count = 1
    block_count = 1
    bundle_count = 1
    assets_start = 52
    blocks_start = assets_start + asset_count * 12
    bundles_start = blocks_start + block_count * 9
    bundles_end = bundles_start + bundle_count * 28
    raw = bytearray(bundles_end)
    struct.pack_into("<I", raw, 8, asset_count)
    struct.pack_into("<I", raw, 12, block_count)
    struct.pack_into("<I", raw, 16, bundle_count)
    struct.pack_into("<I", raw, 20, assets_start)
    struct.pack_into("<Q", raw, 28, blocks_start)
    struct.pack_into("<Q", raw, 36, bundles_start)
    struct.pack_into("<Q", raw, 44, bundles_end)
    struct.pack_into("<I", raw, assets_start, 0)
    struct.pack_into("<Q", raw, assets_start + 4, asset_hash)
    struct.pack_into("<I", raw, blocks_start + 1, 12345)
    struct.pack_into("<I", raw, bundles_start, 0)

    catalog = Catalog(bytes(raw))
    by_block, matched = map_story_assets(catalog, {path})
    assert matched == 1
    assert 12345 in by_block
    assert path in by_block[12345]


def test_scan_cab_matches_individual_scanners():
    # CAB strings are UTF-16LE values separated by non-UTF16 bytes.  Keeping
    # the fixture small makes it easy to compare the shared one-pass scanner
    # with the three public compatibility helpers.
    values = [
        "avatarName",
        "Avatar_Test",
        "dialogueKey",
        "Main_GalGame_Chapter00_10000001_001",
        "externalVoiceKey",
        "GalGame_Chapter00_Susie_001",
        "textKey",
        "Main_GalGame_Chapter00_10000001_Option1_01",
        "avatarName",
        "nodeMark",
        "dialogueKey",
        "Main_GalGame_Chapter00_10000001_002",
    ]
    cab = b"\xff".join(value.encode("utf-16le") for value in values)

    links, avatars, options = scan_cab(cab)
    assert links == list(dialogue_links_from_cab(cab))
    assert avatars == list(avatar_links_from_cab(cab))
    assert options == list(option_keys_from_cab(cab))
