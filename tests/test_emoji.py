"""Tests for src/emoji.py."""

from __future__ import annotations

import json
import os
import sys
import time


import emoji as em


# ---------------------------------------------------------------------------
# load_pack
# ---------------------------------------------------------------------------


def test_load_pack_valid(data_dir, pack_file, monkeypatch):
    monkeypatch.setenv("alfred_workflow_data", str(data_dir))
    pack = em.load_pack()
    assert pack is not None
    assert "orderedEmoji" in pack


def test_load_pack_missing(data_dir, monkeypatch):
    monkeypatch.setenv("alfred_workflow_data", str(data_dir))
    assert em.load_pack() is None


def test_load_pack_corrupted(data_dir, monkeypatch):
    monkeypatch.setenv("alfred_workflow_data", str(data_dir))
    (data_dir / "emoji.pack.json").write_text("{ not valid json }")
    assert em.load_pack() is None


# ---------------------------------------------------------------------------
# needs_setup
# ---------------------------------------------------------------------------


def test_needs_setup_no_data_dir(monkeypatch):
    monkeypatch.delenv("alfred_workflow_data", raising=False)
    assert em.needs_setup() is True


def test_needs_setup_missing_icons_dir(data_dir, pack_file, monkeypatch):
    monkeypatch.setenv("alfred_workflow_data", str(data_dir))
    assert em.needs_setup() is True


def test_needs_setup_missing_version_info(data_dir, pack_file, monkeypatch):
    monkeypatch.setenv("alfred_workflow_data", str(data_dir))
    (data_dir / "icons").mkdir()
    assert em.needs_setup() is True


def test_needs_setup_incomplete_icons(data_dir, pack_file, monkeypatch):
    monkeypatch.setenv("alfred_workflow_data", str(data_dir))
    icons = data_dir / "icons"
    icons.mkdir()
    (icons / "thumbs_up.png").touch()
    vi = data_dir / "version_info.json"
    vi.write_text(json.dumps({"icon_count": 10}))
    assert em.needs_setup() is True


def test_needs_setup_complete(complete_setup, monkeypatch):
    monkeypatch.setenv("alfred_workflow_data", str(complete_setup))
    assert em.needs_setup() is False


# ---------------------------------------------------------------------------
# should_trigger_update
# ---------------------------------------------------------------------------


def test_should_trigger_update_no_file(data_dir):
    assert em.should_trigger_update(str(data_dir)) is True


def test_should_trigger_update_fresh(data_dir):
    stamp = data_dir / em.UPDATE_TRIGGER_FILE
    stamp.touch()
    assert em.should_trigger_update(str(data_dir)) is False


def test_should_trigger_update_stale(data_dir):
    stamp = data_dir / em.UPDATE_TRIGGER_FILE
    stamp.touch()
    stale = time.time() - em.UPDATE_INTERVAL - 1
    os.utime(str(stamp), (stale, stale))
    assert em.should_trigger_update(str(data_dir)) is True


# ---------------------------------------------------------------------------
# is_updater_running
# ---------------------------------------------------------------------------


def test_is_updater_running_no_lock(data_dir):
    assert em.is_updater_running(str(data_dir)) is False


def test_is_updater_running_stale_lock(data_dir):
    lock = data_dir / em.EMOJI_LOCK_FILE
    lock.write_text("99999999")
    assert em.is_updater_running(str(data_dir)) is False
    assert not lock.exists()


def test_is_updater_running_live_pid(data_dir):
    lock = data_dir / em.EMOJI_LOCK_FILE
    lock.write_text(str(os.getpid()))
    assert em.is_updater_running(str(data_dir)) is True


# ---------------------------------------------------------------------------
# _read_setup_retries / _increment_setup_retries
# ---------------------------------------------------------------------------


def test_read_setup_retries_no_file(data_dir):
    assert em._read_setup_retries(str(data_dir)) == 0


def test_read_setup_retries_current(data_dir):
    (data_dir / em.SETUP_RETRY_FILE).write_text("2")
    assert em._read_setup_retries(str(data_dir)) == 2


def test_read_setup_retries_stale(data_dir):
    p = data_dir / em.SETUP_RETRY_FILE
    p.write_text("2")
    stale = time.time() - em.UPDATE_INTERVAL - 1
    os.utime(str(p), (stale, stale))
    assert em._read_setup_retries(str(data_dir)) == 0


