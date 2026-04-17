# `onboard_client_v2.py` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement `deploy/onboard_client_v2.py` — CLI Python single-file that provisions a client's TB profiles/devices, configures NR, runs smoke tests, and writes `.env` secrets per service — replacing the ad-hoc `/tmp/fase3_exec.py`.

**Architecture:** Monolithic Python script (`deploy/onboard_client_v2.py`) driven by a YAML manifest per client (`deploy/clients/<CLIENT>.yaml`) and env vars for TB/NR URLs + admin credentials. Outputs `.env` files in `deploy/secrets/<CLIENT>/` (gitignored) consumable by ML and airtrace services via Docker compose `env_file:`. Idempotent, fail-fast, exit codes categorized.

**Tech Stack:** Python 3.9+, `requests` (HTTP), `PyYAML` (manifest loading). No test framework dependency (MVP per spec §10). Manual verification per task against a live TB+NR stack.

**Spec reference:** [docs/superpowers/specs/2026-04-17-onboard-client-v2-design.md](../specs/2026-04-17-onboard-client-v2-design.md)

**Prerequisites for executing this plan:**

- Running TB CE 4.1 on `http://localhost:9090` (or override via `TB_URL`).
- Running Node-RED on `http://localhost:1880` with `flows.json` deployed (admin endpoints `/admin/set-expected-tags` + `/admin/set-ml-url` available). Verify: `curl -sf http://localhost:1880/admin/get-expected-tags`.
- `TB_ADMIN_PASSWORD` exported (default TB CE: `tenant`).
- Python 3.9+, `pip install requests pyyaml`.
- Reference ad-hoc script `/tmp/fase3_exec.py` still accessible (source of truth for API body shapes).

---

## File structure

Created in this plan (UCAM repo paths):

```
deploy/
├── onboard_client_v2.py           [NEW]   CLI monolítico (~450 líneas esperadas)
├── clients/                        [NEW]   manifests committeados
│   └── FR_ARAGON.yaml              [NEW]   primer manifest (27 tags)
├── secrets/                        [NEW]   gitignored, creado por el script en runtime
├── requirements.txt                [NEW]   requests>=2.28, pyyaml>=6.0
└── README.md                       [MODIFIED]   sección "onboard_client_v2.py — Testing Instructions"

.gitignore                          [MODIFIED]   añade deploy/secrets/
```

Unchanged (v1 legacy coexiste):

```
deploy/env_client.py               (v1 orquestador)
deploy/1_*.py  2_*.py  3_*.py  4_*.py   (v1 scripts numerados)
deploy/APIThingsboard.py            (v1 helpers — NO importado por v2)
deploy/Client.json  ESAMUR/  Plantillas/   (v1 data)
```

Responsibility of `onboard_client_v2.py` (single file, organized by sections):

1. CLI arg parsing + env var reading (§6 del spec)
2. Manifest loading + validation (§5)
3. TB REST helpers: login, profiles, devices, credentials, telemetry, timeseries
4. NR admin helpers: set-expected-tags, set-ml-url, clear-ml-url
5. Secrets rendering + secure file writing
6. Phase orchestrator (`main()` — 7 phases per §7)

---

## Task 1 — Scaffolding: CLI stub, manifest, gitignore

**Files:**
- Create: `deploy/onboard_client_v2.py`
- Create: `deploy/clients/FR_ARAGON.yaml`
- Create: `deploy/requirements.txt`
- Modify: `.gitignore`

- [ ] **Step 1: Create `deploy/requirements.txt`**

```
requests>=2.28
pyyaml>=6.0
```

- [ ] **Step 2: Append to root `.gitignore`**

```bash
# Append if not already present — verify first:
grep -q "deploy/secrets/" .gitignore || echo "deploy/secrets/" >> .gitignore
```

Verify: `grep "deploy/secrets" .gitignore` prints the line.

- [ ] **Step 3: Create `deploy/onboard_client_v2.py` stub**

