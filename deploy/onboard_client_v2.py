#!/usr/bin/env python3
"""onboard_client_v2.py — provisioning pipeline v2 para clientes UCAM.

Spec: docs/superpowers/specs/2026-04-17-onboard-client-v2-design.md
"""
import argparse
import os
import re
import sys
from pathlib import Path
from typing import Any

import requests
import yaml

# ============================================================================
# Exit codes (spec §6.4)
# ============================================================================
EXIT_OK = 0
EXIT_UNEXPECTED = 1
EXIT_BAD_INPUT = 2
EXIT_EXTERNAL = 3
EXIT_SMOKE_FAILED = 4


# ============================================================================
# Manifest loading + validation (spec §5)
# ============================================================================

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
    # ml_inference.url (optional)
    ml = m.get("ml_inference") or {}
    ml_url = ml.get("url")
    if ml_url is not None:
        if not isinstance(ml_url, str) or not URL_RE.match(ml_url):
            raise ManifestError(f"manifest: ml_inference.url {ml_url!r}: must start with http:// or https://")


# ============================================================================
# Env vars (spec §6.3)
# ============================================================================

DEFAULT_TB_URL = "http://localhost:9090"
DEFAULT_TB_USER = "tenant@thingsboard.org"
DEFAULT_NR_URL = "http://localhost:1880"


def read_env() -> dict:
    """Read TB_* and NR_URL from environment.

    Returns dict with tb_url, tb_user, tb_password, nr_url.
    Raises RuntimeError if TB_ADMIN_PASSWORD is not set.
    """
    password = os.environ.get("TB_ADMIN_PASSWORD")
    if not password:
        raise RuntimeError("env: TB_ADMIN_PASSWORD is required (not set)")
    return {
        "tb_url": os.environ.get("TB_URL", DEFAULT_TB_URL).rstrip("/"),
        "tb_user": os.environ.get("TB_ADMIN_USER", DEFAULT_TB_USER),
        "tb_password": password,
        "nr_url": os.environ.get("NR_URL", DEFAULT_NR_URL).rstrip("/"),
    }


# ============================================================================
# TB REST helpers
# ============================================================================

HTTP_TIMEOUT = 10


class ExternalError(RuntimeError):
    """Raised when an external system (TB or NR) fails."""


REQUIRED_PROFILES = {
    "sensor_planta":        "Device profile para sensores del PLC (v2). Ver ADR-003.",
    "inference_input":      "Audit-trail del snapshot LOCF enviado al servicio ML. Ver ml-inference.md §A8.",
    "inference_results":    "Writebacks del servicio ML. Ver ml-writeback.md.",
    "blockchain_anchor":    "Writebacks de airtrace. Ver airtrace-writeback.md.",
}


def _auth_headers(jwt: str) -> dict:
    return {"X-Authorization": f"Bearer {jwt}"}


def tb_list_profiles(url: str, jwt: str) -> list[dict]:
    r = requests.get(
        f"{url}/api/deviceProfiles?pageSize=100&page=0",
        headers=_auth_headers(jwt),
        timeout=HTTP_TIMEOUT,
    )
    if r.status_code != 200:
        raise ExternalError(f"TB list profiles: HTTP {r.status_code}: {r.text[:200]}")
    return r.json().get("data", [])


def tb_create_profile(url: str, jwt: str, name: str, description: str) -> str:
    """POST /api/deviceProfile with full body (TB CE 4.1 requires profileData)."""
    body = {
        "name": name,
        "type": "DEFAULT",
        "transportType": "DEFAULT",
        "provisionType": "DISABLED",
        "description": description,
        "profileData": {
            "configuration": {"type": "DEFAULT"},
            "transportConfiguration": {"type": "DEFAULT"},
            "provisionConfiguration": {"type": "DISABLED", "provisionDeviceSecret": None},
            "alarms": None,
        },
    }
    r = requests.post(
        f"{url}/api/deviceProfile",
        headers=_auth_headers(jwt),
        json=body,
        timeout=HTTP_TIMEOUT,
    )
    if r.status_code >= 400:
        raise ExternalError(f"TB create profile {name!r}: HTTP {r.status_code}: {r.text[:200]}")
    return r.json()["id"]["id"]


