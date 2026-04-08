#!/usr/bin/env python3
"""Workflow auto-updater — checks GitHub releases and installs when a new version is available."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from typing import Any

GITHUB_REPO = "kylebelt/alfred-emoji"
UPDATE_INTERVAL = 604800  # seconds (7 days)
TIMESTAMP_FILE = ".last_workflow_update_check"


def data_dir() -> str:
    return os.environ.get("alfred_workflow_data", "")


def is_update_due(dd: str) -> bool:
    """Return True if UPDATE_INTERVAL has elapsed since the last update check."""
    stamp = os.path.join(dd, TIMESTAMP_FILE)
    try:
        return time.time() - os.path.getmtime(stamp) >= UPDATE_INTERVAL
    except FileNotFoundError:
        return True


def touch_timestamp(dd: str) -> None:
    stamp = os.path.join(dd, TIMESTAMP_FILE)
    try:
        os.utime(stamp, None)
    except FileNotFoundError:
        with open(stamp, "w"):
            pass


def fetch_latest_release(repo: str) -> dict[str, Any]:
    """Fetch the latest GitHub release metadata."""
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read())


def get_download_url(release: dict[str, Any]) -> str | None:
    """Return the .alfredworkflow asset download URL, or None if not found."""
    for asset in release.get("assets", []):
        if asset.get("name", "").endswith(".alfredworkflow"):
            url = asset.get("browser_download_url")
            if url:
                return url
    return None


def download_and_install(url: str) -> None:
    """Download the workflow archive and open it for installation."""
    fd, tmp = tempfile.mkstemp(suffix=".alfredworkflow")
    os.close(fd)
    with urllib.request.urlopen(url, timeout=60) as r, open(tmp, "wb") as f:
        f.write(r.read())
    subprocess.run(["open", tmp])


def main() -> None:
    workflow_version = os.environ.get("alfred_workflow_version", "")
    dd = data_dir()

    if not workflow_version:
        print("alfred_workflow_version not set", file=sys.stderr)
        sys.exit(1)

    if not dd:
        print("alfred_workflow_data not set", file=sys.stderr)
        sys.exit(1)

    os.makedirs(dd, exist_ok=True)

    if not is_update_due(dd):
        sys.exit(0)

    try:
        release = fetch_latest_release(GITHUB_REPO)
    except Exception as e:
        print(f"Failed to fetch release info: {e}", file=sys.stderr)
        sys.exit(0)

    remote_version = release.get("tag_name", "").lstrip("v")
    if workflow_version == remote_version:
        touch_timestamp(dd)
        sys.exit(0)

    download_url = get_download_url(release)
    if not download_url:
        print("No .alfredworkflow asset found in latest release", file=sys.stderr)
        sys.exit(1)

    download_and_install(download_url)
    touch_timestamp(dd)


if __name__ == "__main__":
    main()
