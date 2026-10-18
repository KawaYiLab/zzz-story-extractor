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
DEFAULT_VERSION = "3.2.0"

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


def download_file(rel_path: str, destination: Path, refresh: bool = False) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.stat().st_size > 1000 and not refresh:
        return destination

    tmp = destination.with_suffix(destination.suffix + ".part")
    errors: list[str] = []
    for base in (GITEA_RAW, GITHUB_RAW):
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


def fetch_source_version() -> str:
    try:
        response = requests.get(
            f"{GITEA_API}/commits?limit=1",
            timeout=20,
            headers={"User-Agent": "zzz-story-extractor/0.1"},
        )
        response.raise_for_status()
        payload = response.json()
        message = payload[0]["commit"]["message"] if payload else ""
        match = re.search(r"(?:Win|REL)(\d+\.\d+\.\d+)", message, re.IGNORECASE)
        if match:
            return match.group(1)
    except Exception:  # noqa: BLE001 - metadata only
        pass
    return DEFAULT_VERSION


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
    result: dict[str, Path] = {}

    if data_dir is not None:
        missing = [rel for rel in required if not (data_dir / rel).exists()]
        if missing:
            raise FileNotFoundError("missing files under data-dir:\n" + "\n".join(missing))
        return {rel: data_dir / rel for rel in required}

    version = DEFAULT_VERSION
    target = CACHE_ROOT / version
    print(f"Preparing ZenlessData cache at {target}")
    for rel in required:
        result[rel] = download_file(rel, target / rel, refresh=refresh)
    return result


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