def ensure_profiles(url: str, jwt: str) -> dict[str, str]:
    """Idempotently ensure REQUIRED_PROFILES exist. Returns {name: id}."""
    existing = {p["name"]: p["id"]["id"] for p in tb_list_profiles(url, jwt)}
    result = {}
    for name, description in REQUIRED_PROFILES.items():
        if name in existing:
            print(f"[=] profile {name:20s} existed  id={existing[name]}")
            result[name] = existing[name]
        else:
            pid = tb_create_profile(url, jwt, name, description)
            print(f"[✓] profile {name:20s} created  id={pid}")
            result[name] = pid
    return result


def tb_get_device_by_name(url: str, jwt: str, name: str) -> dict | None:
    r = requests.get(
        f"{url}/api/tenant/devices?deviceName={name}",
        headers=_auth_headers(jwt),
        timeout=HTTP_TIMEOUT,
    )
    if r.status_code == 200 and r.json():
        return r.json()
    if r.status_code == 404:
        return None
    if r.status_code != 200:
        raise ExternalError(f"TB get device {name!r}: HTTP {r.status_code}: {r.text[:200]}")
    return None


def tb_create_device(url: str, jwt: str, name: str, profile_id: str, description: str) -> str:
    body = {
        "name": name,
        "type": name.split("-")[0],  # arbitrary label for UI grouping
        "deviceProfileId": {"entityType": "DEVICE_PROFILE", "id": profile_id},
        "additionalInfo": {"description": description},
    }
    r = requests.post(
        f"{url}/api/device",
        headers=_auth_headers(jwt),
        json=body,
        timeout=HTTP_TIMEOUT,
    )
    if r.status_code >= 400:
        raise ExternalError(f"TB create device {name!r}: HTTP {r.status_code}: {r.text[:200]}")
    return r.json()["id"]["id"]


def tb_get_credentials(url: str, jwt: str, device_id: str) -> str:
    r = requests.get(
        f"{url}/api/device/{device_id}/credentials",
        headers=_auth_headers(jwt),
        timeout=HTTP_TIMEOUT,
    )
    if r.status_code != 200:
        raise ExternalError(f"TB get credentials {device_id}: HTTP {r.status_code}: {r.text[:200]}")
    token = r.json().get("credentialsId")
    if not token:
        raise ExternalError(f"TB get credentials {device_id}: no credentialsId in response")
    return token


def tb_rotate_credentials(url: str, jwt: str, device_id: str) -> str:
    """POST credentials with new credentialsId — TB generates a fresh token."""
    # Fetch current to get credentialsType/credentialsValue baseline if needed
    r_get = requests.get(
        f"{url}/api/device/{device_id}/credentials",
        headers=_auth_headers(jwt),
        timeout=HTTP_TIMEOUT,
    )
    if r_get.status_code != 200:
        raise ExternalError(f"TB rotate credentials (read) {device_id}: HTTP {r_get.status_code}")
    creds = r_get.json()
    # Pop the old credentialsId so TB regenerates; keep id+version+deviceId
    creds["credentialsId"] = None
    r = requests.post(
        f"{url}/api/device/credentials",
        headers=_auth_headers(jwt),
        json=creds,
        timeout=HTTP_TIMEOUT,
    )
    if r.status_code >= 400:
        raise ExternalError(f"TB rotate credentials {device_id}: HTTP {r.status_code}: {r.text[:200]}")
    token = r.json().get("credentialsId")
    if not token:
        raise ExternalError(f"TB rotate credentials {device_id}: no new credentialsId in response")
    return token


