"""Tests for src/update_emoji.py."""

from __future__ import annotations

import http.client
import json
import os
import sys
import urllib.error
from typing import Any
from unittest.mock import MagicMock

import pytest

import update_emoji as ue


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_response(body: bytes, etag: str = "") -> MagicMock:
    """Return a mock urlopen context manager response."""
    resp = MagicMock()
    resp.read.return_value = body
    resp.headers.get.return_value = etag
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("url", code, "err", http.client.HTTPMessage(), None)


def _source_responses() -> dict[str, Any]:
    return {
        "keywords": {"\U0001f44d": ["thumbs_up"]},
        "emoji_data": {
            "\U0001f44d": {
                "name": "thumbs up",
                "slug": "thumbs_up",
                "skin_tone_support": True,
            }
        },
        "ordered": ["\U0001f44d"],
        "components": {
            "light_skin_tone": "\U0001f3fb",
            "medium_light_skin_tone": "\U0001f3fc",
            "medium_skin_tone": "\U0001f3fd",
            "medium_dark_skin_tone": "\U0001f3fe",
            "dark_skin_tone": "\U0001f3ff",
        },
        "emojilib_pkg": {"version": "4.0.0"},
        "unicode_pkg": {"version": "0.8.0"},
    }


# ---------------------------------------------------------------------------
# ETag helpers
# ---------------------------------------------------------------------------


def test_load_etag_missing(data_dir):
    assert ue.load_etag(str(data_dir), "keywords") is None


def test_save_and_load_etag(data_dir):
    ue.save_etag(str(data_dir), "keywords", '"abc123"')
    assert ue.load_etag(str(data_dir), "keywords") == '"abc123"'


def test_save_etag_empty_string_skipped(data_dir):
    ue.save_etag(str(data_dir), "keywords", "")
    assert ue.load_etag(str(data_dir), "keywords") is None


# ---------------------------------------------------------------------------
# download_json_conditional
# ---------------------------------------------------------------------------


def test_download_conditional_200(data_dir, mocker):
    payload = json.dumps({"key": "value"}).encode()
    mocker.patch(
        "urllib.request.urlopen",
        return_value=_make_response(payload, '"etag1"'),
    )
    data, changed = ue.download_json_conditional(
        "https://example.com/data.json", str(data_dir), "test"
    )
    assert changed is True
    assert data == {"key": "value"}
    assert ue.load_etag(str(data_dir), "test") == '"etag1"'


def test_download_conditional_304(data_dir, mocker):
    mocker.patch("urllib.request.urlopen", side_effect=_http_error(304))
    data, changed = ue.download_json_conditional(
        "https://example.com/data.json", str(data_dir), "test"
    )
    assert changed is False
    assert data is None


def test_download_conditional_other_http_error(data_dir, mocker):
    mocker.patch("urllib.request.urlopen", side_effect=_http_error(500))
    with pytest.raises(urllib.error.HTTPError):
        ue.download_json_conditional(
            "https://example.com/data.json", str(data_dir), "test"
        )


# ---------------------------------------------------------------------------
# gen_pack
# ---------------------------------------------------------------------------


def test_gen_pack_all_changed_writes_to_staging(data_dir, mocker):
    responses = _source_responses()

    def fake_download(url, dd, key):
        return responses[key], True

    mocker.patch("update_emoji.download_json_conditional", side_effect=fake_download)
    pack, changed = ue.gen_pack(str(data_dir))

    assert changed is True
    # New pack must be in staging, not yet live
    staging_path = data_dir / ue.STAGING_DIR / "emoji.pack.json"
    live_path = data_dir / "emoji.pack.json"
    assert staging_path.exists()
    assert not live_path.exists()
    assert "\U0001f44d" in pack["emoji"]


def test_gen_pack_no_change_loads_existing(data_dir, mocker):
    existing = {
        "orderedEmoji": ["\U0001f44d"],
        "emoji": {},
        "keywords": {},
        "searchTerms": [],
        "emojiComponents": {},
        "versions": {},
    }
    (data_dir / "emoji.pack.json").write_text(json.dumps(existing))
    mocker.patch(
        "update_emoji.download_json_conditional",
        return_value=(None, False),
    )
    pack, changed = ue.gen_pack(str(data_dir))
    assert changed is False
    assert pack["orderedEmoji"] == ["\U0001f44d"]
    assert not (data_dir / ue.STAGING_DIR).exists()


