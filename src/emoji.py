#!/usr/bin/env python3
"""Alfred Script Filter — emoji search."""

from __future__ import annotations

import json
import os
import random
import subprocess
import sys
import time
from typing import Any

ZWJ = "\u200d"

ICON_UPDATE = "ICON_SYNC.png"
UPDATE_TRIGGER_FILE = ".last_update_trigger"
EMOJI_LOCK_FILE = ".emoji_update_lock"
FAILED_FILE = ".update_failed"
ICONS_EXPECTED_FILE = ".icons_expected"
UPDATE_IN_PROGRESS_FILE = ".update_in_progress"
SETUP_RETRY_FILE = ".setup_retries"
UPDATE_INTERVAL = 604800  # seconds (7 days)
MAX_SETUP_RETRIES = 3

_SETUP_ITEM: dict[str, Any] = {
    "title": "Setting up emoji data...",
    "subtitle": "Downloading and generating icons. Results will appear shortly.",
    "valid": False,
    "icon": {"path": ICON_UPDATE},
}

_UPDATE_ITEM: dict[str, Any] = {
    "title": "Updating emoji data...",
    "subtitle": "New emoji data available. Updating in background.",
    "valid": False,
    "icon": {"path": ICON_UPDATE},
}

_ERROR_ITEM: dict[str, Any] = {
    "title": "Could not set up emoji data",
    "subtitle": "Setup failed after several attempts. Will retry in a week.",
    "valid": False,
    "icon": {"path": ICON_UPDATE},
}


def data_dir() -> str:
    """Return the Alfred workflow data directory from the environment."""
    return os.environ.get("alfred_workflow_data", "")


def needs_setup() -> bool:
    """Return True if icons or version metadata are missing or incomplete."""
    dd = data_dir()
    if not dd:
        return True
    icons_dir = os.path.join(dd, "icons")
    if not os.path.isdir(icons_dir):
        return True
    vi_path = os.path.join(dd, "version_info.json")
    if not os.path.isfile(vi_path):
        return True
    try:
        with open(vi_path) as f:
            expected = json.load(f).get("icon_count", 0)
        if expected and len(os.listdir(icons_dir)) < expected:
            return True
    except (ValueError, OSError):
        return True
    return False


def load_pack() -> dict[str, Any] | None:
    """Load emoji pack from data dir. Returns None if missing or corrupted."""
    dd = data_dir()
    if not dd:
        return None
    p = os.path.join(dd, "emoji.pack.json")
    if not os.path.isfile(p):
        return None
    try:
        with open(p) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def is_updater_running(dd: str) -> bool:
    """Return True if update_emoji.py is running. Removes stale lock if not."""
    lock = os.path.join(dd, EMOJI_LOCK_FILE)
    if not os.path.isfile(lock):
        return False
    try:
        with open(lock) as f:
            pid = int(f.read().strip())
        os.kill(pid, 0)
        return True
    except (ValueError, ProcessLookupError, PermissionError, OSError):
        try:
            os.unlink(lock)
        except OSError:
            pass
        return False


def is_update_in_progress(dd: str) -> bool:
    """Return True if update_emoji.py has confirmed real changes are being applied."""
    return os.path.isfile(os.path.join(dd, UPDATE_IN_PROGRESS_FILE))


