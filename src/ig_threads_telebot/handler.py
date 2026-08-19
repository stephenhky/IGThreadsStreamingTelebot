"""AWS Lambda handler – Telegram webhook entry point."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from ig_threads_telebot.telegram import parse_links, validate_update
from ig_threads_telebot.sheets import append_links

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


def _response(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }
