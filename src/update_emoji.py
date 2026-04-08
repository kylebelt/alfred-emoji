#!/usr/bin/env python3
"""Download emoji data and generate icons for the alfred-emoji workflow."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

SOURCES: dict[str, str] = {
    "keywords": "https://raw.githubusercontent.com/muan/emojilib/main/dist/emoji-en-US.json",
    "emoji_data": "https://raw.githubusercontent.com/muan/unicode-emoji-json/main/data-by-emoji.json",
    "ordered": "https://raw.githubusercontent.com/muan/unicode-emoji-json/main/data-ordered-emoji.json",
    "components": "https://raw.githubusercontent.com/muan/unicode-emoji-json/main/data-emoji-components.json",
    "emojilib_pkg": "https://raw.githubusercontent.com/muan/emojilib/main/package.json",
    "unicode_pkg": "https://raw.githubusercontent.com/muan/unicode-emoji-json/main/package.json",
}

ZWJ = "\u200d"

LOCK_FILE = ".emoji_update_lock"
STAGING_DIR = ".update"
FAILED_FILE = ".update_failed"
ICONS_EXPECTED_FILE = ".icons_expected"
UPDATE_IN_PROGRESS_FILE = ".update_in_progress"
ICONGEN_SWIFT = Path(__file__).parent / "icongen.swift"
ICONGEN_HASH_FILE = ".icongen_hash"
ICONGEN_BINARY = "_icongen"
ICONGEN_SWIFT_TMP = "_icongen.swift"


def etag_path(data_dir: str, key: str) -> str:
    return os.path.join(data_dir, f".etag_{key}")


def load_etag(data_dir: str, key: str) -> str | None:
    p = etag_path(data_dir, key)
    if not os.path.isfile(p):
        return None
    with open(p) as f:
        return f.read().strip()


def save_etag(data_dir: str, key: str, etag: str) -> None:
    if etag:
        with open(etag_path(data_dir, key), "w") as f:
            f.write(etag)


def download_json_conditional(url: str, data_dir: str, key: str) -> tuple[Any, bool]:
    """Download JSON with ETag caching. Returns (data, changed)."""
    req = urllib.request.Request(url)
    old_etag = load_etag(data_dir, key)
    if old_etag:
        req.add_header("If-None-Match", old_etag)
    try:
        with urllib.request.urlopen(req) as r:
            new_etag = r.headers.get("ETag", "")
            data = json.loads(r.read())
            save_etag(data_dir, key, new_etag)
            return data, True
    except urllib.error.HTTPError as e:
        if e.code == 304:
            return None, False
        raise


def gen_pack(data_dir: str) -> tuple[dict[str, Any], bool]:
    """Download emoji sources and stage emoji.pack.json. Returns (pack, changed)."""
    print("Checking for emoji data updates...", file=sys.stderr)
    results: dict[str, Any] = {}
    any_changed = False
    for key, url in SOURCES.items():
        data, changed = download_json_conditional(url, data_dir, key)
        results[key] = data
        print(f"  {key}: {'updated' if changed else 'unchanged'}", file=sys.stderr)
        if changed:
            any_changed = True

    live_pack_path = os.path.join(data_dir, "emoji.pack.json")

    if not any_changed and os.path.isfile(live_pack_path):
        print("All sources unchanged, loading existing pack.", file=sys.stderr)
        with open(live_pack_path) as f:
            return json.load(f), False

    # Signal to emoji.py that a real rebuild is starting.
    with open(os.path.join(data_dir, UPDATE_IN_PROGRESS_FILE), "w") as f:
        f.write("")

    for key, url in SOURCES.items():
        if results[key] is None:
            print(f"  Re-downloading {key} (needed for rebuild)...", file=sys.stderr)
            ep = etag_path(data_dir, key)
            if os.path.isfile(ep):
                os.unlink(ep)
            with urllib.request.urlopen(url) as r:
                results[key] = json.loads(r.read())

    keywords = results["keywords"]
    emoji_data = results["emoji_data"]
    ordered = results["ordered"]
    components = results["components"]
    emojilib_ver = results["emojilib_pkg"]["version"]
    unicode_ver = results["unicode_pkg"]["version"]

    keywords_map: dict[str, list[str]] = {}
    emoji_info: dict[str, Any] = {}
    for symbol, kws in keywords.items():
        for kw in kws:
            keywords_map.setdefault(kw, []).append(symbol)
        if symbol in emoji_data:
            cp = format(ord(symbol[0]), "X").zfill(4)
            emoji_info[symbol] = {
                **emoji_data[symbol],
                "codepoint": cp,
                "keywords": kws,
            }

    pack: dict[str, Any] = {
        "keywords": keywords_map,
        "searchTerms": list(keywords_map.keys()),
        "emoji": emoji_info,
        "orderedEmoji": ordered,
        "emojiComponents": components,
        "versions": {"emojilib": emojilib_ver, "unicode_emoji_json": unicode_ver},
    }

    staging_dir = os.path.join(data_dir, STAGING_DIR)
    os.makedirs(staging_dir, exist_ok=True)
    staged_path = os.path.join(staging_dir, "emoji.pack.json")
    with open(staged_path, "w") as f:
        json.dump(pack, f, ensure_ascii=False, separators=(",", ":"))
    print(f"Staged new pack at {staged_path}", file=sys.stderr)
    return pack, True


def _swift_source() -> str:
    return ICONGEN_SWIFT.read_text()


def _swift_hash(source: str) -> str:
    return hashlib.md5(source.encode()).hexdigest()


def gen_icons(data_dir: str, pack: dict[str, Any]) -> tuple[int, int]:
    """Generate missing emoji PNG icons. Returns (icons_on_disk, icons_expected)."""
    icons_dir = os.path.join(data_dir, "icons")
    os.makedirs(icons_dir, exist_ok=True)

    components = pack["emojiComponents"]
    modifiers = [
        components["light_skin_tone"],
        components["medium_light_skin_tone"],
        components["medium_skin_tone"],
        components["medium_dark_skin_tone"],
        components["dark_skin_tone"],
    ]

    all_jobs: list[tuple[str, str]] = []
    for char in pack["orderedEmoji"]:
        info = pack["emoji"].get(char)
        if not info:
            continue
        all_jobs.append((char, info["slug"]))
        if info.get("skin_tone_support"):
            for i, mod in enumerate(modifiers):
                mc = char.replace(ZWJ, mod + ZWJ) if ZWJ in char else char + mod
                all_jobs.append((mc, f"{info['slug']}_{i}"))

    expected = len(all_jobs)
    existing = set(os.listdir(icons_dir))
    jobs = [(c, n) for c, n in all_jobs if f"{n}.png" not in existing]

    if not jobs:
        print(f"All {expected} icons already exist, skipping.", file=sys.stderr)
        return expected, expected

    print(
        f"Generating {len(jobs)} icons ({expected - len(jobs)} already exist)...",
        file=sys.stderr,
    )

    with open(os.path.join(data_dir, ICONS_EXPECTED_FILE), "w") as f:
        f.write(str(expected))

    source = _swift_source()
    src_hash = _swift_hash(source)
    hash_file = os.path.join(data_dir, ICONGEN_HASH_FILE)
    binary = os.path.join(data_dir, ICONGEN_BINARY)

    cached = False
    if os.path.isfile(binary) and os.path.isfile(hash_file):
        with open(hash_file) as f:
            cached = f.read().strip() == src_hash

    if not cached:
        swift_tmp = os.path.join(data_dir, ICONGEN_SWIFT_TMP)
        with open(swift_tmp, "w") as f:
            f.write(source)
        try:
            rc = subprocess.run(
                ["swiftc", "-O", "-o", binary, swift_tmp],
                capture_output=True,
                text=True,
            )
        finally:
            if os.path.isfile(swift_tmp):
                os.unlink(swift_tmp)
        if rc.returncode != 0:
            raise RuntimeError(f"Swift compilation failed:\n{rc.stderr}")
        with open(hash_file, "w") as f:
            f.write(src_hash)

    input_data = "\n".join(f"{c}\t{os.path.join(icons_dir, n)}.png" for c, n in jobs)
    result = subprocess.run([binary], input=input_data, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Icon generation failed: {result.stderr}", file=sys.stderr)

    actual = sum(1 for f in os.listdir(icons_dir) if f.endswith(".png"))
    print(f"Icons: {len(jobs)} attempted, {actual} total on disk", file=sys.stderr)
    return actual, expected


def save_version_info(
    data_dir: str,
    pack: dict[str, Any],
    icons_generated: int,
    icons_expected: int,
) -> None:
    """Save version metadata for emoji.py to read.

    icons_expected is stored as icon_count and is what needs_setup() checks
    against to detect incomplete icon generation.
    """
    info = {
        "versions": pack.get("versions", {}),
        "emoji_count": len(pack["orderedEmoji"]),
        "icon_count": icons_expected,
        "icons_generated": icons_generated,
    }
    with open(os.path.join(data_dir, "version_info.json"), "w") as f:
        json.dump(info, f)


def main() -> None:
    dd = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] else ""
    dd = dd or os.environ.get("alfred_workflow_data", "")
    if not dd:
        print("Usage: python3 update_emoji.py <output_dir>", file=sys.stderr)
        print("  Or set alfred_workflow_data env var.", file=sys.stderr)
        sys.exit(1)

    os.makedirs(dd, exist_ok=True)

    staging_dir = os.path.join(dd, STAGING_DIR)
    failed_file = os.path.join(dd, FAILED_FILE)

    try:
        pack, pack_changed = gen_pack(dd)
        actual, expected = gen_icons(dd, pack)

        if pack_changed:
            os.replace(
                os.path.join(staging_dir, "emoji.pack.json"),
                os.path.join(dd, "emoji.pack.json"),
            )
            shutil.rmtree(staging_dir, ignore_errors=True)

        save_version_info(dd, pack, actual, expected)

        if os.path.isfile(failed_file):
            os.unlink(failed_file)

    except Exception as e:
        print(f"Update failed: {e}", file=sys.stderr)
        try:
            with open(failed_file, "w") as f:
                f.write(str(e))
        except OSError:
            pass
        shutil.rmtree(staging_dir, ignore_errors=True)

    finally:
        for path in (
            os.path.join(dd, LOCK_FILE),
            os.path.join(dd, ICONS_EXPECTED_FILE),
            os.path.join(dd, UPDATE_IN_PROGRESS_FILE),
        ):
            if os.path.isfile(path):
                os.unlink(path)


if __name__ == "__main__":
    main()
