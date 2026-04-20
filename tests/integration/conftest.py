"""Fixtures compartidas para tests de integración del pipeline v2.

Asume stack Docker up: TB en :9090, NR en :1880. El mock ML corre en el
host en un puerto aleatorio y NR lo alcanza vía host.docker.internal
(requiere extra_hosts en truedata-nodered/docker-compose.yml).
La configuración de EXPECTED_TAGS y URL ML se aplica escribiendo
`truedata-nodered/data/runtime_config.json` (bind-mounted en /data).
"""
from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
import requests
from dotenv import find_dotenv, load_dotenv

# Carga `.env` desde la raíz del repo antes de que pytest resuelva fixtures.
# Variables del shell ganan (load_dotenv no sobrescribe por default).
load_dotenv(find_dotenv(usecwd=True))


# ---------------------------------------------------------------------------
# Base URLs and credentials
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def nr_base_url() -> str:
    return os.environ.get("NR_URL", "http://localhost:1880")


@pytest.fixture(scope="session")
def tb_base_url() -> str:
    return os.environ.get("TB_URL", "http://localhost:9090")


@pytest.fixture(scope="session")
def nr_runtime_config_path() -> Path:
    """Host path bind-mounted as /data/runtime_config.json in Node-RED."""
    raw = os.environ.get("NR_RUNTIME_CONFIG_HOST_PATH", "truedata-nodered/data/runtime_config.json")
    return Path(raw).resolve()


@pytest.fixture(scope="session")
def tb_token(tb_base_url: str) -> str:
    user = os.environ.get("TB_USER", "tenant@thingsboard.org")
    password = os.environ.get("TB_PASS", "tenant")
    resp = requests.post(
        f"{tb_base_url}/api/auth/login",
        json={"username": user, "password": password},
        timeout=5,
    )
    resp.raise_for_status()
    return resp.json()["token"]


# ---------------------------------------------------------------------------
# Mock ML server (in-process, random port)
# ---------------------------------------------------------------------------

@dataclass
class MockMl:
    url: str = ""
    received: list[dict[str, Any]] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def append(self, payload: dict[str, Any]) -> None:
        with self._lock:
            self.received.append(payload)

    def reset(self) -> None:
        with self._lock:
            self.received.clear()


@pytest.fixture(scope="module")
def mock_ml() -> MockMl:
    """Mock ML HTTP server, one per pytest module. State reset between tests via clean_state."""
    mock = MockMl()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length else b""
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                payload = {"_raw": raw.decode("utf-8", errors="replace")}
            mock.append(payload)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *_args, **_kwargs):
            pass  # silenciar stderr

    server = ThreadingHTTPServer(("0.0.0.0", 0), Handler)
    port = server.server_address[1]
    mock.url = f"http://host.docker.internal:{port}/"

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    yield mock

    server.shutdown()
    server.server_close()


# ---------------------------------------------------------------------------
# NR API helper
# ---------------------------------------------------------------------------