def test_increment_setup_retries(data_dir):
    em._increment_setup_retries(str(data_dir))
    assert em._read_setup_retries(str(data_dir)) == 1
    em._increment_setup_retries(str(data_dir))
    assert em._read_setup_retries(str(data_dir)) == 2


# ---------------------------------------------------------------------------
# add_modifier
# ---------------------------------------------------------------------------


def test_add_modifier_no_support():
    assert em.add_modifier("😊", False, "🏽") == "😊"


def test_add_modifier_no_modifier():
    assert em.add_modifier("👍", True, None) == "👍"


def test_add_modifier_plain():
    assert em.add_modifier("👍", True, "🏽") == "👍🏽"


def test_add_modifier_zwj():
    singer = "\U0001f9d1\u200d\U0001f3a4"
    modified = em.add_modifier(singer, True, "🏽")
    assert "🏽" in modified
    assert "\u200d" in modified


# ---------------------------------------------------------------------------
# do_search
# ---------------------------------------------------------------------------


def test_do_search_no_query(minimal_pack, monkeypatch):
    monkeypatch.setenv("alfred_workflow_data", "")
    items = em.do_search("", minimal_pack, None, False)
    titles = [i["title"] for i in items]
    assert titles == ["thumbs up", "smiling face", "singer"]


def test_do_search_with_query(minimal_pack, monkeypatch):
    monkeypatch.setenv("alfred_workflow_data", "")
    items = em.do_search("thumbs", minimal_pack, None, False)
    assert len(items) == 1
    assert items[0]["title"] == "thumbs up"


def test_do_search_ordering_deterministic(minimal_pack, monkeypatch):
    """Results must follow orderedEmoji position, not set iteration order."""
    monkeypatch.setenv("alfred_workflow_data", "")
    items = em.do_search("s", minimal_pack, None, False)
    titles = [i["title"] for i in items]
    ordered = ["thumbs up", "smiling face", "singer"]
    assert titles == [t for t in ordered if t in titles]


def test_do_search_skin_tone_applied(minimal_pack, monkeypatch):
    monkeypatch.setenv("alfred_workflow_data", "")
    items = em.do_search("thumbs", minimal_pack, 2, False)
    assert items[0]["arg"] == "👍🏽"


def test_do_search_skin_tone_shift_mod_is_base(minimal_pack, monkeypatch):
    monkeypatch.setenv("alfred_workflow_data", "")
    items = em.do_search("thumbs", minimal_pack, 2, False)
    assert items[0]["mods"]["shift"]["arg"] == "👍"


def test_do_search_no_skin_support(minimal_pack, monkeypatch):
    monkeypatch.setenv("alfred_workflow_data", "")
    items = em.do_search("smile", minimal_pack, 2, False)
    assert items[0]["arg"] == "😊"


def test_do_search_skin_tone_out_of_range(minimal_pack, monkeypatch):
    monkeypatch.setenv("alfred_workflow_data", "")
    items = em.do_search("thumbs", minimal_pack, 5, False)
    assert items[0]["arg"] == "👍"


def test_do_search_zwj_modifier(minimal_pack, monkeypatch):
    monkeypatch.setenv("alfred_workflow_data", "")
    items = em.do_search("rockstar", minimal_pack, 2, False)
    result = items[0]["arg"]
    assert "🏽" in result
    assert "\u200d" in result


def test_do_search_paste_by_default(minimal_pack, monkeypatch):
    monkeypatch.setenv("alfred_workflow_data", "")
    items = em.do_search("thumbs", minimal_pack, None, True)
    assert "Paste" in items[0]["subtitle"]
    assert "as snippet" in items[0]["subtitle"]


# ---------------------------------------------------------------------------
# Alfred item constants — no mods, valid: False
# ---------------------------------------------------------------------------


def test_setup_item_no_mods():
    assert "mods" not in em._SETUP_ITEM


def test_update_item_no_mods():
    assert "mods" not in em._UPDATE_ITEM


def test_error_item_no_mods():
    assert "mods" not in em._ERROR_ITEM


def test_setup_item_not_valid():
    assert em._SETUP_ITEM["valid"] is False


def test_update_item_not_valid():
    assert em._UPDATE_ITEM["valid"] is False


# ---------------------------------------------------------------------------
# output
# ---------------------------------------------------------------------------


def test_output_basic(capsys, minimal_pack, monkeypatch):
    monkeypatch.setenv("alfred_workflow_data", "")
    items = em.do_search("", minimal_pack, None, False)
    em.output(items)
    captured = json.loads(capsys.readouterr().out)
    assert "items" in captured
    assert len(captured["items"]) == 3


