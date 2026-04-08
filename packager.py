#!/usr/bin/env python3
"""Alfred Emoji Workflow Packager.

Packages src/ into an .alfredworkflow zip archive.

Usage:
    python packager.py <version>             # build only
    python packager.py <version> --release   # build + create GitHub release via gh
"""

from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent
SRC_DIR = REPO_ROOT / "src"
INFO_PLIST = SRC_DIR / "info.plist"

EXCLUDED_NAMES: set[str] = {"prefs.plist", ".DS_Store"}
EXCLUDED_DIRS: set[str] = {"__pycache__"}
EXCLUDED_EXTS: set[str] = {".alfredworkflow"}


def log(msg: str, *, step: bool = False, error: bool = False) -> None:
    if error:
        print(f"  ✗ {msg}", file=sys.stderr)
    elif step:
        print(f"\n▶ {msg}")
    else:
        print(f"  ✓ {msg}")


def read_plist(path: Path) -> dict[str, Any]:
    with open(path, "rb") as f:
        return plistlib.load(f)


def should_exclude(rel_path: str) -> bool:
    p = Path(rel_path)
    if any(d in EXCLUDED_DIRS for d in p.parts):
        return True
    if p.name in EXCLUDED_NAMES:
        return True
    if p.suffix in EXCLUDED_EXTS:
        return True
    return False


def clear_exported_variables(plist_data: dict[str, Any]) -> None:
    """Blank out variables listed in variablesdontexport."""
    dont_export = plist_data.get("variablesdontexport", [])
    variables = plist_data.get("variables", {})
    for var in dont_export:
        if var in variables:
            variables[var] = ""


def build_workflow_zip(output_path: Path, plist_data: dict[str, Any]) -> None:
    """Zip src/ into output_path, substituting info.plist with the filled version."""
    serialized_plist = plistlib.dumps(plist_data, fmt=plistlib.FMT_XML)
    try:
        col = os.get_terminal_size().columns
    except OSError:
        col = 80

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
        for root, dirs, files in os.walk(SRC_DIR):
            dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
            for filename in files:
                full = Path(root) / filename
                rel = full.relative_to(SRC_DIR).as_posix()

                if should_exclude(rel):
                    continue

                if rel == "info.plist":
                    zf.writestr("info.plist", serialized_plist)
                    msg = "  + info.plist (filled)"
                else:
                    size_kb = full.stat().st_size / 1024
                    msg = f"  + {rel} ({size_kb:.1f} KB)"
                    zf.write(full, rel)

                line = msg[: col - 1].ljust(col - 1)
                print(f"\r{line}", end="", flush=True)

    print(f"\r{' ' * (col - 1)}\r", end="", flush=True)


def main() -> None:
    args = sys.argv[1:]
    release_flag = "--release" in args
    positional = [a for a in args if not a.startswith("--")]

    if not positional:
        log("Usage: python packager.py <version> [--release]", error=True)
        sys.exit(1)

    version = positional[0]

    if not INFO_PLIST.exists():
        log(f"info.plist not found at {INFO_PLIST}", error=True)
        sys.exit(1)

    print(f"Packaging alfred-emoji v{version}")

    log("Preparing info.plist", step=True)
    plist_data = read_plist(INFO_PLIST)
    plist_data["version"] = version
    clear_exported_variables(plist_data)
    log("Version injected, variables sanitized")

    log("Building .alfredworkflow", step=True)
    output_path = REPO_ROOT / f"alfred-emoji-{version}.alfredworkflow"
    tmp_path = REPO_ROOT / f".alfred-emoji-{version}.tmp.alfredworkflow"
    try:
        build_workflow_zip(tmp_path, plist_data)
        shutil.move(str(tmp_path), str(output_path))
    finally:
        if tmp_path.exists():
            tmp_path.unlink()

    size_mb = output_path.stat().st_size / (1024 * 1024)
    log(f"Created {output_path.name} ({size_mb:.1f} MB)")

    if not release_flag:
        print(f"\n✓ Done — alfred-emoji v{version}")
        print("  Run with --release to publish to GitHub.")
        return

    log("Creating GitHub release", step=True)
    if not shutil.which("gh"):
        log("gh CLI not found — install from https://cli.github.com", error=True)
        sys.exit(1)

    result = subprocess.run(
        [
            "gh",
            "release",
            "create",
            f"v{version}",
            str(output_path),
            "--title",
            f"v{version}",
            "--generate-notes",
        ],
    )
    if result.returncode != 0:
        log("GitHub release failed", error=True)
        sys.exit(1)

    log(f"GitHub release v{version} created")
    print(f"\n✓ Done — alfred-emoji v{version} released")


if __name__ == "__main__":
    main()
