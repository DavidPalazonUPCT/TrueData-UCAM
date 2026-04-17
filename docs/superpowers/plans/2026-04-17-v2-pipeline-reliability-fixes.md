# Plan — Correcciones de fiabilidad del pipeline v2

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cerrar BUG-1/2/3 + LIMIT-2/4 del findings v2 con un único fix en `fn_main`, respaldado por una suite pytest de 22 tests y contratos actualizados.

**Architecture:**
1. Escribir suite pytest que valide los 22 comportamientos (7 críticos fallan en RED, 15 regresión pasan).
2. Aplicar los 4 fixes en `fn_main` (un solo commit con JS final en el mensaje, por PLAN-001 §D.4.1.7) → 22/22 GREEN.
3. Alinear contratos y runbook F1.

**Tech Stack:** Node-RED 3.1.9 + ThingsBoard CE 4.1.0 (Docker), Python 3.11+ (pytest, requests), JavaScript (function node inline).

**Spec de referencia:** `docs/superpowers/specs/2026-04-17-v2-pipeline-reliability-fixes-design.md`.

---

## Prerrequisitos (verificar antes de empezar)

- [ ] Stack arriba: `docker compose up -d` (desde raíz del repo).
- [ ] Red docker existe: `docker network inspect truedata_iot_network` (si falla: `docker network create truedata_iot_network`).
- [ ] TB healthy: `curl -s http://localhost:9090/login` responde HTML.
- [ ] NR healthy: `curl -s http://localhost:1880/api/get-ml-url` responde JSON (admin endpoint).
- [ ] Python 3.11+ en el host: `python3 --version`.
- [ ] Tenant TB credentials en env: `export TB_USER=tenant@thingsboard.org TB_PASS=tenant` (credenciales por defecto TB CE).

---

## Task 1: Infraestructura de tests de integración

**Objetivo:** Crear `requirements-dev.txt`, `conftest.py` con todas las fixtures, README del harness, y añadir `extra_hosts` a NR compose para que el container alcance al mock ML del host.

**Files:**
- Create: `requirements-dev.txt`
- Create: `tests/integration/conftest.py`
- Create: `tests/integration/README.md`
- Create: `tests/__init__.py` (vacío, para evitar warnings de pytest en algunos setups)
- Create: `tests/integration/__init__.py` (vacío)
- Modify: `truedata-nodered/docker-compose.yml` — añadir `extra_hosts`

- [ ] **Step 1: Añadir `extra_hosts` al compose de NR**

Modificar `truedata-nodered/docker-compose.yml` (bajo `services.nodered_tb`, después de `environment:`) para que `host.docker.internal` resuelva al host desde dentro del container:

```yaml
    environment:
      - TZ=Europe/Madrid
      - NR_ADMIN_ENABLED=true
    extra_hosts:
      - "host.docker.internal:host-gateway"
    networks:
      - iot_network
```

- [ ] **Step 2: Re-crear container NR para aplicar extra_hosts**

```bash
docker compose -f truedata-nodered/docker-compose.yml up -d --force-recreate
```

Verificar:
```bash
docker exec truedata-nodered_tb-1 getent hosts host.docker.internal
```
Expected: línea con una IP (típicamente gateway de la red docker).

> **Nota:** el nombre exacto del container depende del project name; puede ser `truedata-nodered_tb-1`, `truedata_nodered_tb_1`, etc. Usar `docker ps` para confirmarlo.

- [ ] **Step 3: Crear `requirements-dev.txt`**

```
pytest>=8.0.0
requests>=2.31.0
```

- [ ] **Step 4: Crear `tests/__init__.py` y `tests/integration/__init__.py`**

Ambos archivos vacíos. Los creamos para evitar cualquier ambigüedad de rootdir de pytest.

- [ ] **Step 5: Crear `tests/integration/conftest.py`**

```python
"""Fixtures compartidas para tests de integración del pipeline v2.

Asume stack Docker up: TB en :9090, NR en :1880. El mock ML corre en el
host en un puerto aleatorio y NR lo alcanza vía host.docker.internal
(requiere extra_hosts en truedata-nodered/docker-compose.yml).
"""
from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest
import requests


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
        r = requests.post(
            f"{self.base_url}/admin/set-expected-tags",
            json={"tags": tags},
            timeout=5,
        )
        r.raise_for_status()

    def clear_expected_tags(self) -> None:
        requests.post(f"{self.base_url}/admin/clear-expected-tags", timeout=5)

    def set_ml_url(self, url: str) -> None:
        r = requests.post(
            f"{self.base_url}/admin/set-ml-url",
            json={"url": url},
            timeout=5,
        )
        r.raise_for_status()

    def clear_ml_url(self) -> None:
        requests.post(f"{self.base_url}/admin/clear-ml-url", timeout=5)


@pytest.fixture
def nr_api(nr_base_url: str) -> NrApi:
    return NrApi(base_url=nr_base_url)


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
    nr_api.clear_expected_tags()
    nr_api.clear_ml_url()
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
```

- [ ] **Step 6: Crear `tests/integration/README.md`**

```markdown
# Integration tests — pipeline v2

Suite de regresión contra la implementación v2 (NR + TB + mock ML).

## Prerrequisitos

1. Stack Docker arriba:
   ```bash
   docker compose up -d
   ```
2. Red externa:
   ```bash
   docker network create truedata_iot_network  # si no existe
   ```
3. NR con `NR_ADMIN_ENABLED=true` y `extra_hosts: host.docker.internal:host-gateway`
   (ya configurado en `truedata-nodered/docker-compose.yml`).
4. Dependencias de test:
   ```bash
   pip install -r requirements-dev.txt
   ```
5. Credenciales TB:
   ```bash
   export TB_USER=tenant@thingsboard.org
   export TB_PASS=tenant
   ```

## Ejecutar

```bash
pytest tests/integration/ -v
```

## Qué valida

- **Bloque A** (9): validación defensiva del endpoint (`/api/opc-ingest`).
- **Bloque B** (4): comportamiento con valores null, tipos cambiantes, extremos, idempotencia.
- **Bloque C** (2): tags fuera de EXPECTED_TAGS, dropout LOCF.
- **Bloque Warmup** (2): gate LOCF pre/post warmup.
- **Bloque F** (5): escenarios OPC-UA realistas (out-of-order, reconnect, fragmentation, ts window, fault+recovery).

Total: **22 tests** + runbook manual F1 (multi-rate burst) en `docs/testing/runbooks/`.

## Troubleshooting

- **Mock ML no recibe nada**: verificar que NR alcanza `host.docker.internal`:
  ```bash
  docker exec <container_nr> curl -s http://host.docker.internal:<puerto>/
  ```
- **TB auth falla**: el token expira a las 2h; re-lanzar `pytest` lo re-autentica (fixture session-scoped fresca).
- **Tests flaky por timing**: aumentar `wait_for_ml` timeout vía env var si fuera necesario (no implementado; fixar si aparece).
```

- [ ] **Step 7: Commit**

```bash
git add requirements-dev.txt tests/__init__.py tests/integration/__init__.py \
        tests/integration/conftest.py tests/integration/README.md \
        truedata-nodered/docker-compose.yml
git commit -m "$(cat <<'EOF'
chore(tests): añadir harness de integración v2 (pytest, fixtures, mock ML)

- requirements-dev.txt con pytest + requests
- conftest.py con fixtures: nr_api, tb_client, mock_ml, clean_state autouse
- Mock ML en proceso (ThreadingHTTPServer puerto aleatorio)
- NR compose: extra_hosts host.docker.internal:host-gateway para alcanzar mock del host
- README con prerrequisitos y troubleshooting

Sin tests aún; los añade el siguiente commit.
EOF
)"
```

---

## Task 2: Tests del Bloque A (validación defensiva, 9 tests)

**Objetivo:** Cubrir A1-A5 (comportamientos ya correctos, regresión), A6 (BUG-1), A7 + E1 + E2 (BUG-2).

**Files:**
- Create: `tests/integration/test_pipeline_v2.py`

- [ ] **Step 1: Crear el archivo con el scaffold y los tests del Bloque A**

