"""S3 operations – archive spreadsheet folders."""

from __future__ import annotations

import logging
import os
import time

import boto3
from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger(__name__)
logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))

_BUCKET = os.environ.get("S3_BUCKET", "")

_SOURCE_PREFIXES = ("spreadsheet/instagram/", "spreadsheet/threads/")
_DEST_PREFIXES = {"instagram": "archive/instagram/", "threads": "archive/threads/"}


def _get_client():
    logger.info("Creating S3 client for bucket=%s, region=%s", _BUCKET, os.environ.get("AWS_REGION", "default"))
    start = time.monotonic()
    try:
        client = boto3.client("s3")
        logger.info("S3 client created in %.3fs", time.monotonic() - start)
        return client
    except Exception:
        logger.exception("Failed to create S3 client after %.3fs", time.monotonic() - start)
        raise


def _detect_category(key: str) -> str | None:
    if key.startswith("spreadsheet/instagram/"):
        return "instagram"
    if key.startswith("spreadsheet/threads/"):
        return "threads"
    return None


def _list_top_level_folders(category: str) -> list[str]:
    prefix = f"spreadsheet/{category}/"
    logger.info("Listing folders under %s", prefix)
    client = _get_client()
    folders: list[str] = []
    start = time.monotonic()
    try:
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=_BUCKET, Prefix=prefix, Delimiter="/"):
            for cp in page.get("CommonPrefixes", []):
                folder = cp["Prefix"].rstrip("/")
                name = folder[len(prefix):]
                if name and name not in folders:
                    folders.append(name)
        logger.info("Found %d folder(s) under %s in %.3fs", len(folders), prefix, time.monotonic() - start)
    except (ClientError, BotoCoreError) as exc:
        logger.error("Failed to list folders under %s: %s", prefix, exc)
        raise
    return folders


def _list_objects(prefix: str) -> list[str]:
    logger.info("Listing objects under %s", prefix)
    client = _get_client()
    keys: list[str] = []
    start = time.monotonic()
    try:
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=_BUCKET, Prefix=prefix):
            for obj in page.get("Contents", []):
                keys.append(obj["Key"])
        logger.info("Found %d object(s) under %s in %.3fs", len(keys), prefix, time.monotonic() - start)
    except (ClientError, BotoCoreError) as exc:
        logger.error("Failed to list objects under %s: %s", prefix, exc)
        raise
    return keys


def _existing_dest_folders(category: str) -> set[str]:
    prefix = _DEST_PREFIXES[category]
    logger.info("Listing existing archive folders under %s", prefix)
    client = _get_client()
    names: set[str] = set()
    start = time.monotonic()
    try:
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=_BUCKET, Prefix=prefix, Delimiter="/"):
            for cp in page.get("CommonPrefixes", []):
                folder = cp["Prefix"].rstrip("/")
                name = folder[len(prefix):]
                if name:
                    names.add(name)
        logger.info(
            "Found %d existing archive folder(s) under %s in %.3fs",
            len(names), prefix, time.monotonic() - start,
        )
    except (ClientError, BotoCoreError) as exc:
        logger.error("Failed to list existing archive folders under %s: %s", prefix, exc)
        raise
    return names


def _unique_dest_name(base_name: str, existing: set[str]) -> str:
    if base_name not in existing:
        existing.add(base_name)
        return base_name
    counter = 1
    while f"{base_name}-{counter}" in existing:
        counter += 1
    name = f"{base_name}-{counter}"
    existing.add(name)
    return name


def archive_spreadsheet_folders() -> dict[str, list[str]]:
    """Move folders from /spreadsheet/{instagram,threads}/ to /archive/{instagram,threads}/.

    Overlapping folder names get ``-1``, ``-2``, ... suffixes (no overwrite).

    Returns
    -------
    dict
        ``{"instagram": [moved...], "threads": [moved...]}`` – original folder
        names and their destination name when renamed.

    Raises
    ------
    RuntimeError
        If ``S3_BUCKET`` is not configured.
    """
    logger.info("archive_spreadsheet_folders called, S3_BUCKET=%s", _BUCKET or "<not set>")
    if not _BUCKET:
        raise RuntimeError("S3_BUCKET environment variable is not set.")

    overall_start = time.monotonic()
    moved: dict[str, list[str]] = {"instagram": [], "threads": []}

    for category in ("instagram", "threads"):
        logger.info("Processing category: %s", category)
        category_start = time.monotonic()

        try:
            folders = _list_top_level_folders(category)
        except Exception:
            logger.exception("Skipping category %s due to listing failure", category)
            continue

        if not folders:
            logger.info("No folders to archive under spreadsheet/%s/", category)
            continue

        try:
            existing = _existing_dest_folders(category)
        except Exception:
            logger.exception("Skipping category %s due to failure listing existing archives", category)
            continue

        dest_prefix = _DEST_PREFIXES[category]

        for folder in folders:
            src_prefix = f"spreadsheet/{category}/{folder}/"
            dest_name = _unique_dest_name(folder, existing)
            dest_base = f"{dest_prefix}{dest_name}/"

            try:
                keys = _list_objects(src_prefix)
            except Exception:
                logger.exception("Skipping folder %s due to listing failure", folder)
                continue

            if not keys:
                logger.info("No objects in %s, skipping", src_prefix)
                continue

            logger.info("Moving %d object(s) from %s to %s", len(keys), src_prefix, dest_base)
            move_start = time.monotonic()

            try:
                for key in keys:
                    rel = key[len(src_prefix):]
                    dest_key = f"{dest_base}{rel}"
                    client = _get_client()
                    client.copy_object(
                        Bucket=_BUCKET,
                        CopySource={"Bucket": _BUCKET, "Key": key},
                        Key=dest_key,
                    )

                client = _get_client()
                client.delete_objects(
                    Bucket=_BUCKET,
                    Delete={"Objects": [{"Key": k} for k in keys]},
                )
            except (ClientError, BotoCoreError) as exc:
                logger.error("Failed to move %s: %s", folder, exc)
                continue

            elapsed = time.monotonic() - move_start
            entry = folder if dest_name == folder else f"{folder} -> {dest_name}"
            moved[category].append(entry)
            logger.info("Archived %s/%s to %s (%d objects) in %.3fs", category, folder, dest_name, len(keys), elapsed)

        logger.info("Category %s completed in %.3fs", category, time.monotonic() - category_start)

    logger.info("archive_spreadsheet_folders completed in %.3fs, moved=%s", time.monotonic() - overall_start, moved)
    return moved
