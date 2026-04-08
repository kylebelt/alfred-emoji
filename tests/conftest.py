"""Shared fixtures for the alfred-emoji test suite."""

from __future__ import annotations

import copy
import json
from typing import Any

import pytest

# Minimal pack with three emoji covering: skin tone, ZWJ sequence, plain
MINIMAL_PACK: dict[str, Any] = {
    "keywords": {
        "thumbs_up": ["\U0001f44d"],
        "thumbs": ["\U0001f44d"],
        "smile": ["\U0001f60a"],
        "smiling": ["\U0001f60a"],
        "rockstar": ["\U0001f9d1\u200d\U0001f3a4"],
        "music": ["\U0001f9d1\u200d\U0001f3a4"],
    },
    "searchTerms": [
        "thumbs_up",
        "thumbs",
        "smile",
        "smiling",
        "rockstar",
        "music",
    ],
    "emoji": {
        "\U0001f44d": {
            "name": "thumbs up",
            "slug": "thumbs_up",
            "skin_tone_support": True,
            "codepoint": "1F44D",
            "keywords": ["thumbs_up", "thumbs"],
        },
        "\U0001f60a": {
            "name": "smiling face",
            "slug": "smiling_face",
            "skin_tone_support": False,
            "codepoint": "1F60A",
            "keywords": ["smile", "smiling"],
        },
        "\U0001f9d1\u200d\U0001f3a4": {
            "name": "singer",
            "slug": "singer",
            "skin_tone_support": True,
            "codepoint": "1F9D1",
            "keywords": ["rockstar", "music"],
        },
    },
    "orderedEmoji": ["\U0001f44d", "\U0001f60a", "\U0001f9d1\u200d\U0001f3a4"],
    "emojiComponents": {
        "light_skin_tone": "\U0001f3fb",
        "medium_light_skin_tone": "\U0001f3fc",
        "medium_skin_tone": "\U0001f3fd",
        "medium_dark_skin_tone": "\U0001f3fe",
        "dark_skin_tone": "\U0001f3ff",
    },
    "versions": {"emojilib": "4.0.0", "unicode_emoji_json": "0.8.0"},
}


@pytest.fixture
def minimal_pack() -> dict[str, Any]:
    return copy.deepcopy(MINIMAL_PACK)


@pytest.fixture
def data_dir(tmp_path):
    """Isolated alfred_workflow_data directory."""
    d = tmp_path / "workflow_data"
    d.mkdir()
    return d


@pytest.fixture
def pack_file(data_dir, minimal_pack):
    """Write minimal_pack to data_dir and return its path."""
    p = data_dir / "emoji.pack.json"
    p.write_text(json.dumps(minimal_pack), encoding="utf-8")
    return p


@pytest.fixture
def complete_setup(data_dir, pack_file):
    """Full data_dir with pack, version_info.json, and enough icon stubs."""
    icons = data_dir / "icons"
    icons.mkdir()
    for name in ("thumbs_up", "smiling_face", "singer"):
        (icons / f"{name}.png").touch()
    vi = data_dir / "version_info.json"
    vi.write_text(
        json.dumps({"icon_count": 3, "emoji_count": 3, "versions": {}}),
        encoding="utf-8",
    )
    return data_dir