```python
"""Suite de regresión para el pipeline v2.

Spec: docs/superpowers/specs/2026-04-17-v2-pipeline-reliability-fixes-design.md
Findings: docs/architecture/FINDINGS-v2-pipeline-reliability.md
"""
from __future__ import annotations

import time

import pytest
import requests

from tests.integration.conftest import MockMl, NrApi, TbClient, now_ms, wait_for_ml


# ===========================================================================
# Bloque A — Validación defensiva
# ===========================================================================

class TestBlockA:
    """Validación defensiva del endpoint /api/opc-ingest."""

    def test_A1_ts_missing(self, nr_api: NrApi):
        r = nr_api.post_ingest({"values": {"X": 1}})
        assert r.status_code == 400
        assert r.json()["reason"] == "ts missing or not finite number"

    def test_A2_ts_null(self, nr_api: NrApi):
        r = nr_api.post_ingest({"ts": None, "values": {"X": 1}})
        assert r.status_code == 400
        assert r.json()["reason"] == "ts missing or not finite number"

    def test_A3_ts_string(self, nr_api: NrApi):
        r = nr_api.post_ingest({"ts": "2026-01-01", "values": {"X": 1}})
        assert r.status_code == 400
        assert r.json()["reason"] == "ts missing or not finite number"

    def test_A4_values_missing(self, nr_api: NrApi):
        r = nr_api.post_ingest({"ts": now_ms()})
        assert r.status_code == 400
        assert r.json()["reason"] == "values must be non-empty object"

    def test_A5_values_empty(self, nr_api: NrApi):
        r = nr_api.post_ingest({"ts": now_ms(), "values": {}})
        assert r.status_code == 400
        assert r.json()["reason"] == "values must be non-empty object"

    def test_A6_values_array(self, nr_api: NrApi):
        """BUG-1: values como array debe rechazarse."""
        r = nr_api.post_ingest({"ts": now_ms(), "values": [{"tag": "X"}]})
        assert r.status_code == 400
        assert r.json()["reason"] == "values must be non-empty object"

    def test_A7_body_not_json_text_plain(self, nr_api: NrApi):
        """BUG-2: body no-JSON con Content-Type text/plain debe dar mensaje claro."""
        r = nr_api.post_ingest("this is not json", content_type="text/plain")
        assert r.status_code == 400
        assert r.json()["reason"] == "body not valid JSON object"

    def test_E1_body_empty(self, nr_api: NrApi):
        """BUG-2: body vacío debe dar mensaje claro."""
        r = nr_api.post_ingest(None)
        assert r.status_code == 400
        assert r.json()["reason"] == "body not valid JSON object"

    def test_E2_json_body_with_text_plain(self, nr_api: NrApi):
        """BUG-2: JSON válido con CT text/plain debe rechazarse con mensaje claro."""
        r = nr_api.post_ingest('{"ts":123,"values":{"X":1}}', content_type="text/plain")
        assert r.status_code == 400
        assert r.json()["reason"] == "body not valid JSON object"
```

- [ ] **Step 2: Correr el Bloque A contra el código actual (RED esperado para A6/A7/E1/E2)**

```bash
pytest tests/integration/test_pipeline_v2.py::TestBlockA -v
```

Expected:
- A1, A2, A3, A4, A5 → **PASS** (ya funcionan).
- A6 → **FAIL**: código actual devuelve `200` para `values: [{}]` (BUG-1 aún sin corregir).
- A7, E1, E2 → **FAIL por aserción**: código actual devuelve `"ts missing or not number"` en vez de `"body not valid JSON object"` (BUG-2 aún sin corregir).

Si A1-A5 fallan, parar y diagnosticar (stack mal arriba, network, etc.).

---

## Task 3: Tests del Bloque B (null, type change, extremos, idempotencia, 4 tests)

**Files:**
- Modify: `tests/integration/test_pipeline_v2.py` — añadir `TestBlockB`

- [ ] **Step 1: Añadir la clase `TestBlockB` al archivo**

```python
# ===========================================================================
# Bloque B — Comportamiento de values
# ===========================================================================

class TestBlockB:
    """Null, type change, valores extremos, idempotencia TB."""

    def test_B1_null_value_doesnt_contaminate_locf(
        self, nr_api: NrApi, mock_ml: MockMl
    ):
        """LIMIT-2: values.X = null NO debe contaminar lastSeen ni snapshots."""
        nr_api.set_expected_tags(["B1_X", "B1_Y", "B1_Z"])
        nr_api.set_ml_url(mock_ml.url)

        t1 = now_ms()
        nr_api.post_ingest({"ts": t1, "values": {"B1_X": 1.0, "B1_Y": 2.0, "B1_Z": 3.0}})
        wait_for_ml(mock_ml, 1)

        t2 = t1 + 1000
        r = nr_api.post_ingest({"ts": t2, "values": {"B1_X": None, "B1_Y": 4.0}})
        assert r.status_code == 200

        t3 = t2 + 1000
        nr_api.post_ingest({"ts": t3, "values": {"B1_Z": 5.0}})
        wait_for_ml(mock_ml, 3)

        for rec in mock_ml.received:
            for tag, val in rec["sensors"].items():
                assert val is not None, f"Snapshot contenía null para {tag}: {rec}"

        final = mock_ml.received[-1]["sensors"]
        assert final["B1_X"] == 1.0  # LOCF preservó el valor original
        assert final["B1_Y"] == 4.0  # del bundle 2
        assert final["B1_Z"] == 5.0  # del bundle 3

    def test_B2_type_change_between_bundles(self, nr_api: NrApi, tb_client: TbClient):
        """LIMIT-3 regresión: tipo distinto entre bundles del mismo tag → ambos aceptados."""
        tag = "B2_TYPE_CHANGE"
        t1 = now_ms()
        r1 = nr_api.post_ingest({"ts": t1, "values": {tag: 1.5}})
        assert r1.status_code == 200
        t2 = t1 + 1000
        r2 = nr_api.post_ingest({"ts": t2, "values": {tag: "TYPE_CHANGED"}})
        assert r2.status_code == 200

        time.sleep(1.5)  # Dar tiempo a MQTT Gateway a persistir en TB
        ts_data = tb_client.query_timeseries(tag, ["value"], t1 - 1000, t2 + 1000)
        assert len(ts_data.get("value", [])) == 2

    def test_B3_extreme_float_value(self, nr_api: NrApi, tb_client: TbClient):
        """Regresión: float64 max se acepta y persiste."""
        tag = "B3_EXTREME"
        t1 = now_ms()
        r = nr_api.post_ingest({"ts": t1, "values": {tag: 1.79e308}})
        assert r.status_code == 200

        time.sleep(1.5)
        ts_data = tb_client.query_timeseries(tag, ["value"], t1 - 1000, t1 + 1000)
        assert len(ts_data.get("value", [])) >= 1

    def test_B5_tb_idempotency_last_write_wins(
        self, nr_api: NrApi, tb_client: TbClient
    ):
        """Regresión: dos POSTs mismo ts con vals distintos → TB guarda el último."""
        tag = "B5_IDEMPOTENCY"
        t1 = now_ms()
        nr_api.post_ingest({"ts": t1, "values": {tag: 111}})
        nr_api.post_ingest({"ts": t1, "values": {tag: 222}})

        time.sleep(1.5)
        ts_data = tb_client.query_timeseries(tag, ["value"], t1, t1)
        values = ts_data.get("value", [])
        assert len(values) == 1
        assert int(values[0]["value"]) == 222
```

- [ ] **Step 2: Correr el Bloque B contra el código actual**

```bash
pytest tests/integration/test_pipeline_v2.py::TestBlockB -v
```

Expected:
- B1 → **FAIL**: código actual hace `lastSeen["B1_X"] = null`; snapshot final tendría `B1_X=null` (LIMIT-2 aún sin corregir).
- B2, B3, B5 → **PASS**.

---

## Task 4: Tests del Bloque C + Warmup (4 tests)

**Files:**
- Modify: `tests/integration/test_pipeline_v2.py` — añadir `TestBlockC` y `TestWarmup`

- [ ] **Step 1: Añadir las clases al archivo**

