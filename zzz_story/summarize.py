"""Generated plot summaries: an AI-written layer over the extracted story text.

``summarize`` reads ``story.jsonl`` / ``extra.jsonl`` from an extraction output and asks an
OpenAI-compatible chat model, per chapter or event group, for

* a summary in short paragraphs, each citing the scenes it rests on, and
* a one-sentence synopsis for every scene the game gives no outline (``scene_intro``).

The result is ``summaries.jsonl`` next to the extraction output; ``upload`` ships it in the
bundle. It is derived text, not game text: every record names the model and prompt version,
and consumers must label it as AI-written and keep it out of quote verification.

Faithfulness guards: the game's own scene outlines go in as trusted anchors; every paragraph
must cite scenes; a paragraph naming a character who appears nowhere in the scenes it cites
is dropped (the commonest failure is mixing up who did what). Units are cached by
(prompt version, model, source text), so a rerun only pays for changed units, and an
exhausted quota or rate limit stops the run without marking anything done.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

PROMPT_VERSION = "1"
# 一次请求最多放这么多字原文；更长的单元按场景切块，逐块总结后再合成。
CHUNK_CHARS = 60_000
SCHEMA_VERSION = 1

SYSTEM_PROMPT = """你在为《绝区零》剧情资料库整理剧情梗概。你只依据用户给出的原文工作，不使用任何原文以外的知识。

规则：
1. 每段只写原文里明确发生的事；人名、称号、地名照原文写，不要改写，也不要补充原文没有的设定或动机。
2. 每段都要列出它依据的场景编号（如 S3、S4），只引用确实写到这件事的场景。
3. 带「游戏梗概」的场景，梗概是游戏官方写的，视为可靠；台词署名可能缺失（标「？」），这时根据上下文判断说话人，判断不了就不要写是谁说的。
4. 主角兄妹按原文称呼（哲、铃），原文写「我」时指主角。
5. 只输出一个 JSON 对象，不要其他文字。"""

USER_TEMPLATE = """下面是「{label}」{part}的原文，共 {count} 个场景。

请输出 JSON：
{{"summary": [{{"text": "一段梗概", "scenes": ["S1", "S2"]}}, ...],
 "scene_synopses": [{{"scene": "S5", "text": "这个场景发生了什么，一句话"}}, ...]}}

- summary：按剧情先后写 {paragraphs} 段，每段 1～3 句，讲清谁、在哪、做了什么、结果如何。
- scene_synopses：只给没有「游戏梗概」、且有实际剧情的场景各写一句（闲聊、商店台词、重复的系统提示可以跳过）。

原文：
{text}"""

MERGE_TEMPLATE = """下面是「{label}」分 {count} 部分整理的梗概（按先后排列，括号里是依据的场景）。
请合并成一份连贯的梗概，按剧情先后写 {paragraphs} 段，每段 1～3 句；每段列出依据的场景编号，只能用下面出现过的编号。
只输出 JSON：{{"summary": [{{"text": "一段梗概", "scenes": ["S1", "S2"]}}, ...]}}