def test_output_with_rerun(capsys):
    em.output([], rerun=2)
    captured = json.loads(capsys.readouterr().out)
    assert captured["rerun"] == 2


def test_output_zero_rerun(capsys):
    """rerun=0 must be included, not skipped as falsy."""
    em.output([], rerun=0)
    captured = json.loads(capsys.readouterr().out)
    assert "rerun" in captured
    assert captured["rerun"] == 0


def test_output_with_cache(capsys):
    em.output([], cache_seconds=60)
    captured = json.loads(capsys.readouterr().out)
    assert captured["cache"]["seconds"] == 60


def test_output_none_rerun_omitted(capsys):
    em.output([])
    captured = json.loads(capsys.readouterr().out)
    assert "rerun" not in captured


# ---------------------------------------------------------------------------
# _parse_skin_tone
# ---------------------------------------------------------------------------


def test_parse_skin_tone_none():
    assert em._parse_skin_tone("") is None


def test_parse_skin_tone_valid():
    assert em._parse_skin_tone("2") == 2


def test_parse_skin_tone_out_of_range():
    assert em._parse_skin_tone("9") is None


def test_parse_skin_tone_random():
    result = em._parse_skin_tone("random")
    assert result in range(5)


# ---------------------------------------------------------------------------
# main() — setup retry logic
# ---------------------------------------------------------------------------


def test_main_setup_first_attempt(data_dir, monkeypatch, mocker, capsys):
    """First attempt: spawn updater, show setup banner with rerun."""
    monkeypatch.setenv("alfred_workflow_data", str(data_dir))
    mocker.patch("emoji.run_updater", return_value=True)
    mocker.patch.object(sys, "argv", ["emoji.py", ""])
    em.main()
    out = json.loads(capsys.readouterr().out)
    assert out["items"][0]["title"] == em._SETUP_ITEM["title"]
    assert out["rerun"] == 2
    assert em._read_setup_retries(str(data_dir)) == 1


def test_main_setup_retries_within_limit(data_dir, monkeypatch, mocker, capsys):
    """Retry 2 of 3: still shows setup banner."""
    monkeypatch.setenv("alfred_workflow_data", str(data_dir))
    (data_dir / em.SETUP_RETRY_FILE).write_text("1")
    mocker.patch("emoji.run_updater", return_value=True)
    mocker.patch.object(sys, "argv", ["emoji.py", ""])
    em.main()
    out = json.loads(capsys.readouterr().out)
    assert out["items"][0]["title"] == em._SETUP_ITEM["title"]
    assert out["rerun"] == 2


def test_main_setup_retries_exhausted_no_pack(data_dir, monkeypatch, mocker, capsys):
    """Max retries, no pack — show error item, no rerun."""
    monkeypatch.setenv("alfred_workflow_data", str(data_dir))
    (data_dir / em.SETUP_RETRY_FILE).write_text(str(em.MAX_SETUP_RETRIES))
    mocker.patch.object(sys, "argv", ["emoji.py", ""])
    em.main()
    out = json.loads(capsys.readouterr().out)
    assert out["items"][0]["title"] == em._ERROR_ITEM["title"]
    assert "rerun" not in out


def test_main_setup_retries_exhausted_with_pack(
    data_dir, pack_file, complete_setup, monkeypatch, mocker, capsys
):
    """Max retries but valid pack exists — fall through to show results."""
    monkeypatch.setenv("alfred_workflow_data", str(complete_setup))
    (complete_setup / em.SETUP_RETRY_FILE).write_text(str(em.MAX_SETUP_RETRIES))
    # Simulate needs_setup returning False (setup is actually complete)
    mocker.patch("emoji.needs_setup", return_value=False)
    mocker.patch.object(sys, "argv", ["emoji.py", ""])
    em.main()
    out = json.loads(capsys.readouterr().out)
    assert "items" in out
    # Should get real results, not an error item
    assert out["items"][0]["title"] != em._ERROR_ITEM["title"]


def test_main_updater_not_found_shows_error(data_dir, monkeypatch, mocker, capsys):
    """run_updater returns False (script not found) — show error immediately."""
    monkeypatch.setenv("alfred_workflow_data", str(data_dir))
    mocker.patch("emoji.run_updater", return_value=False)
    mocker.patch.object(sys, "argv", ["emoji.py", ""])
    em.main()
    out = json.loads(capsys.readouterr().out)
    assert out["items"][0]["title"] == em._ERROR_ITEM["title"]


