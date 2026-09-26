"""Random pauses so a Pixiv session does not fire requests in a burst.

Call pause() before opening another artwork or search page, and pause("file")
before the next full-size image in the same work. Retries keep their own
backoff. This module does not open a browser.
"""

from __future__ import annotations

import random
import time

# Inclusive ranges in seconds. A page pause is the gap between navigations.
# A file pause is the gap between img-original bytes of one work.
_PAGE = (3.5, 8.5)
_PAGE_SLOW = (8.0, 14.0)
_PAGE_LONG = (15.0, 32.0)
_FILE = (1.8, 4.5)
_FILE_SLOW = (4.0, 8.0)


def human_pause(kind: str = "page") -> float:
    """Return a wait in seconds. Most gaps are a few seconds; some are longer."""
    roll = random.random()
    if kind == "file":
        low, high = _FILE_SLOW if roll < 0.12 else _FILE
    elif roll < 0.12:
        low, high = _PAGE_LONG
    elif roll < 0.35:
        low, high = _PAGE_SLOW
    else:
        low, high = _PAGE
    return random.uniform(low, high)


def pause(kind: str = "page") -> float:
    """Sleep a human-sized gap and return how long it was."""
    seconds = human_pause(kind)
    time.sleep(seconds)
    return seconds