{text}"""


class StopGeneration(RuntimeError):
    """Quota exhausted, rate-limited or unauthorised: stop the run, keep what is done."""


@dataclass
class Scene:
    family: str
    scene: str
    title: str
    intro: str | None
    lines: list[tuple[str | None, str]] = field(default_factory=list)
    names: set[str] = field(default_factory=set)

    def chars(self) -> int:
        return sum(len(text) + 4 for _, text in self.lines)


@dataclass
class Unit:
    source: str  # story | extra
    chapter: str
    label: str
    scenes: list[Scene]


def load_units(out_dir: Path, only: set[str] | None = None) -> list[Unit]:
    """Chapters (story.jsonl) and event groups (extra.jsonl), scenes in export order."""
    units: list[Unit] = []
    for source in ("story", "extra"):
        path = out_dir / f"{source}.jsonl"
        if not path.is_file():
            continue
        groups: "OrderedDict[str, tuple[str, OrderedDict[tuple[str, str], Scene]]]" = OrderedDict()
        with path.open(encoding="utf-8") as handle:
            for raw in handle:
                if not raw.strip():
                    continue
                row = json.loads(raw)
                chapter = row["chapter"]
                if only and chapter not in only:
                    continue
                label, scenes = groups.setdefault(chapter, (row.get("chapter_label") or chapter, OrderedDict()))
                key = (row.get("family") or "", str(row.get("scene") or ""))
                scene = scenes.get(key)
                if scene is None:
                    title = row.get("scene_title") or row.get("quest_name") or f"{key[0]} {key[1]}"
                    scene = scenes[key] = Scene(key[0], key[1], title, row.get("scene_intro"))
                speaker = row.get("speaker")
                scene.lines.append((speaker, row.get("text") or ""))
                if speaker:
                    scene.names.add(speaker)
                scene.names.update(row.get("scene_speakers") or [])
        for chapter, (label, scenes) in groups.items():
            units.append(Unit(source, chapter, label, list(scenes.values())))
    return units


def render(scenes: list[Scene], start: int) -> str:
    """Scenes numbered S<start>…, each with its game outline and attributed lines."""
    parts = []
    for offset, scene in enumerate(scenes):
        head = f"## S{start + offset} {scene.title}"
        body = [head]
        if scene.intro:
            body.append(f"游戏梗概：{scene.intro}")
        for speaker, text in scene.lines:
            body.append(f"{speaker or '？'}：{text}")
        parts.append("\n".join(body))
    return "\n\n".join(parts)


def chunks(scenes: list[Scene], limit: int | None = None) -> list[tuple[int, list[Scene]]]:
    """Consecutive scene runs under ``limit`` (default ``CHUNK_CHARS``) characters, with their
    first scene number."""
    limit = CHUNK_CHARS if limit is None else limit
    out: list[tuple[int, list[Scene]]] = []
    current: list[Scene] = []
    size = 0
    start = 1
    for index, scene in enumerate(scenes, 1):
        if current and size + scene.chars() > limit:
            out.append((start, current))
            current, size, start = [], 0, index
        current.append(scene)
        size += scene.chars()
    if current:
        out.append((start, current))
    return out


def paragraphs_for(chars: int) -> str:
    if chars < 3_000:
        return "1～2"
    if chars < 20_000:
        return "3～5"
    if chars < 60_000:
        return "5～8"
    return "8～12"


def parse_json(content: str) -> dict:
    start, end = content.find("{"), content.rfind("}")
    if start < 0 or end <= start:
        raise ValueError(f"模型没有返回 JSON：{content[:200]}")
    return json.loads(content[start : end + 1])


Post = Callable[[dict], dict]


def http_post(base_url: str, api_key: str, timeout: float = 600.0) -> Post:
    import requests

    url = base_url.rstrip("/") + "/chat/completions"

    def post(body: dict) -> dict:
        attempts = 6
        for attempt in range(attempts):
            last = attempt == attempts - 1
            try:
                response = requests.post(url, json=body, timeout=timeout,
                                         headers={"Authorization": f"Bearer {api_key}"})
            except requests.RequestException:
                if last:
                    raise
                time.sleep(5 * (attempt + 1))
                continue
            # 限流：退避重试，多次仍限流才停。鉴权失败、余额不足直接停。
            if response.status_code == 429 and not last:
                time.sleep(15 * (attempt + 1))
                continue
            if response.status_code in (401, 402, 403, 429):
                raise StopGeneration(f"{response.status_code} {response.text[:300]}")
            if response.status_code >= 500 and not last:
                time.sleep(5 * (attempt + 1))
                continue
            response.raise_for_status()
            return response.json()
        raise RuntimeError("unreachable")

    return post


def ask(post: Post, model: str, prompt: str) -> dict:
    reply = post({
        "model": model,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}],
        "max_tokens": 8000,
    })
    content = reply["choices"][0]["message"].get("content") or ""
    return parse_json(content)


# 署名和姓名表里也有泛称（「众人」「邦布们」「箱子」），它们出现在梗概里不算串了人。
_GENERIC_NAME = re.compile(
    r"^(众人|大家|所有人|其他人|众邦布|邦布|小邦布|路人|市民|居民|游客|店员|店主|老板|士兵|守卫|警卫|学生|员工|"
    r"职员|工作人员|声音|广播|系统|电视|手机|箱子|电脑|通讯器|无线电|未知|神秘人|陌生人|？+)$"
    r"|们$|^(?:路人|市民|居民|游客|店员|士兵|守卫|学生|员工|职员|邦布)")


def known_names(units: list[Unit]) -> set[str]:
    """Speakers and name-table entries (two characters or longer), minus collective nouns."""
    names: set[str] = set()
    for unit in units:
        for scene in unit.scenes:
            names.update(n for n in scene.names if len(n) >= 2 and not _GENERIC_NAME.search(n))
    return names


def scene_text(scene: Scene) -> str:
    return "\n".join([scene.title, scene.intro or "", *scene.names, *(text for _, text in scene.lines)])


def check_paragraph(text: str, cited: list[Scene], names: set[str]) -> list[str]:
    """Names in ``text`` that none of the cited scenes contains."""
    corpus = "\n".join(scene_text(s) for s in cited)
    return sorted(n for n in names if n in text and n not in corpus)


def _cited(refs: list, numbered: dict[str, Scene]) -> list[Scene]:
    return [numbered[r] for r in refs if isinstance(r, str) and r in numbered]


def generate_unit(unit: Unit, post: Post, model: str) -> dict:
    """The model's raw output for one unit (cached as is; validation runs at write time)."""
    parts = chunks(unit.scenes)
    paragraphs: list[dict] = []
    synopses: list[dict] = []
    for part_index, (start, scenes) in enumerate(parts, 1):
        text = render(scenes, start)
        part = f"（第 {part_index}/{len(parts)} 部分）" if len(parts) > 1 else ""
        data = ask(post, model, USER_TEMPLATE.format(
            label=unit.label, part=part, count=len(scenes), text=text,
            paragraphs=paragraphs_for(len(text))))
        paragraphs.extend(p for p in data.get("summary") or [] if isinstance(p, dict))
        synopses.extend(s for s in data.get("scene_synopses") or [] if isinstance(s, dict))
    if len(parts) > 1:
        listing = "\n".join(f"- {p.get('text', '')}（{'、'.join(map(str, p.get('scenes') or []))}）"
                            for p in paragraphs)
        prompt = MERGE_TEMPLATE.format(
            label=unit.label, count=len(parts), text=listing,
            paragraphs=paragraphs_for(sum(s.chars() for s in unit.scenes)))
        # 合并偶尔不按格式输出（例如先讨论两部分哪里有出入）：重试一次，还不行就保留分块梗概。
        for _ in range(2):
            try:
                merged = [p for p in ask(post, model, prompt).get("summary") or [] if isinstance(p, dict)]
            except ValueError:
                continue
            if merged:
                paragraphs = merged
                break
    return {"summary": paragraphs, "scene_synopses": synopses, "parts": len(parts)}