@dataclass
class NrApi:
    base_url: str
    runtime_config_path: Path

    def _read_runtime_config(self) -> dict[str, Any]:
        if not self.runtime_config_path.exists():
            return {}
        try:
            parsed = json.loads(self.runtime_config_path.read_text(encoding="utf-8"))
            return parsed if isinstance(parsed, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _write_runtime_config(self, config: dict[str, Any]) -> None:
        payload = dict(config)
        payload["_revision_ns"] = time.time_ns()
        self.runtime_config_path.parent.mkdir(parents=True, exist_ok=True)
        self.runtime_config_path.write_text(
            json.dumps(payload, ensure_ascii=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        stamp_ns = time.time_ns()
        os.utime(self.runtime_config_path, ns=(stamp_ns, stamp_ns))

    def post_ingest(
        self,
        body: dict | list | str | bytes | None,
        content_type: str = "application/json",
    ) -> requests.Response:
        url = f"{self.base_url}/api/opc-ingest"
        headers = {"Content-Type": content_type}
        if body is None:
            return requests.post(url, data=b"", headers=headers, timeout=5)
        if isinstance(body, (str, bytes)):
            return requests.post(url, data=body, headers=headers, timeout=5)
        # dict or list → JSON
        return requests.post(url, data=json.dumps(body), headers=headers, timeout=5)

    def set_expected_tags(self, tags: list[str]) -> None:
        cfg = self._read_runtime_config()
        cfg["expected_tags"] = tags
        self._write_runtime_config(cfg)

    def clear_expected_tags(self) -> None:
        cfg = self._read_runtime_config()
        cfg["expected_tags"] = []
        self._write_runtime_config(cfg)

    def set_ai_url(self, url: str) -> None:
        cfg = self._read_runtime_config()
        cfg["ai_inference_url"] = url
        self._write_runtime_config(cfg)

    def clear_ai_url(self) -> None:
        cfg = self._read_runtime_config()
        cfg.pop("ai_inference_url", None)
        self._write_runtime_config(cfg)

    def set_timing(
        self,
        interval_ms: int | None = None,
        ttl_ms: int | None = None,
        warmup_timeout_ms: int | None = None,
    ) -> None:
        cfg = self._read_runtime_config()
        if interval_ms is not None:
            cfg["inference_emit_interval_ms"] = interval_ms
        if ttl_ms is not None:
            cfg["max_tag_staleness_ms"] = ttl_ms
        if warmup_timeout_ms is not None:
            cfg["warmup_timeout_ms"] = warmup_timeout_ms
        self._write_runtime_config(cfg)

    def get_stats(self) -> dict[str, Any]:
        r = requests.get(f"{self.base_url}/api/debug/stats", timeout=5)
        r.raise_for_status()
        return r.json()


@pytest.fixture
def nr_api(nr_base_url: str, nr_runtime_config_path: Path) -> NrApi:
    return NrApi(base_url=nr_base_url, runtime_config_path=nr_runtime_config_path)


# ---------------------------------------------------------------------------
# TB REST client
# ---------------------------------------------------------------------------

@dataclass
class TbClient:
    base_url: str
    token: str

    def _headers(self) -> dict[str, str]:
        return {"X-Authorization": f"Bearer {self.token}"}

    def get_device_id(self, device_name: str) -> str | None:
        r = requests.get(
            f"{self.base_url}/api/tenant/devices",
            params={"deviceName": device_name},
            headers=self._headers(),
            timeout=5,
        )
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()["id"]["id"]

    def query_timeseries(
        self,
        device_name: str,
        keys: list[str],
        start_ts: int,
        end_ts: int,
        limit: int = 1000,
    ) -> dict[str, list[dict]]:
        device_id = self.get_device_id(device_name)
        if device_id is None:
            return {}
        r = requests.get(
            f"{self.base_url}/api/plugins/telemetry/DEVICE/{device_id}/values/timeseries",
            params={
                "keys": ",".join(keys),
                "startTs": start_ts,
                "endTs": end_ts,
                "limit": limit,
            },
            headers=self._headers(),
            timeout=5,
        )
        r.raise_for_status()
        return r.json()


@pytest.fixture(scope="session")
def tb_client(tb_base_url: str, tb_token: str) -> TbClient:
    return TbClient(base_url=tb_base_url, token=tb_token)


# ---------------------------------------------------------------------------
# Per-test state cleanup (autouse)
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clean_state(nr_api: NrApi, mock_ml: MockMl):
    """Reset per-test: clear tags/url and set fast timing so tests run in seconds.

    With the periodic-emit design the inject heartbeat is hardcoded at 1s, so
    effective cadence is capped at ~1 Hz even if interval_ms is lower. 500ms
    means "emit whenever the next 1s tick fires" — i.e. ~1 emit/sec in tests.
    TTL=5s is enough to observe boundary behaviour without waiting minutes.
    """
    cfg = nr_api._read_runtime_config()
    cfg["expected_tags"] = []
    cfg.pop("ai_inference_url", None)
    cfg["inference_emit_interval_ms"] = 500
    cfg["max_tag_staleness_ms"] = 5000
    cfg["warmup_timeout_ms"] = 30000
    nr_api._write_runtime_config(cfg)
    mock_ml.reset()
    yield


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def now_ms() -> int:
    return int(time.time() * 1000)


def wait_for_ml(mock_ml: MockMl, count: int, timeout: float = 2.0) -> None:
    """Bloquea hasta que mock_ml tenga ≥count entradas o timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if len(mock_ml.received) >= count:
            return
        time.sleep(0.05)
    raise AssertionError(
        f"Timeout esperando {count} posts en mock_ml; recibidos {len(mock_ml.received)}"
    )