def ensure_writeback_devices(url: str, jwt: str, client: str, profile_ids: dict, force: bool) -> dict:
    """Idempotently ensure 2 writeback devices exist. Returns {role: {id, token, name}}."""
    devices_spec = [
        ("ml",       f"ml-inference-{client}",    "inference_results",    f"Writeback del servicio ML. Cliente: {client}."),
        ("airtrace", f"airtrace-anchor-{client}", "blockchain_anchor",    f"Writeback del servicio airtrace. Cliente: {client}."),
    ]
    result = {}
    for role, name, profile_name, description in devices_spec:
        existing = tb_get_device_by_name(url, jwt, name)
        if existing:
            dev_id = existing["id"]["id"]
            if force:
                token = tb_rotate_credentials(url, jwt, dev_id)
                print(f"[↻] device  {name:35s} rotated  token={token[:4]}...{token[-2:]}")
            else:
                token = tb_get_credentials(url, jwt, dev_id)
                print(f"[=] device  {name:35s} existed  token={token[:4]}...{token[-2:]}")
        else:
            dev_id = tb_create_device(url, jwt, name, profile_ids[profile_name], description)
            token = tb_get_credentials(url, jwt, dev_id)
            print(f"[✓] device  {name:35s} created  token={token[:4]}...{token[-2:]}")
        result[role] = {"id": dev_id, "token": token, "name": name}
    return result


def tb_login(url: str, user: str, password: str) -> str:
    """POST /api/auth/login → JWT. Raises ExternalError on failure."""
    try:
        r = requests.post(
            f"{url}/api/auth/login",
            json={"username": user, "password": password},
            timeout=HTTP_TIMEOUT,
        )
    except requests.RequestException as e:
        raise ExternalError(f"TB login: unreachable ({e.__class__.__name__})")
    if r.status_code == 401:
        raise ExternalError(f"TB login: 401 Unauthorized (check TB_ADMIN_PASSWORD)")
    if r.status_code != 200:
        raise ExternalError(f"TB login: HTTP {r.status_code}: {r.text[:200]}")
    token = r.json().get("token")
    if not token:
        raise ExternalError("TB login: 200 but no token in response")
    return token


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="onboard_client_v2.py",
        description="Provisiona un cliente en el stack v2 (TB profiles + devices + NR config).",
    )
    p.add_argument("--manifest", required=True, help="Ruta al YAML del cliente")
    p.add_argument("--dry-run", action="store_true", help="Valida manifest + pings, no aplica cambios")
    p.add_argument("--force", action="store_true", help="Rota tokens de devices existentes")
    p.add_argument("-v", "--verbose", action="store_true", help="Loggea cada request HTTP")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    # Phase 1: load + validate manifest
    try:
        manifest = load_manifest(Path(args.manifest))
    except (FileNotFoundError, ManifestError) as e:
        print(f"[✗] {e}", file=sys.stderr)
        return EXIT_BAD_INPUT
    # Phase 2a: read env vars
    try:
        env = read_env()
    except RuntimeError as e:
        print(f"[✗] {e}", file=sys.stderr)
        return EXIT_BAD_INPUT
    client = manifest["client"]["id"]
    tags = manifest["sensors"]["expected_tags"]
    print(f"[✓] manifest: {args.manifest} (client={client}, {len(tags)} tags)")
    # Phase 2b: TB login
    try:
        jwt = tb_login(env["tb_url"], env["tb_user"], env["tb_password"])
    except ExternalError as e:
        print(f"[✗] {e}", file=sys.stderr)
        return EXIT_EXTERNAL
    print(f"[✓] TB login: {env['tb_url']} (user={env['tb_user']})")
    # Phase 3: ensure profiles
    try:
        profile_ids = ensure_profiles(env["tb_url"], jwt)
    except ExternalError as e:
        print(f"[✗] {e}", file=sys.stderr)
        return EXIT_EXTERNAL
    # Phase 4: ensure writeback devices + capture tokens
    try:
        devices = ensure_writeback_devices(env["tb_url"], jwt, client, profile_ids, args.force)
    except ExternalError as e:
        print(f"[✗] {e}", file=sys.stderr)
        return EXIT_EXTERNAL
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