def validate_unit(unit: Unit, raw: dict, names: set[str]) -> dict:
    """Keep cited paragraphs whose names all occur in the scenes they cite."""
    numbered = {f"S{i}": scene for i, scene in enumerate(unit.scenes, 1)}
    paragraphs = [p for p in raw.get("summary") or [] if isinstance(p, dict)]
    synopses = [s for s in raw.get("scene_synopses") or [] if isinstance(s, dict)]
    kept, dropped = [], []
    for p in paragraphs:
        cited = _cited(p.get("scenes") or [], numbered)
        text = str(p.get("text") or "").strip()
        if not text or not cited:
            dropped.append({"text": text, "reason": "no_citation"})
            continue
        stray = check_paragraph(text, cited, names)
        if stray:
            dropped.append({"text": text, "reason": "name_not_in_cited_scenes", "names": stray})
            continue
        kept.append({"text": text, "scenes": [{"family": s.family, "scene": s.scene} for s in cited]})
    scene_synopses = []
    for s in synopses:
        scene = numbered.get(str(s.get("scene")))
        text = str(s.get("text") or "").strip()
        if not scene or not text or scene.intro:
            continue
        stray = check_paragraph(text, [scene], names)
        if stray:
            dropped.append({"text": text, "reason": "name_not_in_cited_scenes", "names": stray})
            continue
        scene_synopses.append({"family": scene.family, "scene": scene.scene, "text": text})
    return {"summary": kept, "scene_synopses": scene_synopses, "dropped": dropped}