# ---------------------------------------------------------------------------
# main() — daily update failure throttle
# ---------------------------------------------------------------------------


def test_main_daily_update_skipped_after_recent_failure(
    complete_setup, monkeypatch, mocker, capsys
):
    """Recent .update_failed present — daily trigger must not spawn updater."""
    monkeypatch.setenv("alfred_workflow_data", str(complete_setup))
    # Write a fresh .update_failed
    (complete_setup / em.FAILED_FILE).write_text("error")
    # Make daily trigger fire
    stale = time.time() - em.UPDATE_INTERVAL - 1
    stamp = complete_setup / em.UPDATE_TRIGGER_FILE
    stamp.touch()
    os.utime(str(stamp), (stale, stale))

    run_mock = mocker.patch("emoji.run_updater", return_value=False)
    mocker.patch.object(sys, "argv", ["emoji.py", ""])
    em.main()
    run_mock.assert_not_called()


def test_main_daily_update_retried_after_interval(
    complete_setup, monkeypatch, mocker, capsys
):
    """Stale .update_failed (>24h) — daily trigger should spawn updater."""
    monkeypatch.setenv("alfred_workflow_data", str(complete_setup))
    failed = complete_setup / em.FAILED_FILE
    failed.write_text("error")
    stale = time.time() - em.UPDATE_INTERVAL - 1
    os.utime(str(failed), (stale, stale))
    stamp = complete_setup / em.UPDATE_TRIGGER_FILE
    stamp.touch()
    os.utime(str(stamp), (stale, stale))

    run_mock = mocker.patch("emoji.run_updater", return_value=False)
    mocker.patch("emoji.is_updater_running", return_value=False)
    mocker.patch.object(sys, "argv", ["emoji.py", ""])
    em.main()
    run_mock.assert_called_once()


# ---------------------------------------------------------------------------
# _progress_subtitle / _with_progress
# ---------------------------------------------------------------------------


def test_progress_subtitle_no_data(data_dir):
    """Returns empty string when no icons and no expected-count files exist."""
    assert em._progress_subtitle(str(data_dir)) == ""


def test_progress_subtitle_icons_only_no_expected(data_dir):
    """Returns empty string when icons exist but the expected count is unknown."""
    icons = data_dir / "icons"
    icons.mkdir()
    for i in range(5):
        (icons / f"emoji_{i}.png").touch()
    assert em._progress_subtitle(str(data_dir)) == ""


def test_progress_subtitle_with_icons_expected_file(data_dir):
    """Uses .icons_expected (current-run file) for the total."""
    icons = data_dir / "icons"
    icons.mkdir()
    for i in range(150):
        (icons / f"emoji_{i}.png").touch()
    (data_dir / em.ICONS_EXPECTED_FILE).write_text("3521", encoding="utf-8")
    assert em._progress_subtitle(str(data_dir)) == "150 out of 3521 done."


def test_progress_subtitle_ignores_version_info_without_expected_file(data_dir):
    """Without .icons_expected, version_info.json is not used as a fallback."""
    icons = data_dir / "icons"
    icons.mkdir()
    for i in range(3):
        (icons / f"emoji_{i}.png").touch()
    (data_dir / "version_info.json").write_text(
        json.dumps({"icon_count": 10}), encoding="utf-8"
    )
    assert em._progress_subtitle(str(data_dir)) == ""


def test_with_progress_no_data_returns_item_unchanged(data_dir):
    """When no icons exist, the original item dict is returned as-is."""
    result = em._with_progress(em._SETUP_ITEM, str(data_dir), "Prefix")
    assert result is em._SETUP_ITEM


def test_with_progress_substitutes_subtitle(data_dir):
    """When icons exist, subtitle becomes '{prefix}. N out of X done.'"""
    icons = data_dir / "icons"
    icons.mkdir()
    for i in range(50):
        (icons / f"emoji_{i}.png").touch()
    (data_dir / em.ICONS_EXPECTED_FILE).write_text("100", encoding="utf-8")
    result = em._with_progress(
        em._SETUP_ITEM, str(data_dir), "Downloading and generating icons"
    )
    assert result["subtitle"] == "Downloading and generating icons. 50 out of 100 done."
    assert result["title"] == em._SETUP_ITEM["title"]
    assert "mods" not in result


def test_with_progress_does_not_mutate_original(data_dir):
    """The returned dict is a new object; the original constant is untouched."""
    icons = data_dir / "icons"
    icons.mkdir()
    (icons / "one.png").touch()
    (data_dir / em.ICONS_EXPECTED_FILE).write_text("100", encoding="utf-8")
    original_subtitle = em._SETUP_ITEM["subtitle"]
    em._with_progress(em._SETUP_ITEM, str(data_dir), "Prefix")
    assert em._SETUP_ITEM["subtitle"] == original_subtitle