```python
# ===========================================================================
# Bloque C — Tag handling
# ===========================================================================

class TestBlockC:
    """Tags fuera de EXPECTED_TAGS, dropout LOCF."""

    def test_C1_unknown_tag_provisioned_excluded_from_snapshot(
        self, nr_api: NrApi, mock_ml: MockMl, tb_client: TbClient
    ):
        """Tag fuera de EXPECTED_TAGS: device TB auto-provisionado, excluido de snapshot ML."""
        nr_api.set_expected_tags(["C1_X", "C1_Y"])
        nr_api.set_ml_url(mock_ml.url)

        t1 = now_ms()
        nr_api.post_ingest({
            "ts": t1,
            "values": {"C1_X": 1, "C1_Y": 2, "C1_NUEVO": 99},
        })
        wait_for_ml(mock_ml, 1)

        snapshot = mock_ml.received[-1]["sensors"]
        assert "C1_X" in snapshot
        assert "C1_Y" in snapshot
        assert "C1_NUEVO" not in snapshot, "Tag fuera de EXPECTED_TAGS filtró al ML"

        time.sleep(1.5)
        ts_data = tb_client.query_timeseries("C1_NUEVO", ["value"], t1 - 1000, t1 + 1000)
        assert len(ts_data.get("value", [])) >= 1

    def test_C2_dropout_locf_holds_stale_value(self, nr_api: NrApi, mock_ml: MockMl):
        """LIMIT-1 regresión: sensor ausente N bundles → LOCF mantiene último valor."""
        nr_api.set_expected_tags(["C2_X", "C2_Y"])
        nr_api.set_ml_url(mock_ml.url)

        t_base = now_ms()
        nr_api.post_ingest({"ts": t_base, "values": {"C2_X": 100, "C2_Y": 200}})
        wait_for_ml(mock_ml, 1)

        for i in range(1, 6):
            nr_api.post_ingest({"ts": t_base + i * 1000, "values": {"C2_Y": 200 + i}})
        wait_for_ml(mock_ml, 6)

        for rec in mock_ml.received:
            assert rec["sensors"]["C2_X"] == 100, "LOCF no mantuvo el valor stale"
        assert mock_ml.received[-1]["sensors"]["C2_Y"] == 205


# ===========================================================================
# Bloque Warmup
# ===========================================================================

class TestWarmup:
    """Gate LOCF pre/post warmup."""

    def test_W_partial_no_emit(self, nr_api: NrApi, mock_ml: MockMl):
        nr_api.set_expected_tags(["W1_X", "W1_Y", "W1_Z"])
        nr_api.set_ml_url(mock_ml.url)

        r = nr_api.post_ingest({"ts": now_ms(), "values": {"W1_X": 1, "W1_Y": 2}})
        assert r.status_code == 200
        assert "warmup" in r.json()["inference"]
        time.sleep(0.5)
        assert len(mock_ml.received) == 0

    def test_W_full_emits_snapshot(self, nr_api: NrApi, mock_ml: MockMl):
        nr_api.set_expected_tags(["W2_X", "W2_Y", "W2_Z"])
        nr_api.set_ml_url(mock_ml.url)

        t = now_ms()
        nr_api.post_ingest({"ts": t, "values": {"W2_X": 1}})
        nr_api.post_ingest({"ts": t + 1, "values": {"W2_Y": 2}})
        r = nr_api.post_ingest({"ts": t + 2, "values": {"W2_Z": 3}})
        assert r.status_code == 200
        assert r.json()["inference"] == "emitted"
        wait_for_ml(mock_ml, 1)

        assert mock_ml.received[-1]["sensors"] == {"W2_X": 1, "W2_Y": 2, "W2_Z": 3}
        assert mock_ml.received[-1]["ts"] == t + 2
```

- [ ] **Step 2: Correr Bloque C + Warmup**

```bash
pytest tests/integration/test_pipeline_v2.py::TestBlockC \
       tests/integration/test_pipeline_v2.py::TestWarmup -v
```

Expected: todos **PASS** (son regresión, el código actual ya los cumple).

---

## Task 5: Tests del Bloque F (5 tests: F2, F3, F4, F5, F6)

**Files:**
- Modify: `tests/integration/test_pipeline_v2.py` — añadir `TestBlockF`

- [ ] **Step 1: Añadir la clase al archivo**

```python
# ===========================================================================
# Bloque F — Escenarios OPC-UA realistas
# ===========================================================================

class TestBlockF:
    """F1 está en runbook manual. F2..F6 automatizados."""

    def test_F2_out_of_order_doesnt_corrupt_locf(
        self, nr_api: NrApi, mock_ml: MockMl
    ):
        """BUG-3: bundle late (ts antiguo) NO debe sobreescribir state LOCF."""
        nr_api.set_expected_tags(["F2_X"])
        nr_api.set_ml_url(mock_ml.url)

        t_base = now_ms() - 60_000  # 1 min atrás, dentro ventana

        nr_api.post_ingest({"ts": t_base, "values": {"F2_X": 100}})
        wait_for_ml(mock_ml, 1)

        nr_api.post_ingest({"ts": t_base + 1000, "values": {"F2_X": 200}})
        wait_for_ml(mock_ml, 2)

        # Late arrival: ts anterior
        nr_api.post_ingest({"ts": t_base - 500, "values": {"F2_X": 50}})
        wait_for_ml(mock_ml, 3)

        nr_api.post_ingest({"ts": t_base + 2000, "values": {"F2_X": 300}})
        wait_for_ml(mock_ml, 4)

        # Snapshot del bundle late (índice 2): debe reflejar LOCF=200, NO 50
        assert mock_ml.received[2]["sensors"]["F2_X"] == 200, (
            f"BUG-3 regressed: late arrival corrompió LOCF. "
            f"Snapshots: {[r['sensors']['F2_X'] for r in mock_ml.received]}"
        )
        assert mock_ml.received[3]["sensors"]["F2_X"] == 300

    def test_F3_reconnect_burst_past_ts_accepted(
        self, nr_api: NrApi, tb_client: TbClient
    ):
        """Regresión: 30 bundles con ts=now-10min → aceptados y persistidos."""
        base_ts = now_ms() - 10 * 60 * 1000
        tag = "F3_RECONNECT"
        nr_api.set_expected_tags([tag])

        for i in range(30):
            r = nr_api.post_ingest({"ts": base_ts + i * 1000, "values": {tag: i}})
            assert r.status_code == 200

        time.sleep(2)
        ts_data = tb_client.query_timeseries(
            tag, ["value"], base_ts - 1000, base_ts + 60_000, limit=100
        )
        assert len(ts_data.get("value", [])) == 30

    def test_F4_fragmentation_two_bundles_two_snapshots(
        self, nr_api: NrApi, mock_ml: MockMl
    ):
        """Regresión: bundles ts=T y T+20ms → 2 snapshots distintos a ML."""
        nr_api.set_expected_tags(["F4_X"])
        nr_api.set_ml_url(mock_ml.url)

        t1 = now_ms()
        nr_api.post_ingest({"ts": t1, "values": {"F4_X": 1}})
        nr_api.post_ingest({"ts": t1 + 20, "values": {"F4_X": 2}})
        wait_for_ml(mock_ml, 2)

        assert mock_ml.received[0]["ts"] == t1
        assert mock_ml.received[1]["ts"] == t1 + 20

    @pytest.mark.parametrize(
        "ts_strategy,expected_status",
        [
            ("epoch_zero", 400),        # ts=0
            ("negative", 400),          # ts=-1
            ("future_far", 400),        # now + 10min
            ("past_1h", 200),           # now - 1h (dentro ventana)
            ("past_40d", 400),          # now - 40d (fuera ventana)
        ],
    )
    def test_F5_ts_sanity_window(
        self, nr_api: NrApi, ts_strategy: str, expected_status: int
    ):
        """LIMIT-4: ventana de ts [now-30d .. now+5min]."""
        now = now_ms()
        ts = {
            "epoch_zero": 0,
            "negative": -1,
            "future_far": now + 10 * 60 * 1000,
            "past_1h": now - 60 * 60 * 1000,
            "past_40d": now - 40 * 24 * 3600 * 1000,
        }[ts_strategy]

        r = nr_api.post_ingest({"ts": ts, "values": {"F5_X": 1}})
        assert r.status_code == expected_status, (
            f"{ts_strategy} (ts={ts}): esperaba {expected_status}, got {r.status_code} "
            f"body={r.text[:200]}"
        )
        if expected_status == 400:
            assert "ts outside acceptable window" in r.json()["reason"]

    def test_F6_sensor_fault_recovery(self, nr_api: NrApi, mock_ml: MockMl):
        """Regresión: sensor ausente 3 bundles + vuelve → LOCF reacciona al recovery."""
        nr_api.set_expected_tags(["F6_X", "F6_Y"])
        nr_api.set_ml_url(mock_ml.url)

        t_base = now_ms()
        nr_api.post_ingest({"ts": t_base, "values": {"F6_X": 100, "F6_Y": 200}})
        wait_for_ml(mock_ml, 1)

        for i in range(1, 4):
            nr_api.post_ingest({"ts": t_base + i * 1000, "values": {"F6_Y": 200 + i * 10}})
        wait_for_ml(mock_ml, 4)

        for rec in mock_ml.received[:4]:
            assert rec["sensors"]["F6_X"] == 100

        nr_api.post_ingest({"ts": t_base + 4000, "values": {"F6_X": 500, "F6_Y": 240}})
        wait_for_ml(mock_ml, 5)

        assert mock_ml.received[-1]["sensors"]["F6_X"] == 500
        assert mock_ml.received[-1]["sensors"]["F6_Y"] == 240
```

