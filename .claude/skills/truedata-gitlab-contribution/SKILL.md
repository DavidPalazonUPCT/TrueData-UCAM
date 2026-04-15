---
name: truedata-gitlab-contribution
description: >
  Guides the execution of UCAM's contribution to the TRUEDATA GitLab monorepo.
  Covers porting ThingsBoard + Node-RED + deploy automation from the UCAM repo
  to the GitLab scaffold as three sequential Merge Requests (MR-1 infrastructure,
  MR-2 deploy pipeline, MR-3 simulator + OPC contract).

  Use this skill whenever the user mentions: TRUEDATA GitLab contribution,
  porting files to GitLab, MR-1/MR-2/MR-3, base module contribution,
  sanitization of UCAM code, deploy pipeline porting, OPC Client contract,
  simulator porting, CONTRIBUTING.md compliance, pre-MR checklist,
  secret scanning, or any task referencing the contribution implementation plan.

  Also trigger when the user asks about: "next task in the plan", "where are we
  in the contribution", "run the pre-MR checklist", "sanitize this file",
  "scan for secrets", or references Phase 0, Pre-Flight, or any numbered
  task like "Task 1.2" or "Task 2.3".
---

# TRUEDATA GitLab Contribution Skill

## Purpose

Execute UCAM's three-MR contribution to the TRUEDATA GitLab monorepo,
porting ThingsBoard + Node-RED services, a deploy automation pipeline,
and a DEMO simulator from the private UCAM repo to the shared GitLab scaffold.

## When to use

- Executing any task from the contribution implementation plan
- Porting files between the UCAM source repo and the GitLab target
- Sanitizing code (removing secrets, replacing hardcoded values with env vars)
- Running pre-MR validation (secret scan, compose check, commit format)
- Writing module READMEs that comply with CONTRIBUTING.md's 10-section schema
- Managing the git workflow (branching, conventional commits, rebasing, MR creation)

## Critical context

### Two repositories

| Role | Path | Purpose |
|---|---|---|
| **Source** (read-only) | `/mnt/c/Users/david/TrueData/TrueData-UCAM` | UCAM's working repo. Contains secrets in history. |
| **Target** (MRs go here) | `/mnt/c/Users/david/TrueData/truedata-gitlab` | INCIBE monorepo scaffold. |

### Architecture reality

The scaffold assumes MQTT + Node-RED as primary hub. Reality is **100% HTTP REST**:
- Node-RED is a post-TB aggregator (called by TB Rule Chains), not a primary hub
- Simulator POSTs directly to TB (bypasses Node-RED) — documented divergence for DEMO
- OPC Client will POST to Node-RED `/api/opc-ingest` in production (Neoradix, pending)

### MR sequence

1. **MR-1** `feature/base/thingsboard-nodered-setup` — TB + Node-RED + docker-compose.override.yml
2. **MR-2** `feature/base/deploy-automation` — 5-script deploy pipeline + TEMPLATE client
3. **MR-3** `feature/base/opc-client-contract` — shared/simulator + OPC contract stub

Each MR depends on the previous being merged (or at least approved).

---

## Workflow: executing a task

### Step 1: Locate yourself in the plan

Read the implementation plan to identify which phase/task you're on.
The plan lives at the path the user provides (or search for it).
Phases run in order: Phase 0 → Pre-Flight → MR-1 → MR-2 → MR-3.

### Step 2: Before any MR work, re-read CONTRIBUTING.md

```bash
cat /mnt/c/Users/david/TrueData/truedata-gitlab/CONTRIBUTING.md
```

CONTRIBUTING.md is the **absolute source of truth**. If this skill and
CONTRIBUTING.md conflict, CONTRIBUTING.md wins. Update the plan, never deviate.

### Step 3: Execute the task

Follow the plan's step-by-step instructions. For each step:
- Run the command shown
- Verify the expected output
- If the step involves creating/modifying files, apply sanitization rules (see below)
- If the step involves a commit or push, **ask for user confirmation first**

### Step 4: After completing a task, validate

Run the appropriate checks from `scripts/` before moving on:
- After any file port: `python scripts/sanitize_check.py <file>`
- After any commit: `bash scripts/validate_commit_msg.sh`
- Before any MR push: `bash scripts/pre_mr_checklist.sh`

---

## Sanitization rules

Every file ported from UCAM → GitLab MUST be sanitized. Run `scripts/sanitize_check.py`
on each ported file. The rules are:

| Pattern in source | Replacement in GitLab |
|---|---|
| `http://localhost:9090` hardcoded | `${TB_URL:-http://thingsboard:9090}` or `os.environ["TB_URL"]` |
| `http://localhost:1880` hardcoded | `${NODE_RED_URL:-http://node-red:1880}` or `os.environ["NODE_RED_URL"]` |
| `http://172.25.0.x:...` hardcoded IPs | Service hostnames (`thingsboard`, `node-red`, `postgres`) |
| `tenant@thingsboard.org` / `tenant` | `${TB_ADMIN_USER}` / `${TB_ADMIN_PASSWORD}` env vars |
| `tenant` / `tenantairtrace` NR login | `${NODE_RED_USER}` / `${NODE_RED_PASSWORD}` env vars |
| `credentialSecret: "airtrace"` | `credentialSecret: process.env.NODE_RED_CREDENTIAL_SECRET` |
| AWS keys `"X"` in compose | **Delete** (unused) |
| `deploy/MCT/*.csv` or `deploy/ESAMUR/*.csv` | **Never copy.** Use `deploy/TEMPLATE/` |
| `Credenciales.txt` references | **Don't copy the referencing file** |

