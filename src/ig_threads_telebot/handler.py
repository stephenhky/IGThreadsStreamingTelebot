"""AWS Lambda handler – Telegram webhook entry point."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from ig_threads_telebot.s3 import archive_spreadsheet_folders
from ig_threads_telebot.sheets import append_links
from ig_threads_telebot.telegram import parse_links, validate_update

logger = logging.getLogger(__name__)
logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))

# Telegram bot token – used to verify incoming webhook requests
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Handle an incoming Telegram webhook update forwarded by API Gateway.

    Parameters
    ----------
    event : dict
        API Gateway proxy event containing the Telegram update in ``body``.
    context : Any
        Lambda context (unused).

    Returns
    -------
    dict
        HTTP-style response (statusCode + body).
    """
    try:
        body = json.loads(event.get("body", "{}"))
        logger.info("Received update: %s", json.dumps(body, indent=2))

        if not validate_update(body):
            logger.warning("Invalid or irrelevant update – skipping.")
            return _response(200, {"ok": True, "skipped": True})

        command = _extract_command(body)
        if command == "archive":
            return _handle_archive()

        links = parse_links(body)
        if not links:
            logger.info("No IG/Threads links found in message.")
            return _response(200, {"ok": True, "links_found": 0})

        append_links(links)
        logger.info("Appended %d link(s) to Google Sheet.", len(links))
        return _response(200, {"ok": True, "links_found": len(links)})

    except Exception:
        logger.exception("Unhandled error processing webhook.")
        # Return 200 so Telegram doesn't retry endlessly
        return _response(200, {"ok": False, "error": "internal"})


def _handle_archive() -> dict[str, Any]:
    try:
        moved = archive_spreadsheet_folders()
        total = len(moved["instagram"]) + len(moved["threads"])
        logger.info("Archive complete: %d folder(s) moved.", total)
        return _response(200, {"ok": True, "archived": moved})
    except RuntimeError as exc:
        logger.error("Archive failed: %s", exc)
        return _response(200, {"ok": False, "error": str(exc)})
    except Exception:
        logger.exception("Archive failed due to unexpected error.")
        return _response(200, {"ok": False, "error": "archive_failed"})


def _extract_command(update: dict[str, Any]) -> str | None:
    """Return a leading ``/command`` string from the update, or ``None``."""
    message = update.get("message") or update.get("channel_post") or {}
    text = message.get("text", "")
    if not text or not text.startswith("/"):
        return None
    return text.split()[0][1:].split("@")[0].lower()


def _response(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }
