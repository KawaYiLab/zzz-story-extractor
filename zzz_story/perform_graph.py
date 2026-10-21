"""Evidence from configured GalGame assets, including explicit gender arms."""

from __future__ import annotations

from dataclasses import dataclass, field

import xxhash

from .odin import Node, OdinError, perform_entries, walk_nodes


def asset_hash(path: str) -> str:
    return str(xxhash.xxh64(("assets/napresources/" + path).lower().encode()).intdigest())


def sequence(value) -> list:
    if not isinstance(value, Node) or len(value.entries) != 1 or value.entries[0].name is not None:
        raise OdinError("expected serialized list")
    values = value.entries[0].value
    if not isinstance(values, list):
        raise OdinError("expected list array")
    return values


@dataclass
class Graph:
    name: str
    keys: set[str] = field(default_factory=set)
    avatars: dict[str, set[str]] = field(default_factory=dict)
    voices: dict[str, set[str]] = field(default_factory=dict)
    sides: dict[str, set[str]] = field(default_factory=dict)
    pairs: dict[str, str] = field(default_factory=dict)
    conditions: int = 0


def graph_from_raw(raw: bytes) -> Graph:
    name, entries = perform_entries(raw)
    roots = [e.value for e in entries if e.name == "storySections"]
    if len(roots) != 1:
        raise OdinError("missing/ambiguous storySections")
    sections = [sequence(s) for s in sequence(roots[0])]
    nodes = {}
    following = {}
    for section_idx, section in enumerate(sections):
        for sub_idx, node in enumerate(section):
            if not isinstance(node, Node) or (node.get("sectionIdx"), node.get("subSectionIdx")) != (section_idx, sub_idx):
                raise OdinError("node address does not match section array")
            address = (section_idx, sub_idx)
            nodes[address] = node
            if sub_idx + 1 < len(section):
                following[address] = (section_idx, sub_idx + 1)
    graph = Graph(name)
    occurrences = {}
    arm_occurrences = {}

    def text_keys(node):
        return {e.value for child in walk_nodes(node) for e in child.entries
                if e.name in ("dialogueKey", "textKey") and isinstance(e.value, str) and e.value}

    for address, node in nodes.items():
        keys = text_keys(node)
        graph.keys.update(keys)
        for key in keys:
            occurrences.setdefault(key, set()).add(address)
        key = node.get("dialogueKey")
        if not key:
            continue
        avatar = node.get("avatarName")
        if avatar:
            graph.avatars.setdefault(key, set()).add(avatar)
        for field_name in ("voiceKey", "externalVoiceKey"):
            voice = node.get(field_name)
            if voice:
                graph.voices.setdefault(key, set()).add(voice)

    def linear(start):
        path, seen = [], set()
        address = start
        while address in nodes and address not in seen:
            seen.add(address)
            path.append(address)
            node = nodes[address]
            kind = (node.type_name or "").split(",")[0].rsplit(".", 1)[-1]
            if kind == "GalJumpChapterNode":
                address = (node.get("chapterIndex"), node.get("subIndex"))
                if address not in nodes:
                    return []
            elif kind in {"GalPlayStoryNode", "GalPlayPictureStoryNode", "GalSwitchSceneNode", "GalActionPlayNode"}:
                address = following.get(address)
            else:
                break
        return path

    for node in nodes.values():
        if not (node.type_name or "").startswith("MoleMole.GalGame.GalConditionNode,") or node.get("conditionKey") != "Gender":
            continue
        branches = sequence(node.get("conditionList"))
        if len(branches) != 2 or {b.get("value") for b in branches} != {1, 2}:
            continue
        paths = {"M" if b.get("value") == 1 else "F": linear((b.get("bindSectionIndex"), b.get("bindSubSectionIndex"))) for b in branches}
        common = set(paths["M"]) & set(paths["F"])
        # An explicit reunion proves these are alternatives, without guessing
        # unknown condition types, section fall-through, or later choices.
        if not common:
            continue
        arms = {}
        for side, path in paths.items():
            arm = []
            for address in path:
                if address in common:
                    break
                keys = text_keys(nodes[address])
                arm.extend(sorted(keys))
                for key in keys:
                    arm_occurrences.setdefault(key, set()).add(address)
            arms[side] = arm
            for key in arm:
                graph.sides.setdefault(key, set()).add(side)
        graph.conditions += 1
        if len(arms["M"]) == len(arms["F"]):
            for male, female in zip(arms["M"], arms["F"]):
                graph.pairs[male] = female
                graph.pairs[female] = male
    for key, addresses in occurrences.items():
        if key in graph.sides and addresses - arm_occurrences.get(key, set()):
            graph.sides[key].update(("M", "F"))
    return graph