def run_updater(dd: str) -> bool:
    """Spawn update_emoji.py in the background. Returns True if running or started."""
    if is_updater_running(dd):
        return True
    updater = os.path.join(os.getcwd(), "update_emoji.py")
    if not os.path.isfile(updater):
        print(f"Updater not found: {updater}", file=sys.stderr)
        return False
    os.makedirs(dd, exist_ok=True)
    p = subprocess.Popen(
        [sys.executable, updater, dd],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    lock = os.path.join(dd, EMOJI_LOCK_FILE)
    with open(lock, "w") as f:
        f.write(str(p.pid))
    _touch(os.path.join(dd, UPDATE_TRIGGER_FILE))
    return True


def should_trigger_update(dd: str) -> bool:
    """Return True if UPDATE_INTERVAL has elapsed since the last update trigger."""
    stamp = os.path.join(dd, UPDATE_TRIGGER_FILE)
    try:
        return time.time() - os.path.getmtime(stamp) >= UPDATE_INTERVAL
    except FileNotFoundError:
        return True


def _touch(path: str) -> None:
    try:
        os.utime(path, None)
    except FileNotFoundError:
        with open(path, "w"):
            pass


def _read_setup_retries(dd: str) -> int:
    """Return setup retry count, treating absent or stale file as 0."""
    p = os.path.join(dd, SETUP_RETRY_FILE)
    try:
        if time.time() - os.path.getmtime(p) >= UPDATE_INTERVAL:
            return 0
        with open(p) as f:
            return int(f.read().strip())
    except (FileNotFoundError, ValueError, OSError):
        return 0


def _clear_setup_retries(dd: str) -> None:
    """Remove the retry counter so the next setup attempt starts fresh."""
    try:
        os.unlink(os.path.join(dd, SETUP_RETRY_FILE))
    except FileNotFoundError:
        pass


def _recently_failed(dd: str) -> bool:
    """Return True if a failure was recorded within UPDATE_INTERVAL."""
    p = os.path.join(dd, FAILED_FILE)
    try:
        return time.time() - os.path.getmtime(p) < UPDATE_INTERVAL
    except FileNotFoundError:
        return False


def _increment_setup_retries(dd: str) -> None:
    count = _read_setup_retries(dd)
    with open(os.path.join(dd, SETUP_RETRY_FILE), "w") as f:
        f.write(str(count + 1))


def _progress_subtitle(dd: str) -> str:
    """Return 'N out of X done.' while icons are being generated, else empty string."""
    try:
        with open(os.path.join(dd, ICONS_EXPECTED_FILE)) as f:
            expected = int(f.read().strip())
    except (OSError, ValueError):
        return ""

    if not expected:
        return ""

    icons_dir = os.path.join(dd, "icons")
    try:
        actual = sum(1 for f in os.listdir(icons_dir) if f.endswith(".png"))
    except OSError:
        actual = 0

    return f"{actual} out of {expected} done."


def _with_progress(item: dict[str, Any], dd: str, prefix: str) -> dict[str, Any]:
    """Return a copy of item with progress counter appended when icons are being generated."""
    progress = _progress_subtitle(dd)
    if not progress:
        return item
    return {**item, "subtitle": f"{prefix}. {progress}"}


def add_modifier(char: str, skin_support: bool, modifier: str | None) -> str:
    """Apply a skin tone modifier to an emoji character."""
    if not modifier or not skin_support:
        return char
    return char.replace(ZWJ, modifier + ZWJ) if ZWJ in char else char + modifier


def icon_path(
    slug: str, skin_tone: int | None, skin_support: bool, icons_dir: str
) -> str:
    """Resolve the icon file path, falling back to a relative path if not found."""
    name = (
        f"{slug}_{skin_tone}"
        if skin_support and skin_tone is not None and 0 <= skin_tone <= 4
        else slug
    )
    p = os.path.join(icons_dir, f"{name}.png")
    return p if os.path.isfile(p) else f"./icons/{name}.png"


def build_item(
    char: str,
    info: dict[str, Any],
    modifier: str | None,
    skin_tone: int | None,
    icons_dir: str,
    verb: str,
    prep: str,
) -> dict[str, Any]:
    """Build an Alfred result item for an emoji."""
    skin_support = info.get("skin_tone_support", False)
    modified = add_modifier(char, skin_support, modifier)
    slug = info["slug"]
    name = info["name"]
    cp = info.get("codepoint", "")
    icon = icon_path(slug, skin_tone, skin_support, icons_dir)
    base_icon = icon_path(slug, None, False, icons_dir)
    return {
        "uid": name,
        "title": name,
        "subtitle": f'{verb} "{modified}" ({name}) {prep}',
        "arg": modified,
        "autocomplete": name,
        "icon": {"path": icon},
        "mods": {
            "alt": {
                "subtitle": f'{verb} ":{slug}:" ({char}) {prep}',
                "arg": f":{slug}:",
                "icon": {"path": base_icon},
            },
            "shift": {
                "subtitle": f'{verb} "{char}" ({name}) {prep}',
                "arg": char,
                "icon": {"path": base_icon},
            },
            "ctrl": {
                "subtitle": f'{verb} "U+{cp}" ({char}) {prep}',
                "arg": f"U+{cp}",
                "icon": {"path": base_icon},
            },
        },
    }


def do_search(
    query: str,
    pack: dict[str, Any],
    skin_tone: int | None,
    paste_by_default: bool,
) -> list[dict[str, Any]]:
    """Search emoji by query and return Alfred result items."""
    verb = "Paste" if paste_by_default else "Copy"
    prep = "as snippet" if paste_by_default else "to clipboard"

    components = pack["emojiComponents"]
    mods = [
        components["light_skin_tone"],
        components["medium_light_skin_tone"],
        components["medium_skin_tone"],
        components["medium_dark_skin_tone"],
        components["dark_skin_tone"],
    ]
    modifier = (
        mods[skin_tone] if skin_tone is not None and 0 <= skin_tone <= 4 else None
    )

    dd = data_dir()
    icons_dir = os.path.join(dd, "icons") if dd else "./icons"
    emoji_info: dict[str, Any] = pack["emoji"]
    ordered: list[str] = pack["orderedEmoji"]

    if query:
        terms = query.replace(":", "").split()
        keywords_map: dict[str, list[str]] = pack["keywords"]
        search_terms: list[str] = pack["searchTerms"]
        matched: set[str] = set()
        for term in terms:
            for st in search_terms:
                if term in st:
                    matched.update(keywords_map[st])
        position = {c: i for i, c in enumerate(ordered)}
        chars: list[str] = sorted(matched, key=lambda c: position.get(c, len(ordered)))
    else:
        chars = ordered

    items = []
    for char in chars:
        info = emoji_info.get(char)
        if info:
            items.append(
                build_item(char, info, modifier, skin_tone, icons_dir, verb, prep)
            )
    return items


def output(
    items: list[dict[str, Any]],
    cache_seconds: int | None = None,
    rerun: int | float | None = None,
) -> None:
    """Write Alfred JSON response to stdout."""
    result: dict[str, Any] = {"items": items}
    if cache_seconds is not None:
        result["cache"] = {"seconds": cache_seconds, "loosereload": True}
    if rerun is not None:
        result["rerun"] = rerun
    json.dump(result, sys.stdout, ensure_ascii=False)


def _parse_skin_tone(raw: str) -> int | None:
    if raw == "random":
        return random.randint(0, 4)
    if raw.isdigit():
        val = int(raw)
        if 0 <= val <= 4:
            return val
    return None


def main() -> None:
    query = sys.argv[1].strip() if len(sys.argv) > 1 else ""
    dd = data_dir()
    pack = load_pack()

    if not pack or needs_setup():
        # No recorded failure — clear any stale retry count in case files were deleted.
        if not _recently_failed(dd):
            _clear_setup_retries(dd)

        if is_updater_running(dd):
            output(
                [_with_progress(_SETUP_ITEM, dd, "Downloading and generating icons")],
                rerun=2,
            )
            return

        retries = _read_setup_retries(dd)
        if retries < MAX_SETUP_RETRIES:
            if run_updater(dd):
                _increment_setup_retries(dd)
                output(
                    [
                        _with_progress(
                            _SETUP_ITEM, dd, "Downloading and generating icons"
                        )
                    ],
                    rerun=2,
                )
            else:
                output([_ERROR_ITEM])
            return

        # Retries exhausted — show what we have or error
        if not pack:
            output([_ERROR_ITEM])
            return

    # Daily update trigger
    if should_trigger_update(dd):
        if not _recently_failed(dd):
            run_updater(dd)

    if is_updater_running(dd) and is_update_in_progress(dd):
        output([_with_progress(_UPDATE_ITEM, dd, "New emoji data available")], rerun=2)
        return

    skin_tone = _parse_skin_tone(os.environ.get("skin_tone", ""))
    paste = bool(os.environ.get("snippetapp", ""))
    items = do_search(query, pack, skin_tone, paste)
    output(items)


if __name__ == "__main__":
    main()