- [ ] **Step 2: Correr Bloque F**

```bash
pytest tests/integration/test_pipeline_v2.py::TestBlockF -v
```

Expected:
- F2 → **FAIL**: snapshot[2]["F2_X"] = 50 en código actual (BUG-3), esperamos 200.
- F3, F4, F6 → **PASS**.
- F5: `past_1h` **PASS**, `future_far`/`past_40d` **FAIL** (código actual acepta), `epoch_zero`/`negative` **FAIL** (código actual acepta).

---

## Task 6: Verificar matriz RED completa y commitear la suite

- [ ] **Step 1: Correr toda la suite**

```bash
pytest tests/integration/ -v
```

- [ ] **Step 2: Verificar la matriz RED esperada**

Contar resultados. **FAILs esperados (7 críticos sobre BUG/LIMIT no corregidos aún):**

| Test | Razón |
|---|---|
| `test_A6_values_array` | BUG-1 |
| `test_A7_body_not_json_text_plain` | BUG-2 |
| `test_E1_body_empty` | BUG-2 |
| `test_E2_json_body_with_text_plain` | BUG-2 |
| `test_B1_null_value_doesnt_contaminate_locf` | LIMIT-2 |
| `test_F2_out_of_order_doesnt_corrupt_locf` | BUG-3 |
| `test_F5_ts_sanity_window[epoch_zero]` | LIMIT-4 |
| `test_F5_ts_sanity_window[negative]` | LIMIT-4 |
| `test_F5_ts_sanity_window[future_far]` | LIMIT-4 |
| `test_F5_ts_sanity_window[past_40d]` | LIMIT-4 |

F5 parametrizado cuenta como 5 tests en pytest; 4 deben fallar (sólo `past_1h` pasa). El findings habla de "7 críticos" pero pytest contará más por la parametrización. El total esperado es: **10 failing test cases, 16 passing** (total 26 case runs desde 22 "tests lógicos").

Si el conteo no cuadra, diagnosticar antes de continuar (posible bug en el test harness, no en el código). NO proceder al fix hasta tener una matriz RED limpia.

- [ ] **Step 3: Commit de la suite**

```bash
git add tests/integration/test_pipeline_v2.py
git commit -m "$(cat <<'EOF'
test(integration): suite de regresión v2 — Grupos A/B/C/E/F2-F6 (22 casos, RED antes del fix)

Cubre:
- Bloque A (9): validación defensiva, incluye BUG-1/BUG-2 (A6/A7/E1/E2)
- Bloque B (4): null/type change/extremos/idempotencia TB (B1 = LIMIT-2)
- Bloque C (2): tag unknown, dropout LOCF (regresión LIMIT-1)
- Bloque Warmup (2): gate LOCF pre/post
- Bloque F (5): F2 = BUG-3, F3/F4/F6 regresión, F5 parametrizado = LIMIT-4

Estado RED esperado: ~10 failing case runs (7 tests lógicos: A6, A7, E1, E2, B1, F2, F5×4).
Fix consolidado llega en el commit siguiente.
EOF
)"
```

---

## Task 7: Añadir flag `--shift-to-now` al simulador

**Objetivo:** Permitir replay del dump histórico FR_ARAGON tras aplicar LIMIT-4 (dump es de diciembre 2025, fuera de ventana `[now-30d, now+5min]`).

**Files:**
- Modify: `simulator/opc_client_v2.py`

- [ ] **Step 1: Añadir helper `apply_time_shift` y flag al parser**

En `simulator/opc_client_v2.py`, localizar la función `run()` (≈línea 174) y el `build_parser()` (≈línea 235).

Añadir la función `apply_time_shift` antes de `run()`:

```python
def apply_time_shift(bundles: list[Bundle], shift_ms: int) -> list[Bundle]:
    """Desplaza los ts de todos los bundles en `shift_ms` preservando deltas."""
    return [Bundle(ts_ms=b.ts_ms + shift_ms, values=b.values) for b in bundles]
```

En `run()`, tras `bundles = load_bundles(sql_path)` y **antes** de la sección `if args.limit:` (≈línea 184), añadir:

```python
    if args.shift_to_now and bundles:
        shift_ms = int(time.time() * 1000) - bundles[0].ts_ms
        bundles = apply_time_shift(bundles, shift_ms)
        print(
            f"Time-shifted {len(bundles)} bundles by {shift_ms} ms "
            f"(first bundle now at {bundles[0].ts_ms})",
            file=sys.stderr,
        )
```

En `build_parser()`, añadir el argumento:

```python
    p.add_argument(
        "--shift-to-now",
        action="store_true",
        help="Desplaza ts de todos los bundles para que el primero caiga en 'ahora' "
             "(preserva deltas relativos). Útil para replayear dumps históricos "
             "fuera de la ventana de validación de NR.",
    )
```

- [ ] **Step 2: Validar sintaxis Python**

```bash
python3 -c "import ast; ast.parse(open('simulator/opc_client_v2.py').read())"
```

Expected: sin output (syntax OK).

- [ ] **Step 3: Smoke test del flag con --dry-run**

```bash
python3 simulator/opc_client_v2.py \
  --sql src/FR_ARAGON/Francisco_16_01_2026.sql \
  --limit 3 --shift-to-now --dry-run
```

Expected: línea `Time-shifted N bundles by M ms ...` en stderr, y en stdout los 3 primeros bundles con `ts` cerca de ahora (en milisegundos).

- [ ] **Step 4: Commit**

```bash
git add simulator/opc_client_v2.py
git commit -m "$(cat <<'EOF'
feat(simulator): añadir flag --shift-to-now para replay de dumps históricos

Desplaza los ts de todos los bundles para que el primero caiga en el instante
actual, preservando los deltas temporales relativos. Permite reutilizar dumps
viejos (p.ej. FR_ARAGON de diciembre 2025) bajo la validación LIMIT-4 que NR
aplica tras el fix de fiabilidad v2 (ventana [now-30d, now+5min]).
EOF
)"
```

---

## Task 8: Aplicar el fix consolidado en `fn_main`

**Objetivo:** Un único commit al function node principal con los 4 fixes (BUG-1/2/3 + LIMIT-2/4). El commit message incluye el JS final completo (convención PLAN-001 §D.4.1.7).

**Files:**
- Modify: `truedata-nodered/data/flows.json` — nodo `fn_main`

- [ ] **Step 1: Abrir `truedata-nodered/data/flows.json` y localizar el nodo `fn_main`**

Es el objeto con `"id": "fn_main"` (≈línea 49). El campo `"func"` contiene el código JavaScript como string escapado.

- [ ] **Step 2: Reemplazar el valor completo de `"func"` por el JS nuevo**

El JavaScript final (tal cual va en el archivo, con escapes JSON aplicados al guardarlo):