For Python files, the standard sanitization header is:

```python
import os
from pathlib import Path

TB_URL = os.environ.get("TB_URL", "http://localhost:9090")
NODE_RED_URL = os.environ.get("NODE_RED_URL", "http://localhost:1880")
TB_ADMIN_USER = os.environ.get("TB_ADMIN_USER", "tenant@thingsboard.org")
TB_ADMIN_PASSWORD = os.environ["TB_ADMIN_PASSWORD"]  # required, fail fast
```

For detailed rules and edge cases, read `references/sanitization-rules.md`.

---

## Git workflow rules

### Branch naming
```
feature/base/<short-description>   # hyphen-separated, lowercase
```

### Commit format
```
<type>(<module>): <subject>

<optional body>
```
Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`
Module: `base`, `shared`, or omit for root-level changes.

### MR description template
```
## What
## Why
## How to Test
## Files Changed
## Notes
```

### Confirmation gates

**Always ask the user before:**
- `git commit` — show the message and staged files
- `git push` — show the branch and remote
- `git rebase` — warn about potential conflicts
- Opening an MR — show the title and description draft

---

## Subagent delegation

Some tasks can run in parallel via `--fork-session`. Here's the parallelization map:

### MR-1: can parallelize
- Task 1.2 (thingsboard/) and Task 1.3 (node-red/) are independent → fork both
- Task 1.5 (.env.example) depends on 1.2+1.3 → sequential after both complete

### MR-2: mostly sequential
- Task 2.2 (APIThingsboard.py) must come first (other scripts import it)
- Task 2.3 (numbered scripts) can be forked per-file IF sanitization is consistent
- Task 2.4 (Plantillas) and Task 2.5 (TEMPLATE) are independent → fork both

### MR-3: can parallelize
- Task 3.2 (simulator) and Task 3.4+3.5 (opc-ingest + contract) are independent → fork

When delegating to a subagent, include in the prompt:
1. The specific task from the plan (copy the full task text)
2. The sanitization rules table
3. The CONTRIBUTING.md commit format
4. The instruction to NOT commit — return the work for the master to review and commit

---

## Files excluded from porting

Never port these (they are RUIDO or out of scope):
- `src/` (ML pipelines — `ml-classical` is standby)
- Root Dockerfiles (`Dockerfile`, `DockerfileETL`, etc.)
- `locustfile.py`, `entrypoint.sh`, `fetch_tokens_remote.py`
- `INJECTION_SETUP.md`, `SIMULATION_GUIDE.md`, `images/`
- `docs/openapi.yaml`, `swagger.html`, `redoc.html`
- `system_sizing/`
- `deploy/MCT/`, `deploy/ESAMUR/`, `deploy/t`, `deploy/ParametrosConfiguracion.txt`

---

## README 10-section schema

Every module README must cover (per CONTRIBUTING.md):

1. **Purpose** — what this module does
2. **Responsible partner** — who owns it
3. **Technologies** — stack with versions
4. **Input / Output** — data contracts
5. **Integration points** — how other modules connect
6. **Architecture** — directory tree + component diagram
7. **How to build** — docker build command
8. **How to run standalone** — docker compose up with env setup
9. **Environment variables** — table with var, default, required, description
10. **Testing** — smoke test commands + expected output
11. **TODO / Known limitations** — roadmap items

---

## Scripts reference

All scripts live in `scripts/` within this skill directory. Copy them to the
working directory before use, or reference them by absolute path.

| Script | Purpose | When to run |
|---|---|---|
| `sanitize_check.py` | Scan a file for unsanitized patterns | After porting any file |
| `secret_scan.sh` | Scan git diff for leaked secrets | Before every commit |
| `pre_mr_checklist.sh` | Full pre-MR validation suite | Before pushing any MR branch |
| `validate_commit_msg.sh` | Check commit message format | After every commit |

---

## Quick command reference

```bash
# Sanitization check on a ported file
python <skill>/scripts/sanitize_check.py base/deploy/APIThingsboard.py

# Secret scan on current diff vs main
bash <skill>/scripts/secret_scan.sh

# Full pre-MR checklist
bash <skill>/scripts/pre_mr_checklist.sh

# Validate last commit message
bash <skill>/scripts/validate_commit_msg.sh

# Docker Compose syntax check (base standalone)
NODE_RED_CREDENTIAL_SECRET=dummy docker compose -f base/docker-compose.override.yml config > /dev/null

# Docker Compose syntax check (full stack with demo)
SIMULATOR_DEVICE_TOKEN=x NODE_RED_CREDENTIAL_SECRET=x docker compose --profile base --profile demo config > /dev/null
```
