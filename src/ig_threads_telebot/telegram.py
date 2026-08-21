"""Telegram update parsing and link extraction."""

from __future__ import annotations

import re
from typing import Any

# Patterns for Instagram and Threads URLs
_IG_PATTERN = re.compile(
    r"https?://(?:www\.)?instagram\.com/(?:p|reel|tv)/[\w-]+/?",
    re.IGNORECASE,
)
_THREADS_POST_PATTERN = re.compile(
    r"https?://(?:www\.)?threads\.net/@[\w.]+/post/[\w-]+/?",
    re.IGNORECASE,
)
_THREADS_SHARE_PATTERN = re.compile(
    r"https?://(?:www\.)?threads\.com/share/[\w-]+/?",
    re.IGNORECASE,
)


def validate_update(update: dict[str, Any]) -> bool:
    """Return ``True`` if the update contains a usable text message."""
    message = update.get("message") or update.get("channel_post")
    if not message:
        return False
    # Must have text (or a caption on media)
    return bool(message.get("text") or message.get("caption"))


def parse_links(update: dict[str, Any]) -> list[str]:
    """Extract Instagram and Threads URLs from a Telegram update.

    Looks at both ``message.text`` and ``message.caption``.

    Returns
    -------
    list[str]
        De-duplicated list of matched URLs, preserving first-seen order.
    """
    message = update.get("message") or update.get("channel_post") or {}
    text = message.get("text", "") or message.get("caption", "")

    seen: set[str] = set()
    links: list[str] = []

    for match in _IG_PATTERN.finditer(text):
        url = match.group().rstrip("/")
        if url not in seen:
            seen.add(url)
            links.append(url)

    for pattern in (_THREADS_POST_PATTERN, _THREADS_SHARE_PATTERN):
        for match in pattern.finditer(text):
            url = match.group().rstrip("/")
            if url not in seen:
                seen.add(url)
                links.append(url)

    return links
