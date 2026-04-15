# Sanitization Rules Reference

Complete reference for sanitizing files ported from UCAM (`TrueData-UCAM`) to
GitLab (`truedata-gitlab`). The `sanitize_check.py` script automates detection;
this document provides the context and fix patterns.

## Table of contents

1. [Python files (.py)](#python-files)
2. [JavaScript files (.js)](#javascript-files)
3. [YAML / Docker Compose files](#yaml-docker-compose)
4. [JSON templates (Plantillas/)](#json-templates)
5. [Markdown / README files](#markdown-readme)
6. [Edge cases and exceptions](#edge-cases)

---

## Python files

### URL replacement pattern

Every Python file that makes HTTP calls to TB or Node-RED needs this block
near the top (after stdlib imports, before any function definitions):

```python
import os
from pathlib import Path

TB_URL = os.environ.get("TB_URL", "http://localhost:9090")
NODE_RED_URL = os.environ.get("NODE_RED_URL", "http://localhost:1880")
```

Then replace all occurrences:
- `"http://localhost:9090"` → `TB_URL`
- `"http://localhost:1880"` → `NODE_RED_URL`
- `"http://172.25.0.2:9090"` (or any IP) → `TB_URL`
- `"http://172.25.0.3:1880"` (or any IP) → `NODE_RED_URL`

**Watch out for f-strings and string concatenation:**
```python
# BEFORE (bad):
url = f"http://localhost:9090/api/v1/{token}/telemetry"
# AFTER (good):
url = f"{TB_URL}/api/v1/{token}/telemetry"

# BEFORE (bad):
url = "http://localhost:9090" + "/api/auth/login"
# AFTER (good):
url = TB_URL + "/api/auth/login"
```

### Credential replacement pattern

For admin credentials used in API authentication:

```python
TB_ADMIN_USER = os.environ.get("TB_ADMIN_USER", "tenant@thingsboard.org")
TB_ADMIN_PASSWORD = os.environ["TB_ADMIN_PASSWORD"]  # Required, fail fast
```

Note: `TB_ADMIN_PASSWORD` has NO default — the script should fail immediately
if the password isn't provided. This is intentional: we never want a ported
script to silently use "tenant" as the password.

For sysadmin credentials (used in initial setup scripts like `1_Configuracion_General.py`):

```python
TB_SYSADMIN_USER = os.environ.get("TB_SYSADMIN_USER", "sysadmin@thingsboard.org")
TB_SYSADMIN_PASSWORD = os.environ["TB_SYSADMIN_PASSWORD"]
```

### Client directory pattern

Scripts that reference `deploy/{ClientName}/` paths:

```python
CLIENT_DIR = Path(os.environ.get("CLIENT_DIR", Path(__file__).parent / "TEMPLATE"))
```

Then replace:
- `f"deploy/{cliente}/DeviceImport.csv"` → `CLIENT_DIR / "DeviceImport.csv"`
- `f"deploy/{cliente}/Client.json"` → `CLIENT_DIR / "Client.json"`

### Node-RED credentials in Python

For scripts that authenticate with Node-RED admin API:

```python
NODE_RED_USER = os.environ.get("NODE_RED_USER", "admin")
NODE_RED_PASSWORD = os.environ["NODE_RED_PASSWORD"]  # Required
```

---

## JavaScript files

### settings.js (Node-RED)

The main file to sanitize is `base/node-red/settings.js`.

```javascript
// BEFORE:
credentialSecret: "airtrace",

// AFTER:
credentialSecret: process.env.NODE_RED_CREDENTIAL_SECRET,
```

```javascript
// BEFORE:
adminAuth: {
    type: "credentials",
    users: [{
        username: "tenant",
        password: "$2b$08$...",  // bcrypt of "tenantairtrace"
        ...
    }]
}

// AFTER:
adminAuth: {
    type: "credentials",
    users: [{
        username: process.env.NODE_RED_USER || "admin",
        password: process.env.NODE_RED_PASSWORD_HASH || "",
        permissions: "*"
    }]
}
```

---

## YAML / Docker Compose

### Environment variable syntax

In `docker-compose.override.yml` and the root `docker-compose.yml`:

```yaml
# Use ${VAR:-default} for optional vars with defaults
TB_URL: ${TB_URL:-http://thingsboard:9090}

# Use ${VAR:?error message} for required vars (fail fast)
NODE_RED_CREDENTIAL_SECRET: ${NODE_RED_CREDENTIAL_SECRET:?NODE_RED_CREDENTIAL_SECRET must be set}
```

### Service hostnames

Inside the Docker Compose network, services reference each other by service name,
not by IP or localhost:

- `http://thingsboard:9090` (not `http://localhost:9090` or `http://172.25.0.2:9090`)
- `http://node-red:1880` (not `http://localhost:1880`)
- `postgres:5432` (not `localhost:5432`)

### AWS keys

The source compose has placeholder AWS keys:

```yaml
# BEFORE:
AWS_ACCESS_KEY_ID: "X"
AWS_SECRET_ACCESS_KEY: "X"

# AFTER:
# DELETE ENTIRELY — not used by UCAM contribution
```

---

## JSON templates

### Plantillas/ directory

JSON templates under `deploy/Plantillas/` use placeholder variables that
the deploy scripts interpolate at runtime. These should NOT contain real tokens.

Check for:
- `"accessToken": "<real token>"` → should be `"${accessTokenVar}"` or absent
- `"http://localhost:9090"` → should be `"${ROOT_ThingsBoard}"`
- `"http://localhost:1880"` → should be `"${ROOT_NodeRed}"`

### Client.json

The TEMPLATE `Client.json` must be generic:

```json
{
  "Client": "TEMPLATE",
  "Model": "M3"
}
```

Never use real client names (MCT, ESAMUR, AirTrace).

---

## Markdown / README

READMEs can contain example URLs like `http://localhost:9090` in documentation
context — this is fine and expected. The sanitize checker skips these in
non-strict mode.

However, READMEs should:
- Never contain real device tokens
- Never reference `deploy/MCT/` or `deploy/ESAMUR/` as if they exist
- Always use `TEMPLATE` as the example client name
- Use `${VAR}` notation when showing env var usage

---

## Edge cases

### Comments containing old patterns

Comments that explain what was replaced are fine:

```python
# Previously hardcoded as http://localhost:9090, now read from env
TB_URL = os.environ.get("TB_URL", "http://localhost:9090")
```

The sanitize checker (non-strict mode) allows HIGH/MEDIUM patterns in comments.
CRITICAL patterns (actual secrets like "airtrace") are flagged even in comments.

### Default values in os.environ.get()

Using `http://localhost:9090` as a default value in `os.environ.get()` is
intentional and correct — it lets developers run scripts outside Docker
(against a local TB instance). The sanitize checker accepts this pattern.

### Files that should NOT be sanitized

Some files are copied as-is because they're templates meant to be interpolated:
- `deploy/Plantillas/*.json` — contain `${variable}` placeholders, not hardcoded values
- `base/node-red/flows/opc-ingest.json` — Node-RED flow JSON with no secrets

### Multiple credential sets

The deploy pipeline uses two credential levels:
1. **Sysadmin** (`sysadmin@thingsboard.org`) — used only in `1_Configuracion_General.py`
   for global TB setup
2. **Tenant admin** (`tenant@thingsboard.org`) — used in all other scripts for
   client-scoped operations

Both need separate env vars. Don't collapse them into one.