def graphs_from_cab(cab: bytes, wanted: dict[str, str]) -> dict[str, Graph]:
    """Resolve exact configured assets by AssetBundle container hash and PPtr."""
    import UnityPy

    env = UnityPy.load(cab)
    objects = {obj.path_id: obj for obj in env.objects}
    result = {}
    for obj in env.objects:
        if obj.class_id != 142:
            continue
        for key, info in obj.read().m_Container:
            path = wanted.get(key)
            if path is None or info.asset.m_FileID != 0:
                continue
            target = objects.get(info.asset.m_PathID)
            if target is None or target.class_id != 114:
                raise OdinError("configured asset has no MonoBehaviour")
            result[path] = graph_from_raw(target.get_raw_data())
    return result


def configured_routes(perform: object) -> dict[str, set[str]]:
    routes = {}
    for row in perform.get("IAEFFFFLKNB", []) if isinstance(perform, dict) else []:
        if not isinstance(row, dict):
            continue
        for field_name, side in (("BCKKFAEFDPP", "M"), ("LGJCAHIEBBK", "F")):
            path = row.get(field_name)
            if isinstance(path, str) and path.startswith("Data/ScriptConfig/Perform/Data/GalGame/") and path.endswith(".asset"):
                routes.setdefault(path, set()).add(side)
    return routes


def graph_links(graphs: dict[str, Graph], routes: dict[str, set[str]]) -> dict[str, dict]:
    links = {}
    for path, graph in graphs.items():
        declared = routes.get(path, set())
        for key in graph.keys:
            link = links.setdefault(key, {"assets": [], "sides": set(), "avatars": set(), "voice_keys": set(), "paired_keys": set()})
            link["assets"].append(path)
            link["avatars"].update(graph.avatars.get(key, set()))
            link["voice_keys"].update(graph.voices.get(key, set()))
            local = graph.sides.get(key)
            # Separate assets are only used for positive references. Absence
            # from another asset is not sufficient evidence for filtering.
            link["sides"].update(declared & local if local else declared)
            if local and key in graph.pairs:
                link["paired_keys"].add(graph.pairs[key])
    for link in links.values():
        for field_name in ("assets", "sides", "avatars", "voice_keys", "paired_keys"):
            link[field_name] = sorted(link[field_name])
        link["paired_key"] = link["paired_keys"][0] if len(link["paired_keys"]) == 1 else None
        link["explicit_gender"] = bool(link["paired_key"]) and link["sides"] in (["M"], ["F"])
    return links


def link_unused_copies(links: dict[str, dict], graphs: dict[str, Graph], routes: dict[str, set[str]], text_map) -> None:
    """Accept only duplicate-only omissions in otherwise covered namespaces."""
    import re

    key_pattern = re.compile(r"^(Main_GalGame_Chapter\d+_\d+)_(\d+)$")
    namespaces = {}
    for key in text_map.keys():
        match = key_pattern.fullmatch(key)
        if match:
            namespaces.setdefault(match[1], {})[int(match[2])] = key
    for prefix, numbered in namespaces.items():
        used = {n: key for n, key in numbered.items() if key in links}
        missing = {n: key for n, key in numbered.items() if key not in links}
        if not missing or len(used) < 10 or len(used) / len(numbered) < 0.8:
            continue
        assets = {path for key in used.values() for path in links[key]["assets"]}
        # A single common asset must serve both protagonists. Missing alternate
        # assets and partially rewritten scenes are never treated as deletions.
        if len(assets) != 1:
            continue
        path = next(iter(assets))
        if routes.get(path) != {"M", "F"} or graphs[path].name != prefix:
            continue
        copies = {}
        for n, key in missing.items():
            peers = [other for m, other in used.items() if 0 < n - m <= 3
                     and links[other]["sides"] == ["F", "M"]
                     and text_map.get(other) == text_map.get(key)]
            if len(peers) != 1:
                break
            copies[key] = peers[0]
        if len(copies) != len(missing):
            continue
        for key, peer in copies.items():
            links[key] = {**links[peer], "copy_of": peer}