```javascript
// ============================================================
// PASO 1: VALIDATION
// ============================================================
if (!msg.payload || typeof msg.payload !== "object" || Array.isArray(msg.payload)) {
    msg.statusCode = 400;
    msg.payload = { status: "error", reason: "body not valid JSON object" };
    return [null, null, msg];
}
const ts = msg.payload.ts;
const values = msg.payload.values;

if (typeof ts !== "number" || !Number.isFinite(ts)) {
    msg.statusCode = 400;
    msg.payload = { status: "error", reason: "ts missing or not finite number" };
    return [null, null, msg];
}

const now = Date.now();
if (ts < now - 30*24*3600*1000 || ts > now + 5*60*1000) {
    msg.statusCode = 400;
    msg.payload = { status: "error", reason: "ts outside acceptable window (now-30d .. now+5min)" };
    return [null, null, msg];
}

if (typeof values !== "object" || values === null || Array.isArray(values) || Object.keys(values).length === 0) {
    msg.statusCode = 400;
    msg.payload = { status: "error", reason: "values must be non-empty object" };
    return [null, null, msg];
}

// ============================================================
// LOCF: update last-seen state (BUG-3 + LIMIT-2)
// lastSeen shape: {tag: {value, ts}}
// ============================================================
const lastSeen = flow.get("lastSeen") || {};
for (const [tag, value] of Object.entries(values)) {
    if (value === null || value === undefined) continue;
    const prev = lastSeen[tag];
    if (!prev || ts >= prev.ts) {
        lastSeen[tag] = { value: value, ts: ts };
    }
}
flow.set("lastSeen", lastSeen);

// ============================================================
// PASO 2a: BUILD CONNECT MESSAGES (per-sensor devices, raw path)
// ============================================================
const DEVICE_PROFILE = flow.get("DEVICE_PROFILE") || "sensor_planta";
const INFERENCE_DEVICE = flow.get("INFERENCE_DEVICE") || "inference-input";
const INFERENCE_PROFILE = flow.get("INFERENCE_PROFILE") || "inference_input";
const seen = flow.get("connectedDevices") || {};
const connectMsgs = [];

for (const tagName of Object.keys(values)) {
    if (!seen[tagName]) {
        connectMsgs.push({
            payload: JSON.stringify({ device: tagName, type: DEVICE_PROFILE }),
            topic: "v1/gateway/connect",
            qos: 1
        });
        seen[tagName] = true;
    }
}

// ============================================================
// PASO 2b: BUILD PER-SENSOR TELEMETRY (raw, always)
// ============================================================
const gatewayPayload = {};
for (const [tag, value] of Object.entries(values)) {
    gatewayPayload[tag] = [{ ts: ts, values: { value: value } }];
}
const mqttMsg = {
    payload: JSON.stringify(gatewayPayload),
    topic: "v1/gateway/telemetry",
    qos: 1
};

// ============================================================
// PASO 3: LOCF SNAPSHOT for ML + inference-input device
// ============================================================
const expectedTags = flow.get("EXPECTED_TAGS");
const mlUrl = flow.get("ML_INFERENCE_URL");
const inferenceMsgs = [];
let mlMsg = null;
let warmup = null;

if (expectedTags && Array.isArray(expectedTags) && expectedTags.length > 0) {
    const missing = expectedTags.filter(t => !(t in lastSeen));
    if (missing.length === 0) {
        const snapshot = {};
        for (const t of expectedTags) snapshot[t] = lastSeen[t].value;

        if (!seen[INFERENCE_DEVICE]) {
            inferenceMsgs.push({
                payload: JSON.stringify({ device: INFERENCE_DEVICE, type: INFERENCE_PROFILE }),
                topic: "v1/gateway/connect",
                qos: 1
            });
            seen[INFERENCE_DEVICE] = true;
        }
        inferenceMsgs.push({
            payload: JSON.stringify({ [INFERENCE_DEVICE]: [{ ts: ts, values: snapshot }] }),
            topic: "v1/gateway/telemetry",
            qos: 1
        });

        if (mlUrl) {
            mlMsg = {
                payload: { ts: ts, sensors: snapshot },
                url: mlUrl,
                method: "POST",
                headers: { "Content-Type": "application/json" },
                requestTimeout: 5000
            };
        }
    } else {
        warmup = { missing: missing.length, total: expectedTags.length };
        node.log(`LOCF warm-up: ${missing.length}/${expectedTags.length} tags missing (first: ${missing.slice(0,3).join(',')})`);
    }
} else if (mlUrl) {
    mlMsg = {
        payload: { ts: ts, sensors: values },
        url: mlUrl,
        method: "POST",
        headers: { "Content-Type": "application/json" },
        requestTimeout: 5000
    };
}

flow.set("connectedDevices", seen);

// ============================================================
// ACK + outputs
// ============================================================
msg.statusCode = 200;
msg.payload = {
    status: "ok",
    tags: Object.keys(values).length,
    inference: mlMsg ? "emitted" : (warmup ? `warmup(${warmup.missing}/${warmup.total})` : "disabled")
};

const output1 = [...connectMsgs, mqttMsg, ...inferenceMsgs];
return [output1, mlMsg, msg];
```

**Cómo hacer el reemplazo en `flows.json`:** el campo `"func"` es una única string JSON-escapada. Procedimiento seguro:

1. Copia el JS anterior completo (desde `// PASO 1` hasta `return [output1, mlMsg, msg];`) en un archivo temporal `/tmp/fn_main_new.js`.
2. Usa Python para generar la string JSON escapada:
   ```bash
   python3 -c "import json; print(json.dumps(open('/tmp/fn_main_new.js').read()))" > /tmp/fn_main_new.json_str
   ```
3. Abre `truedata-nodered/data/flows.json` en el editor, localiza `"func": "..."` dentro del objeto `fn_main`, y reemplaza el valor (el string entero, entre comillas dobles) por el contenido de `/tmp/fn_main_new.json_str`.
4. Verifica que el JSON sigue siendo válido:
   ```bash
   python3 -c "import json; json.load(open('truedata-nodered/data/flows.json'))"
   ```
   Expected: sin output (JSON válido).

- [ ] **Step 3: Validar que NR carga el flow sin errores**

```bash
docker compose -f truedata-nodered/docker-compose.yml restart nodered_tb
sleep 8
docker logs --tail=30 truedata-nodered_tb-1 2>&1 | grep -i "error\|fail" || echo "NR arrancó limpio"
```

Si hay errores de parsing, deshacer el paso 2 y revisar el escape.

- [ ] **Step 4: Sanity check del admin endpoint post-redeploy**

```bash
curl -s http://localhost:1880/admin/clear-expected-tags -X POST
curl -s http://localhost:1880/admin/get-expected-tags
```

Expected: `{"expectedTags":null, ... }` (state limpio).

- [ ] **Step 5: Correr suite completa — esperamos GREEN 100%**

```bash
pytest tests/integration/ -v
```

Expected: **todos pasan** (26 case runs GREEN, incluyendo los 5 de F5 parametrizado).

Si algún test sigue en RED, diagnosticar por categoría:
- A6/A7/E1/E2/B1/F2/F5 siguen fallando → el reemplazo del `"func"` no tomó efecto (redeploy, state cache). Re-verificar paso 3.
- Tests antes GREEN ahora fallan → efecto lateral del cambio de shape de `lastSeen` (revisar que snapshot builder usa `.value`).

- [ ] **Step 6: Commit con JS final en el mensaje**

```bash
git add truedata-nodered/data/flows.json
git commit -m "$(cat <<'EOF'
fix(nodered): corregir BUG-1/2/3 + LIMIT-2/4 en fn_main (validación body + LOCF state)

Cierra la matriz de fiabilidad del findings v2:
- BUG-1: rechazar `values` como array
- BUG-2: body no-JSON (vacío, CT text/plain) → mensaje claro
- BUG-3: bundle con ts antiguo no sobreescribe state LOCF
- LIMIT-2: valores null/undefined no contaminan lastSeen
- LIMIT-4: ts fuera de [now-30d .. now+5min] → 400

Cambio de forma: `flow.lastSeen` pasa de `{tag: value}` a `{tag: {value, ts}}`.
Snapshot builder extrae `.value`. Tras redeploy, ejecutar
`POST /admin/clear-expected-tags` para limpiar state viejo (ya lo hace el
autouse fixture de la suite pytest).

Suite pytest pasa 22/22 contra este fix (ver tests/integration/).

Por convención PLAN-001 §D.4.1.7 el código JS final del function node:

```javascript
// PASO 1: VALIDATION
if (!msg.payload || typeof msg.payload !== "object" || Array.isArray(msg.payload)) {
    msg.statusCode = 400;
    msg.payload = { status: "error", reason: "body not valid JSON object" };
    return [null, null, msg];
}
const ts = msg.payload.ts;
const values = msg.payload.values;

if (typeof ts !== "number" || !Number.isFinite(ts)) {
    msg.statusCode = 400;
    msg.payload = { status: "error", reason: "ts missing or not finite number" };
    return [null, null, msg];
}

const now = Date.now();
if (ts < now - 30*24*3600*1000 || ts > now + 5*60*1000) {
    msg.statusCode = 400;
    msg.payload = { status: "error", reason: "ts outside acceptable window (now-30d .. now+5min)" };
    return [null, null, msg];
}

if (typeof values !== "object" || values === null || Array.isArray(values) || Object.keys(values).length === 0) {
    msg.statusCode = 400;
    msg.payload = { status: "error", reason: "values must be non-empty object" };
    return [null, null, msg];
}