def test_gen_pack_structure(data_dir, mocker):
    responses = _source_responses()

    def fake_download(url, dd, key):
        return responses[key], True

    mocker.patch("update_emoji.download_json_conditional", side_effect=fake_download)
    pack, _ = ue.gen_pack(str(data_dir))
    for key in (
        "keywords",
        "searchTerms",
        "emoji",
        "orderedEmoji",
        "emojiComponents",
        "versions",
    ):
        assert key in pack


def test_gen_pack_mixed_304_no_redundant_call(data_dir, mocker):
    """304 sources must be re-fetched with a single direct urlopen call."""
    responses = _source_responses()
    call_count: dict[str, int] = {}

    def fake_download(url, dd, key):
        call_count[key] = call_count.get(key, 0) + 1
        if key == "keywords":
            return None, False
        return responses[key], True

    mocker.patch("update_emoji.download_json_conditional", side_effect=fake_download)
    mocker.patch(
        "urllib.request.urlopen",
        return_value=_make_response(json.dumps(responses["keywords"]).encode()),
    )
    ue.gen_pack(str(data_dir))
    assert call_count.get("keywords", 0) == 1


# ---------------------------------------------------------------------------
# gen_icons
# ---------------------------------------------------------------------------


def test_gen_icons_skips_all_existing(data_dir, minimal_pack, mocker):
    icons_dir = data_dir / "icons"
    icons_dir.mkdir()
    for name in ("thumbs_up", "smiling_face", "singer"):
        (icons_dir / f"{name}.png").touch()
    for i in range(5):
        (icons_dir / f"thumbs_up_{i}.png").touch()
        (icons_dir / f"singer_{i}.png").touch()

    run_mock = mocker.patch("subprocess.run")
    mocker.patch("update_emoji._swift_source", return_value="swift code")

    actual, expected = ue.gen_icons(str(data_dir), minimal_pack)
    run_mock.assert_not_called()
    assert actual == expected


def test_gen_icons_returns_tuple(data_dir, minimal_pack, mocker):
    mocker.patch("update_emoji._swift_source", return_value="swift code")
    src_hash = ue._swift_hash("swift code")
    (data_dir / ue.ICONGEN_HASH_FILE).write_text(src_hash)
    (data_dir / ue.ICONGEN_BINARY).touch()
    mocker.patch(
        "subprocess.run",
        return_value=MagicMock(returncode=0, stderr=""),
    )
    result = ue.gen_icons(str(data_dir), minimal_pack)
    assert isinstance(result, tuple)
    assert len(result) == 2


def test_gen_icons_raises_on_swift_failure(data_dir, minimal_pack, mocker):
    mocker.patch("update_emoji._swift_source", return_value="swift code")
    mocker.patch(
        "subprocess.run",
        return_value=MagicMock(returncode=1, stderr="error"),
    )
    with pytest.raises(RuntimeError, match="Swift compilation failed"):
        ue.gen_icons(str(data_dir), minimal_pack)


def test_gen_icons_binary_cache_hit(data_dir, minimal_pack, mocker):
    """swiftc must not be called when hash matches and binary exists."""
    mocker.patch("update_emoji._swift_source", return_value="swift code")
    src_hash = ue._swift_hash("swift code")
    (data_dir / ue.ICONGEN_HASH_FILE).write_text(src_hash)
    (data_dir / ue.ICONGEN_BINARY).touch()

    run_mock = mocker.patch(
        "subprocess.run",
        return_value=MagicMock(returncode=0, stderr=""),
    )
    ue.gen_icons(str(data_dir), minimal_pack)
    calls = [str(c) for c in run_mock.call_args_list]
    assert not any("swiftc" in c for c in calls)


def test_gen_icons_binary_cache_miss(data_dir, minimal_pack, mocker):
    """swiftc must be called when hash differs."""
    mocker.patch("update_emoji._swift_source", return_value="swift code")
    (data_dir / ue.ICONGEN_HASH_FILE).write_text("stale_hash")
    (data_dir / ue.ICONGEN_BINARY).touch()

    run_mock = mocker.patch(
        "subprocess.run",
        return_value=MagicMock(returncode=0, stderr=""),
    )
    ue.gen_icons(str(data_dir), minimal_pack)
    calls = [str(c) for c in run_mock.call_args_list]
    assert any("swiftc" in c for c in calls)


