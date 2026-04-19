"""Smoke tests for writeback devices (spec §7 Fase 6).

POSTs synthetic telemetry with the device tokens captured in Phase 4,
then GETs the timeseries back to verify persistence through TB's rule chain.
"""
import time

import requests

from deploy.onboarding.tb import (
    ExternalError,
    HTTP_TIMEOUT,
    auth_headers,
)


class SmokeError(RuntimeError):
    """Raised when smoke test verification fails."""


AI_SMOKE_BODY = {"score": 0.42, "model_version": "smoke-test", "latency_ms": 10, "status": "ok"}
BLOCKCHAIN_SMOKE_BODY = {
    "status": "confirmed",
    "chain_id": "smoke-test",
    "tx_hash": "0xdeadbeef",
    "block_number": 1,
    "anchor_ts": 0,  # overwritten at runtime
    "payload_digest": "sha256:smoke",
}


def tb_post_telemetry(url: str, token: str, ts: int, values: dict) -> None:
    r = requests.post(
        f"{url}/api/v1/{token}/telemetry",
        json={"ts": ts, "values": values},
        timeout=HTTP_TIMEOUT,
    )
    if r.status_code != 200:
        raise ExternalError(f"TB POST telemetry: HTTP {r.status_code}: {r.text[:200]}")


def tb_get_timeseries(url: str, jwt: str, device_id: str, keys: list[str], start_ts: int, end_ts: int) -> dict:
    keys_csv = ",".join(keys)
    r = requests.get(
        f"{url}/api/plugins/telemetry/DEVICE/{device_id}/values/timeseries"
        f"?keys={keys_csv}&startTs={start_ts}&endTs={end_ts}&limit=1",
        headers=auth_headers(jwt),
        timeout=HTTP_TIMEOUT,
    )
    if r.status_code != 200:
        raise ExternalError(f"TB GET timeseries: HTTP {r.status_code}: {r.text[:200]}")
    return r.json()


def smoke_tests(tb_url: str, jwt: str, devices: dict) -> None:
    """Phase 6: POST fake telemetry + verify persistence."""
    ts = int(time.time() * 1000)
    # AI
    ai_values = dict(AI_SMOKE_BODY)
    tb_post_telemetry(tb_url, devices["ai"]["token"], ts, ai_values)
    # Blockchain
    bc_values = dict(BLOCKCHAIN_SMOKE_BODY, anchor_ts=ts + 15000)
    tb_post_telemetry(tb_url, devices["blockchain"]["token"], ts, bc_values)
    # Wait + verify
    time.sleep(1)
    for role, expected in [("ai", list(AI_SMOKE_BODY.keys())), ("blockchain", list(BLOCKCHAIN_SMOKE_BODY.keys()))]:
        data = tb_get_timeseries(tb_url, jwt, devices[role]["id"], expected, ts - 1, ts + 1)
        missing = [k for k in expected if not data.get(k)]
        if missing:
            raise SmokeError(f"smoke test {role}: keys missing after 1s: {missing}")
    print(f"[✓] smoke tests:     AI 200 OK (score persisted), blockchain 200 OK (tx_hash persisted)")
