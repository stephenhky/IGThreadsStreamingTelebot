"""Google Sheets integration – append collected links."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

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
        | timestamp (UTC ISO-8601) | url | platform | downloaded |

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
        rows.append([now, url, platform, "FALSE"])

    worksheet.append_rows(rows, value_input_option="USER_ENTERED")


def _detect_platform(url: str) -> str:
    """Return ``'instagram'`` or ``'threads'`` based on the URL domain."""
    if "threads.net" in url:
        return "threads"
    return "instagram"
