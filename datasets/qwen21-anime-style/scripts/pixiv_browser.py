"""Launch the dedicated Pixiv Chrome profile. Windows entry points only.

The profile directory is persistent. Callers must not delete it: that is the
login. This module does not read cookies.
"""

from __future__ import annotations

import sys
from pathlib import Path

from chrome_profile import assert_dedicated_profile, validate_proxy


def require_windows(what: str) -> None:
    if sys.platform == "win32":
        return
    print(
        f"{what} runs on Windows with a dedicated Chrome profile and your local proxy. "
        "This cloud machine cannot download Pixiv originals. "
        "See collect_pixiv_windows.md.",
        file=sys.stderr,
    )
    raise SystemExit(2)


def launch_dedicated(playwright, profile: Path, proxy: str, *, headless: bool = False):
    return playwright.chromium.launch_persistent_context(
        str(profile),
        channel="chrome",
        headless=headless,
        proxy={"server": validate_proxy(proxy)},
        viewport={"width": 1280, "height": 900},
        args=["--disable-blink-features=AutomationControlled"],
    )


def prepare_profile(profile: Path, repo_root: Path) -> None:
    assert_dedicated_profile(profile, repo_root)
    profile.mkdir(parents=True, exist_ok=True)


def open_pixiv(profile: Path, proxy: str, repo_root: Path, *, headless: bool = False):
    """Context manager-like pair: (playwright, context). Caller closes both."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "Install Playwright on this Windows PC: py -3 -m pip install playwright\n"
            "Launch uses installed Google Chrome (channel=chrome), not bundled Chromium.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    prepare_profile(profile, repo_root)
    playwright = sync_playwright().start()
    try:
        context = launch_dedicated(playwright, profile, proxy, headless=headless)
    except Exception:
        playwright.stop()
        raise
    return playwright, context