def test_gen_icons_checks_binary_returncode(data_dir, minimal_pack, mocker, capsys):
    """Non-zero exit from the icongen binary must be logged but not raise."""
    mocker.patch("update_emoji._swift_source", return_value="swift code")
    src_hash = ue._swift_hash("swift code")
    (data_dir / ue.ICONGEN_HASH_FILE).write_text(src_hash)
    (data_dir / ue.ICONGEN_BINARY).touch()

    mocker.patch(
        "subprocess.run",
        return_value=MagicMock(returncode=1, stderr="icon error"),
    )
    ue.gen_icons(str(data_dir), minimal_pack)
    assert "icon error" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# save_version_info
# ---------------------------------------------------------------------------


def test_save_version_info_stores_expected_count(data_dir, minimal_pack):
    ue.save_version_info(
        str(data_dir), minimal_pack, icons_generated=10, icons_expected=100
    )
    vi = json.loads((data_dir / "version_info.json").read_text())
    assert vi["icon_count"] == 100  # expected — what needs_setup() checks
    assert vi["icons_generated"] == 10  # actual


def test_save_version_info_structure(data_dir, minimal_pack):
    ue.save_version_info(
        str(data_dir), minimal_pack, icons_generated=3, icons_expected=3
    )
    vi = json.loads((data_dir / "version_info.json").read_text())
    assert vi["emoji_count"] == len(minimal_pack["orderedEmoji"])
    assert "versions" in vi


# ---------------------------------------------------------------------------
# main() — lock, staging, failure handling
# ---------------------------------------------------------------------------


def _make_pack_responses(mocker, data_dir):
    responses = _source_responses()

    def fake_download(url, dd, key):
        return responses[key], True

    mocker.patch("update_emoji.download_json_conditional", side_effect=fake_download)
    mocker.patch("update_emoji._swift_source", return_value="swift code")
    src_hash = ue._swift_hash("swift code")
    (data_dir / ue.ICONGEN_HASH_FILE).write_text(src_hash)
    (data_dir / ue.ICONGEN_BINARY).touch()
    mocker.patch(
        "subprocess.run",
        return_value=MagicMock(returncode=0, stderr=""),
    )


def test_main_lock_cleaned_on_success(data_dir, mocker):
    _make_pack_responses(mocker, data_dir)
    lock = data_dir / ue.LOCK_FILE
    lock.write_text(str(os.getpid()))

    mocker.patch.object(sys, "argv", ["update_emoji.py", str(data_dir)])
    ue.main()
    assert not lock.exists()


def test_main_lock_cleaned_on_failure(data_dir, mocker):
    mocker.patch("update_emoji.gen_pack", side_effect=RuntimeError("network down"))
    lock = data_dir / ue.LOCK_FILE
    lock.write_text("12345")

    mocker.patch.object(sys, "argv", ["update_emoji.py", str(data_dir)])
    ue.main()
    assert not lock.exists()


def test_main_failed_file_written_on_failure(data_dir, mocker):
    mocker.patch("update_emoji.gen_pack", side_effect=RuntimeError("network down"))

    mocker.patch.object(sys, "argv", ["update_emoji.py", str(data_dir)])
    ue.main()
    failed = data_dir / ue.FAILED_FILE
    assert failed.exists()
    assert "network down" in failed.read_text()


def test_main_staging_discarded_on_failure(data_dir, mocker):
    staging = data_dir / ue.STAGING_DIR
    staging.mkdir()
    (staging / "emoji.pack.json").write_text("{}")
    mocker.patch("update_emoji.gen_pack", side_effect=RuntimeError("fail"))

    mocker.patch.object(sys, "argv", ["update_emoji.py", str(data_dir)])
    ue.main()
    assert not staging.exists()


def test_main_pack_not_swapped_on_failure(data_dir, mocker):
    old_pack = {"orderedEmoji": ["old"], "emoji": {}}
    live = data_dir / "emoji.pack.json"
    live.write_text(json.dumps(old_pack))
    mocker.patch("update_emoji.gen_pack", side_effect=RuntimeError("fail"))

    mocker.patch.object(sys, "argv", ["update_emoji.py", str(data_dir)])
    ue.main()
    assert json.loads(live.read_text()) == old_pack


def test_main_atomic_swap_on_success(data_dir, mocker):
    _make_pack_responses(mocker, data_dir)

    mocker.patch.object(sys, "argv", ["update_emoji.py", str(data_dir)])
    ue.main()
    live = data_dir / "emoji.pack.json"
    assert live.exists()
    assert not (data_dir / ue.STAGING_DIR).exists()


