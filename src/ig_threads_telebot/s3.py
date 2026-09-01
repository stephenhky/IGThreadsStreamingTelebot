"""S3 operations – archive spreadsheet folders."""

from __future__ import annotations

import logging
import os

import boto3

logger = logging.getLogger(__name__)

_BUCKET = os.environ.get("S3_BUCKET", "")

_SOURCE_PREFIXES = ("spreadsheet/instagram/", "spreadsheet/threads/")
_DEST_PREFIXES = {"instagram": "archive/instagram/", "threads": "archive/threads/"}


def _get_client():
    return boto3.client("s3")


def _detect_category(key: str) -> str | None:
    if key.startswith("spreadsheet/instagram/"):
        return "instagram"
    if key.startswith("spreadsheet/threads/"):
        return "threads"
    return None


def _list_top_level_folders(category: str) -> list[str]:
    prefix = f"spreadsheet/{category}/"
    client = _get_client()
    folders: list[str] = []
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=_BUCKET, Prefix=prefix, Delimiter="/"):
        for cp in page.get("CommonPrefixes", []):
            folder = cp["Prefix"].rstrip("/")
            name = folder[len(prefix):]
            if name and name not in folders:
                folders.append(name)
    return folders


def _list_objects(prefix: str) -> list[str]:
    client = _get_client()
    keys: list[str] = []
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=_BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            keys.append(obj["Key"])
    return keys


def _existing_dest_folders(category: str) -> set[str]:
    prefix = _DEST_PREFIXES[category]
    client = _get_client()
    names: set[str] = set()
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=_BUCKET, Prefix=prefix, Delimiter="/"):
        for cp in page.get("CommonPrefixes", []):
            folder = cp["Prefix"].rstrip("/")
            name = folder[len(prefix):]
            if name:
                names.add(name)
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
    if not _BUCKET:
        raise RuntimeError("S3_BUCKET environment variable is not set.")

    client = _get_client()
    moved: dict[str, list[str]] = {"instagram": [], "threads": []}

    for category in ("instagram", "threads"):
        folders = _list_top_level_folders(category)
        if not folders:
            logger.info("No folders to archive under spreadsheet/%s/", category)
            continue

        existing = _existing_dest_folders(category)
        dest_prefix = _DEST_PREFIXES[category]

        for folder in folders:
            src_prefix = f"spreadsheet/{category}/{folder}/"
            dest_name = _unique_dest_name(folder, existing)
            dest_base = f"{dest_prefix}{dest_name}/"

            keys = _list_objects(src_prefix)
            if not keys:
                continue

            for key in keys:
                rel = key[len(src_prefix):]
                dest_key = f"{dest_base}{rel}"
                client.copy_object(
                    Bucket=_BUCKET,
                    CopySource={"Bucket": _BUCKET, "Key": key},
                    Key=dest_key,
                )

            client.delete_objects(
                Bucket=_BUCKET,
                Delete={"Objects": [{"Key": k} for k in keys]},
            )

            entry = folder if dest_name == folder else f"{folder} -> {dest_name}"
            moved[category].append(entry)
            logger.info("Archived %s/%s to %s (%d objects)", category, folder, dest_name, len(keys))

    return moved
