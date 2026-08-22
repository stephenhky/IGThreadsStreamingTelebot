"""Google Sheets integration – append collected links."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import gspread
from google.oauth2.service_account import Credentials

# Scopes required for reading/writing Google Sheets
_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# Environment variables
_SPREADSHEET_ID = os.environ.get("GOOGLE_SPREADSHEET_ID", "")
_WORKSHEET_NAME = os.environ.get("GOOGLE_WORKSHEET_NAME", "Links")

# Service-account credentials can be provided as either:
#   1. A path to a JSON key file  (GOOGLE_SA_KEY_FILE)
#   2. The JSON key inlined        (GOOGLE_SA_KEY_JSON) — handy for Lambda env vars / Secrets Manager
_SA_KEY_FILE = os.environ.get("GOOGLE_SA_KEY_FILE", "")
_SA_KEY_JSON = os.environ.get("GOOGLE_SA_KEY_JSON", "")


def _get_client() -> gspread.Client:
    """Build an authorised gspread client from service-account credentials."""
    if _SA_KEY_JSON:
        info = json.loads(_SA_KEY_JSON)
        creds = Credentials.from_service_account_info(info, scopes=_SCOPES)
    elif _SA_KEY_FILE:
        creds = Credentials.from_service_account_file(_SA_KEY_FILE, scopes=_SCOPES)
    else:
        raise RuntimeError(
            "No Google service-account credentials configured. "
            "Set GOOGLE_SA_KEY_FILE or GOOGLE_SA_KEY_JSON."
        )
    return gspread.authorize(creds)


def append_links(links: list[str]) -> None:
    """Append one row per link to the configured Google Sheet.

    Each row contains:
        | timestamp (UTC ISO-8601) | url | rectified url | username |
        | platform | status | comments |

    ``rectified url`` strips Meta tracing params (``?xmt=...`` and, for
    Instagram, ``?img_index=<int>``). ``username`` is the post author's
    handle where it can be derived from the URL.
    Status is set to ``PENDING`` for newly added links.

    Parameters
    ----------
    links : list[str]
        URLs to append.
    """
    if not links:
        return

    client = _get_client()
    sheet = client.open_by_key(_SPREADSHEET_ID)
    worksheet = sheet.worksheet(_WORKSHEET_NAME)

    now = datetime.now(timezone.utc).isoformat()

    rows = []
    for url in links:
        platform = _detect_platform(url)
        rows.append(
            [now, url, _rectify_link(url, platform), _extract_username(url), platform, "PENDING", ""]
        )

    worksheet.append_rows(rows, value_input_option="USER_ENTERED")


def _detect_platform(url: str) -> str:
    """Return ``'instagram'`` or ``'threads'`` based on the URL domain."""
    if "threads.net" in url or "threads.com" in url:
        return "threads"
    return "instagram"


def _rectify_link(url: str, platform: str) -> str:
    """Strip Meta tracing query params from a URL.

    Always removes ``xmt``. For Instagram links, also removes ``img_index``.
    """
    parts = urlparse(url)
    if not parts.query:
        return url

    drop = {"xmt"}
    if platform == "instagram":
        drop.add("img_index")

    kept = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k not in drop]
    query = urlencode(kept)
    return urlunparse(parts._replace(query=query))


def _extract_username(url: str) -> str:
    """Return the post author's username from a URL, or ``''`` if not present.

    Threads URLs embed ``@username``; Instagram post URLs only contain a
    username when the shortcode is preceded by the author segment.
    """
    if "threads.net" in url or "threads.com" in url:
        match = re.search(r"threads\.(?:net|com)/@([\w.]+)", url, re.IGNORECASE)
        return match.group(1) if match else ""

    match = re.search(r"instagram\.com/([\w.]+)/(?:p|reel|tv)/", url, re.IGNORECASE)
    return match.group(1) if match else ""