```python
#!/usr/bin/env python3
"""onboard_client_v2.py — provisioning pipeline v2 para clientes UCAM.

Spec: docs/superpowers/specs/2026-04-17-onboard-client-v2-design.md
"""
import argparse
import sys

# ============================================================================
# Exit codes (spec §6.4)
# ============================================================================
EXIT_OK = 0
EXIT_UNEXPECTED = 1
EXIT_BAD_INPUT = 2
EXIT_EXTERNAL = 3
EXIT_SMOKE_FAILED = 4


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
    print(f"[stub] manifest={args.manifest} dry_run={args.dry_run} force={args.force}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Create `deploy/clients/FR_ARAGON.yaml` with the 27 tags**

Obtén la lista canónica de tags desde NR (es la verdad operacional — fueron configurados a mano en Fase 3):

```bash
mkdir -p deploy/clients
TAGS_JSON=$(curl -s http://localhost:1880/admin/get-expected-tags)
echo "$TAGS_JSON" | python3 -m json.tool
```

Expected: JSON con `expectedCount: 27`, campo `expectedTags` conteniendo exactamente 27 strings.

Genera el YAML desde ese JSON (one-shot, sin copy-paste manual):

```bash
python3 <<'PYEOF' > deploy/clients/FR_ARAGON.yaml
import json, subprocess, textwrap
raw = subprocess.check_output(["curl", "-s", "http://localhost:1880/admin/get-expected-tags"])
tags = json.loads(raw)["expectedTags"]
assert len(tags) == 27, f"expected 27 tags, got {len(tags)}"
print(textwrap.dedent(f"""\
# Cliente: FR_ARAGON — EDAR Francisco (Aragón)
# Tags: {len(tags)} — fuente: NR /admin/get-expected-tags al momento de generación
# Ver docs/architecture/PLAN-001.md §Fase 3
client:
  id: FR_ARAGON
  name: "EDAR Francisco (Aragón)"
  description: "Planta piloto v2"

sensors:
  expected_tags:"""))
for t in tags:
    print(f"    - {t}")
print("""
ml_inference:
  url: http://ml-classical:5000/api/inference""")
PYEOF
```

Verify: `wc -l deploy/clients/FR_ARAGON.yaml` debe ser ~35 líneas (9 header + 27 tags + 3 ml_inference).

- [ ] **Step 5: Verify the CLI stub runs**

Run: `python3 deploy/onboard_client_v2.py --help`

Expected output contains `--manifest`, `--dry-run`, `--force`, `--verbose`, and exits 0.

Run: `python3 deploy/onboard_client_v2.py --manifest deploy/clients/FR_ARAGON.yaml`

Expected: `[stub] manifest=deploy/clients/FR_ARAGON.yaml dry_run=False force=False`, exit 0.

- [ ] **Step 6: Commit**

```bash
git add deploy/onboard_client_v2.py deploy/clients/FR_ARAGON.yaml deploy/requirements.txt .gitignore
git commit -m "feat(deploy): scaffold onboard_client_v2.py stub + FR_ARAGON manifest"
```

---

## Task 2 — Manifest loading + validation

**Files:**
- Modify: `deploy/onboard_client_v2.py` (add load/validate functions)

- [ ] **Step 1: Verify the failing behavior (no loader yet)**

Run: `python3 -c "from pathlib import Path; import sys; sys.path.insert(0, 'deploy'); from onboard_client_v2 import load_manifest; print(load_manifest(Path('deploy/clients/FR_ARAGON.yaml')))"`

Expected: `ImportError: cannot import name 'load_manifest'`.

- [ ] **Step 2: Implement manifest load + validation**

Add to `deploy/onboard_client_v2.py` (below the Exit codes section):

```python
import re
from pathlib import Path
from typing import Any

import yaml

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
```

- [ ] **Step 3: Verify loading the real FR_ARAGON manifest**

Run: `python3 -c "from pathlib import Path; import sys; sys.path.insert(0, 'deploy'); from onboard_client_v2 import load_manifest; m = load_manifest(Path('deploy/clients/FR_ARAGON.yaml')); print('OK:', m['client']['id'], len(m['sensors']['expected_tags']), 'tags')"`

Expected: `OK: FR_ARAGON 27 tags`.

- [ ] **Step 4: Verify rejection of invalid manifests (inline cases)**

Run inline test with a few malformed cases:

```bash
python3 <<'EOF'
import sys
from pathlib import Path
sys.path.insert(0, 'deploy')
from onboard_client_v2 import load_manifest, ManifestError
import tempfile

cases = [
    ("lowercase id", "client: {id: fr_aragon, name: X}\nsensors: {expected_tags: [A]}"),
    ("missing tags",  "client: {id: FOO, name: X}\nsensors: {expected_tags: []}"),
    ("dup tag",       "client: {id: FOO, name: X}\nsensors: {expected_tags: [A, A]}"),
    ("bad url",       "client: {id: FOO, name: X}\nsensors: {expected_tags: [A]}\nml_inference: {url: ftp://x}"),
]
for name, yml in cases:
    with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
        f.write(yml)
        p = Path(f.name)
    try:
        load_manifest(p)
        print(f"FAIL (no error raised): {name}")
    except ManifestError as e:
        print(f"OK: {name} → {e}")
EOF
```

Expected: 4 lines `OK: <case> → manifest: ...`.

- [ ] **Step 5: Commit**

```bash
git add deploy/onboard_client_v2.py
git commit -m "feat(deploy): add YAML manifest loader with schema validation"
```

---

## Task 3 — Env var reading + wire manifest into main()

**Files:**
- Modify: `deploy/onboard_client_v2.py`

- [ ] **Step 1: Add env var reader**

Add below the manifest validation section:

```python
import os

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
```

- [ ] **Step 2: Wire manifest + env into main()**

Replace the stub `main()` with:

```python
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
    print(f"[stub] env tb={env['tb_url']} nr={env['nr_url']}")
    return EXIT_OK
```

- [ ] **Step 3: Verify missing password → exit 2**

Run: `unset TB_ADMIN_PASSWORD; python3 deploy/onboard_client_v2.py --manifest deploy/clients/FR_ARAGON.yaml; echo "exit=$?"`

Expected: `[✗] env: TB_ADMIN_PASSWORD is required (not set)`, `exit=2`.

- [ ] **Step 4: Verify happy path prints summary**

Run: `export TB_ADMIN_PASSWORD=tenant; python3 deploy/onboard_client_v2.py --manifest deploy/clients/FR_ARAGON.yaml`

Expected: two lines with `[✓] manifest:` and `[stub] env tb=`.

- [ ] **Step 5: Commit**

```bash
git add deploy/onboard_client_v2.py
git commit -m "feat(deploy): add env var reader and wire manifest loading into main()"
```

---

## Task 4 — TB login helper

**Files:**
- Modify: `deploy/onboard_client_v2.py`

- [ ] **Step 1: Add TB helpers section with login**

Add below env section:

```python
import requests

# ============================================================================
# TB REST helpers
# ============================================================================

HTTP_TIMEOUT = 10


class ExternalError(RuntimeError):
    """Raised when an external system (TB or NR) fails."""


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
```

- [ ] **Step 2: Wire login into main()**

Replace the last line of `main()` (`return EXIT_OK`) with:

```python
    # Phase 2b: TB login
    try:
        jwt = tb_login(env["tb_url"], env["tb_user"], env["tb_password"])
    except ExternalError as e:
        print(f"[✗] {e}", file=sys.stderr)
        return EXIT_EXTERNAL
    print(f"[✓] TB login: {env['tb_url']} (user={env['tb_user']})")
    return EXIT_OK
```

- [ ] **Step 3: Verify happy path**

Run: `export TB_ADMIN_PASSWORD=tenant; python3 deploy/onboard_client_v2.py --manifest deploy/clients/FR_ARAGON.yaml`

Expected: last line is `[✓] TB login: http://localhost:9090 (user=tenant@thingsboard.org)`, exit 0.

- [ ] **Step 4: Verify 401 handling**

Run: `TB_ADMIN_PASSWORD=wrong python3 deploy/onboard_client_v2.py --manifest deploy/clients/FR_ARAGON.yaml; echo "exit=$?"`

Expected: `[✗] TB login: 401 Unauthorized`, `exit=3`.

- [ ] **Step 5: Verify unreachable handling**

Run: `TB_URL=http://localhost:9999 python3 deploy/onboard_client_v2.py --manifest deploy/clients/FR_ARAGON.yaml; echo "exit=$?"`

Expected: `[✗] TB login: unreachable (ConnectionError)`, `exit=3`.

- [ ] **Step 6: Commit**

```bash
git add deploy/onboard_client_v2.py
git commit -m "feat(deploy): add TB login helper with error mapping to exit codes"
```

---

## Task 5 — Phase 3: Ensure 4 profiles (idempotente)

**Files:**
- Modify: `deploy/onboard_client_v2.py`

- [ ] **Step 1: Add profile helpers**

Add to the TB helpers section:

```python
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
```

- [ ] **Step 2: Wire into main()**

Replace the current tail of `main()` with:

```python
    # Phase 3: ensure profiles
    try:
        profile_ids = ensure_profiles(env["tb_url"], jwt)
    except ExternalError as e:
        print(f"[✗] {e}", file=sys.stderr)
        return EXIT_EXTERNAL
    return EXIT_OK
```

- [ ] **Step 3: Verify idempotence with a clean run**

Before running, optionally delete the 2 non-auto-created profiles via TB UI or API (for a clean test). In a fresh state:

Run: `python3 deploy/onboard_client_v2.py --manifest deploy/clients/FR_ARAGON.yaml`

Expected: `[=]` on `sensor_planta` and `inference_input` (auto-created by NR in Fases 2.1 and 2.4), `[✓]` on `inference_results` and `blockchain_anchor` if they don't exist, or `[=]` if they do.

- [ ] **Step 4: Verify second run is fully idempotent**

Run the same command again.

Expected: all 4 profiles show `[=]`, no `[✓]`.

- [ ] **Step 5: Verify in TB UI**

Open `http://localhost:9090` → Profiles → Device Profiles. Confirm the 4 names are present.

- [ ] **Step 6: Commit**

```bash
git add deploy/onboard_client_v2.py
git commit -m "feat(deploy): implement Fase 3 — idempotent profile creation"
```

---

## Task 6 — Phase 4: Ensure 2 writeback devices + capture tokens

**Files:**
- Modify: `deploy/onboard_client_v2.py`

- [ ] **Step 1: Add device helpers**

Add to TB helpers:

```python
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
```

- [ ] **Step 2: Wire into main()**

Append to `main()` before `return EXIT_OK`:

```python
    # Phase 4: ensure writeback devices + capture tokens
    try:
        devices = ensure_writeback_devices(env["tb_url"], jwt, client, profile_ids, args.force)
    except ExternalError as e:
        print(f"[✗] {e}", file=sys.stderr)
        return EXIT_EXTERNAL
```

- [ ] **Step 3: Verify clean-slate creation (if devices don't exist)**

Optionally: via TB UI delete `ml-inference-FR_ARAGON` and `airtrace-anchor-FR_ARAGON` first.

Run: `python3 deploy/onboard_client_v2.py --manifest deploy/clients/FR_ARAGON.yaml`

Expected: two `[✓] device  ml-inference-FR_ARAGON ...` and `airtrace-anchor-FR_ARAGON ...` lines.

- [ ] **Step 4: Verify idempotence**

Re-run the same command.

Expected: two `[=] device  ... existed` lines. Same token prefixes as before.

- [ ] **Step 5: Commit**

```bash
git add deploy/onboard_client_v2.py
git commit -m "feat(deploy): implement Fase 4 — idempotent writeback devices with token capture"
```

---

## Task 7 — Phase 5: Configure Node-RED (expected_tags + ml_url)

**Files:**
- Modify: `deploy/onboard_client_v2.py`

- [ ] **Step 1: Add NR helpers**

Add a new section below TB helpers:

```python
# ============================================================================
# NR admin helpers (spec §7 Fase 5)
# ============================================================================


def nr_set_expected_tags(url: str, tags: list[str]) -> None:
    r = requests.post(
        f"{url}/admin/set-expected-tags",
        json={"tags": tags},
        timeout=HTTP_TIMEOUT,
    )
    if r.status_code != 200:
        raise ExternalError(f"NR set-expected-tags: HTTP {r.status_code}: {r.text[:200]}")


def nr_set_ml_url(url: str, ml_url: str) -> None:
    r = requests.post(
        f"{url}/admin/set-ml-url",
        json={"url": ml_url},
        timeout=HTTP_TIMEOUT,
    )
    if r.status_code != 200:
        raise ExternalError(f"NR set-ml-url: HTTP {r.status_code}: {r.text[:200]}")


def nr_clear_ml_url(url: str) -> None:
    r = requests.post(
        f"{url}/admin/clear-ml-url",
        timeout=HTTP_TIMEOUT,
    )
    if r.status_code != 200:
        raise ExternalError(f"NR clear-ml-url: HTTP {r.status_code}: {r.text[:200]}")


def configure_nodered(url: str, manifest: dict) -> None:
    tags = manifest["sensors"]["expected_tags"]
    try:
        nr_set_expected_tags(url, tags)
    except requests.RequestException as e:
        raise ExternalError(f"NR unreachable: {e.__class__.__name__}")
    ml_url = (manifest.get("ml_inference") or {}).get("url")
    if ml_url:
        nr_set_ml_url(url, ml_url)
        print(f"[✓] NR configured:   EXPECTED_TAGS=[{len(tags)} tags], ML_INFERENCE_URL=<set>")
    else:
        nr_clear_ml_url(url)
        print(f"[✓] NR configured:   EXPECTED_TAGS=[{len(tags)} tags], ML_INFERENCE_URL=<cleared>")
```

- [ ] **Step 2: Wire into main()**

Append before `return EXIT_OK`:

```python
    # Phase 5: configure NR
    try:
        configure_nodered(env["nr_url"], manifest)
    except ExternalError as e:
        print(f"[✗] {e}", file=sys.stderr)
        return EXIT_EXTERNAL
```

- [ ] **Step 3: Verify NR state after running**

Run: `python3 deploy/onboard_client_v2.py --manifest deploy/clients/FR_ARAGON.yaml`

Expected line: `[✓] NR configured:   EXPECTED_TAGS=[27 tags], ML_INFERENCE_URL=<set>`.

Then:

```bash
curl -s http://localhost:1880/admin/get-expected-tags | python3 -m json.tool | head -5
curl -s http://localhost:1880/admin/get-ml-url
```

Expected: `expectedCount: 27`; ml_url shows the value from the manifest.

- [ ] **Step 4: Verify NR unreachable handling**

Run: `NR_URL=http://localhost:1899 python3 deploy/onboard_client_v2.py --manifest deploy/clients/FR_ARAGON.yaml; echo "exit=$?"`

Expected: `[✗] NR unreachable: ConnectionError`, `exit=3`.

- [ ] **Step 5: Commit**

```bash
git add deploy/onboard_client_v2.py
git commit -m "feat(deploy): implement Fase 5 — NR admin configuration"
```

---

## Task 8 — Phase 6: Smoke tests (POST + GET verify)

**Files:**
- Modify: `deploy/onboard_client_v2.py`

- [ ] **Step 1: Add smoke test helpers**

Add after NR helpers:

```python
import time

# ============================================================================
# Smoke tests (spec §7 Fase 6)
# ============================================================================


class SmokeError(RuntimeError):
    """Raised when smoke test verification fails."""


ML_SMOKE_BODY = {"score": 0.42, "model_version": "smoke-test", "latency_ms": 10, "status": "ok"}
AIRTRACE_SMOKE_BODY = {
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
        headers=_auth_headers(jwt),
        timeout=HTTP_TIMEOUT,
    )
    if r.status_code != 200:
        raise ExternalError(f"TB GET timeseries: HTTP {r.status_code}: {r.text[:200]}")
    return r.json()


def smoke_tests(tb_url: str, jwt: str, devices: dict) -> None:
    """Phase 6: POST fake telemetry + verify persistence."""
    ts = int(time.time() * 1000)
    # ML
    ml_values = dict(ML_SMOKE_BODY)
    tb_post_telemetry(tb_url, devices["ml"]["token"], ts, ml_values)
    # Airtrace
    at_values = dict(AIRTRACE_SMOKE_BODY, anchor_ts=ts + 15000)
    tb_post_telemetry(tb_url, devices["airtrace"]["token"], ts, at_values)
    # Wait + verify
    time.sleep(1)
    for role, expected in [("ml", list(ML_SMOKE_BODY.keys())), ("airtrace", list(AIRTRACE_SMOKE_BODY.keys()))]:
        data = tb_get_timeseries(tb_url, jwt, devices[role]["id"], expected, ts - 1, ts + 1)
        missing = [k for k in expected if not data.get(k)]
        if missing:
            raise SmokeError(f"smoke test {role}: keys missing after 1s: {missing}")
    print(f"[✓] smoke tests:     ML 200 OK (score persisted), airtrace 200 OK (tx_hash persisted)")
```

- [ ] **Step 2: Wire into main()**

Append before `return EXIT_OK`:

```python
    # Phase 6: smoke tests
    try:
        smoke_tests(env["tb_url"], jwt, devices)
    except ExternalError as e:
        print(f"[✗] {e}", file=sys.stderr)
        return EXIT_EXTERNAL
    except SmokeError as e:
        print(f"[✗] {e}", file=sys.stderr)
        return EXIT_SMOKE_FAILED
```

- [ ] **Step 3: Verify happy path**

Run: `python3 deploy/onboard_client_v2.py --manifest deploy/clients/FR_ARAGON.yaml`

Expected line: `[✓] smoke tests:     ML 200 OK ...`.

- [ ] **Step 4: Verify exit 4 on smoke failure (optional hardening)**

Para verificar que el manejo del exit code 4 funciona, lo más fiable es pedir a la smoke a buscar una key que no se postea. Aplica esta modificación temporal en `smoke_tests`:

```python
# En el bucle de verify, cambia expected para ml añadiendo una key ficticia:
for role, expected in [
    ("ml", list(ML_SMOKE_BODY.keys()) + ["nonexistent_force_fail"]),
    ("airtrace", list(AIRTRACE_SMOKE_BODY.keys())),
]:
```

Run: `python3 deploy/onboard_client_v2.py --manifest deploy/clients/FR_ARAGON.yaml; echo "exit=$?"`

Expected: `[✗] smoke test ml: keys missing after 1s: ['nonexistent_force_fail']`, `exit=4`.

**Importante:** revierte la modificación antes de commitear.

- [ ] **Step 5: Commit**

```bash
git add deploy/onboard_client_v2.py
git commit -m "feat(deploy): implement Fase 6 — smoke tests for ML and airtrace writebacks"
```

---

## Task 9 — Phase 7: Secrets file rendering + secure writing

**Files:**
- Modify: `deploy/onboard_client_v2.py`

- [ ] **Step 1: Add rendering + writing helpers**

Add a new section:

```python
import stat
from datetime import datetime, timezone

# ============================================================================
# Secrets (spec §8)
# ============================================================================

ENV_TEMPLATE = """\
# onboard_client_v2.py — generated {timestamp}
# DO NOT EDIT MANUALLY. Regenerate via deploy/onboard_client_v2.py.
# Deliver this file to the {service_team} team via secure channel.
CLIENT={client}
TB_HOST={tb_host}
TB_DEVICE_NAME={device_name}
TB_DEVICE_TOKEN={token}
"""


def render_env(client: str, tb_host: str, device_name: str, token: str, service_team: str) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return ENV_TEMPLATE.format(
        timestamp=now,
        service_team=service_team,
        client=client,
        tb_host=tb_host,
        device_name=device_name,
        token=token,
    )


def ensure_dir_secure(path: Path, mode: int = 0o700) -> None:
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(mode)


def secure_write(path: Path, content: str, mode: int = 0o600) -> None:
    # Open with mode 0o600 from the start to avoid a window where the file is world-readable
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(path, flags, mode)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(content)
    except Exception:
        if os.path.exists(path):
            os.unlink(path)
        raise
    os.chmod(path, mode)  # enforce even if file existed with laxer mode


def write_secrets(client: str, tb_host: str, devices: dict, secrets_root: Path) -> list[Path]:
    client_dir = secrets_root / client
    ensure_dir_secure(client_dir, 0o700)
    specs = [
        ("ml",       "ml-inference.env",      "ML service"),
        ("airtrace", "airtrace-anchor.env",   "airtrace service"),
    ]
    written = []
    for role, filename, team in specs:
        content = render_env(
            client=client,
            tb_host=tb_host,
            device_name=devices[role]["name"],
            token=devices[role]["token"],
            service_team=team,
        )
        target = client_dir / filename
        secure_write(target, content, 0o600)
        written.append(target)
        print(f"[✓] secrets written: {target} (0600)")
    return written
```

- [ ] **Step 2: Wire into main()**

Append before `return EXIT_OK`:

```python
    # Phase 7: write secrets
    secrets_root = Path("deploy/secrets")
    try:
        write_secrets(client, env["tb_url"], devices, secrets_root)
    except OSError as e:
        print(f"[✗] secrets: {e}", file=sys.stderr)
        return EXIT_UNEXPECTED
    print(f"\nonboarding complete. servicios ML y blockchain-api pueden arrancar "
          f"(env_file apunta a deploy/secrets/{client}/).")
```

- [ ] **Step 3: Verify secrets are written with correct permissions**

Run: `python3 deploy/onboard_client_v2.py --manifest deploy/clients/FR_ARAGON.yaml`

Then:

```bash
ls -la deploy/secrets/FR_ARAGON/
```

Expected: directory mode `drwx------` (0700), two files mode `-rw-------` (0600), named `ml-inference.env` and `airtrace-anchor.env`.

```bash
cat deploy/secrets/FR_ARAGON/ml-inference.env
```

Expected schema:
```
# onboard_client_v2.py — generated 2026-04-17T...Z
# DO NOT EDIT MANUALLY. ...
# Deliver this file to the ML service team via secure channel.
CLIENT=FR_ARAGON
TB_HOST=http://localhost:9090
TB_DEVICE_NAME=ml-inference-FR_ARAGON
TB_DEVICE_TOKEN=<20-char-alnum>
```

- [ ] **Step 4: Verify the token in the .env actually works against TB**

```bash
TOKEN=$(grep TB_DEVICE_TOKEN deploy/secrets/FR_ARAGON/ml-inference.env | cut -d= -f2)
curl -s -o /dev/null -w "%{http_code}\n" -X POST \
  "http://localhost:9090/api/v1/${TOKEN}/telemetry" \
  -H "Content-Type: application/json" \
  -d '{"ts": '$(date +%s%3N)', "values": {"verify": 1}}'
```

Expected: `200`.

- [ ] **Step 5: Verify idempotent re-write preserves token but updates timestamp**

Re-run the command. `diff` the file before/after: only the `generated` timestamp line changes.

```bash
cp deploy/secrets/FR_ARAGON/ml-inference.env /tmp/env_before
python3 deploy/onboard_client_v2.py --manifest deploy/clients/FR_ARAGON.yaml
diff /tmp/env_before deploy/secrets/FR_ARAGON/ml-inference.env
```

Expected: only the `# generated ...` line differs; `TB_DEVICE_TOKEN=` is identical.

- [ ] **Step 6: Commit**

```bash
git add deploy/onboard_client_v2.py
git commit -m "feat(deploy): implement Fase 7 — secrets .env rendering with secure file writes"
```

---

## Task 10 — End-to-end happy path + stdout format audit

**Files:**
- Modify: `deploy/onboard_client_v2.py` (minor polish if stdout doesn't match spec §6.5)

- [ ] **Step 1: Clean-state test**

Via TB UI delete `ml-inference-FR_ARAGON` and `airtrace-anchor-FR_ARAGON`. Optionally delete the two non-auto profiles (`inference_results`, `blockchain_anchor`).

- [ ] **Step 2: Run from scratch and capture full stdout**

```bash
python3 deploy/onboard_client_v2.py --manifest deploy/clients/FR_ARAGON.yaml 2>&1 | tee /tmp/onboarding_output.txt
```

Expected stdout (order-sensitive, see spec §6.5):

```
[✓] manifest: deploy/clients/FR_ARAGON.yaml (client=FR_ARAGON, 27 tags)
[✓] TB login: http://localhost:9090 (user=tenant@thingsboard.org)
[=] profile sensor_planta           existed  id=...
[=] profile inference_input         existed  id=...
[✓] profile inference_results       created  id=...
[✓] profile blockchain_anchor       created  id=...
[✓] device  ml-inference-FR_ARAGON       created  token=...
[✓] device  airtrace-anchor-FR_ARAGON    created  token=...
[✓] NR configured:   EXPECTED_TAGS=[27 tags], ML_INFERENCE_URL=<set>
[✓] smoke tests:     ML 200 OK (score persisted), airtrace 200 OK (tx_hash persisted)
[✓] secrets written: deploy/secrets/FR_ARAGON/ml-inference.env (0600)
[✓] secrets written: deploy/secrets/FR_ARAGON/airtrace-anchor.env (0600)

onboarding complete. servicios ML y blockchain-api pueden arrancar (env_file apunta a deploy/secrets/FR_ARAGON/).
```

Verify exit code: `echo "exit=$?"` expects `exit=0`.

- [ ] **Step 3: Immediate re-run verifies idempotence**

```bash
python3 deploy/onboard_client_v2.py --manifest deploy/clients/FR_ARAGON.yaml
```

Expected: all `[=]` on profiles/devices, `[✓]` on NR config / smoke tests / secrets (those are overwrites and always show ✓).

- [ ] **Step 4: No code commit expected (audit only)**

If the stdout deviated from the spec in minor ways (alignment, spacing), fix `print()` format strings and commit as a polish commit. Otherwise, skip this step.

---

## Task 11 — `--dry-run` mode

**Files:**
- Modify: `deploy/onboard_client_v2.py`

- [ ] **Step 1: Implement dry-run branches**

At the top of `main()` after loading manifest and env, add a dry-run branch that exits early:

```python
    # --dry-run: validate + ping, no side effects
    if args.dry_run:
        print(f"[dry-run] manifest: {args.manifest} (valid)")
        try:
            jwt = tb_login(env["tb_url"], env["tb_user"], env["tb_password"])
            print(f"[dry-run] TB login: {env['tb_url']} OK")
        except ExternalError as e:
            print(f"[dry-run] {e}", file=sys.stderr)
            return EXIT_EXTERNAL
        try:
            r = requests.get(f"{env['nr_url']}/admin/get-expected-tags", timeout=HTTP_TIMEOUT)
            r.raise_for_status()
            print(f"[dry-run] NR ping:  {env['nr_url']} OK")
        except requests.RequestException as e:
            print(f"[dry-run] NR unreachable: {e.__class__.__name__}", file=sys.stderr)
            return EXIT_EXTERNAL
        existing = {p["name"] for p in tb_list_profiles(env["tb_url"], jwt)}
        would_create_profiles = [p for p in REQUIRED_PROFILES if p not in existing]
        would_create_devices = []
        for name in [f"ml-inference-{client}", f"airtrace-anchor-{client}"]:
            if not tb_get_device_by_name(env["tb_url"], jwt, name):
                would_create_devices.append(name)
        tags = manifest["sensors"]["expected_tags"]
        ml_url = (manifest.get("ml_inference") or {}).get("url")
        ml_action = "set-ml-url" if ml_url else "clear-ml-url"
        print(f"[dry-run] would create: {len(would_create_profiles)} profiles: {would_create_profiles}")
        print(f"[dry-run] would create: {len(would_create_devices)} devices: {would_create_devices}")
        print(f"[dry-run] would configure NR: set-expected-tags ({len(tags)}), {ml_action}")
        print(f"[dry-run] would write: deploy/secrets/{client}/*.env")
        print("\nno side effects performed. run without --dry-run to apply.")
        return EXIT_OK
```

Place this right after the `print(f"[✓] manifest: ...")` line, before Phase 2b (TB login) — but since dry-run does its own login, rearrange so dry-run branch happens after manifest load + env read, replacing the normal flow.

- [ ] **Step 2: Verify `--dry-run` doesn't write anything**

```bash
rm -rf /tmp/check_secrets_before
cp -r deploy/secrets /tmp/check_secrets_before 2>/dev/null || mkdir /tmp/check_secrets_before

python3 deploy/onboard_client_v2.py --manifest deploy/clients/FR_ARAGON.yaml --dry-run

diff -r /tmp/check_secrets_before deploy/secrets
```

Expected: no diff (or "only the files that already existed" — no new files).

- [ ] **Step 3: Verify `--dry-run` exit 0 on happy path**

Run: `python3 deploy/onboard_client_v2.py --manifest deploy/clients/FR_ARAGON.yaml --dry-run; echo "exit=$?"`

Expected output matches spec §6.5 dry-run example; `exit=0`.

- [ ] **Step 4: Commit**

```bash
git add deploy/onboard_client_v2.py
git commit -m "feat(deploy): add --dry-run mode (validate + ping, no side effects)"
```

---

## Task 12 — `--force` rotation

**Files:**
- Modify: `deploy/onboard_client_v2.py`

**Note:** the `tb_rotate_credentials` function and `force` branch in `ensure_writeback_devices` were added in Task 6. This task validates the rotation path end-to-end.

- [ ] **Step 1: Capture current tokens**

```bash
OLD_ML_TOKEN=$(grep TB_DEVICE_TOKEN deploy/secrets/FR_ARAGON/ml-inference.env | cut -d= -f2)
OLD_AT_TOKEN=$(grep TB_DEVICE_TOKEN deploy/secrets/FR_ARAGON/airtrace-anchor.env | cut -d= -f2)
echo "OLD_ML=$OLD_ML_TOKEN OLD_AT=$OLD_AT_TOKEN"
```

- [ ] **Step 2: Run with `--force`**

```bash
python3 deploy/onboard_client_v2.py --manifest deploy/clients/FR_ARAGON.yaml --force
```

Expected: two `[↻] device  ... rotated  token=...` lines, smoke tests still pass.

- [ ] **Step 3: Verify tokens changed**

```bash
NEW_ML_TOKEN=$(grep TB_DEVICE_TOKEN deploy/secrets/FR_ARAGON/ml-inference.env | cut -d= -f2)
NEW_AT_TOKEN=$(grep TB_DEVICE_TOKEN deploy/secrets/FR_ARAGON/airtrace-anchor.env | cut -d= -f2)
[ "$OLD_ML_TOKEN" != "$NEW_ML_TOKEN" ] && echo "ML rotated OK" || echo "ML NOT rotated"
[ "$OLD_AT_TOKEN" != "$NEW_AT_TOKEN" ] && echo "AT rotated OK" || echo "AT NOT rotated"
```

Expected: `ML rotated OK`, `AT rotated OK`.

- [ ] **Step 4: Verify old token is invalidated**

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X POST \
  "http://localhost:9090/api/v1/${OLD_ML_TOKEN}/telemetry" \
  -H "Content-Type: application/json" \
  -d '{"ts": '$(date +%s%3N)', "values": {"test": 1}}'
```

Expected: `401`.

- [ ] **Step 5: Verify new token works**

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X POST \
  "http://localhost:9090/api/v1/${NEW_ML_TOKEN}/telemetry" \
  -H "Content-Type: application/json" \
  -d '{"ts": '$(date +%s%3N)', "values": {"test": 1}}'
```

Expected: `200`.

- [ ] **Step 6: Verify re-run without `--force` keeps new token stable**

```bash
python3 deploy/onboard_client_v2.py --manifest deploy/clients/FR_ARAGON.yaml
# (no --force)
```

Expected: `[=] device  ... existed  token=...` with same prefixes as NEW_*_TOKEN.

- [ ] **Step 7: No new code commit if Task 6 already wired `--force`**

If a bug surfaced in Task 6's rotation logic, fix and commit:
```bash
git add deploy/onboard_client_v2.py
git commit -m "fix(deploy): <describe rotation fix>"
```

---

## Task 13 — Update `deploy/README.md` with Testing Instructions

**Files:**
- Create or Modify: `deploy/README.md`

- [ ] **Step 1: Check current state**

```bash
ls deploy/README.md 2>/dev/null && echo "exists" || echo "create new"
```

- [ ] **Step 2: Add/update the file**

If it doesn't exist, create `deploy/README.md`. If it exists, append the new section at the end. Content of the new section:

````markdown
## onboard_client_v2.py — Testing Instructions

Pipeline v2 de onboarding para clientes. Spec: [`docs/superpowers/specs/2026-04-17-onboard-client-v2-design.md`](../docs/superpowers/specs/2026-04-17-onboard-client-v2-design.md).

### 1. Prerequisites

- TB running: `curl -sf http://localhost:9090/login >/dev/null && echo OK`
- NR running with v2 flow: `curl -sf http://localhost:1880/admin/get-expected-tags && echo OK`
- Python deps: `pip install -r deploy/requirements.txt`
- Admin password exported:
  ```bash
  export TB_ADMIN_PASSWORD=tenant   # default TB CE
  ```

### 2. Dry-run (no side effects)

```bash
python3 deploy/onboard_client_v2.py --manifest deploy/clients/FR_ARAGON.yaml --dry-run
# Expected: exit 0, stdout shows "[dry-run] would create: ..."
```

Verify no files written:
```bash
ls deploy/secrets/ 2>/dev/null || echo "no secrets dir yet (OK)"
```

### 3. Happy path

```bash
python3 deploy/onboard_client_v2.py --manifest deploy/clients/FR_ARAGON.yaml
# Expected: exit 0, stdout ends with "onboarding complete"
ls -la deploy/secrets/FR_ARAGON/
# Expected: 2 files mode -rw-------
```

### 4. Idempotency

```bash
python3 deploy/onboard_client_v2.py --manifest deploy/clients/FR_ARAGON.yaml
# Expected: exit 0, stdout shows [=] on every profile and device (no [✓] created)
```

### 5. Verify TB state

```bash
JWT=$(curl -s -X POST http://localhost:9090/api/auth/login \
    -H "Content-Type: application/json" \
    -d '{"username":"tenant@thingsboard.org","password":"'$TB_ADMIN_PASSWORD'"}' | python3 -c "import sys, json; print(json.load(sys.stdin)['token'])")
curl -s "http://localhost:9090/api/deviceProfiles?pageSize=100&page=0" \
    -H "X-Authorization: Bearer $JWT" | python3 -m json.tool | grep '"name"'
# Expected: contains sensor_planta, inference_input, inference_results, blockchain_anchor
```

### 6. Verify NR state

```bash
curl -s http://localhost:1880/admin/get-expected-tags | python3 -m json.tool
# Expected: expectedCount matches manifest (27 for FR_ARAGON)
curl -s http://localhost:1880/admin/get-ml-url
# Expected: matches manifest.ml_inference.url
```

### 7. Force rotation

```bash
OLD=$(grep TB_DEVICE_TOKEN deploy/secrets/FR_ARAGON/ml-inference.env | cut -d= -f2)
python3 deploy/onboard_client_v2.py --manifest deploy/clients/FR_ARAGON.yaml --force
NEW=$(grep TB_DEVICE_TOKEN deploy/secrets/FR_ARAGON/ml-inference.env | cut -d= -f2)
[ "$OLD" != "$NEW" ] && echo "rotated OK"
# Expected: "rotated OK"

# Verify old invalidated
curl -s -o /dev/null -w "%{http_code}\n" -X POST \
  "http://localhost:9090/api/v1/${OLD}/telemetry" \
  -H "Content-Type: application/json" -d '{"ts":0,"values":{}}'
# Expected: 401
```

### Exit codes (spec §6.4)

| Code | Significado |
|---|---|
| `0` | OK |
| `1` | Error inesperado (bug) |
| `2` | Input inválido (manifest o env var) |
| `3` | Sistema externo falló (TB/NR) |
| `4` | Smoke test falló |

### Consumo del `.env` por servicios downstream

Docker compose directiva `env_file:`:
```yaml
ml-classical:
  env_file: ./deploy/secrets/FR_ARAGON/ml-inference.env
blockchain-api:
  env_file: ./deploy/secrets/FR_ARAGON/airtrace-anchor.env
```

Docker inyecta `TB_HOST`, `TB_DEVICE_TOKEN`, etc. como env vars del contenedor. El código del servicio compone `${TB_HOST}/api/v1/${TB_DEVICE_TOKEN}/telemetry`.
````

- [ ] **Step 3: Commit**

```bash
git add deploy/README.md
git commit -m "docs(deploy): add Testing Instructions section for onboard_client_v2.py"
```

---

## Task 14 — Final audit + mark ad-hoc script obsolete

**Files:**
- Modify: `docs/architecture/PLAN-001.md` (optional — add a note)

- [ ] **Step 1: Verify the ad-hoc script is no longer needed**

```bash
diff <(python3 /tmp/fase3_exec.py 2>/dev/null || echo "no longer runnable OK") <(python3 deploy/onboard_client_v2.py --manifest deploy/clients/FR_ARAGON.yaml)
```

Expected: the v2 output is a superset of the ad-hoc's responsibilities (adds NR config + secrets file).

- [ ] **Step 2: Optionally delete the ad-hoc script**

`/tmp/fase3_exec.py` lives outside the repo; it will be wiped by any reboot. No action needed in git.

If you want to mark it as superseded in the conversation / runbook:

```bash
mv /tmp/fase3_exec.py /tmp/fase3_exec.py.DEPRECATED_see_onboard_client_v2
```

- [ ] **Step 3: Optionally add a note in PLAN-001.md**

Find in `docs/architecture/PLAN-001.md` the "Resultado Fase 3" section and add a sentence referencing the replacement:

```markdown
> **Update 2026-04-17:** el script ad-hoc `/tmp/fase3_exec.py` ha sido sustituido por
> `deploy/onboard_client_v2.py`, que añade configuración de NR, smoke tests integrados
> y entrega de tokens vía `deploy/secrets/<CLIENT>/*.env`. Ver spec:
> [docs/superpowers/specs/2026-04-17-onboard-client-v2-design.md](...).
```

- [ ] **Step 4: Final commit**

```bash
git add docs/architecture/PLAN-001.md
git commit -m "docs(architecture): note that /tmp/fase3_exec.py is superseded by onboard_client_v2.py"
```

- [ ] **Step 5: Run the full procedural test suite from `deploy/README.md` §Testing Instructions**

End-to-end verification that the MVP is demoable:

1. Dry-run → exit 0, no files
2. Happy path → exit 0, 2 `.env` files mode 0600
3. Idempotency → `[=]` en todos los pasos, tokens unchanged
4. TB state → 4 profiles visibles
5. NR state → expectedCount = 27
6. Force rotation → token cambia, viejo invalidado, nuevo válido

Si todos pasan, el MVP está listo para presentación a INCIBE.

---

## Post-implementation checklist

- [ ] `git log --oneline` muestra ~13 commits con tipos `feat(deploy)`, `docs(deploy)`, `docs(architecture)`
- [ ] `grep -r "TODO\|FIXME\|XXX" deploy/onboard_client_v2.py` devuelve 0 líneas
- [ ] `python3 deploy/onboard_client_v2.py --help` imprime todos los flags con descripciones
- [ ] `cat .gitignore | grep deploy/secrets` presente
- [ ] El fichero `deploy/secrets/FR_ARAGON/ml-inference.env` existe y es gitignored (`git check-ignore deploy/secrets/FR_ARAGON/ml-inference.env` devuelve la ruta)
- [ ] El spec `docs/superpowers/specs/2026-04-17-onboard-client-v2-design.md` no requiere cambios tras la implementación (si sí — actualizar y commitear)
