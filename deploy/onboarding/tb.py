"""ThingsBoard REST client helpers + domain provisioning (spec §7 Fases 2-4)."""
import requests


HTTP_TIMEOUT = 10


class ExternalError(RuntimeError):
    """Raised when an external system (TB or NR) fails."""


REQUIRED_PROFILES = {
    "Gateway":              "Device profile del Gateway MQTT (NR → TB). Ver ADR-003.",
    "sensor_planta":        "Device profile para sensores del PLC (v2). Ver ADR-003.",
    "inference_input":      "Audit-trail del snapshot LOCF enviado al servicio AI. Ver ai-inference.md §A8.",
    "inference_results":    "Writebacks del servicio AI. Ver ai-writeback.md.",
    "blockchain_anchor":    "Writebacks del servicio blockchain. Ver blockchain-writeback.md.",
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


def tb_create_device(
    url: str,
    jwt: str,
    name: str,
    profile_id: str,
    description: str,
    extra_info: dict | None = None,
) -> str:
    additional_info: dict = {"description": description}
    if extra_info:
        additional_info.update(extra_info)
    body = {
        "name": name,
        "type": name.split("-")[0],  # arbitrary label for UI grouping
        "deviceProfileId": {"entityType": "DEVICE_PROFILE", "id": profile_id},
        "additionalInfo": additional_info,
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


def tb_ensure_additional_info(url: str, jwt: str, device: dict, extra_info: dict) -> None:
    """Idempotently merge `extra_info` into an existing device's additionalInfo.

    No-op if all keys already match. Required for the Gateway flag: TB silently
    drops `v1/gateway/*` messages from devices without `additionalInfo.gateway=true`.
    """
    current = dict(device.get("additionalInfo") or {})
    if all(current.get(k) == v for k, v in extra_info.items()):
        return
    updated = {**current, **extra_info}
    body = {**device, "additionalInfo": updated}
    r = requests.post(
        f"{url}/api/device",
        headers=_auth_headers(jwt),
        json=body,
        timeout=HTTP_TIMEOUT,
    )
    if r.status_code >= 400:
        raise ExternalError(
            f"TB update additionalInfo {device.get('name')!r}: HTTP {r.status_code}: {r.text[:200]}"
        )


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
    """POST credentials with a freshly generated ACCESS_TOKEN.

    TB CE 4.1 requires credentialsId to be specified (cannot be null). We
    generate a 20-char alphanumeric token locally and submit it as the new
    credentialsId.
    """
    import secrets as _secrets
    import string as _string
    r_get = requests.get(
        f"{url}/api/device/{device_id}/credentials",
        headers=_auth_headers(jwt),
        timeout=HTTP_TIMEOUT,
    )
    if r_get.status_code != 200:
        raise ExternalError(f"TB rotate credentials (read) {device_id}: HTTP {r_get.status_code}")
    creds = r_get.json()
    alphabet = _string.ascii_letters + _string.digits
    new_token = "".join(_secrets.choice(alphabet) for _ in range(20))
    creds["credentialsId"] = new_token
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
        ("ai",         f"ai-inference-{client}",      "inference_results",    f"Writeback del servicio AI. Cliente: {client}."),
        ("blockchain", f"blockchain-anchor-{client}", "blockchain_anchor",    f"Writeback del servicio blockchain. Cliente: {client}."),
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


def ensure_gateway_device(url: str, jwt: str, profile_ids: dict, force: bool) -> dict:
    """Idempotently ensure the OPC-Gateway device exists. Returns {id, token, name}.

    The Gateway is stack infrastructure (one per stack, single-tenant), not
    client-specific. NR uses its access token to publish telemetry via the
    Gateway MQTT API (v1/gateway/telemetry + v1/gateway/connect).
    """
    name = "OPC-Gateway"
    description = "Gateway MQTT para publicación de telemetría desde Node-RED. Ver ADR-003."
    # TB only accepts v1/gateway/* from devices with additionalInfo.gateway=true.
    gateway_info = {"gateway": True, "overwriteActivityTime": False}
    existing = tb_get_device_by_name(url, jwt, name)
    if existing:
        dev_id = existing["id"]["id"]
        tb_ensure_additional_info(url, jwt, existing, gateway_info)
        if force:
            token = tb_rotate_credentials(url, jwt, dev_id)
            print(f"[↻] device  {name:35s} rotated  token={token[:4]}...{token[-2:]}")
        else:
            token = tb_get_credentials(url, jwt, dev_id)
            print(f"[=] device  {name:35s} existed  token={token[:4]}...{token[-2:]}")
    else:
        dev_id = tb_create_device(
            url, jwt, name, profile_ids["Gateway"], description, extra_info=gateway_info
        )
        token = tb_get_credentials(url, jwt, dev_id)
        print(f"[✓] device  {name:35s} created  token={token[:4]}...{token[-2:]}")
    return {"id": dev_id, "token": token, "name": name}


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