// LOCF update (BUG-3 + LIMIT-2)
const lastSeen = flow.get("lastSeen") || {};
for (const [tag, value] of Object.entries(values)) {
    if (value === null || value === undefined) continue;
    const prev = lastSeen[tag];
    if (!prev || ts >= prev.ts) {
        lastSeen[tag] = { value: value, ts: ts };
    }
}
flow.set("lastSeen", lastSeen);

// PASO 2a: connect messages (sin cambios desde versión anterior)
const DEVICE_PROFILE = flow.get("DEVICE_PROFILE") || "sensor_planta";
const INFERENCE_DEVICE = flow.get("INFERENCE_DEVICE") || "inference-input";
const INFERENCE_PROFILE = flow.get("INFERENCE_PROFILE") || "inference_input";
const seen = flow.get("connectedDevices") || {};
const connectMsgs = [];
for (const tagName of Object.keys(values)) {
    if (!seen[tagName]) {
        connectMsgs.push({
            payload: JSON.stringify({ device: tagName, type: DEVICE_PROFILE }),
            topic: "v1/gateway/connect", qos: 1
        });
        seen[tagName] = true;
    }
}

// PASO 2b: raw telemetry
const gatewayPayload = {};
for (const [tag, value] of Object.entries(values)) {
    gatewayPayload[tag] = [{ ts: ts, values: { value: value } }];
}
const mqttMsg = { payload: JSON.stringify(gatewayPayload), topic: "v1/gateway/telemetry", qos: 1 };

// PASO 3: snapshot builder — extrae .value del nuevo shape
const expectedTags = flow.get("EXPECTED_TAGS");
const mlUrl = flow.get("ML_INFERENCE_URL");
const inferenceMsgs = [];
let mlMsg = null;
let warmup = null;

if (expectedTags && Array.isArray(expectedTags) && expectedTags.length > 0) {
    const missing = expectedTags.filter(t => !(t in lastSeen));
    if (missing.length === 0) {
        const snapshot = {};
        for (const t of expectedTags) snapshot[t] = lastSeen[t].value;
        if (!seen[INFERENCE_DEVICE]) {
            inferenceMsgs.push({
                payload: JSON.stringify({ device: INFERENCE_DEVICE, type: INFERENCE_PROFILE }),
                topic: "v1/gateway/connect", qos: 1
            });
            seen[INFERENCE_DEVICE] = true;
        }
        inferenceMsgs.push({
            payload: JSON.stringify({ [INFERENCE_DEVICE]: [{ ts: ts, values: snapshot }] }),
            topic: "v1/gateway/telemetry", qos: 1
        });
        if (mlUrl) {
            mlMsg = {
                payload: { ts: ts, sensors: snapshot },
                url: mlUrl, method: "POST",
                headers: { "Content-Type": "application/json" },
                requestTimeout: 5000
            };
        }
    } else {
        warmup = { missing: missing.length, total: expectedTags.length };
        node.log(`LOCF warm-up: ${missing.length}/${expectedTags.length} tags missing (first: ${missing.slice(0,3).join(',')})`);
    }
} else if (mlUrl) {
    mlMsg = {
        payload: { ts: ts, sensors: values },
        url: mlUrl, method: "POST",
        headers: { "Content-Type": "application/json" },
        requestTimeout: 5000
    };
}

flow.set("connectedDevices", seen);

msg.statusCode = 200;
msg.payload = {
    status: "ok",
    tags: Object.keys(values).length,
    inference: mlMsg ? "emitted" : (warmup ? `warmup(${warmup.missing}/${warmup.total})` : "disabled")
};

const output1 = [...connectMsgs, mqttMsg, ...inferenceMsgs];
return [output1, mlMsg, msg];
```
EOF
)"
```

---

## Task 9: Actualizar contratos públicos (`docs/contracts/*.md`)

**Files:**
- Modify: `docs/contracts/opc-ingest.md`
- Modify: `docs/contracts/ml-inference.md`
- Modify: `docs/contracts/ml-writeback.md`

- [ ] **Step 1: Leer los 3 contratos actuales**

Para entender el contexto antes de editar:
```bash
wc -l docs/contracts/opc-ingest.md docs/contracts/ml-inference.md docs/contracts/ml-writeback.md
```

- [ ] **Step 2: Actualizar `opc-ingest.md`**

En **§Respuestas** (tabla de códigos 200/400), reemplazar las filas 400 actuales por:

```markdown
| `400 Bad Request` | `{"status": "error", "reason": "body not valid JSON object"}` | Body ausente, no parseable como JSON, o de tipo distinto a objeto (array, primitivo) |
| `400 Bad Request` | `{"status": "error", "reason": "ts missing or not finite number"}` | `ts` ausente, no es `typeof number`, o es `NaN`/`Infinity` |
| `400 Bad Request` | `{"status": "error", "reason": "ts outside acceptable window (now-30d .. now+5min)"}` | `ts` fuera de la ventana aceptable (ver A6) |
| `400 Bad Request` | `{"status": "error", "reason": "values must be non-empty object"}` | `values` ausente, no es objeto, es un array, o está vacío |
```

En **§Validaciones que rechazan el POST**, reemplazar la tabla por:

```markdown
| Orden | Check | Fallo → reason |
|---|---|---|
| 1 | body JSON, typeof "object", no null, no array | `"body not valid JSON object"` |
| 2 | `typeof ts === "number"` && `Number.isFinite(ts)` | `"ts missing or not finite number"` |
| 3 | `ts ∈ [now-30d, now+5min]` | `"ts outside acceptable window (now-30d .. now+5min)"` |
| 4 | `typeof values === "object"`, no null, no array, ≥1 key | `"values must be non-empty object"` |
```

En **§Reglas semánticas**, añadir al final (después de "Cardinalidad libre"):

```markdown
- **`value: null` o `undefined` ≡ tag ausente del bundle**. Un bundle `{ts, values: {X: null}}` devuelve `200 OK` pero X no entra al state LOCF (equivalente a que el bundle no contuviera X). Consistente con OPC-UA: un DataValue con StatusCode Bad suele llevar `value: null`.
- **Cambio de tipo del valor entre bundles no validado**. El mismo `tag` puede enviar `float` en un bundle y `string` en otro; NR propaga ambos. Responsabilidad del consumidor ML hacer sanity-check de tipos.
```

En **§Asunciones explícitas**, añadir una nueva sección tras A5:

```markdown
### A6 — `ts` en ventana [now-30d .. now+5min]

NR rechaza (`400`) cualquier POST con `ts` fuera de esta ventana respecto al reloj del host de NR. El rango tolera:

- Store-and-forward del servicio OPC hasta 30 días de backlog.
- Clock skew moderado entre el PLC/servicio OPC y el host de NR (±5 min en el futuro).

Valores fuera de rango (p.ej. `ts=0` por bug del cliente, `ts` de años atrás por replay de dumps antiguos) se rechazan para prevenir contaminación del histórico TB y queries confusas.
```

En **§Casos de error operacionales** (tabla), añadir filas:

```markdown
| `ts` epoch (`0`) o negativo | Rechazo con `400 ts outside acceptable window`. Indica bug en el cliente, no se ingesta |
| `ts` futuro > now+5min | Rechazo con `400 ts outside acceptable window`. Indica clock skew extremo o ts erróneo |
| `ts` muy antiguo (> 30 días atrás) | Rechazo con `400 ts outside acceptable window`. Requiere replay con desplazamiento temporal si se desea reingestar |
| Content-Type no JSON (p.ej. `text/plain`) | Rechazo con `400 body not valid JSON object` |
| Body vacío | Rechazo con `400 body not valid JSON object` |
```

- [ ] **Step 3: Actualizar `ml-inference.md`**

Añadir nueva sección **§Garantías de NR hacia el servicio ML** (o ampliar la existente):

```markdown
### Garantías sobre el campo `sensors`

- **Nunca contiene `null` ni `undefined`**. NR filtra valores nulos al actualizar su state LOCF; el snapshot siempre trae valores reales del último bundle válido por tag.
- **Contiene exactamente los tags de `EXPECTED_TAGS`**. Tags fuera del set no entran al snapshot (sí persisten en TB raw por separado).
- **El `ts` del snapshot corresponde al `ts` del bundle que disparó la inferencia**, no al instante de envío. Los valores de tags que no llegaron en ese bundle vienen por carry-forward (LOCF) del último bundle válido por tag.
```

Añadir nueva sección **§Asunciones sobre el consumidor ML** (o equivalente):

