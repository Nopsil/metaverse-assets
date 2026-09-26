"""Copy a Chrome profile aside so Pixiv can be opened without touching the live one.

Only the files Chrome needs to reuse a login are copied: Local State (the
OS-encryption key lives here) and that profile's Cookies database plus
preferences. Login Data, History, and caches are not copied. Cookie values
are never read or logged. The caller deletes the destination when finished.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

# Allowlist. Anything else in the profile (passwords, history, cache) stays put.
PROFILE_FILE_RELPATHS = (
    "Network/Cookies",
    "Network/Cookies-journal",
    "Cookies",
    "Preferences",
    "Secure Preferences",
)


def default_chrome_user_data() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / "Google" / "Chrome" / "User Data"
    return Path.home() / "AppData" / "Local" / "Google" / "Chrome" / "User Data"


def assert_outside_repo(path: Path, repo_root: Path) -> None:
    resolved = path.resolve()
    root = repo_root.resolve()
    if resolved == root or root in resolved.parents:
        raise RuntimeError("Refusing to place a Chrome profile copy inside the git repo.")


def copy_chrome_profile_for_pixiv(
    src_user_data: Path,
    profile_name: str,
    dest_user_data: Path,
) -> dict:
    """Copy login files into dest_user_data/Default. Does not modify src.

    Playwright's persistent context reads the Default profile folder, so a
    non-default Chrome profile is copied into that folder name.
    """
    if not src_user_data.is_dir():
        raise FileNotFoundError(f"Chrome user data not found: {src_user_data}")
    local_state = src_user_data / "Local State"
    if not local_state.is_file():
        raise FileNotFoundError("Chrome Local State is missing; cannot reuse the profile copy.")
    src_profile = src_user_data / profile_name
    if not src_profile.is_dir():
        raise FileNotFoundError(f"Chrome profile not found: {src_profile}")

    dest_user_data.mkdir(parents=True, exist_ok=False)
    shutil.copy2(local_state, dest_user_data / "Local State")
    _retarget_local_state_copy(dest_user_data / "Local State")

    dest_profile = dest_user_data / "Default"
    dest_profile.mkdir()
    copied: list[str] = []
    missing: list[str] = []
    for rel in PROFILE_FILE_RELPATHS:
        src = src_profile / rel
        if not src.is_file():
            missing.append(rel)
            continue
        dest = dest_profile / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        copied.append(rel)
    if "Network/Cookies" not in copied and "Cookies" not in copied:
        raise FileNotFoundError(
            "Could not copy a Cookies database. Close Chrome completely and rerun. "
            "This script does not read the live profile in place."
        )
    return {
        "copied_files": copied,
        "missing_files": missing,
        "profile_name": profile_name,
        "dest_profile": "Default",
    }


def _retarget_local_state_copy(path: Path) -> None:
    """Point the temp copy at the Default folder. Never touches the source file."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    profile = data.get("profile")
    if isinstance(profile, dict):
        profile["last_used"] = "Default"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
