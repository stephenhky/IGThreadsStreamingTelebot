"""Google Sheets integration – append collected links."""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import gspread
from google.oauth2.service_account import Credentials
from gspread.exceptions import WorksheetNotFound

logger = logging.getLogger(__name__)
logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))

# Scopes required for reading/writing Google Sheets
_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# Environment variables
_SPREADSHEET_ID = os.environ.get("GOOGLE_SPREADSHEET_ID", "")
_WORKSHEET_NAME = os.environ.get("GOOGLE_WORKSHEET_NAME", "Links")
_STREAM_WORKSHEET_NAME = os.environ.get("GOOGLE_STREAM_WORKSHEET_NAME", "stream")
_ARCHIVE_WORKSHEET_NAME = os.environ.get("GOOGLE_ARCHIVE_WORKSHEET_NAME", "archive")
_DOWNLOADED_STATUS = os.environ.get("GOOGLE_DOWNLOADED_STATUS", "DOWNLOADED")

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
            "No Google service-account credentials configured. Set GOOGLE_SA_KEY_FILE or GOOGLE_SA_KEY_JSON."
        )
    return gspread.authorize(creds)


def append_links(links: list[str]) -> None:
    """Append one row per link to the configured Google Sheet.

    Each row contains:
        | timestamp (UTC ISO-8601) | url | rectified url | username |
        | platform | status | suffix | comments |

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
        rows.append([now, url, _rectify_link(url, platform), _extract_username(url), platform, "PENDING", "", ""])

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


def _status_matches_downloaded(row: list[str], status_col: int) -> bool:
    """Return ``True`` when *row*'s status cell equals the downloaded label."""
    if status_col >= len(row):
        return False
    return row[status_col].strip() == _DOWNLOADED_STATUS


def _row_has_data(row: list[str]) -> bool:
    """Return ``True`` if the row contains at least one non-empty cell."""
    return any(str(cell).strip() for cell in row)


def _find_status_column(header: list[str]) -> int:
    """Return the 0-based index of the ``status`` column from the header.

    Falls back to column index 5 (the 6th column), matching the layout written
    by :func:`append_links` when no header identifies the status column.
    """
    for idx, name in enumerate(header):
        if name.strip().lower() == "status":
            return idx
    return 5


def _get_or_create_archive_sheet(sheet: Any, header: list[str]) -> tuple[Any, bool]:
    """Return the archive worksheet, creating it (with a header) if missing."""
    try:
        return sheet.worksheet(_ARCHIVE_WORKSHEET_NAME), False
    except WorksheetNotFound:
        pass

    cols = max(len(header), 1) if header else 8
    rows = 100
    archive = sheet.add_worksheet(title=_ARCHIVE_WORKSHEET_NAME, rows=rows, cols=cols)
    if header:
        archive.append_row(header, value_input_option="USER_ENTERED")
    logger.info("Created archive worksheet %r.", _ARCHIVE_WORKSHEET_NAME)
    return archive, True


def move_downloaded_to_archive() -> dict[str, int | bool]:
    """Move rows labelled ``DOWNLOADED`` from the *stream* worksheet to *archive*.

    Steps:

    1. Read all rows from the stream worksheet.
    2. Locate the ``status`` column from the header (falls back to column 6).
    3. Select data rows whose status equals :data:`_DOWNLOADED_STATUS`.
    4. Append those rows to the archive worksheet (created if missing).
    5. Remove them from the stream worksheet, retaining the header.

    Returns
    -------
    dict
        ``{"moved": <count>, "archive_created": <bool>}``

    Raises
    ------
    RuntimeError
        If ``GOOGLE_SPREADSHEET_ID`` is not configured.
    """
    if not _SPREADSHEET_ID:
        raise RuntimeError("GOOGLE_SPREADSHEET_ID environment variable is not set.")

    client = _get_client()
    sheet = client.open_by_key(_SPREADSHEET_ID)

    stream_ws = sheet.worksheet(_STREAM_WORKSHEET_NAME)
    rows = stream_ws.get_all_values()
    if not rows:
        logger.info("Stream worksheet %r is empty – nothing to archive.", _STREAM_WORKSHEET_NAME)
        return {"moved": 0, "archive_created": False}

    header = rows[0]
    status_col = _find_status_column(header)
    logger.info(
        "Stream %r has %d data row(s); status column index=%d",
        _STREAM_WORKSHEET_NAME,
        len(rows) - 1,
        status_col,
    )

    downloaded = [r for r in rows[1:] if _status_matches_downloaded(r, status_col)]
    kept = [r for r in rows[1:] if not _status_matches_downloaded(r, status_col) and _row_has_data(r)]

    if not downloaded:
        logger.info("No %r rows in stream – nothing to archive.", _DOWNLOADED_STATUS)
        return {"moved": 0, "archive_created": False}

    archive_ws, created = _get_or_create_archive_sheet(sheet, header)
    archive_ws.append_rows(downloaded, value_input_option="USER_ENTERED")
    logger.info("Appended %d DOWNLOADED row(s) to %r.", len(downloaded), _ARCHIVE_WORKSHEET_NAME)

    # Rewrite the stream without the moved rows (header retained).
    stream_ws.clear()
    stream_ws.append_rows([header] + kept, value_input_option="USER_ENTERED")
    logger.info("Removed %d DOWNLOADED row(s) from %r.", len(downloaded), _STREAM_WORKSHEET_NAME)

    return {"moved": len(downloaded), "archive_created": created}