```markdown
### Detección de sensor dropout (stale LOCF)

NR no implementa timers de stale ni alarmas de sensor caído. Si un sensor dejara de emitir (avería persistente), el snapshot seguirá recibiendo su último valor conocido indefinidamente vía LOCF (ver FINDINGS-v2 §LIMIT-1).

**Responsabilidad del servicio ML:** comparar el `ts` del snapshot entrante contra el `ts` del último punto de cada sensor individual en TB raw (`GET /api/plugins/telemetry/DEVICE/{sensor}/values/timeseries`). Si el gap es mayor que N ventanas operativas, emitir `status: "degraded"` en el writeback (ver `ml-writeback.md`).

### Estabilidad del tipo de valor

NR no valida el tipo del valor de cada tag. El mismo `sensors[tag]` puede ser `float` en una inferencia y `string` en la siguiente si el PLC cambia el tipo de la variable subyacente. El ML debe hacer sanity-check de tipos en su preproc (p.ej. `isinstance(v, (int, float))`) y rutar a un fallback si el tipo no es el esperado.
```

- [ ] **Step 4: Actualizar `ml-writeback.md`**

En la sección que describe los campos del writeback (estructura del request del ML hacia blockchain/TB), añadir al final de la tabla de campos opcionales:

```markdown
| `status` | string | No (default `"ok"`) | `"ok"` si la inferencia se hizo con datos frescos; `"degraded"` si el ML detectó staleness en uno o más sensores vía comparación contra TB raw (mitigación de LIMIT-1 del findings v2). Valor libre para extensiones futuras (`"rejected"`, `"low_confidence"`, etc.) |
```

Si la sección de campos no existe con ese formato, añadir una subsección nueva:

```markdown
### Campo `status` — señalización de calidad de inferencia (opcional)

El ML puede incluir un campo `status` en el writeback para señalizar que detectó condiciones anómalas en el snapshot que recibió de NR:

- `"ok"` (default si se omite): inferencia realizada con datos frescos.
- `"degraded"`: el ML detectó staleness (LOCF stale) en uno o más sensores comparando el `ts` del snapshot contra TB raw. La inferencia se hizo pero los consumidores downstream pueden querer tratarla con menor peso.

Este mecanismo compensa la ausencia de detección de dropout en NR (ver ml-inference.md §Detección de sensor dropout y FINDINGS-v2 §LIMIT-1).
```

- [ ] **Step 5: Commit de los 3 contratos**

```bash
git add docs/contracts/opc-ingest.md docs/contracts/ml-inference.md docs/contracts/ml-writeback.md
git commit -m "$(cat <<'EOF'
docs(contracts): alinear opc-ingest + ml-inference + ml-writeback con v2 post-fix

- opc-ingest: nuevos 4 reasons de 400, nueva asunción A6 (ventana ts),
  reglas semánticas sobre null = ausente y tipos no validados
- ml-inference: garantía "sensors sin null", asunción de detección de
  dropout por el ML (LIMIT-1), sanity-check de tipos (LIMIT-3)
- ml-writeback: campo opcional `status` para señalizar inferencia "degraded"

Contratos ahora reflejan el comportamiento real tras los fixes del pipeline v2.
EOF
)"
```

---

## Task 10: Actualizar docs internos (PLAN-001 + FINDINGS-v2)

**Files:**
- Modify: `docs/architecture/PLAN-001.md` — §D.4 pseudocódigo
- Modify: `docs/architecture/FINDINGS-v2-pipeline-reliability.md` — §9 Historial

- [ ] **Step 1: Actualizar `PLAN-001.md` §D.4**

Localizar la sección `### D.4 — Flujo del function node (pseudo-código)` (≈línea 1826). Reemplazar el bloque de pseudo-código entre triple-backtick por:

```
input:  msg.payload (HTTP body del OPC Client)
output 1 → mqtt-out (connects + telemetry hacia TB Gateway MQTT)
output 2 → http-request (body hacia ML inference)
output 3 → http-response (error 400 | ACK 200)

// ============================================================
// PASO 1: VALIDACIÓN (orden estricto)
// ============================================================
if !msg.payload or typeof msg.payload !== "object" or Array.isArray(msg.payload):
    return [null, null, { statusCode: 400, payload: { reason: "body not valid JSON object" } }]

const ts = msg.payload.ts
if typeof ts !== "number" or !Number.isFinite(ts):
    return [null, null, { statusCode: 400, payload: { reason: "ts missing or not finite number" } }]

const now = Date.now()
if ts < now - 30*24*3600*1000 or ts > now + 5*60*1000:
    return [null, null, { statusCode: 400, payload: { reason: "ts outside acceptable window (now-30d .. now+5min)" } }]

const values = msg.payload.values
if typeof values !== "object" or values === null or Array.isArray(values) or Object.keys(values).length === 0:
    return [null, null, { statusCode: 400, payload: { reason: "values must be non-empty object" } }]

// ============================================================
// PASO 1bis: LOCF update — shape {tag: {value, ts}}
// ============================================================
const lastSeen = flow.get("lastSeen") || {}
for each (tag, value) in values:
    if value === null or value === undefined: continue  // LIMIT-2
    const prev = lastSeen[tag]
    if !prev or ts >= prev.ts:                          // BUG-3
        lastSeen[tag] = { value: value, ts: ts }
flow.set("lastSeen", lastSeen)

// ============================================================
// PASO 2a: CONNECT MESSAGES — sin cambios respecto a versión anterior
// ============================================================
// (ver código JS del commit fix(nodered): corregir BUG-1/2/3 + LIMIT-2/4)

// ============================================================
// PASO 2b: RAW TELEMETRY — sin cambios
// ============================================================

// ============================================================
// PASO 3: SNAPSHOT + ML dispatch (extrae .value del nuevo shape)
// ============================================================
if expectedTags configurado:
    missing = expectedTags.filter(t => !(t in lastSeen))
    if missing.length === 0:
        snapshot = {}
        for each t in expectedTags:
            snapshot[t] = lastSeen[t].value     // nuevo: .value
        construir inferenceMsgs (connect + telemetry) hacia inference-input
        si mlUrl: construir mlMsg con payload {ts, sensors: snapshot}
    else:
        warmup = {missing: N, total: M}

return [[...connectMsgs, mqttMsg, ...inferenceMsgs], mlMsg, ack]
```

En **§D.4.1 — Notas operacionales**, añadir un nuevo apartado al final:

```markdown
8. **Ventana de validación de `ts` (LIMIT-4)**. El rango aceptable es
   `[now-30d, now+5min]` respecto al reloj del host de NR. La cota
   inferior tolera store-and-forward de hasta 30 días; la superior
   absorbe clock skew moderado. `ts` fuera de rango se rechaza con
   `400 ts outside acceptable window`. Para replayear dumps antiguos
   hay que desplazarlos temporalmente antes (ver
   `simulator/opc_client_v2.py --shift-to-now`).

9. **Compat del state `lastSeen` tras redeploy**. Si queda un
   `lastSeen` en flow context con la forma vieja (`{tag: value}`), el
   siguiente bundle que incluya ese tag sobreescribe la entrada con
   la forma nueva (`{tag: {value, ts}}`). Para tags que no vuelvan a
   llegar, `lastSeen[t].value` sería `undefined` (forma vieja) y el
   snapshot contendría `undefined`. Mitigación: tras un redeploy que
   toque el function node, ejecutar
   `POST /admin/clear-expected-tags` (limpia EXPECTED_TAGS + lastSeen).
   La suite pytest lo hace via el autouse fixture `clean_state`.
```

- [ ] **Step 2: Actualizar `FINDINGS-v2-pipeline-reliability.md` §9 Historial**

Localizar `## 9. Historial` (final del documento). Añadir una nueva fila a la tabla:

```markdown
| 2026-04-17 | David Palazon / Claude | Cierre de la matriz: BUG-1/2/3 y LIMIT-2/4 corregidos en `fn_main` (ver commit `fix(nodered): corregir BUG-1/2/3 + LIMIT-2/4`). Suite pytest de 22 tests en `tests/integration/test_pipeline_v2.py` valida el resultado. LIMIT-1/3/5 consolidados como asunciones en `docs/contracts/ml-inference.md` y `opc-ingest.md` sin cambios de código |
```

- [ ] **Step 3: Commit**

