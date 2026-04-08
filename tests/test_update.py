"""Tests for src/update.py."""

from __future__ import annotations

import os
import time

import pytest

import update as up


# ---------------------------------------------------------------------------
# is_update_due
# ---------------------------------------------------------------------------


def test_is_update_due_no_file(data_dir):
    assert up.is_update_due(str(data_dir)) is True


def test_is_update_due_fresh(data_dir):
    stamp = data_dir / up.TIMESTAMP_FILE
    stamp.touch()
    assert up.is_update_due(str(data_dir)) is False


def test_is_update_due_stale(data_dir):
    stamp = data_dir / up.TIMESTAMP_FILE
    stamp.touch()
    stale = time.time() - up.UPDATE_INTERVAL - 1
    os.utime(str(stamp), (stale, stale))
    assert up.is_update_due(str(data_dir)) is True


# ---------------------------------------------------------------------------
# get_download_url
# ---------------------------------------------------------------------------


def test_get_download_url_found():
    release = {
        "assets": [
            {
                "name": "alfred-emoji-2.3.1.alfredworkflow",
                "browser_download_url": "https://example.com/alfred-emoji.alfredworkflow",
            },
        ]
    }
    assert (
        up.get_download_url(release)
        == "https://example.com/alfred-emoji.alfredworkflow"
    )


def test_get_download_url_no_assets():
    assert up.get_download_url({"assets": []}) is None


def test_get_download_url_wrong_extension():
    release = {
        "assets": [{"name": "notes.txt", "browser_download_url": "https://x.com"}]
    }
    assert up.get_download_url(release) is None


def test_get_download_url_returns_first_match():
    release = {
        "assets": [
            {"name": "a.alfredworkflow", "browser_download_url": "https://a.com"},
            {"name": "b.alfredworkflow", "browser_download_url": "https://b.com"},
        ]
    }
    assert up.get_download_url(release) == "https://a.com"


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def test_main_missing_workflow_version(data_dir, monkeypatch):
    monkeypatch.delenv("alfred_workflow_version", raising=False)
    monkeypatch.setenv("alfred_workflow_data", str(data_dir))
    with pytest.raises(SystemExit) as exc:
        up.main()
    assert exc.value.code == 1


def test_main_missing_data_dir(monkeypatch):
    monkeypatch.setenv("alfred_workflow_version", "2.3.1")
    monkeypatch.delenv("alfred_workflow_data", raising=False)
    with pytest.raises(SystemExit) as exc:
        up.main()
    assert exc.value.code == 1


def test_main_not_due_exits_zero(data_dir, monkeypatch):
    monkeypatch.setenv("alfred_workflow_version", "2.3.1")
    monkeypatch.setenv("alfred_workflow_data", str(data_dir))
    stamp = data_dir / up.TIMESTAMP_FILE
    stamp.touch()
    with pytest.raises(SystemExit) as exc:
        up.main()
    assert exc.value.code == 0


def test_main_up_to_date_touches_timestamp(data_dir, monkeypatch, mocker):
    monkeypatch.setenv("alfred_workflow_version", "2.3.1")
    monkeypatch.setenv("alfred_workflow_data", str(data_dir))
    release = {"tag_name": "v2.3.1", "assets": []}
    mocker.patch("update.fetch_latest_release", return_value=release)
    with pytest.raises(SystemExit) as exc:
        up.main()
    assert exc.value.code == 0
    assert (data_dir / up.TIMESTAMP_FILE).exists()


def test_main_update_available(data_dir, monkeypatch, mocker):
    monkeypatch.setenv("alfred_workflow_version", "2.3.0")
    monkeypatch.setenv("alfred_workflow_data", str(data_dir))
    release = {
        "tag_name": "v2.3.1",
        "assets": [
            {
                "name": "alfred-emoji-2.3.1.alfredworkflow",
                "browser_download_url": "https://example.com/a.alfredworkflow",
            },
        ],
    }
    mocker.patch("update.fetch_latest_release", return_value=release)
    install_mock = mocker.patch("update.download_and_install")
    up.main()
    install_mock.assert_called_once_with("https://example.com/a.alfredworkflow")
    assert (data_dir / up.TIMESTAMP_FILE).exists()


def test_main_network_failure_exits_zero(data_dir, monkeypatch, mocker):
    monkeypatch.setenv("alfred_workflow_version", "2.3.0")
    monkeypatch.setenv("alfred_workflow_data", str(data_dir))
    mocker.patch("update.fetch_latest_release", side_effect=OSError("timeout"))
    with pytest.raises(SystemExit) as exc:
        up.main()
    assert exc.value.code == 0