# ---------------------------------------------------------------------------
# is_update_in_progress
# ---------------------------------------------------------------------------


def test_is_update_in_progress_no_file(data_dir):
    assert em.is_update_in_progress(str(data_dir)) is False


def test_is_update_in_progress_file_exists(data_dir):
    (data_dir / em.UPDATE_IN_PROGRESS_FILE).write_text("")
    assert em.is_update_in_progress(str(data_dir)) is True


# ---------------------------------------------------------------------------
# main() — update banner gated on UPDATE_IN_PROGRESS_FILE
# ---------------------------------------------------------------------------


def test_main_no_banner_without_in_progress_file(
    complete_setup, monkeypatch, mocker, capsys
):
    """Updater running but no .update_in_progress → show results, not banner."""
    monkeypatch.setenv("alfred_workflow_data", str(complete_setup))
    # Lock file present with our own PID so is_updater_running() returns True
    (complete_setup / em.EMOJI_LOCK_FILE).write_text(str(os.getpid()))
    # No .update_in_progress file
    mocker.patch.object(sys, "argv", ["emoji.py", ""])
    em.main()
    out = json.loads(capsys.readouterr().out)
    # Should have fallen through to search results, not the update banner
    assert out["items"][0]["title"] != em._UPDATE_ITEM["title"]


def test_main_banner_shown_when_in_progress(
    complete_setup, monkeypatch, mocker, capsys
):
    """Both lock and .update_in_progress present → show update banner."""
    monkeypatch.setenv("alfred_workflow_data", str(complete_setup))
    (complete_setup / em.EMOJI_LOCK_FILE).write_text(str(os.getpid()))
    (complete_setup / em.UPDATE_IN_PROGRESS_FILE).write_text("")
    mocker.patch.object(sys, "argv", ["emoji.py", ""])
    em.main()
    out = json.loads(capsys.readouterr().out)
    assert out["items"][0]["title"] == em._UPDATE_ITEM["title"]
    assert out["rerun"] == 2


# ---------------------------------------------------------------------------
# _clear_setup_retries
# ---------------------------------------------------------------------------


def test_clear_setup_retries_removes_file(data_dir):
    (data_dir / em.SETUP_RETRY_FILE).write_text("2")
    em._clear_setup_retries(str(data_dir))
    assert not (data_dir / em.SETUP_RETRY_FILE).exists()


def test_clear_setup_retries_no_file_is_noop(data_dir):
    em._clear_setup_retries(str(data_dir))  # must not raise


# ---------------------------------------------------------------------------
# main() — setup retry counter reset on fresh missing-files detection
# ---------------------------------------------------------------------------


def test_main_setup_resets_retries_when_no_recent_failure(
    data_dir, monkeypatch, mocker, capsys
):
    """Pack missing, no .update_failed → retry counter cleared → setup starts."""
    monkeypatch.setenv("alfred_workflow_data", str(data_dir))
    # Retry counter is at max from a previous session
    (data_dir / em.SETUP_RETRY_FILE).write_text(str(em.MAX_SETUP_RETRIES))
    # No .update_failed file — this looks like fresh corruption
    mocker.patch("emoji.run_updater", return_value=True)
    mocker.patch.object(sys, "argv", ["emoji.py", ""])
    em.main()
    out = json.loads(capsys.readouterr().out)
    # Counter was cleared, so setup could proceed and shows the setup banner
    assert out["items"][0]["title"] == em._SETUP_ITEM["title"]
    assert out["rerun"] == 2


def test_main_setup_keeps_retries_when_recently_failed(
    data_dir, monkeypatch, mocker, capsys
):
    """Pack missing, .update_failed present → retry counter kept → error shown."""
    monkeypatch.setenv("alfred_workflow_data", str(data_dir))
    (data_dir / em.SETUP_RETRY_FILE).write_text(str(em.MAX_SETUP_RETRIES))
    (data_dir / em.FAILED_FILE).write_text("network error")
    mocker.patch.object(sys, "argv", ["emoji.py", ""])
    em.main()
    out = json.loads(capsys.readouterr().out)
    # Counter was not cleared, retries exhausted, no pack → error item
    assert out["items"][0]["title"] == em._ERROR_ITEM["title"]
    assert "rerun" not in out