def summarize_unit(unit: Unit, post: Post, model: str, names: set[str]) -> dict:
    return validate_unit(unit, generate_unit(unit, post, model), names)


def unit_hash(unit: Unit, model: str) -> str:
    digest = hashlib.sha256()
    digest.update(f"{PROMPT_VERSION}\0{model}\0{unit.label}\0".encode())
    digest.update(render(unit.scenes, 1).encode())
    return digest.hexdigest()


def run(out_dir: Path, post: Post, model: str, *, only: set[str] | None = None,
        limit: int | None = None, jobs: int = 1, log: Callable[[str], None] = print) -> dict:
    """Generate every unit not yet cached, then write ``summaries.jsonl``. Returns run stats.

    ``jobs`` units are generated at once. After a quota/auth stop no new unit is started;
    units already running finish and are cached.
    """
    from concurrent.futures import ThreadPoolExecutor
    import threading

    units = load_units(out_dir, only)
    cache_dir = out_dir / "summaries-cache"
    cache_dir.mkdir(exist_ok=True)
    stats = {"units": len(units), "generated": 0, "cached": 0, "stopped": None, "dropped": 0}
    pending = []
    for unit in units:
        cached = cache_dir / f"{unit_hash(unit, model)}.json"
        if cached.is_file():
            stats["cached"] += 1
        elif limit is None or len(pending) < limit:
            pending.append((unit, cached))
    lock = threading.Lock()
    stop = threading.Event()

    def work(item) -> None:
        unit, cached = item
        if stop.is_set():
            return
        try:
            raw = generate_unit(unit, post, model)
        except StopGeneration as exc:
            with lock:
                if not stop.is_set():
                    stats["stopped"] = str(exc)
                    log(f"  停止：{exc}")
                stop.set()
            return
        except (ValueError, KeyError) as exc:
            log(f"  {unit.chapter}：生成失败，跳过（{exc}）")
            return
        except Exception as exc:  # 网络等偶发错误：跳过这个单元，下次续跑再补。
            log(f"  {unit.chapter}：请求失败，跳过（{type(exc).__name__}: {str(exc)[:200]}）")
            return
        raw["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        cached.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        with lock:
            stats["generated"] += 1
            log(f"  {unit.chapter}（{unit.label}）：{len(raw['summary'])} 段，"
                f"{len(raw['scene_synopses'])} 个场景梗概 [{stats['generated']}/{len(pending)}]")

    if jobs <= 1:
        for item in pending:
            work(item)
            if stop.is_set():
                break
    else:
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            list(pool.map(work, pending))
    stats["dropped"] = write_summaries(out_dir, model)["dropped"]
    return stats


def write_summaries(out_dir: Path, model: str) -> dict:
    """Validate cached outputs for the current units and write ``summaries.jsonl``.

    Also writes ``summaries-dropped.jsonl`` (what validation removed) for review.
    """
    units = load_units(out_dir)
    names = known_names(units)
    cache_dir = out_dir / "summaries-cache"
    rows, dropped_rows = [], []
    for unit in units:
        key = unit_hash(unit, model)
        cached = cache_dir / f"{key}.json"
        if not cached.is_file():
            continue
        raw = json.loads(cached.read_text(encoding="utf-8"))
        result = validate_unit(unit, raw, names)
        rows.append(json.dumps({
            "schema_version": SCHEMA_VERSION,
            "record_type": "unit_summary",
            "source": unit.source,
            "chapter": unit.chapter,
            "chapter_label": unit.label,
            "summary": result["summary"],
            "scene_synopses": result["scene_synopses"],
            "model": model,
            "prompt_version": PROMPT_VERSION,
            "source_sha256": key,
            "generated_at": raw.get("generated_at"),
        }, ensure_ascii=False))
        dropped_rows.extend(json.dumps({"chapter": unit.chapter, **d}, ensure_ascii=False) for d in result["dropped"])
    for name, lines in (("summaries.jsonl", rows), ("summaries-dropped.jsonl", dropped_rows)):
        path = out_dir / name
        if lines:
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        elif path.exists():
            path.unlink()
    return {"units": len(rows), "dropped": len(dropped_rows)}
