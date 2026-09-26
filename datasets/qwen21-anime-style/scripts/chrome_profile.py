"""Dedicated Playwright Chrome profile for a home Pixiv session.

Do not copy the system Chrome profile. Current Chrome stores cookies with
app-bound encryption (ABE v20). A copy of Default, including Cookies and
Local State, does not stay logged in. Log in once inside a separate
user-data directory and reuse that directory. Cookie values are never read.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

_PROXY_RE = re.compile(r"^https?://[A-Za-z0-9.\-]+:\d+$")


def system_chrome_user_data() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / "Google" / "Chrome" / "User Data"
    return Path.home() / "AppData" / "Local" / "Google" / "Chrome" / "User Data"


def default_dedicated_profile() -> Path:
    """Folder that already worked on the home PC. Not the system Chrome profile."""
    return Path.home() / "temp" / "pixiv-collector-chrome"


def assert_outside_repo(path: Path, repo_root: Path) -> None:
    resolved = path.resolve()
    root = repo_root.resolve()
    if resolved == root or root in resolved.parents:
        raise RuntimeError("Refusing to place a Chrome profile or image download inside the git repo.")


def is_system_chrome_path(path: Path) -> bool:
    resolved = path.resolve()
    system = system_chrome_user_data().resolve()
    if resolved == system or system in resolved.parents:
        return True
    text = str(resolved).replace("/", "\\").lower()
    return "\\google\\chrome\\user data" in text


def assert_dedicated_profile(path: Path, repo_root: Path) -> None:
    """Accept only a profile directory that is not system Chrome and not the repo."""
    if not str(path).strip():
        raise RuntimeError("Pass --dedicated-profile. Do not copy the Chrome Default profile.")
    assert_outside_repo(path, repo_root)
    if is_system_chrome_path(path):
        raise RuntimeError(
            "Refusing the system Chrome profile. Default cookies use ABE v20 and a copy does not log in. "
            "Use a dedicated directory such as "
            + str(default_dedicated_profile())
        )


def validate_proxy(proxy: str) -> str:
    value = (proxy or "").strip()
    if not _PROXY_RE.match(value):
        raise RuntimeError("Pass --proxy like http://127.0.0.1:7890. A scheme and port are required.")
    return value
