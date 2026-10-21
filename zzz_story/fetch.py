"""Data acquisition: TextMap/FileCfg downloads and local game discovery."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CACHE_ROOT = PROJECT_ROOT / "data" / "cache"
DEFAULT_VERSION = "3.3.0"

GITEA_RAW = "https://git.mero.moe/dimbreath/ZenlessData/raw/branch/master"
GITHUB_RAW = "https://raw.githubusercontent.com/malu-no996/ZenlessData/master"
GITEA_API = "https://git.mero.moe/api/v1/repos/dimbreath/ZenlessData"

# TextMap language file stems.  CHS uses the base file.
LANG_STEMS = {
    "CHS": None,
    "CHT": "CHT",
    "DE": "DE",
    "EN": "EN",
    "ES": "ES",
    "FR": "FR",
    "ID": "ID",
    "JA": "JA",
    "KO": "KO",
    "PT": "PT",
    "RU": "RU",
    "TH": "TH",
    "VI": "VI",
}

REQUIRED_FILES = [
    "TextMap/TextMapTemplateTb.json",
    "TextMap/TextMapOverwriteTemplateTb.json",
    # English names are used to resolve internal voice aliases (Nekomata ->
    # 猫又, StudentWise -> 哲, ...) to Chinese display names.
    "TextMap/TextMap_ENTemplateTb.json",
    "TextMap/TextMap_ENOverwriteTemplateTb.json",
    "FileCfg/PerformTemplateTb.json",
    # Official story-replay archive: GalGame scene order and quest grouping.
    "FileCfg/ArchivePerformTemplateTb.json",
    # Quest names for the archive's quest ids.
    "FileCfg/QuestConfigTemplateTb.json",
    # In-level dialogue (Ongoing*) text keys -> speaker names / voice aliases.
    "FileCfg/OngoingTipsConfigTemplateTb.json",
    "FileCfg/ChapterTipsConfigTemplateTb.json",
    "FileCfg/ChapterConfigTemplateTb.json",
    "FileCfg/MainStorySeasonTemplateTb.json",
    "FileCfg/AvatarBaseTemplateTb.json",
    "Data/_unsorted/VoiceData.json",
]

GAME_CANDIDATES = [
    Path(r"D:\米哈游\miHoYo Launcher\games\ZenlessZoneZero Game"),
    Path(r"C:\Program Files\HoYoPlay\games\ZenlessZoneZero Game"),
    Path(r"D:\HoYoPlay\games\ZenlessZoneZero Game"),
    Path(r"E:\HoYoPlay\games\ZenlessZoneZero Game"),
    Path(r"C:\Program Files\miHoYo Launcher\games\ZenlessZoneZero Game"),
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _http_get(url: str) -> requests.Response:
    response = requests.get(
        url,
        stream=True,
        timeout=(15, 240),
        headers={"User-Agent": "zzz-story-extractor/0.1"},
    )
    if response.status_code != 200:
        response.close()
        raise RuntimeError(f"HTTP {response.status_code} for {url}")
    return response


def download_file(rel_path: str, destination: Path, refresh: bool = False, *, bases: tuple[str, ...] | None = None) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.stat().st_size > 1000 and not refresh:
        return destination

    tmp = destination.with_suffix(destination.suffix + ".part")
    errors: list[str] = []
    for base in bases or (GITEA_RAW, GITHUB_RAW):
        url = f"{base}/{rel_path}"
        try:
            response = _http_get(url)
            total = int(response.headers.get("Content-Length", "0") or "0")
            written = 0
            last_report = 0
            with tmp.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if not chunk:
                        continue
                    handle.write(chunk)
                    written += len(chunk)
                    if total and written - last_report >= 16 * 1024 * 1024:
                        print(f"  {rel_path}: {written / 1e6:.1f}/{total / 1e6:.1f} MB")
                        last_report = written
            response.close()
            if written < 100:
                raise RuntimeError(f"downloaded only {written} bytes")
            os.replace(tmp, destination)
            print(f"  saved {rel_path} ({written / 1e6:.1f} MB)")
            return destination
        except Exception as exc:  # noqa: BLE001 - try the mirror
            errors.append(f"{url}: {exc}")
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            time.sleep(0.5)
    raise RuntimeError("could not download " + rel_path + "\n" + "\n".join(errors))


SOURCE_VERSION_CACHE = "source_version.txt"


SOURCE_PROVENANCE = "source_provenance.json"


def _verified_provenance(cache_dir: Path, required_files: list[str] | None = None) -> dict | None:
    try:
        provenance = read_json(cache_dir / SOURCE_PROVENANCE)
        if not isinstance(provenance, dict):
            return None
        files = provenance.get("files")
        if not isinstance(files, dict) or not files or not provenance.get("commit"):
            return None
        if required_files and not set(required_files).issubset(files):
            return None
        for rel, metadata in files.items():
            path = (cache_dir / rel).resolve()
            if not path.is_relative_to(cache_dir.resolve()):
                return None
            if sha256_file(path) != metadata["sha256"]:
                return None
        return provenance
    except (OSError, ValueError, KeyError, TypeError):
        return None


def fetch_source_version(cache_dir: Path | None = None, refresh: bool = False, *, required_files: list[str] | None = None) -> str:
    """Return only a version bound to the actual input files, never latest upstream.

    Legacy source_version.txt is a hint, not proof of the files' version.
    Custom datasets may provide source_provenance.json with file hashes.
    """
    if cache_dir is None:
        return "unknown"
    provenance = _verified_provenance(cache_dir, required_files)
    version = provenance.get("version") if provenance else None
    return version if isinstance(version, str) and version else "unknown"


def _upstream_snapshot() -> tuple[str, str]:
    """Resolve one commit before downloading, keeping all tables in one snapshot."""
    with requests.get(f"{GITEA_API}/commits?limit=1", timeout=20,
                      headers={"User-Agent": "zzz-story-extractor/0.1"}) as response:
        response.raise_for_status()
        payload = response.json()
    commit = payload[0]["sha"]
    if not re.fullmatch(r"[0-9a-fA-F]{40}", commit):
        raise ValueError("upstream did not return a valid commit SHA")
    message = payload[0]["commit"]["message"]
    match = re.search(r"(?:Win|REL)(\d+\.\d+\.\d+)", message, re.IGNORECASE)
    return commit, match.group(1) if match else "unknown"


def _language_files(lang: str) -> list[str]:
    stem = LANG_STEMS.get(lang.upper())
    if stem is None:
        if lang.upper() != "CHS":
            raise ValueError(f"unknown language {lang!r}; known: {', '.join(LANG_STEMS)}")
        return []
    return [
        f"TextMap/TextMap_{stem}TemplateTb.json",
        f"TextMap/TextMap_{stem}OverwriteTemplateTb.json",
    ]


def ensure_data(
    lang: str = "CHS",
    refresh: bool = False,
    data_dir: Path | None = None,
) -> dict[str, Path]:
    """Return absolute paths for the files the extractor needs."""
    lang = lang.upper()
    required = list(REQUIRED_FILES) + _language_files(lang)

    if data_dir is not None:
        missing = [rel for rel in required if not (data_dir / rel).exists()]
        if missing:
            raise FileNotFoundError("missing files under data-dir:\n" + "\n".join(missing))
        return {rel: data_dir / rel for rel in required}

    target = CACHE_ROOT / DEFAULT_VERSION
    print(f"Preparing ZenlessData cache at {target}")
    if not refresh and all((target / rel).is_file() for rel in required):
        if (target / SOURCE_PROVENANCE).exists() and _verified_provenance(target, required) is None:
            raise ValueError("缓存来源哈希不一致或不完整；请用 --refresh 重建完整快照")
        return {rel: target / rel for rel in required}

    # Download the entire required snapshot before replacing any existing data.
    # A failed refresh preserves the old cache. Hash verification detects an
    # interrupted replacement instead of labeling mixed files as one version.
    import tempfile
    from .writers import write_json
    target.parent.mkdir(parents=True, exist_ok=True)
    commit, version = _upstream_snapshot()
    bases = (f"https://git.mero.moe/dimbreath/ZenlessData/raw/commit/{commit}",
             f"https://raw.githubusercontent.com/malu-no996/ZenlessData/{commit}")
    with tempfile.TemporaryDirectory(prefix="snapshot-", dir=target.parent) as staging:
        stage = Path(staging)
        for rel in required:
            download_file(rel, stage / rel, refresh=True, bases=bases)
        provenance = {"commit": commit, "version": version, "files": {
            rel: {"sha256": sha256_file(stage / rel), "bytes": (stage / rel).stat().st_size}
            for rel in required
        }}
        for rel in required:
            destination = target / rel
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(stage / rel, destination)
        write_json(target / SOURCE_PROVENANCE, provenance)
    return {rel: target / rel for rel in required}


def detect_game_dir(explicit: Path | None = None) -> Path | None:
    if explicit is not None:
        return explicit if _looks_like_game(explicit) else None

    for candidate in GAME_CANDIDATES:
        if _looks_like_game(candidate):
            return candidate

    try:
        import winreg

        for hive, key_path in (
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        ):
            try:
                root = winreg.OpenKey(hive, key_path)
            except OSError:
                continue
            for index in range(winreg.QueryInfoKey(root)[0]):
                try:
                    sub_name = winreg.EnumKey(root, index)
                    sub = winreg.OpenKey(root, sub_name)
                    display = winreg.QueryValueEx(sub, "DisplayName")[0]
                    location = winreg.QueryValueEx(sub, "InstallLocation")[0]
                except OSError:
                    continue
                if not isinstance(display, str) or not any(x in display for x in ("绝区零", "Zenless")):
                    continue
                base = Path(location) / "games" / "ZenlessZoneZero Game"
                if _looks_like_game(base):
                    return base
                if _looks_like_game(Path(location)):
                    return Path(location)
    except Exception:  # noqa: BLE001 - registry is optional
        pass
    return None


def _looks_like_game(path: Path) -> bool:
    try:
        return (path / "ZenlessZoneZero_Data" / "StreamingAssets" / "Blocks").is_dir()
    except OSError:
        return False


def read_game_version(game_dir: Path) -> str:
    for rel in ("version_info", "ZenlessZoneZero_Data/version_info"):
        path = game_dir / rel
        if path.exists():
            try:
                return path.read_text(encoding="utf-8", errors="replace").strip()
            except OSError:
                pass
    return ""


def read_json(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)