```bash
git add docs/architecture/PLAN-001.md docs/architecture/FINDINGS-v2-pipeline-reliability.md
git commit -m "$(cat <<'EOF'
docs(architecture): actualizar PLAN-001 §D.4 y cerrar FINDINGS-v2

- PLAN-001 §D.4: pseudocódigo con nuevo orden de validación (body → ts → window → values)
  y nueva forma de lastSeen = {tag: {value, ts}}. §D.4.1 nuevas notas 8/9
  sobre ventana de ts y compat del state en redeploy.
- FINDINGS-v2 §9: entrada fechada cerrando la matriz de bugs corregidos.
EOF
)"
```

---

## Task 11: Runbook F1 (multi-rate burst, manual)

**Files:**
- Create: `docs/testing/runbooks/v2-smoke-f1-multirate-burst.md`

- [ ] **Step 1: Crear el directorio y el runbook**

```bash
mkdir -p docs/testing/runbooks
```

Contenido de `docs/testing/runbooks/v2-smoke-f1-multirate-burst.md`:

```markdown
# Runbook F1 — Smoke multi-rate burst (manual)

> **Tipo:** smoke test probabilístico (no assertions estrictas). Complementa la suite pytest automatizada (`tests/integration/`) cubriendo el caso **F1** del findings v2 que por naturaleza no es determinista (LIMIT-5: posibles pérdidas bajo QoS 1 + burst sub-segundo).

---

## Objetivo

Observar el comportamiento del pipeline v2 bajo un burst multi-rate realista (cadencias heterogéneas ~1 POST/s con bundles de cardinalidad variable), reportando métricas cualitativas de pérdida.

---

## Prerrequisitos

- Stack Docker arriba (`docker compose up -d`).
- Mock ML corriendo en el host (o servicio ML real reachable desde NR).
- `EXPECTED_TAGS` configurado con los tags que planea usar el burst.
- Herramienta `jq` y `curl` disponibles.

---

## Ejecución

### 1. Generar carga

Script sugerido (guardar como `/tmp/f1_burst.sh`):

```bash
#!/bin/bash
NR_URL="${NR_URL:-http://localhost:1880}"
BASE_TS=$(date +%s%3N)

# 30 heart_only (1 tag cada uno, cadencia ~1/s)
for i in $(seq 1 30); do
    TS=$((BASE_TS + i * 1000))
    curl -s -X POST "$NR_URL/api/opc-ingest" \
        -H "Content-Type: application/json" \
        -d "{\"ts\": $TS, \"values\": {\"Heart_Bit\": $i}}" > /dev/null &
done

# 6 ea_only (1 tag cada uno, cadencia ~1/5s)
for i in $(seq 1 6); do
    TS=$((BASE_TS + i * 5000))
    curl -s -X POST "$NR_URL/api/opc-ingest" \
        -H "Content-Type: application/json" \
        -d "{\"ts\": $TS, \"values\": {\"EA_1\": $((i * 100))}}" > /dev/null &
done

# 3 full_scan (27 tags cada uno, cadencia ~1/10s)
for i in $(seq 1 3); do
    TS=$((BASE_TS + i * 10000))
    # Body con 27 tags arbitrarios
    VALUES=$(jq -nc '[range(27)] | map({("TAG_" + (. | tostring)): .}) | add')
    curl -s -X POST "$NR_URL/api/opc-ingest" \
        -H "Content-Type: application/json" \
        -d "{\"ts\": $TS, \"values\": $VALUES}" > /dev/null &
done

wait
echo "Burst completado: 39 POSTs enviados (30 heart + 6 ea + 3 full)"
```

Lanzar:
```bash
chmod +x /tmp/f1_burst.sh
time /tmp/f1_burst.sh
```

### 2. Métricas a recoger

**En TB** (vía `GET /api/plugins/telemetry/DEVICE/<id>/values/timeseries`):
- Puntos persistidos para `Heart_Bit` en la ventana `[BASE_TS, BASE_TS + 35000]`. Esperado: 30.
- Puntos persistidos para `EA_1` en `[BASE_TS, BASE_TS + 35000]`. Esperado: 6.
- Puntos persistidos en `inference-input` en la misma ventana. Esperado: 39 (si EXPECTED_TAGS cubre todos los tags usados).

**En mock ML** (contador de POSTs recibidos):
- Esperado: 39 inferencias.

### 3. Criterio de aceptación

- Pérdida ≤15% en cualquiera de las tres métricas → **smoke OK** (acordado como trade-off aceptable para burst no productivo, ver FINDINGS-v2 §LIMIT-5).
- Pérdida >15% → investigar: ¿QoS 1 bajo sesión clean? ¿Pool MQTT de NR saturado? ¿Rate limit en mock ML?

### 4. Reportar

Documentar el resultado en un issue/ticket con:
- Timestamp del run.
- Pérdida observada por métrica.
- Logs relevantes de NR (`docker logs` o debug sidebar).
- Cambios en la config desde el último run (si los hay).

---

## Notas

- El régimen OPC-UA productivo es **~0,03 POSTs/s** (1 cada 34 s). Este burst ~1,3 POSTs/s está ~40× por encima — explícitamente no productivo.
- La asimetría esperada (más pérdida en heart que en full_scan) es consistente con el cuello MQTT: más mensajes pequeños son más sensibles a ACK drops bajo sesión clean (LIMIT-5).
- Si este smoke empieza a fallar recurrentemente, reconfigurar el nodo `mqtt-broker` de NR con `cleansession: false` + `reconnectPeriod: 1000` para una sesión persistente.
```

- [ ] **Step 2: Commit**

```bash
git add docs/testing/runbooks/v2-smoke-f1-multirate-burst.md
git commit -m "$(cat <<'EOF'
docs(testing): añadir runbook F1 multi-rate burst (smoke manual)

Cubre el test probabilístico F1 del findings v2 (LIMIT-5: pérdidas QoS 1
bajo burst sub-segundo) como complemento a la suite pytest determinista.
Criterio de aceptación: pérdida ≤15% en las tres métricas (TB raw,
inference-input, mock ML) — trade-off aceptable para régimen no productivo.
EOF
)"
```

---

## Task 12: Verificación final end-to-end

- [ ] **Step 1: Correr toda la suite una última vez**

```bash
pytest tests/integration/ -v
```

Expected: **26 case runs PASS, 0 FAIL** (22 tests lógicos, con F5 parametrizado contando 5).

- [ ] **Step 2: Verificar el log de commits**

```bash
git log --oneline -10
```

Expected: los 7 commits del plan en orden:

```
<hash> docs(testing): añadir runbook F1 multi-rate burst
<hash> docs(architecture): actualizar PLAN-001 §D.4 y cerrar FINDINGS-v2
<hash> docs(contracts): alinear opc-ingest + ml-inference + ml-writeback con v2 post-fix
<hash> fix(nodered): corregir BUG-1/2/3 + LIMIT-2/4 en fn_main
<hash> feat(simulator): añadir flag --shift-to-now para replay de dumps históricos
<hash> test(integration): suite de regresión v2 — Grupos A/B/C/E/F2-F6 (22 casos, RED antes del fix)
<hash> chore(tests): añadir harness de integración v2 (pytest, fixtures, mock ML)
```

- [ ] **Step 3: Verificar que no hay archivos huérfanos sin trackear**

```bash
git status
```

Expected: `working tree clean` (salvo los archivos previos al inicio de la sesión que seguían untracked, si los dejó el estado inicial del repo).

- [ ] **Step 4: Ejecutar runbook F1 (opcional, informe)**

Seguir el runbook en `docs/testing/runbooks/v2-smoke-f1-multirate-burst.md`. Documentar el resultado en este ticket como comentario final (no bloquea el cierre si pérdida ≤15%).

---

## Criterios de cierre de sesión (recap)

1. ✅ `pytest tests/integration/ -v` → **22/22 GREEN** (26 case runs contando parametrizados).
2. ✅ 7 commits en orden visibles en `git log`.
3. ✅ Runbook F1 ejecutado y reportado cualitativamente.
4. ✅ Contratos (`docs/contracts/*.md`) reflejan comportamiento post-fix.
5. ✅ Spec en `docs/superpowers/specs/2026-04-17-v2-pipeline-reliability-fixes-design.md` (commiteado al inicio de la sesión, no cambia).

---

## Referencias

- Spec de esta sesión: `docs/superpowers/specs/2026-04-17-v2-pipeline-reliability-fixes-design.md`
- Findings origen: `docs/architecture/FINDINGS-v2-pipeline-reliability.md`
- Arquitectura: `docs/architecture/PLAN-001.md` §D.4
- ADR-003 (pipeline v2 NR + Gateway MQTT)
- Contratos: `docs/contracts/opc-ingest.md`, `ml-inference.md`, `ml-writeback.md`
