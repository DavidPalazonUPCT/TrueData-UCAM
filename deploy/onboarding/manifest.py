"""Manifest schema validation (spec §5)."""
import re
from pathlib import Path
from typing import Any

import yaml


CLIENT_ID_RE = re.compile(r"^[A-Z0-9_]+$")
TAG_RE = re.compile(r"^[A-Za-z0-9_]+$")
URL_RE = re.compile(r"^https?://")


class ManifestError(ValueError):
    """Raised when manifest fails schema validation."""


def load_manifest(path: Path) -> dict[str, Any]:
    """Load YAML, validate schema, return normalized dict.

    Raises:
        FileNotFoundError: if path doesn't exist
        ManifestError: if schema is invalid
    """
    if not path.exists():
        raise FileNotFoundError(f"manifest: file not found: {path}")
    with path.open() as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ManifestError("manifest: top-level must be a mapping")
    _validate(data)
    return data


def _validate(m: dict) -> None:
    # client.id
    client = m.get("client")
    if not isinstance(client, dict):
        raise ManifestError("manifest: 'client' block is required")
    cid = client.get("id")
    if not isinstance(cid, str) or not CLIENT_ID_RE.match(cid) or not (3 <= len(cid) <= 32):
        raise ManifestError(f"manifest: client.id {cid!r}: must match ^[A-Z0-9_]+$ and be 3-32 chars")
    # client.name
    if not isinstance(client.get("name"), str) or not client["name"].strip():
        raise ManifestError("manifest: client.name must be non-empty string")
    # sensors.expected_tags
    sensors = m.get("sensors")
    if not isinstance(sensors, dict):
        raise ManifestError("manifest: 'sensors' block is required")
    tags = sensors.get("expected_tags")
    if not isinstance(tags, list) or not (1 <= len(tags) <= 200):
        raise ManifestError("manifest: sensors.expected_tags must be a list of 1..200 items")
    if len(set(tags)) != len(tags):
        dupes = [t for t in tags if tags.count(t) > 1]
        raise ManifestError(f"manifest: sensors.expected_tags has duplicates: {set(dupes)}")
    for t in tags:
        if not isinstance(t, str) or not TAG_RE.match(t):
            raise ManifestError(f"manifest: tag {t!r}: must match ^[A-Za-z0-9_]+$")
    # ai_inference.url (optional)
    ai = m.get("ai_inference") or {}
    ai_url = ai.get("url")
    if ai_url is not None:
        if not isinstance(ai_url, str) or not URL_RE.match(ai_url):
            raise ManifestError(f"manifest: ai_inference.url {ai_url!r}: must start with http:// or https://")