def test_main_clears_failed_file_on_success(data_dir, mocker):
    _make_pack_responses(mocker, data_dir)
    failed = data_dir / ue.FAILED_FILE
    failed.write_text("previous error")

    mocker.patch.object(sys, "argv", ["update_emoji.py", str(data_dir)])
    ue.main()
    assert not failed.exists()


def test_gen_icons_writes_expected_file(data_dir, minimal_pack, mocker):
    """gen_icons() writes .icons_expected before invoking the binary."""
    mocker.patch("update_emoji._swift_source", return_value="swift code")
    src_hash = ue._swift_hash("swift code")
    (data_dir / ue.ICONGEN_HASH_FILE).write_text(src_hash)
    (data_dir / ue.ICONGEN_BINARY).touch()

    written: list[int] = []

    def capture_run(cmd, **kwargs):
        if ue.ICONGEN_BINARY in str(cmd):
            expected_file = data_dir / ue.ICONS_EXPECTED_FILE
            if expected_file.exists():
                written.append(int(expected_file.read_text()))
        return MagicMock(returncode=0, stderr="")

    mocker.patch("subprocess.run", side_effect=capture_run)
    ue.gen_icons(str(data_dir), minimal_pack)
    assert written, ".icons_expected was not present when binary was called"
    assert written[0] > 0


def test_main_expected_file_cleaned_on_success(data_dir, mocker):
    """main() removes .icons_expected in the finally block on success."""
    _make_pack_responses(mocker, data_dir)
    mocker.patch.object(sys, "argv", ["update_emoji.py", str(data_dir)])
    ue.main()
    assert not (data_dir / ue.ICONS_EXPECTED_FILE).exists()


def test_main_expected_file_cleaned_on_failure(data_dir, mocker):
    """main() removes .icons_expected in the finally block on failure."""
    (data_dir / ue.ICONS_EXPECTED_FILE).write_text("3521")
    mocker.patch("update_emoji.gen_pack", side_effect=RuntimeError("fail"))
    mocker.patch.object(sys, "argv", ["update_emoji.py", str(data_dir)])
    ue.main()
    assert not (data_dir / ue.ICONS_EXPECTED_FILE).exists()


# ---------------------------------------------------------------------------
# .update_in_progress signal
# ---------------------------------------------------------------------------


def test_gen_pack_writes_in_progress_on_changes(data_dir, mocker):
    """gen_pack() writes .update_in_progress when sources have changed."""
    responses = _source_responses()

    def fake_download(url, dd, key):
        return responses[key], True

    mocker.patch("update_emoji.download_json_conditional", side_effect=fake_download)
    ue.gen_pack(str(data_dir))
    assert (data_dir / ue.UPDATE_IN_PROGRESS_FILE).exists()


def test_gen_pack_no_in_progress_when_unchanged(data_dir, mocker):
    """gen_pack() does NOT write .update_in_progress when all sources are 304."""
    existing = {
        "orderedEmoji": ["\U0001f44d"],
        "emoji": {},
        "keywords": {},
        "searchTerms": [],
        "emojiComponents": {},
        "versions": {},
    }
    (data_dir / "emoji.pack.json").write_text(json.dumps(existing))
    mocker.patch(
        "update_emoji.download_json_conditional",
        return_value=(None, False),
    )
    ue.gen_pack(str(data_dir))
    assert not (data_dir / ue.UPDATE_IN_PROGRESS_FILE).exists()


def test_main_in_progress_file_cleaned_on_success(data_dir, mocker):
    """main() removes .update_in_progress in the finally block on success."""
    _make_pack_responses(mocker, data_dir)
    mocker.patch.object(sys, "argv", ["update_emoji.py", str(data_dir)])
    ue.main()
    assert not (data_dir / ue.UPDATE_IN_PROGRESS_FILE).exists()


def test_main_in_progress_file_cleaned_on_failure(data_dir, mocker):
    """main() removes .update_in_progress in the finally block on failure."""
    (data_dir / ue.UPDATE_IN_PROGRESS_FILE).write_text("")
    mocker.patch("update_emoji.gen_pack", side_effect=RuntimeError("fail"))
    mocker.patch.object(sys, "argv", ["update_emoji.py", str(data_dir)])
    ue.main()
    assert not (data_dir / ue.UPDATE_IN_PROGRESS_FILE).exists()
