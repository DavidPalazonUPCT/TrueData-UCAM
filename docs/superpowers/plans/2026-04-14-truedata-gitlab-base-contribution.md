# TRUEDATA GitLab `base/` Contribution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship UCAM's ThingsBoard + Node-RED + deploy automation to the TRUEDATA GitLab monorepo as three focused Merge Requests, delivering a working DEMO stack (simulator-driven) with a clearly documented integration point where Neoradix can plug the real OPC Client later.

**Architecture:** Three sequential MRs into the GitLab `base/` module plus a minimal addition to `shared/`. MR-1 lands TB + Node-RED services (`base/thingsboard/`, `base/node-red/`) with a standalone `docker-compose.override.yml`. MR-2 lands the 5-script Python deploy pipeline under `base/deploy/` with a neutral `TEMPLATE/` client folder. MR-3 adds `shared/simulator/` behind a Docker Compose `demo` profile and documents the OPC Client HTTP contract (OPC → Node-RED → TB) with a skeleton flow in `base/node-red/flows/opc-ingest.json`.

**Tech Stack:** Docker Compose 2.x, ThingsBoard CE 3.6+, Node-RED 3.x, Python 3.9+ (`requests`, `pandas`), GitLab MR workflow.

**Living document:** This plan will iterate as other partners progress. MR-3 in particular may change if Libelium/AirTrace shift architectural assumptions (e.g., reintroduce MQTT).

---

## Non-Negotiable: CONTRIBUTING.md compliance

**`/mnt/c/Users/david/TrueData/truedata-gitlab/CONTRIBUTING.md` is the authoritative source of truth for every MR we open.** This plan implements its rules, but if the two ever conflict, **CONTRIBUTING.md wins** — update the plan, never deviate from CONTRIBUTING.md.

Every task, every commit, every MR must satisfy the full CONTRIBUTING.md checklist. The executor (subagent or human) **re-reads CONTRIBUTING.md at the start of each MR** and again before pushing the branch. The Self-Review Checklist at the bottom of this plan is the minimum bar — not a replacement for CONTRIBUTING.md.

### Rule → plan mapping

| CONTRIBUTING.md rule | Satisfied by |
|---|---|
| No direct commits to `main` | Every MR creates `feature/base/<descr>`; no task ever touches `main` directly |
| Branch naming `feature/<module>/<short-description>` | Tasks 1.1, 2.1, 3.1 (explicit branch names) |
| Rebase on `main` before MR | Tasks 1.8 Step 3, 2.8 Step 3, 3.8 Step 3 |
| `docker compose config` passes locally | Tasks 1.4 Step 2, 1.8 Step 2, 2.8 Step 2, 3.3 Step 4, 3.8 Step 2 |
| Module README covers 10 sections (purpose, partner, tech, I/O, integration, build, run, env vars, testing, TODO) | Task 1.7 (initial), 2.7 (onboarding), 3.6 (OPC integration) |
| `.env.example` updated when new env vars are introduced | Tasks 1.5, 2.3 (via deploy README), 3.3 Step 3 |
| `docker-compose.override.yml` per module for standalone dev | Task 1.4 |
| No hardcoded secrets / credentials in diff | Sanitization rules (Context section) + pre-commit hook (PF.2) + secret scans in 1.8/2.8/3.8 |
| Commit format `<type>(<module>): <subject>` with types `feat/fix/docs/refactor/test/chore` | Every commit message in the plan uses this format |
| MR description includes What / Why / How to Test / Files Changed / Notes | Tasks 1.9 Step 2, 2.8 Step 4, 3.8 Step 4 |
| Reviewer assigned (module maintainer) | Task 1.9 Step 3, same pattern in 2.8 and 3.8 |
| No force-push during review; address feedback with new commits | Task 1.9 Step 4 (and same pattern in 2/3) |
| Delete branch after merge | Post-MR hygiene — executor runs `git branch -d feature/base/<descr>` and `git push origin --delete feature/base/<descr>` after GitLab merges |

**If an executor finds a CONTRIBUTING.md rule this plan doesn't cover, STOP, update the plan, and only then resume the task.**

---

## Context (for an engineer with zero context)

### Two repositories

| Role | Path | Remote | Purpose |
|---|---|---|---|
| **Source** (read-only reference) | `/mnt/c/Users/david/TrueData/TrueData-UCAM` | `github.com/DavidPalazonUPCT/TrueData-UCAM` | UCAM's working repo, 3 years of code. **Contains secrets in history.** |
| **Target** (where MRs go) | `/mnt/c/Users/david/TrueData/truedata-gitlab` | `collab.libelium.com:46231/proyectos-europeos/truedata/truedata.git` | INCIBE monorepo scaffold with 5 module dirs + `shared/`. |

### Architectural reality vs scaffold

The scaffold's `base/README.md` presumes: (a) MQTT bus for inter-module communication, (b) Node-RED as ingestion hub, (c) OPC Client owned by Neoradix. Reality verified in code: (a) **100% HTTP REST, zero MQTT anywhere**, (b) Node-RED is a post-TB aggregator invoked by TB Rule Chains, (c) OPC Client exists only as a simulator (`src/dataloader/simulador_sensores.py`) that bypasses Node-RED and POSTs directly to TB. Team decision: keep HTTP, keep the simulator as DEMO, define the "intended" OPC Client flow via Node-RED for Neoradix to target.

### Topology today (verified)

```
Simulator ─POST /api/v1/{token}/telemetry─► ThingsBoard
                                                │ Rule Chain (TbRestApiCallNode)
                                                ▼
                              POST /endpoint/agregarXXX ─► Node-RED (agg 1s/5s/10s)
                                                ▼
                              POST /api/v1/{token}/telemetry ─► ThingsBoard
```

### Topology target for Neoradix (to be documented in MR-3)

```
OPC Client ─POST /api/opc-ingest─► Node-RED (opc-ingest flow)
                                        │ transform + auth
                                        ▼
                              POST /api/v1/{token}/telemetry ─► ThingsBoard
                                                                   │ Rule Chain unchanged
                                                                   ▼
                                                           Node-RED agg (unchanged)
```

### Contribution constraints (CONTRIBUTING.md, mandatory)

- No direct push to `main`. Everything via MR.
- Branch name: `feature/<module>/<short-description>`.
- Commit: `<type>(<module>): <subject>` with types `feat/fix/docs/refactor/test/chore`.
- Per-module README must cover: purpose, partner, tech, I/O, integration, build, run standalone, env vars, testing, TODO.
- Pre-MR: `docker compose config` passes, no hardcoded secrets, env vars documented.

### Sanitization rules (applied to every file ported from UCAM → GitLab)

| Anti-pattern (source repo) | Replacement (GitLab repo) |
|---|---|
| `http://localhost:9090` hardcoded | `${TB_URL:-http://thingsboard:9090}` env var |
| `http://localhost:1880` hardcoded | `${NODE_RED_URL:-http://node-red:1880}` env var |
| `http://172.25.0.x:...` hardcoded IPs | service hostnames (`thingsboard`, `node-red`, `postgres`) |
| `tenant@thingsboard.org` / `tenant` credentials | `${TB_ADMIN_USER}` / `${TB_ADMIN_PASSWORD}` env vars |
| `tenant` / `tenantairtrace` Node-RED login | `${NODE_RED_USER}` / `${NODE_RED_PASSWORD}` env vars |
| `credentialSecret: "airtrace"` in settings.js | `credentialSecret: process.env.NODE_RED_CREDENTIAL_SECRET` |
| AWS keys `"X"` in docker-compose.yml | **Delete** (unused by UCAM contribution) |
| Any `deploy/MCT/*.csv` or `deploy/ESAMUR/*.csv` | **Never copy.** Use `deploy/TEMPLATE/` with empty placeholders. |
| `Credenciales.txt` references in `locustfile.py` | **Don't copy `locustfile.py` at all.** |

### Files excluded from all three MRs (RUIDO / out of scope)

`src/` (ML pipelines — `ml-classical` module is standby), all root-level Dockerfiles (`Dockerfile`, `DockerfileETL`, `DockerfileInferenceCPU`, `DockerfileTrainPipeline`, `DockerfileTest`, `DockerfileEnvClient`), `locustfile.py`, `entrypoint.sh`, `fetch_tokens_remote.py` (offline recovery tool, not deploy), `INJECTION_SETUP.md`, `SIMULATION_GUIDE.md`, `images/`, `docs/openapi.yaml` / `swagger.html` / `redoc.html` (misaligned with code), `system_sizing/` (possible separate MR later, not in this plan), `deploy/MCT/`, `deploy/ESAMUR/`, `deploy/t`, `deploy/ParametrosConfiguracion.txt`, `deploy/2.2 Manual... .docx`.

---

## File Structure (target layout after all 3 MRs)

```
truedata-gitlab/
├── docker-compose.yml                         # MODIFY (MR-3: add demo profile)
├── .env.example                               # MODIFY (MR-1/2/3: add base + simulator vars)
├── base/
│   ├── README.md                              # REWRITE (MR-1 infra, MR-2 onboarding, MR-3 OPC contract)
│   ├── docker-compose.override.yml            # CREATE (MR-1)
│   ├── thingsboard/
│   │   ├── Dockerfile                         # CREATE (MR-1)
│   │   ├── config/                            # CREATE (MR-1, empty or minimal overrides)
│   │   │   └── .gitkeep
│   │   └── README.md                          # CREATE (MR-1)
│   ├── node-red/
│   │   ├── Dockerfile                         # CREATE (MR-1)
│   │   ├── settings.js                        # CREATE (MR-1, env-based secret)
│   │   ├── flows/
│   │   │   ├── .gitkeep                       # CREATE (MR-1)
│   │   │   └── opc-ingest.json                # CREATE (MR-3, skeleton flow)
│   │   └── README.md                          # CREATE (MR-1)
│   ├── deploy/
│   │   ├── APIThingsboard.py                  # PORT (MR-2)
│   │   ├── env_client.py                      # PORT (MR-2)
│   │   ├── 1_Configuracion_General.py         # PORT (MR-2)
│   │   ├── 1.1_Subir_Niveles_Criticidad_Inicial_Bulk.py  # PORT (MR-2)
│   │   ├── 2_Crear_Entorno_Cliente_ThingsBoard.py        # PORT (MR-2)
│   │   ├── 2.2_Crear_ETL_NodeRed_Cliente.py              # PORT (MR-2)
│   │   ├── 3_Solicitar_Niveles_Criticidad.py             # PORT (MR-2)
│   │   ├── 3.1_Modificar_Niveles_Criticidad.py           # PORT (MR-2)
│   │   ├── 4_Subir_thresholds.py                         # PORT (MR-2)
│   │   ├── Plantillas/                        # PORT (MR-2, JSON templates only, no tokens)
│   │   ├── TEMPLATE/                          # CREATE (MR-2, example empty client)
│   │   │   ├── Client.json
│   │   │   ├── DeviceImport.csv.example
│   │   │   ├── Niveles_de_Criticidad.csv.example
│   │   │   └── README.md
│   │   ├── requirements.txt                   # CREATE (MR-2, minimal deps)
│   │   └── README.md                          # CREATE (MR-2)
│   └── opc-client/
│       └── README.md                          # CREATE (MR-3, contract stub for Neoradix)
└── shared/
    └── simulator/
        ├── Dockerfile                         # CREATE (MR-3)
        ├── src/
        │   └── simulador_sensores.py          # PORT (MR-3)
        ├── data/
        │   └── .gitkeep                       # CREATE (MR-3)
        ├── requirements.txt                   # CREATE (MR-3)
        └── README.md                          # CREATE (MR-3)
```

---

## Phase 0: UCAM Baseline Audit + Verification (before touching anything)

**Location:** `/mnt/c/Users/david/TrueData/TrueData-UCAM` (source repo, not the GitLab clone).

**Goal:** Prove the current UCAM stack still works **before** any cleanup or porting, so we have a known-good reference point and a rollback tag if anything regresses later.

**Guiding principle for the whole Phase 0 + Pre-Flight block:** **maintain as much existing development as possible, modify only what is strictly necessary.** Default action for any file whose status is ambiguous is: leave it alone. Delete only (a) secrets, or (b) files whose junk status is unanimous. Everything else waits for explicit user confirmation.

### Task 0.1: Consolidate file inventory

**Files:** none (read-only)

- [ ] **Step 1: Re-confirm the classification from the earlier audit**

  The conversation that produced this plan contains a file-by-file inventory classifying each root element of the UCAM repo as SEÑAL-base, SEÑAL-sizing, SEÑAL-ml, RUIDO, or SECRETS. Re-read it and confirm it still matches the repo state (3 weeks can shift things).

  Run:
  ```bash
  cd /mnt/c/Users/david/TrueData/TrueData-UCAM
  ls -1 && echo "---" && ls -1 deploy/
  ```
  Cross-check against the audit. Flag any new/moved files.

- [ ] **Step 2: Verify the SECRETS list is still present in the repo**

  ```bash
  ls -la deploy/MCT/ deploy/ESAMUR/ 2>/dev/null | head -5
  test -f deploy/ParametrosConfiguracion.txt && echo "PRESENT: deploy/ParametrosConfiguracion.txt"
  test -f deploy/t && echo "PRESENT: deploy/t"
  test -f locustfile.py && echo "PRESENT: locustfile.py"
  ```
  Expected: outputs show which files still need to be removed in PF.4.

### Task 0.2: Create a baseline git tag (rollback safety)

**Files:** none (git metadata only)

- [ ] **Step 1: Confirm working tree is clean**

  Run: `cd /mnt/c/Users/david/TrueData/TrueData-UCAM && git status --short`
  Expected: empty output. If not, decide with user: commit the WIP, stash, or abort Phase 0.

- [ ] **Step 2: Tag the current HEAD**

  Run:
  ```bash
  git tag -a baseline-pre-contribution -m "Baseline before TRUEDATA GitLab contribution (plan 2026-04-14)"
  git tag -n baseline-pre-contribution
  ```
  Expected: tag listed with the annotation.

- [ ] **Step 3 (optional): Push the tag to GitHub**

  Run: `git push origin baseline-pre-contribution`
  Only if the user wants the tag on their remote. Local-only is fine too.

### Task 0.3: Verify the existing UCAM stack still runs

**Files:** none (runtime verification)

**Pre-requisite:** a populated `.env` at the UCAM repo root (or equivalent), Docker running, port 9090 and 1880 free.

- [ ] **Step 1: Validate root docker-compose syntax**

  Run:
  ```bash
  cd /mnt/c/Users/david/TrueData/TrueData-UCAM
  docker compose config > /tmp/compose-validation.txt 2>&1 && echo "SYNTAX OK" || echo "SYNTAX FAIL — see /tmp/compose-validation.txt"
  ```
  If FAIL: note the errors. The root compose may already be broken (the ML pipeline Dockerfiles it references might expect artifacts that don't exist in this checkout). Escalate to user before proceeding.

- [ ] **Step 2: Identify which services can run standalone**

  Run: `docker compose config --services`
  Expected: list of services. Identify TB + Node-RED (what we care about for contribution); ignore inference/ETL services (they depend on ML models that may not be present locally).

- [ ] **Step 3: Bring up only TB + Node-RED (+ Postgres if referenced)**

  Run:
  ```bash
  docker compose up -d thingsboard node-red 2>&1 | tail -20
  # If postgres is a separate service:
  docker compose up -d postgres 2>&1 | tail -5 || true
  ```
  Expected: containers start. If service names differ (e.g. `tb`, `nodered`), adapt and re-run.

- [ ] **Step 4: Wait for TB readiness (first boot can take 3–5 min)**

  Run:
  ```bash
  for i in {1..60}; do
    code=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:9090/api/auth/login 2>/dev/null || echo "000")
    if [ "$code" = "401" ] || [ "$code" = "200" ]; then
      echo "TB responding after ${i}0s (HTTP $code)"
      break
    fi
    sleep 10
  done
  ```
  Expected: "TB responding..." within 10 min. `401` is healthy (auth required). If timeout: TB may be stuck in DB migration — `docker compose logs thingsboard | tail -50`.

- [ ] **Step 5: Verify Node-RED**

  Run: `curl -sf http://localhost:1880/ -o /dev/null -w "%{http_code}\n"`
  Expected: `200` or `302`. If it fails: `docker compose logs node-red | tail -30`.

- [ ] **Step 6 (optional, high-value): Run the deploy pipeline against current `Client.json`**

  ```bash
  cd deploy
  # Use whatever env vars the current scripts expect; check ParametrosConfiguracion.txt if still present
  python env_client.py 2>&1 | tee /tmp/env-client-run.log | tail -40
  ```
  Expected: 5 scripts execute in order. Any error indicates a broken script we'd be porting as-is to GitLab — worth fixing here before porting. If it succeeds, we know the pipeline is still operational.

- [ ] **Step 7 (optional): Brief simulator smoke test**

  ```bash
  # Adjust --client and --device to the currently-configured client
  timeout 30 python src/dataloader/simulador_sensores.py --client ESAMUR --device "<an existing device name>" --delay 1.0 2>&1 | tail -20 || true
  ```
  Expected: HTTP 200 lines (telemetry accepted by TB). Auth/token errors indicate stale credentials in CSVs.

- [ ] **Step 8: Teardown**

  Run: `docker compose down`
  Expected: all containers stopped. Volumes intact (so next run is fast).

- [ ] **Step 9: Document the baseline verification outcome**

  Record in this plan's Appendix D (append to end of file) which steps passed or failed. If anything fundamental is broken:
  - **Option A:** fix it here, re-tag baseline, proceed
  - **Option B:** accept the broken state, document it, port the working parts only (skip the broken script in MR-2 and flag in the MR description)
  - **Option C:** pause Phase 0 and escalate to user

  Default preference: Option A for small fixes, Option C for anything ambiguous.

---

## Pre-Flight (local only, zero push to GitLab)

### Task PF.1: Verify both workspaces are ready

**Files:** none (read-only checks)

- [ ] **Step 1: Confirm source repo clean**

Run: `cd /mnt/c/Users/david/TrueData/TrueData-UCAM && git status --short`
Expected: empty output (clean working tree). If dirty, stash or commit before proceeding.

- [ ] **Step 2: Confirm GitLab clone fresh and on main**

Run: `cd /mnt/c/Users/david/TrueData/truedata-gitlab && git status --short && git branch --show-current && git log --oneline -3`
Expected: clean, on `main`, 1–3 commits from Libelium's scaffold.

- [ ] **Step 3: Verify authentication to GitLab still works**

Run: `cd /mnt/c/Users/david/TrueData/truedata-gitlab && git fetch origin`
Expected: successful fetch (no auth error). If fails: re-inject token into remote URL via `git remote set-url origin https://oauth2:<TOKEN>@collab.libelium.com:46231/...`.

### Task PF.2: Confirm no secrets leak into GitLab clone during work

**Files:**
- Create: `/mnt/c/Users/david/TrueData/truedata-gitlab/.git/hooks/pre-commit`

- [ ] **Step 1: Install a pre-commit hook that blocks committing obvious secrets**

Create `.git/hooks/pre-commit` with executable bit:

```bash
#!/usr/bin/env bash
# Block commits containing device access tokens or hardcoded creds
if git diff --cached | grep -E '(accessToken.*[A-Za-z0-9]{16,}|credentialSecret.*["'"'"']airtrace["'"'"']|AWS_ACCESS_KEY_ID.*["'"'"'][^X"'"'"'])' ; then
  echo "ERROR: staged content contains what looks like a secret. Abort."
  exit 1
fi
exit 0
```

Run: `chmod +x /mnt/c/Users/david/TrueData/truedata-gitlab/.git/hooks/pre-commit`
Expected: no output.

- [ ] **Step 2: Sanity test the hook**

Run:
```bash
cd /mnt/c/Users/david/TrueData/truedata-gitlab
echo 'credentialSecret: "airtrace"' > /tmp/leak.js
git add /tmp/leak.js 2>/dev/null || true
echo 'test' > leak-test.txt && git add leak-test.txt
```
Expected: `git add` succeeds for non-secret file. Now simulate secret:
```bash
echo 'accessToken: "KH40Iom8Mlnh6Hc3JyX0FAKE"' >> leak-test.txt
git add leak-test.txt
git commit -m "test"
```
Expected: hook **fails** with "ERROR: staged content contains what looks like a secret."

Cleanup:
```bash
git reset HEAD leak-test.txt && rm leak-test.txt
```

### Task PF.3 (user, offline): Rotate exposed credentials in production

**Files:** none in repo

- [ ] **Step 1: Rotate `credentialSecret` in any running Node-RED instance** that was set up with `credentialSecret: "airtrace"`. New value should be a cryptographically random string stored only in env var.

- [ ] **Step 2: If `deploy/MCT/DeviceimportCredentials_MCT.csv` or `deploy/ESAMUR/DeviceimportCredentials_ESAMUR.csv` contain tokens of **actually deployed** ThingsBoard devices**, revoke those tokens in TB and regenerate via `fetch_tokens_remote.py` against the running TB.

- [ ] **Step 3: Revoke the GitLab Personal Access Token shared earlier in the conversation** (glpat-7tSSnNd3arS4FRPZIWE1GW86MQp1OjF6CA.01.0y1z0186l). Generate a new one with `read_repository + write_repository` scopes and re-inject into the GitLab clone's remote URL.

**Note:** This task is executed by the user outside the agent flow. No code changes required.

Given that the MCT/ESAMUR tokens are lab-environment (not production), rotation here is **best-effort, not blocking**. It is still good hygiene but does not gate the plan.

### Task PF.4: Delete SECRETS and unambiguous junk from the UCAM repo (auto-execute)

**Location:** `/mnt/c/Users/david/TrueData/TrueData-UCAM` (source repo).

**Files to DELETE (Tier 1 — auto-execute, no user confirmation needed):**

| Path | Why it goes |
|---|---|
| `deploy/MCT/` | Contains real ThingsBoard device access tokens (lab, but still tokens in clear) |
| `deploy/ESAMUR/` | Idem |
| `deploy/ParametrosConfiguracion.txt` | Plaintext TB admin + Node-RED admin credentials |
| `deploy/t` | 1-character leftover file, no meaningful content |
| `locustfile.py` | Load test that references a `Credenciales.txt` file which is not (and should not be) present; test itself is not deliverable material |

**Everything else stays in UCAM.** In particular, we do NOT touch in this task:

- `src/` (ML pipelines — `ml-classical` is team-standby, not dead)
- `Dockerfile`, `DockerfileETL`, `DockerfileInferenceCPU`, `DockerfileTrainPipeline`, `DockerfileTest`, `DockerfileEnvClient` (ml pipeline Dockerfiles — standby)
- `docker-compose.yml` (root) — standby, paired with the above Dockerfiles
- `system_sizing/` (potential future contribution)
- `truedata-thingsboard/`, `truedata-nodered/`, `deploy/` (contents minus the Tier 1 deletions above)
- `fetch_tokens_remote.py` (operational tool)
- `README.md`, `DEPLOYMENT_GUIDE.md` (reference)
- `requirements.txt`, `.gitignore`, `.dockerignore`

- [ ] **Step 1: Create a dedicated cleanup branch in the UCAM repo**

  Run:
  ```bash
  cd /mnt/c/Users/david/TrueData/TrueData-UCAM
  git checkout -b chore/cleanup-pre-gitlab-contribution
  ```
  Expected: "Switched to a new branch..."

- [ ] **Step 2: List the files to be deleted (sanity check)**

  Run:
  ```bash
  ls -la deploy/MCT deploy/ESAMUR 2>/dev/null | head -20
  ls -la deploy/ParametrosConfiguracion.txt deploy/t locustfile.py 2>/dev/null
  ```
  Expected: each path either shows content (will be deleted) or `No such file` (already gone — fine).

- [ ] **Step 3: Delete with `git rm` (so git history records the removal)**

  Run:
  ```bash
  git rm -rf deploy/MCT deploy/ESAMUR 2>&1 | tail -5
  git rm -f deploy/ParametrosConfiguracion.txt deploy/t locustfile.py 2>&1 | tail -5
  ```
  For any path that doesn't exist, `git rm` will complain — ignore those errors (already removed).

- [ ] **Step 4: Verify no secrets remain in working tree**

  Run:
  ```bash
  grep -rnE 'accessToken.*[A-Za-z0-9]{16,}' . --include='*.csv' --include='*.txt' 2>/dev/null | head
  ls -la deploy/MCT deploy/ESAMUR 2>/dev/null || echo "CLEAN: secret dirs removed"
  ```
  Expected: grep returns nothing; ls shows "CLEAN".

- [ ] **Step 5: Commit the Tier 1 removal**

  Run:
  ```bash
  git commit -m "chore: remove secrets and unambiguous junk pre-GitLab contribution

- deploy/MCT/ and deploy/ESAMUR/ contained lab-env TB device access
  tokens in clear; they are regenerated by the deploy pipeline per
  client and should never be versioned.
- deploy/ParametrosConfiguracion.txt had plaintext admin creds.
- deploy/t was a 1-char leftover file.
- locustfile.py referenced a Credenciales.txt that is not in the repo
  and is not deliverable material.

All other files (including src/, ML Dockerfiles, system_sizing/,
fetch_tokens_remote.py, module directories) are intentionally kept —
ml-classical is standby, not removed. Reference baseline at tag
baseline-pre-contribution."
  ```
  Expected: commit succeeds.

- [ ] **Step 6: Offer history purge (optional, user decides)**

  The secrets are now removed from the working tree but **still present in git history**. To purge them from history entirely (required if this repo is or might become public; optional for a private repo with lab-only tokens):

  ```bash
  # DESTRUCTIVE — only if user confirms
  # Option A (local only, preserves other work):
  #   git filter-repo --path deploy/MCT --path deploy/ESAMUR --path deploy/ParametrosConfiguracion.txt --invert-paths --force
  # Option B (BFG repo cleaner):
  #   bfg --delete-folders MCT,ESAMUR --delete-files ParametrosConfiguracion.txt
  ```

  **Default: skip this step.** The user's repo is private on GitHub, tokens are lab, and history-rewriting has its own risks (force-push, breaks clones). Revisit only if the repo goes public.

### Task PF.5: Delete Tier 2 RUIDO (needs user confirmation before deletion)

**Files proposed for deletion (Tier 2):**

| Path | Why proposed | Risk of keeping | Risk of deleting |
|---|---|---|---|
| `entrypoint.sh` | Runs `pip freeze` at container runtime if `requirements.txt` is empty — antipattern | Zero (file just sits there) | Zero (nothing references it after ML Dockerfiles are removed from GitLab contribution scope; may still be referenced by UCAM-local Dockerfiles) |
| `INJECTION_SETUP.md` | Dev-only ad-hoc documentation of the simulator injection flow | Minor clutter | Lose a doc; content is superseded by `shared/simulator/README.md` in GitLab |
| `SIMULATION_GUIDE.md` | Dev-only ad-hoc documentation | Minor clutter | Same as above |
| `deploy/2.2 Manual para Configuración de Procesos ETL en Node-RED con ThingsBoard.docx` | Word doc superseded by `base/deploy/README.md` in GitLab | Minor clutter + binary in repo | Lose a doc; content captured in deploy/README |
| `docs/openapi.yaml` | OpenAPI spec that the audit flagged as misaligned with actual `inference.py` endpoints | Misleading stale doc | Lose a doc (can regenerate from code later) |
| `docs/swagger.html`, `docs/redoc.html` | Companion renderers for `docs/openapi.yaml` | Same as above | Same |
| `images/` | Screenshots; if referenced only by INJECTION_SETUP / SIMULATION_GUIDE which are being removed, they become orphaned | Disk space | Lose screenshots; check first if other kept docs reference them |

- [ ] **Step 1: Present the list to the user and get per-file or bulk confirmation**

  The executor (or human) asks the user:
  > "Tier 2 deletion candidates: `entrypoint.sh`, `INJECTION_SETUP.md`, `SIMULATION_GUIDE.md`, the `.docx` in `deploy/`, `docs/openapi.yaml` + `swagger.html` + `redoc.html`, and `images/` (if unreferenced). Delete all, delete a subset, or keep all?"

  Wait for explicit answer. Do not default-delete.

- [ ] **Step 2: Before deleting `images/`, check for references**

  Run:
  ```bash
  cd /mnt/c/Users/david/TrueData/TrueData-UCAM
  grep -rnE 'images/' --include='*.md' --include='*.rst' . 2>/dev/null | grep -v baseline-pre-contribution
  ```
  If the only references are from files about to be deleted, `images/` is orphaned → safe to delete. Otherwise, keep.

- [ ] **Step 3: Apply the user's decision with `git rm`**

  For each confirmed file:
  ```bash
  git rm -f <path>
  # For directories:
  git rm -rf <path>
  ```

- [ ] **Step 4: Commit Tier 2 removal (separate commit from PF.4)**

  Run:
  ```bash
  git commit -m "chore: remove stale dev-mode docs and misaligned API specs

Tier 2 cleanup per user review:
- <list the files actually deleted, tailored to the user's decision>

Kept: src/, ML Dockerfiles, docker-compose.yml, system_sizing/,
fetch_tokens_remote.py, README.md, DEPLOYMENT_GUIDE.md."
  ```

### Task PF.6: Re-verify UCAM stack after cleanup (regression check)

- [ ] **Step 1: Re-run Task 0.3 Steps 1–5**

  Same commands. Verify nothing regressed.

- [ ] **Step 2: Compare against baseline**

  If any step that passed in Task 0.3 now fails, we deleted something that mattered. Decision tree:
  - If the failure is clearly tied to a deleted file (e.g., deleted a script the compose file references) → revert that specific deletion, re-commit, re-verify.
  - If the failure is unrelated → note and continue.
  - If unclear → `git reset --hard baseline-pre-contribution` and start PF.4/PF.5 over with a narrower scope.

- [ ] **Step 3: Document outcome in Appendix D**

### Task PF.7: Update UCAM `.gitignore` to prevent RUIDO re-accumulation

**Files:**
- Modify: `/mnt/c/Users/david/TrueData/TrueData-UCAM/.gitignore`

- [ ] **Step 1: Read current `.gitignore`**

  Run: `cat /mnt/c/Users/david/TrueData/TrueData-UCAM/.gitignore`

- [ ] **Step 2: Append prevention patterns**

  Append to `.gitignore`:

  ```gitignore
  # Prevent accidental re-accumulation of secrets / lab-client data.
  # (Post-contribution cleanup 2026-04-14.)
  deploy/MCT/
  deploy/ESAMUR/
  deploy/*/DeviceimportCredentials*.csv
  deploy/*/OthersimportCredentials*.csv
  deploy/ParametrosConfiguracion.txt
  deploy/Credenciales*.txt
  src/dataloader/Credenciales*.txt

  # Word docs (superseded by markdown READMEs)
  *.docx

  # Misc dev leftovers
  /locustfile.py
  /entrypoint.sh
  ```

- [ ] **Step 3: Commit**

  ```bash
  git add .gitignore
  git commit -m "chore: harden .gitignore to block secrets and RUIDO reappearing"
  ```

### Task PF.8: Merge the cleanup branch back to `main` in UCAM (user decides when)

- [ ] **Step 1: Confirm all PF.4–PF.7 commits look right**

  Run: `git log --oneline main..chore/cleanup-pre-gitlab-contribution`
  Expected: 2–4 cleanup commits.

- [ ] **Step 2 (user choice): Merge to `main` locally**

  Two options:
  - **Merge now:** `git checkout main && git merge --no-ff chore/cleanup-pre-gitlab-contribution`
  - **Keep on branch:** Leave on the cleanup branch while MR-1 work proceeds in the GitLab clone; merge to UCAM `main` after all three GitLab MRs land, or never (stays on branch in UCAM).

  Default recommendation: **merge now** — the cleanup is independent of GitLab work and landing it on UCAM main keeps the source repo tidy while we port.

- [ ] **Step 3 (optional): Push to GitHub**

  Run: `git push origin main`
  Only if user wants the cleanup public in their GitHub fork.

---

## MR-1: base/ Infrastructure (ThingsBoard + Node-RED services)

**Branch:** `feature/base/thingsboard-nodered-setup`
**Goal:** Land a working `base/` module with TB + Node-RED that any reviewer can bring up in 5 minutes via `docker compose -f base/docker-compose.override.yml up`.
**Estimated size:** ~15 files created/modified, ~250 lines of YAML/Dockerfile, ~300 lines of README.

**Before starting any task in this MR:** re-read `CONTRIBUTING.md` sections "Branching Strategy", "Merge Request (MR) Process", "Module Development Guidelines", and "Code Review Checklist". Do not push the branch until every item on the Self-Review Checklist passes.

### Task 1.1: Create the feature branch

**Files:** none

- [ ] **Step 1: Switch to clean main**

Run:
```bash
cd /mnt/c/Users/david/TrueData/truedata-gitlab
git checkout main
git pull origin main
```
Expected: "Already up to date" or fast-forward.

- [ ] **Step 2: Create and check out the feature branch**

Run: `git checkout -b feature/base/thingsboard-nodered-setup`
Expected: "Switched to a new branch..."

- [ ] **Step 3: Verify clean state**

Run: `git status`
Expected: "nothing to commit, working tree clean".

### Task 1.2: Create `base/thingsboard/` service

**Files:**
- Create: `/mnt/c/Users/david/TrueData/truedata-gitlab/base/thingsboard/Dockerfile`
- Create: `/mnt/c/Users/david/TrueData/truedata-gitlab/base/thingsboard/config/.gitkeep`
- Create: `/mnt/c/Users/david/TrueData/truedata-gitlab/base/thingsboard/README.md`
- Reference: `/mnt/c/Users/david/TrueData/TrueData-UCAM/truedata-thingsboard/docker-compose.yml` (read-only source)

- [ ] **Step 1: Read the source TB compose file**

Read: `/mnt/c/Users/david/TrueData/TrueData-UCAM/truedata-thingsboard/docker-compose.yml`
Expected: reveals the TB image used (`thingsboard/tb-postgres` or similar) and the config mounts.

- [ ] **Step 2: Create the Dockerfile**

Create `base/thingsboard/Dockerfile`:

```dockerfile
# ThingsBoard CE with Postgres support, baseline for TRUEDATA.
# Partner: UCAM.
# Extend here if custom widgets, rule nodes, or plugins need to be baked in.

FROM thingsboard/tb-postgres:3.6.4

# Placeholder for future customizations (custom widgets, translations, etc.)
# COPY config/ /usr/share/thingsboard/conf/

ENV TZ=UTC
```

- [ ] **Step 3: Create config placeholder**

Create `base/thingsboard/config/.gitkeep` with empty content (so the folder exists in git).

- [ ] **Step 4: Create base/thingsboard/README.md**

Create `base/thingsboard/README.md`:

```markdown
# ThingsBoard Service

**Module:** base
**Partner:** UCAM
**Image base:** `thingsboard/tb-postgres:3.6.4`

## Purpose

ThingsBoard CE instance used by TRUEDATA as the IoT platform: device registry, telemetry storage, rule engine, dashboards. All sensor data (real or simulated) lands here via HTTP REST at `/api/v1/{token}/telemetry`.

## Configuration

Runtime configuration is injected via environment variables (see root `.env.example` and `base/README.md` for the full list). The `config/` folder is reserved for future customizations (custom widgets, translations, rule node JARs) but is currently empty.

## Default credentials

On first start ThingsBoard creates defaults: `sysadmin@thingsboard.org` / `sysadmin` and `tenant@thingsboard.org` / `tenant`. **These must be rotated before any non-demo deployment.** See `../README.md` Environment Variables section for the override mechanism.

## Build

```bash
docker build -t truedata-thingsboard:local .
```

## See also

- `../README.md` — base module overview
- `../deploy/README.md` — how to provision devices, dashboards, rule chains automatically
```

- [ ] **Step 5: Validate structure**

Run: `ls -la /mnt/c/Users/david/TrueData/truedata-gitlab/base/thingsboard/`
Expected: `Dockerfile`, `config/`, `README.md` present.

- [ ] **Step 6: Commit**

```bash
cd /mnt/c/Users/david/TrueData/truedata-gitlab
git add base/thingsboard/
git commit -m "feat(base): add ThingsBoard service scaffolding

Dockerfile based on thingsboard/tb-postgres:3.6.4, empty config/
directory for future customizations, module README."
```

### Task 1.3: Create `base/node-red/` service

**Files:**
- Create: `/mnt/c/Users/david/TrueData/truedata-gitlab/base/node-red/Dockerfile`
- Create: `/mnt/c/Users/david/TrueData/truedata-gitlab/base/node-red/settings.js`
- Create: `/mnt/c/Users/david/TrueData/truedata-gitlab/base/node-red/flows/.gitkeep`
- Create: `/mnt/c/Users/david/TrueData/truedata-gitlab/base/node-red/README.md`
- Reference: `/mnt/c/Users/david/TrueData/TrueData-UCAM/truedata-nodered/settings.js` (read-only source)

- [ ] **Step 1: Read the source Node-RED settings.js to identify what to port**

Read: `/mnt/c/Users/david/TrueData/TrueData-UCAM/truedata-nodered/settings.js`
Focus on: `credentialSecret`, `adminAuth`, `flowFile`, `httpAdminRoot`, custom nodes config.

- [ ] **Step 2: Create sanitized `base/node-red/settings.js`**

Port the file, applying sanitization rules. The minimum required diff against the source:

- Replace `credentialSecret: "airtrace"` with `credentialSecret: process.env.NODE_RED_CREDENTIAL_SECRET`.
- Replace any hardcoded `adminAuth` username/password hashes with `process.env.NODE_RED_USER` / `process.env.NODE_RED_PASSWORD_HASH`.
- Remove any references to hardcoded host IPs (`172.25.0.x`) if present.
- Keep everything else (custom node config, logging, flow file path, httpAdminRoot).

Add a comment at top:

```javascript
/**
 * TRUEDATA Node-RED settings.
 *
 * Partner: UCAM.
 *
 * Credentials and secrets are injected via environment variables. See
 * `../README.md` for the full env var list. Do not hardcode secrets in
 * this file — the repo has a pre-commit hook that will reject such changes.
 */
```

- [ ] **Step 3: Create the Dockerfile**

Create `base/node-red/Dockerfile`:

```dockerfile
# Node-RED for TRUEDATA: flows act as aggregator (post-TB via Rule Chains)
# and future ingestion hub for the OPC Client (see ../opc-client/README.md).
# Partner: UCAM.

FROM nodered/node-red:3.1

USER root

# Install custom nodes needed by UCAM's flows. Extend the list only when
# a flow actually requires a new package — keeps image footprint small.
RUN npm install --unsafe-perm --no-update-notifier --no-fund --only=production \
    node-red-contrib-aggregator \
    node-red-contrib-credentials \
    node-red-contrib-moment \
    && npm cache clean --force

USER node-red

COPY settings.js /data/settings.js

ENV TZ=UTC \
    FLOWS=flows.json \
    NODE_RED_CREDENTIAL_SECRET=
```

Note: the empty `NODE_RED_CREDENTIAL_SECRET` at build time forces docker-compose to fail fast if the env var is not provided at runtime.

- [ ] **Step 4: Create flows directory placeholder**

Create `base/node-red/flows/.gitkeep` with empty content. The `opc-ingest.json` flow will be added in MR-3.

- [ ] **Step 5: Create `base/node-red/README.md`**

Create with content:

```markdown
# Node-RED Service

**Module:** base
**Partner:** UCAM
**Image base:** `nodered/node-red:3.1`

## Roles in TRUEDATA

Node-RED plays **two distinct roles** in this module:

1. **Post-TB aggregator (current, in use):** ThingsBoard Rule Chains call Node-RED via `TbRestApiCallNode` (HTTP POST to `/endpoint/agregar*`). Node-RED batches, computes median/mean over 1/5/10-second windows, and writes the aggregated telemetry back to TB via `/api/v1/{token}/telemetry`. Flows for this role are generated dynamically by `../deploy/2.2_Crear_ETL_NodeRed_Cliente.py` per client.

2. **OPC Client ingestion endpoint (intended, stub only):** `flows/opc-ingest.json` (added in a later MR) exposes `/api/opc-ingest` where the future OPC Client (Neoradix) will POST raw measurements. See `../opc-client/README.md` for the contract.

## Secrets

`credentialSecret` is read from `NODE_RED_CREDENTIAL_SECRET`. **No secret is baked into the image.** The container will start Node-RED with unencryptable credentials if the env var is missing — which is the desired fail-fast behavior.

Admin login (`adminAuth`) uses `NODE_RED_USER` and `NODE_RED_PASSWORD_HASH` (bcrypt hash, generate with `node-red admin hash-pw`).

## Build

```bash
docker build -t truedata-node-red:local .
```

## Custom nodes installed

`node-red-contrib-aggregator`, `node-red-contrib-credentials`, `node-red-contrib-moment`.

## See also

- `../README.md` — base module overview
- `../opc-client/README.md` — OPC Client HTTP contract (added in MR-3)
```

- [ ] **Step 6: Verify no secrets leaked**

Run:
```bash
cd /mnt/c/Users/david/TrueData/truedata-gitlab
grep -rn 'airtrace' base/ || echo "CLEAN: no 'airtrace' string"
grep -rn 'tenant@thingsboard.org' base/node-red/ || echo "CLEAN: no tenant creds"
```
Expected: "CLEAN: ..." for both.

- [ ] **Step 7: Commit**

```bash
git add base/node-red/
git commit -m "feat(base): add Node-RED service scaffolding

Dockerfile based on nodered/node-red:3.1 with custom nodes,
settings.js with credentialSecret via env var (no secrets in file),
empty flows directory ready for MR-2 deploy-generated flows and
MR-3 opc-ingest flow."
```

### Task 1.4: Create `base/docker-compose.override.yml`

**Files:**
- Create: `/mnt/c/Users/david/TrueData/truedata-gitlab/base/docker-compose.override.yml`

- [ ] **Step 1: Write the override**

Create `base/docker-compose.override.yml`:

```yaml
# Standalone dev environment for the base module.
# Brings up ThingsBoard + Node-RED + PostgreSQL only.
# Intended for contributors working on base/ in isolation.
# For the full stack use the root docker-compose.yml with --profile full.
#
# Usage:
#   cd <repo root>
#   cp .env.example .env
#   docker compose -f base/docker-compose.override.yml up --build

services:
  postgres:
    image: postgres:15-alpine
    container_name: truedata-postgres
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-thingsboard}
      POSTGRES_USER: ${POSTGRES_USER:-postgres}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-postgres}
    volumes:
      - postgres-data:/var/lib/postgresql/data
    networks: [truedata-net]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-postgres}"]
      interval: 10s
      timeout: 5s
      retries: 5

  thingsboard:
    build:
      context: ./thingsboard
    container_name: truedata-thingsboard
    depends_on:
      postgres:
        condition: service_healthy
    ports:
      - "${TB_HTTP_PORT:-9090}:9090"
      - "${TB_MQTT_PORT:-1884}:1883"
    environment:
      TB_QUEUE_TYPE: in-memory
      SPRING_DATASOURCE_URL: jdbc:postgresql://postgres:5432/${POSTGRES_DB:-thingsboard}
      SPRING_DATASOURCE_USERNAME: ${POSTGRES_USER:-postgres}
      SPRING_DATASOURCE_PASSWORD: ${POSTGRES_PASSWORD:-postgres}
      TZ: ${TZ:-UTC}
    volumes:
      - thingsboard-data:/data
      - thingsboard-logs:/var/log/thingsboard
    networks: [truedata-net]

  node-red:
    build:
      context: ./node-red
    container_name: truedata-node-red
    depends_on:
      thingsboard:
        condition: service_started
    ports:
      - "${NODE_RED_PORT:-1880}:1880"
    environment:
      NODE_RED_CREDENTIAL_SECRET: ${NODE_RED_CREDENTIAL_SECRET:?NODE_RED_CREDENTIAL_SECRET must be set}
      NODE_RED_USER: ${NODE_RED_USER:-admin}
      NODE_RED_PASSWORD_HASH: ${NODE_RED_PASSWORD_HASH:-}
      TB_URL: http://thingsboard:9090
      TZ: ${TZ:-UTC}
    volumes:
      - node-red-data:/data
      - ./node-red/flows:/data/flows
    networks: [truedata-net]

networks:
  truedata-net:
    driver: bridge

volumes:
  postgres-data:
  thingsboard-data:
  thingsboard-logs:
  node-red-data:
```

- [ ] **Step 2: Validate syntax**

Run:
```bash
cd /mnt/c/Users/david/TrueData/truedata-gitlab
# Provide a dummy env for validation
NODE_RED_CREDENTIAL_SECRET=dummy docker compose -f base/docker-compose.override.yml config > /dev/null
echo "EXIT: $?"
```
Expected: `EXIT: 0` (no output from config — success — followed by `EXIT: 0`).

- [ ] **Step 3: Commit**

```bash
git add base/docker-compose.override.yml
git commit -m "feat(base): add standalone docker-compose.override.yml

Brings up Postgres + ThingsBoard + Node-RED for module-isolated dev.
Node-RED fails fast if NODE_RED_CREDENTIAL_SECRET is not provided."
```

### Task 1.5: Update root `.env.example` with base module variables

**Files:**
- Modify: `/mnt/c/Users/david/TrueData/truedata-gitlab/.env.example`

- [ ] **Step 1: Read the current .env.example**

Read: `/mnt/c/Users/david/TrueData/truedata-gitlab/.env.example`

- [ ] **Step 2: Extend with UCAM base module section**

Append to `.env.example`:

```bash
# ============================================================================
# MODULE 1 (base) — UCAM additions
# ============================================================================

# ThingsBoard
TB_HTTP_PORT=9090
TB_MQTT_PORT=1884
TB_URL=http://thingsboard:9090
TB_ADMIN_USER=tenant@thingsboard.org
TB_ADMIN_PASSWORD=tenant
# Rotate in real deployments; defaults above match ThingsBoard's first-boot seed.

# Node-RED
NODE_RED_PORT=1880
NODE_RED_URL=http://node-red:1880
# REQUIRED: random cryptographic string used to encrypt Node-RED credentials
# Generate with: openssl rand -hex 32
NODE_RED_CREDENTIAL_SECRET=
NODE_RED_USER=admin
# bcrypt hash, generate with: node-red admin hash-pw
NODE_RED_PASSWORD_HASH=

# PostgreSQL (ThingsBoard backing store)
POSTGRES_DB=thingsboard
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
```

- [ ] **Step 3: Commit**

```bash
git add .env.example
git commit -m "docs(base): document base module env vars in root .env.example

Adds TB + Node-RED + Postgres variables with notes on rotation
and generation (openssl, node-red admin hash-pw)."
```

### Task 1.6: Smoke test the base stack end-to-end

**Files:** none (runtime verification only)

- [ ] **Step 1: Prepare a local .env for the smoke test**

Run:
```bash
cd /mnt/c/Users/david/TrueData/truedata-gitlab
cp .env.example .env
sed -i 's|^NODE_RED_CREDENTIAL_SECRET=$|NODE_RED_CREDENTIAL_SECRET='"$(openssl rand -hex 32)"'|' .env
grep NODE_RED_CREDENTIAL_SECRET .env
```
Expected: the variable now has a hex value. Note: `.env` is already gitignored in the scaffold — if not, confirm before proceeding.

- [ ] **Step 2: Verify .env is gitignored**

Run: `git check-ignore -v .env`
Expected: output showing `.gitignore:...:.env` (i.e. ignored). If not ignored, add `.env` to `.gitignore` and commit.

- [ ] **Step 3: Bring up the base stack**

Run:
```bash
docker compose -f base/docker-compose.override.yml up --build -d
```
Expected: all three containers reach "Started" or "healthy".

- [ ] **Step 4: Wait for ThingsBoard to be up (it is slow on first boot)**

Run:
```bash
for i in {1..60}; do
  if curl -sf http://localhost:9090/api/auth/login -o /dev/null -w "%{http_code}" | grep -q 401; then
    echo "TB up after ${i}0s"
    break
  fi
  sleep 10
done
```
Expected: "TB up after N0s" within 10 minutes. HTTP 401 on the login endpoint means TB is serving.

- [ ] **Step 5: Verify Node-RED is up**

Run: `curl -sf http://localhost:1880/ -o /dev/null -w "%{http_code}\n"`
Expected: `200` or `302`.

- [ ] **Step 6: Tear down**

Run: `docker compose -f base/docker-compose.override.yml down -v`
Expected: all containers stopped, volumes removed.

- [ ] **Step 7: If smoke test failed, iterate on Dockerfiles / compose; commit fixes**

Only proceed to 1.7 if the smoke test passed.

### Task 1.7: Write initial `base/README.md` (infrastructure-only, MR-1 scope)

**Files:**
- Modify: `/mnt/c/Users/david/TrueData/truedata-gitlab/base/README.md` (full rewrite)

- [ ] **Step 1: Back up the scaffold README for reference**

Run:
```bash
cp /mnt/c/Users/david/TrueData/truedata-gitlab/base/README.md /tmp/base-README-scaffold.md
```
This is so the later MRs can cross-check what the scaffold assumed.

- [ ] **Step 2: Rewrite base/README.md**

Overwrite with the following content. This is the MR-1 version — MR-2 and MR-3 will extend it.

```markdown
# Module: base — ThingsBoard + Node-RED (UCAM)

## Purpose

Foundational data layer of TRUEDATA. Provides:

- **ThingsBoard CE** — IoT platform: device registry, telemetry storage, rule engine, dashboards.
- **Node-RED** — Two roles: (1) post-ThingsBoard aggregator invoked by TB Rule Chains to compute median/mean over time windows; (2) future ingestion endpoint for the OPC Client (see `opc-client/README.md`, added in a later iteration).
- **PostgreSQL** — ThingsBoard's persistent store.

All inter-service communication in this module is **HTTP REST**. There is no MQTT broker at this layer, contrary to what the original scaffold suggested. Other TRUEDATA modules that need data from `base/` consume it via the ThingsBoard REST API.

## Responsible partner

**UCAM**.

The scaffold originally attributed the OPC Client to Neoradix as part of `base/`. The OPC Client subfolder (`opc-client/`) is a **contract stub** — Neoradix will implement it targeting the HTTP contract documented there.

## Technologies

- ThingsBoard CE 3.6.4 (Java/Spring Boot, `thingsboard/tb-postgres`)
- Node-RED 3.1 (Node.js)
- PostgreSQL 15
- Docker Compose 2.x

## Input / Output

### Inputs (to ThingsBoard)

- **HTTP POST** `/api/v1/{token}/telemetry` — JSON body with flat key/value pairs.
  - Sources today: `shared/simulator/` (DEMO mode, added in MR-3), manual `curl` / `fetch_tokens_remote`-style scripts.
  - Source intended: OPC Client via Node-RED (`opc-client/` — MR-3 stub, Neoradix implementation later).
- **HTTP POST from Node-RED back into TB** — aggregated telemetry (medians/means over windows), same endpoint format.

### Outputs (from ThingsBoard)

- **HTTP REST** at `/api/plugins/telemetry/...` for other modules to read time-series.
- **Rule Chain → Node-RED** — TB invokes Node-RED `/endpoint/agregarXXX` via `TbRestApiCallNode` to trigger aggregation.

## Integration points

| Target module | Protocol | Direction | Purpose |
|---|---|---|---|
| `ml-classical/` (standby) | HTTP REST | pull from TB | Read time-series for training / inference |
| `ai-advanced/` | HTTP REST | pull from TB | Read time-series for GNN models |
| `cybersecurity/` | out of scope | — | Operates on the network layer, not the TB data plane |
| `blockchain/` | HTTP REST | push to TB rule chain output topic (TBD) | Record critical events |

## Architecture

```
base/
├── thingsboard/            # TB service (Docker)
│   ├── Dockerfile
│   ├── config/             # future TB customizations
│   └── README.md
├── node-red/               # Node-RED service (Docker)
│   ├── Dockerfile
│   ├── settings.js         # env-based secrets
│   ├── flows/              # flow definitions (populated by deploy scripts + opc-ingest)
│   └── README.md
├── deploy/                 # (MR-2) per-client provisioning pipeline
├── opc-client/             # (MR-3) contract stub for Neoradix
└── docker-compose.override.yml   # standalone dev environment
```

## How to build

From the repo root:

```bash
docker compose -f base/docker-compose.override.yml build
```

## How to run standalone

```bash
# 1. Configure
cp .env.example .env
# Generate a Node-RED credential secret:
openssl rand -hex 32   # paste into NODE_RED_CREDENTIAL_SECRET

# 2. Start
docker compose -f base/docker-compose.override.yml up --build

# 3. Access
# ThingsBoard UI:  http://localhost:9090  (tenant@thingsboard.org / tenant — rotate!)
# Node-RED editor: http://localhost:1880
```

## Environment variables

See root `.env.example` (section "MODULE 1 (base)"). Summary:

| Variable | Default | Required | Description |
|---|---|---|---|
| `TB_HTTP_PORT` | 9090 | no | Port mapped for TB UI/API |
| `TB_MQTT_PORT` | 1884 | no | Port for TB's own MQTT listener (not used as bus here) |
| `TB_URL` | `http://thingsboard:9090` | no | TB URL as seen from other services in the compose network |
| `TB_ADMIN_USER` / `TB_ADMIN_PASSWORD` | TB defaults | **yes in prod** | Rotate before any non-demo use |
| `NODE_RED_PORT` | 1880 | no | Port mapped for Node-RED editor |
| `NODE_RED_URL` | `http://node-red:1880` | no | Node-RED URL from other services |
| `NODE_RED_CREDENTIAL_SECRET` | — | **yes** | Encrypts Node-RED stored credentials. Fail-fast if missing. |
| `NODE_RED_USER` | `admin` | no | Admin username |
| `NODE_RED_PASSWORD_HASH` | — | **yes in prod** | bcrypt via `node-red admin hash-pw` |
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | `thingsboard` / `postgres` / `postgres` | **yes in prod** | Rotate before any non-demo use |
| `TZ` | `UTC` | no | Timezone |

## Testing

After `docker compose -f base/docker-compose.override.yml up`:

```bash
# ThingsBoard responds on HTTP
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:9090/api/auth/login
# Expected: 401 (auth required = serving)

# Node-RED responds
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:1880/
# Expected: 200 or 302

# Node-RED container refused to start without NODE_RED_CREDENTIAL_SECRET:
unset NODE_RED_CREDENTIAL_SECRET
docker compose -f base/docker-compose.override.yml up node-red
# Expected: "NODE_RED_CREDENTIAL_SECRET must be set" error. Good.
```

## TODO / Known limitations

- [ ] **MR-2:** deploy automation (`deploy/`) + per-client provisioning templates
- [ ] **MR-3:** `shared/simulator/` for DEMO data injection + `opc-client/` contract stub
- [ ] ThingsBoard default credentials must be rotated via TB REST API in any non-demo deployment (scripted in `deploy/` per MR-2)
- [ ] `config/` under `thingsboard/` is empty; custom widgets/rule nodes baked into image go there if ever needed
- [ ] No automated tests yet — reviewers validate by running the smoke test above

## See also

- `thingsboard/README.md` — TB service details
- `node-red/README.md` — Node-RED service details
- `../CONTRIBUTING.md` — branching and MR workflow
- `../shared/README.md` — shared infrastructure (MQTT broker mentioned there is not used by `base/`)
```

- [ ] **Step 3: Commit**

```bash
git add base/README.md
git commit -m "docs(base): rewrite module README to reflect reality

The scaffold README assumed MQTT bus and Neoradix OPC Client; actual
implementation is HTTP REST throughout with Node-RED as TB aggregator.
README now documents MR-1 scope (infrastructure) and flags MR-2 and
MR-3 as TODO."
```

### Task 1.8: Pre-MR checklist for MR-1

- [ ] **Step 1: Secret scan**

Run:
```bash
cd /mnt/c/Users/david/TrueData/truedata-gitlab
git diff main...HEAD | grep -E '(airtrace|tenant@thingsboard.org|AWS_[A-Z_]+.*=.*[A-Za-z0-9])' && echo "LEAK FOUND" || echo "CLEAN"
```
Expected: `CLEAN`. If `LEAK FOUND`, fix and re-commit.

- [ ] **Step 2: Compose validation**

Run:
```bash
NODE_RED_CREDENTIAL_SECRET=dummy docker compose -f base/docker-compose.override.yml config > /dev/null && echo OK
docker compose config > /dev/null 2>&1 && echo "root compose OK" || echo "root compose WARN (expected if other modules not yet ported)"
```
Expected: first OK. Second may warn (acceptable at this stage).

- [ ] **Step 3: Rebase on main**

Run:
```bash
git fetch origin
git rebase origin/main
```
Expected: clean rebase. If conflicts, resolve and continue.

### Task 1.9: Push and open MR-1

- [ ] **Step 1: Push the branch**

Run:
```bash
git push -u origin feature/base/thingsboard-nodered-setup
```
Expected: branch pushed, GitLab returns a URL to open an MR.

- [ ] **Step 2: Open the MR via `gh` or web UI**

If `glab` is available:
```bash
glab mr create --title "feat(base): ThingsBoard + Node-RED service scaffolding" --description-file - <<'EOF'
## What

Lands the `base/` module's core infrastructure: ThingsBoard service, Node-RED service, standalone `docker-compose.override.yml`, module-level `.env.example` entries, and an initial README that replaces the scaffold's assumptions (which presumed MQTT bus + Neoradix-owned OPC Client) with the real HTTP-REST architecture.

## Why

First of three UCAM MRs to the `base/` module. Subsequent MRs will add:
- MR-2: `base/deploy/` automation (5-script per-client provisioning pipeline)
- MR-3: `shared/simulator/` for DEMO mode + `base/opc-client/` contract stub for Neoradix

## How to test

```bash
cp .env.example .env
# Set NODE_RED_CREDENTIAL_SECRET to a random hex string:
openssl rand -hex 32
# Paste into .env

docker compose -f base/docker-compose.override.yml up --build

# In another terminal:
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:9090/api/auth/login  # expect 401
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:1880/                # expect 200 or 302
```

## Files changed

- `base/thingsboard/Dockerfile` — TB image baseline
- `base/node-red/Dockerfile` — Node-RED image with UCAM's custom nodes
- `base/node-red/settings.js` — Node-RED config, `credentialSecret` via env var
- `base/docker-compose.override.yml` — standalone dev environment
- `.env.example` — base module variables appended
- `base/README.md` — rewritten to match actual architecture

## Notes

The original scaffold README presumed MQTT as the inter-module bus. UCAM's implementation is 100% HTTP REST. This has been confirmed with partners (HTTP will also be Neoradix's choice for the OPC Client). The new README makes this explicit.
EOF
```

If `glab` is not available, push the branch and open the MR manually at:
`https://collab.libelium.com:46231/proyectos-europeos/truedata/truedata/-/merge_requests/new?merge_request[source_branch]=feature/base/thingsboard-nodered-setup`

- [ ] **Step 3: Assign module maintainer as reviewer**

Per CONTRIBUTING.md: Base module maintainers are `@ucam-lead` or `@neoradix-opc`. Tag both.

- [ ] **Step 4: Wait for review, address feedback**

Do not start MR-2 until MR-1 is merged (or at least approved-pending-merge) to avoid rebasing cascades. If review is slow, the next MR can branch off `feature/base/thingsboard-nodered-setup` explicitly — note this in the MR-2 description.

---

## MR-2: base/deploy/ Automation + Client Onboarding

**Branch:** `feature/base/deploy-automation` (from `main` once MR-1 merged, otherwise from `feature/base/thingsboard-nodered-setup`).
**Goal:** Port the 5-script deploy pipeline, provide a `TEMPLATE/` client for reviewer smoke-testing, document client onboarding end-to-end.
**Estimated size:** ~10 Python files ported with sanitization, ~4 template files, ~400 lines of README additions.

**Before starting any task in this MR:** re-read `CONTRIBUTING.md` — in particular the "Code Review Checklist" (no hardcoded secrets, env vars documented, commit messages) and the "Per-Module Structure" (`deploy/` subfolder must have its own README that covers the 10 sections). If anything in MR-1 landed in a shape that conflicts with CONTRIBUTING.md, fix it here as part of MR-2 scope.

### Task 2.1: Create the feature branch

- [ ] **Step 1: Switch to the latest base**

Run:
```bash
cd /mnt/c/Users/david/TrueData/truedata-gitlab
git fetch origin
# If MR-1 merged:
git checkout main && git pull origin main
# If MR-1 still open, branch from it:
# git checkout feature/base/thingsboard-nodered-setup
```

- [ ] **Step 2: Create MR-2 branch**

Run: `git checkout -b feature/base/deploy-automation`

### Task 2.2: Port `APIThingsboard.py` with sanitization

**Files:**
- Create: `/mnt/c/Users/david/TrueData/truedata-gitlab/base/deploy/APIThingsboard.py`
- Source: `/mnt/c/Users/david/TrueData/TrueData-UCAM/deploy/APIThingsboard.py`

- [ ] **Step 1: Copy the source file**

Run:
```bash
cp /mnt/c/Users/david/TrueData/TrueData-UCAM/deploy/APIThingsboard.py \
   /mnt/c/Users/david/TrueData/truedata-gitlab/base/deploy/APIThingsboard.py
```

- [ ] **Step 2: Apply sanitization edits**

Read the ported file and replace:
- Any `http://localhost:9090` or `http://172.25.0.x:9090` with a constant `TB_URL` read from environment at module import:
  ```python
  import os
  TB_URL = os.environ.get("TB_URL", "http://localhost:9090")
  ```
- Any hardcoded admin credentials with env-var lookups:
  ```python
  TB_ADMIN_USER = os.environ.get("TB_ADMIN_USER", "tenant@thingsboard.org")
  TB_ADMIN_PASSWORD = os.environ["TB_ADMIN_PASSWORD"]  # required, fail fast
  ```

Detailed rewrite rules:
- Module-level URL: replace ad-hoc `"http://localhost:9090"` strings with `TB_URL` referenced.
- Admin creds: centralize into module-level constants read once from env.
- No behavior change beyond env-var indirection — keep function signatures identical so the numbered scripts continue to import the same symbols.

- [ ] **Step 3: Grep-check sanitization**

Run:
```bash
cd /mnt/c/Users/david/TrueData/truedata-gitlab
grep -E 'localhost:9090|172\.25\.0\.|tenant@thingsboard\.org' base/deploy/APIThingsboard.py && echo "STILL LEAKING" || echo "CLEAN"
```
Expected: `CLEAN`. If residual matches exist in comments that's fine — check they're only in docstrings/comments, not live strings.

- [ ] **Step 4: Verify Python parses**

Run: `python3 -c "import ast; ast.parse(open('/mnt/c/Users/david/TrueData/truedata-gitlab/base/deploy/APIThingsboard.py').read())" && echo OK`
Expected: `OK`. Syntax errors fail here.

- [ ] **Step 5: Commit**

```bash
git add base/deploy/APIThingsboard.py
git commit -m "feat(base): port APIThingsboard.py from UCAM repo

REST wrapper for ThingsBoard API. Sanitized:
- TB_URL read from env (default http://localhost:9090)
- TB_ADMIN_USER / TB_ADMIN_PASSWORD read from env
No functional changes; function signatures preserved."
```

### Task 2.3: Port the numbered deploy scripts

**Files (port each, apply same sanitization pattern):**
- `base/deploy/env_client.py` — orchestrator
- `base/deploy/1_Configuracion_General.py`
- `base/deploy/1.1_Subir_Niveles_Criticidad_Inicial_Bulk.py`
- `base/deploy/2_Crear_Entorno_Cliente_ThingsBoard.py`
- `base/deploy/2.2_Crear_ETL_NodeRed_Cliente.py`
- `base/deploy/3_Solicitar_Niveles_Criticidad.py`
- `base/deploy/3.1_Modificar_Niveles_Criticidad.py`
- `base/deploy/4_Subir_thresholds.py`

- [ ] **Step 1: Copy all scripts from the source**

Run:
```bash
cp /mnt/c/Users/david/TrueData/TrueData-UCAM/deploy/env_client.py \
   /mnt/c/Users/david/TrueData/TrueData-UCAM/deploy/1_Configuracion_General.py \
   /mnt/c/Users/david/TrueData/TrueData-UCAM/deploy/1.1_Subir_Niveles_Criticidad_Inicial_Bulk.py \
   /mnt/c/Users/david/TrueData/TrueData-UCAM/deploy/2_Crear_Entorno_Cliente_ThingsBoard.py \
   /mnt/c/Users/david/TrueData/TrueData-UCAM/deploy/2.2_Crear_ETL_NodeRed_Cliente.py \
   /mnt/c/Users/david/TrueData/TrueData-UCAM/deploy/3_Solicitar_Niveles_Criticidad.py \
   /mnt/c/Users/david/TrueData/TrueData-UCAM/deploy/3.1_Modificar_Niveles_Criticidad.py \
   /mnt/c/Users/david/TrueData/TrueData-UCAM/deploy/4_Subir_thresholds.py \
   /mnt/c/Users/david/TrueData/truedata-gitlab/base/deploy/
```

- [ ] **Step 2: For each file, apply sanitization**

For every `.py` file under `base/deploy/`:
- Replace hardcoded `http://localhost:9090` / `http://172.25.0.x:9090` with `os.environ["TB_URL"]`.
- Replace hardcoded `http://localhost:1880` / `http://172.25.0.3:1880` with `os.environ["NODE_RED_URL"]`.
- Replace hardcoded `"tenant@thingsboard.org"` / `"tenant"` / `"tenantairtrace"` / `"sysadmin@thingsboard.org"` / `"sysadmin"` with env-var reads (`TB_ADMIN_USER`, `TB_ADMIN_PASSWORD`, `NODE_RED_USER`, `NODE_RED_PASSWORD`, `TB_SYSADMIN_USER`, `TB_SYSADMIN_PASSWORD`).
- Replace any path that references `deploy/{Cliente}/...` with `CLIENT_DIR` derived from env or CLI arg.

For each script, add at the top (below imports):

```python
import os
from pathlib import Path

TB_URL = os.environ.get("TB_URL", "http://localhost:9090")
NODE_RED_URL = os.environ.get("NODE_RED_URL", "http://localhost:1880")
CLIENT_DIR = Path(os.environ.get("CLIENT_DIR", Path(__file__).parent / "TEMPLATE"))
```

- [ ] **Step 3: Grep-check sanitization across all scripts**

Run:
```bash
cd /mnt/c/Users/david/TrueData/truedata-gitlab
grep -rnE 'localhost:9090|172\.25\.0\.|tenant@thingsboard\.org|tenantairtrace|sysadmin@thingsboard\.org' base/deploy/*.py | grep -v '^.*#' && echo "STILL LEAKING" || echo "CLEAN"
```
Expected: `CLEAN` (or only matches inside Python comments).

- [ ] **Step 4: Parse-check all scripts**

Run:
```bash
for f in /mnt/c/Users/david/TrueData/truedata-gitlab/base/deploy/*.py; do
  python3 -c "import ast; ast.parse(open('$f').read())" || echo "SYNTAX: $f"
done
```
Expected: no `SYNTAX: ...` lines.

- [ ] **Step 5: Commit**

```bash
git add base/deploy/*.py
git commit -m "feat(base): port deploy pipeline scripts from UCAM repo

Eight scripts ported from deploy/: env_client.py (orchestrator),
1_, 1.1_, 2_, 2.2_, 3_, 3.1_, 4_. All hardcoded URLs and credentials
replaced with env var lookups (TB_URL, NODE_RED_URL, TB_ADMIN_USER,
TB_ADMIN_PASSWORD, NODE_RED_USER, NODE_RED_PASSWORD). CLIENT_DIR
derived from env to allow per-client configuration."
```

### Task 2.4: Port `Plantillas/` JSON templates

**Files:**
- Create: `/mnt/c/Users/david/TrueData/truedata-gitlab/base/deploy/Plantillas/` (entire tree)
- Source: `/mnt/c/Users/david/TrueData/TrueData-UCAM/deploy/Plantillas/`

- [ ] **Step 1: Copy the entire Plantillas tree**

Run:
```bash
cp -r /mnt/c/Users/david/TrueData/TrueData-UCAM/deploy/Plantillas \
      /mnt/c/Users/david/TrueData/truedata-gitlab/base/deploy/
```

- [ ] **Step 2: Scan for hardcoded tokens or URLs in the JSON**

Run:
```bash
cd /mnt/c/Users/david/TrueData/truedata-gitlab
grep -rnE '"accessToken"\s*:\s*"[A-Za-z0-9]{16,}"|http://172\.25\.0\.|tenant@thingsboard\.org' base/deploy/Plantillas/ && echo "LEAK IN TEMPLATES" || echo "CLEAN"
```
Expected: `CLEAN`. Templates should have placeholders like `${accessTokenClientesNiveles}`, `${ROOT_ThingsBoard}`. If real tokens appear, replace with placeholder variables matching how `1_Configuracion_General.py` interpolates them.

- [ ] **Step 3: Commit**

```bash
git add base/deploy/Plantillas/
git commit -m "feat(base): port Plantillas JSON templates

Dashboard, rule chain, and Node-RED flow templates used by the
deploy scripts. Contain placeholders interpolated at deploy time."
```

### Task 2.5: Create `TEMPLATE/` client folder

**Files:**
- Create: `/mnt/c/Users/david/TrueData/truedata-gitlab/base/deploy/TEMPLATE/Client.json`
- Create: `/mnt/c/Users/david/TrueData/truedata-gitlab/base/deploy/TEMPLATE/DeviceImport.csv.example`
- Create: `/mnt/c/Users/david/TrueData/truedata-gitlab/base/deploy/TEMPLATE/Niveles_de_Criticidad.csv.example`
- Create: `/mnt/c/Users/david/TrueData/truedata-gitlab/base/deploy/TEMPLATE/README.md`

- [ ] **Step 1: Create `Client.json`**

```json
{
  "Client": "TEMPLATE",
  "Model": "M3"
}
```

- [ ] **Step 2: Create `DeviceImport.csv.example`**

```csv
name,label,type,group
PUERTO.PLC11.CLORO_PLC11,Chlorine sensor PLC11,sensor,Cl
PUERTO.PLC11.PH_PLC11,pH sensor PLC11,sensor,pH
PUERTO.PLC11.FLOW_PLC11,Flow sensor PLC11,sensor,Flow
```

The `.example` suffix signals that contributors must copy and populate this file per-client locally — it is not versioned per client.

- [ ] **Step 3: Create `Niveles_de_Criticidad.csv.example`**

```csv
Cliente,Modelo,NumNivel,Cota,FechaInicio,FechaFin,Activo
TEMPLATE,M3,1,0.10,2026-01-01,,true
TEMPLATE,M3,2,0.25,2026-01-01,,true
TEMPLATE,M3,3,0.50,2026-01-01,,true
TEMPLATE,M3,4,0.75,2026-01-01,,true
TEMPLATE,M3,5,0.90,2026-01-01,,true
TEMPLATE,M3,6,0.99,2026-01-01,,true
```

- [ ] **Step 4: Create `TEMPLATE/README.md`**

```markdown
# Client TEMPLATE

Reference template for adding a new client to a TRUEDATA deployment.
**Do not version real client data.** Copy this folder to `base/deploy/<ClientName>/`
**outside git** (or in a private fork) and populate with actual devices, thresholds,
and tokens.

## Files

| File | Purpose | Input or Output |
|---|---|---|
| `Client.json` | Selects client name + ML model code | Input (manual) |
| `DeviceImport.csv.example` | List of physical devices/sensors to provision in ThingsBoard | Input (manual) — rename to `DeviceImport.csv` when populated |
| `Niveles_de_Criticidad.csv.example` | Alert thresholds per model | Input (manual) — rename to `Niveles de Criticidad.csv` |
| `DeviceimportCredentials_<Cliente>.csv` | Device tokens | **Output** (generated by `2_Crear_Entorno_Cliente_ThingsBoard.py`) — contains secrets, never commit |
| `OthersimportCredentials_<Cliente>.csv` | Aggregator device tokens | **Output** (generated by the deploy pipeline) — contains secrets, never commit |

## Onboarding a new client

See `../README.md` "Client onboarding" section.

## Why `.example` suffix?

The `.gitignore` in this repo ignores `deploy/*/DeviceImport.csv`,
`deploy/*/Niveles de Criticidad.csv`, `deploy/*/*Credentials*.csv`.
The `.example` files are versioned so contributors see the expected
schema; the real files (without the suffix) are local-only.
```

- [ ] **Step 5: Update root `.gitignore`**

Read current `.gitignore` and append:

```gitignore
# base/deploy client folders — client data is local-only.
# Only base/deploy/TEMPLATE/ is versioned; real clients live outside git.
base/deploy/*/DeviceImport.csv
base/deploy/*/Niveles*.csv
base/deploy/*/*Credentials*.csv
# Exception: the TEMPLATE placeholders with .example suffix ARE versioned
!base/deploy/TEMPLATE/*.example
```

- [ ] **Step 6: Commit**

```bash
git add base/deploy/TEMPLATE/ .gitignore
git commit -m "feat(base): add TEMPLATE client folder + gitignore rules

TEMPLATE/ provides versioned .example files so contributors see the
schema expected by the deploy pipeline. Real client data (tokens,
credentials, real device lists) is local-only, enforced by .gitignore."
```

### Task 2.6: Create `base/deploy/requirements.txt` and `README.md`

**Files:**
- Create: `/mnt/c/Users/david/TrueData/truedata-gitlab/base/deploy/requirements.txt`
- Create: `/mnt/c/Users/david/TrueData/truedata-gitlab/base/deploy/README.md`

- [ ] **Step 1: Inspect imports in the ported scripts to determine dependencies**

Run:
```bash
grep -hE '^\s*(import|from)\s' /mnt/c/Users/david/TrueData/truedata-gitlab/base/deploy/*.py | sort -u
```
Expected output: list of modules. Extract third-party ones (exclude stdlib: `os`, `json`, `csv`, `pathlib`, `sys`, `re`, `time`, `datetime`).

- [ ] **Step 2: Create `requirements.txt`**

```text
requests>=2.31,<3
pandas>=2.0,<3
python-dotenv>=1.0,<2
```

Adjust to actually match what the scripts import (if `pandas` isn't imported anywhere, drop it).

- [ ] **Step 3: Create `base/deploy/README.md`**

```markdown
# base/deploy — Client Provisioning Pipeline

**Partner:** UCAM

## Purpose

Automate per-client setup in ThingsBoard + Node-RED. Given a client's physical device list and alert thresholds, these scripts:

1. Create the TB customer, rule chains, device profiles, and devices
2. Generate device access tokens (returned by TB) and persist them locally
3. Generate Node-RED aggregation flows dynamically (median/mean over 1s/5s/10s)
4. Upload alert thresholds and criticality levels to TB

## Pipeline stages

Execute `env_client.py` to run all stages sequentially. Individual scripts can be run standalone too (they share `APIThingsboard.py` as the REST wrapper).

| # | Script | Reads | Writes |
|---|---|---|---|
| 1 | `1_Configuracion_General.py` | `Client.json` | 2 global TB devices + `DeviceimportCredentials_CORE.csv` + Node-RED "Critical Level" flow |
| 2 | `1.1_Subir_Niveles_Criticidad_Inicial_Bulk.py` | `{ClientDir}/Niveles de Criticidad.csv` | Telemetry on TB device |
| 3 | `2_Crear_Entorno_Cliente_ThingsBoard.py` | `Client.json`, `{ClientDir}/DeviceImport.csv` | TB customer + devices + `{ClientDir}/DeviceimportCredentials_<Cliente>.csv` |
| 4 | `2.2_Crear_ETL_NodeRed_Cliente.py` | `{ClientDir}/OthersimportCredentials_<Cliente>.csv` | Node-RED flows |
| 5 | `4_Subir_thresholds.py` | `{ModelDir}/score_max.csv` | Telemetry on TB threshold device |

Where:
- `{ClientDir}` = `$CLIENT_DIR` (default `base/deploy/TEMPLATE/`)
- `{ModelDir}` = `base/models/<Client>/<Model>/` (not shipped in this repo; provided by the ML team)

## Prerequisites

- Python 3.9+
- `requests`, `pandas` (see `requirements.txt`)
- ThingsBoard + Node-RED running (bring them up via `base/docker-compose.override.yml` from the repo root)
- Env vars set: `TB_URL`, `TB_ADMIN_USER`, `TB_ADMIN_PASSWORD`, `NODE_RED_URL`, `NODE_RED_USER`, `NODE_RED_PASSWORD`, `CLIENT_DIR`

## Quick start against the `TEMPLATE` client

```bash
# From repo root
cp .env.example .env
# Fill in NODE_RED_CREDENTIAL_SECRET and rotate defaults as needed

# Bring up TB + Node-RED
docker compose -f base/docker-compose.override.yml up -d

# Wait ~2 minutes for TB to be ready, then:
cd base/deploy
pip install -r requirements.txt

export $(grep -v '^#' ../../.env | xargs)
export CLIENT_DIR=$(pwd)/TEMPLATE
python env_client.py
```

Expected: 5 scripts execute without error, TB shows a "TEMPLATE" customer with devices, Node-RED has the "Critical Level" flow and aggregation flows.

## Onboarding a new client (offline)

1. Copy `TEMPLATE/` to a local folder **outside git**, e.g. `~/truedata-clients/ACME/`
2. Populate `Client.json` with the client name and model
3. Rename `.example` files and fill with real device lists and thresholds
4. Set `CLIENT_DIR=~/truedata-clients/ACME` in your shell
5. Run `python env_client.py`
6. Collect the generated `DeviceimportCredentials_ACME.csv` for your records — it contains secrets

## What NOT to commit

Never commit files matching:
- `*/DeviceImport.csv` (real device names)
- `*/Niveles de Criticidad.csv` (real thresholds — can be sensitive)
- `*/*Credentials*.csv` (TB device access tokens — always sensitive)

The repo's `.gitignore` enforces this, but review your diffs before pushing.

## Troubleshooting

- **HTTP 401 from TB**: `TB_ADMIN_USER` / `TB_ADMIN_PASSWORD` don't match what's configured in TB. Rotate or align.
- **HTTP 404 on Node-RED `/flow`**: Node-RED admin auth failed. Verify `NODE_RED_USER` / `NODE_RED_PASSWORD`.
- **TB not ready**: first-boot migration can take 3–5 min. Wait, then retry.
```

- [ ] **Step 4: Commit**

```bash
git add base/deploy/requirements.txt base/deploy/README.md
git commit -m "docs(base): document deploy pipeline + requirements

Covers the 5-stage provisioning flow, prerequisites, quick start
against TEMPLATE, offline client onboarding, and what must never
be committed."
```

### Task 2.7: Extend `base/README.md` with onboarding section

**Files:**
- Modify: `/mnt/c/Users/david/TrueData/truedata-gitlab/base/README.md`

- [ ] **Step 1: Append a "Client onboarding" section after "How to run standalone"**

Add to `base/README.md` (between the existing sections):

```markdown
## Client onboarding

Provisioning a new client (creating devices, dashboards, rule chains, Node-RED flows) is automated via the `deploy/` subfolder. See `deploy/README.md` for the full pipeline.

**TL;DR for a fresh client named `ACME`:**

```bash
# 1. Outside git: copy the template
cp -r base/deploy/TEMPLATE ~/truedata-clients/ACME

# 2. Populate files
cd ~/truedata-clients/ACME
mv DeviceImport.csv.example DeviceImport.csv             # edit with real devices
mv Niveles_de_Criticidad.csv.example "Niveles de Criticidad.csv"  # edit with real thresholds
# edit Client.json: { "Client": "ACME", "Model": "M3" }

# 3. Run the pipeline
cd <repo>/base/deploy
export CLIENT_DIR=~/truedata-clients/ACME
export $(grep -v '^#' ../../.env | xargs)
python env_client.py
```

Generated outputs (tokens, device credentials) stay in `~/truedata-clients/ACME/` and **must never be committed**.
```

- [ ] **Step 2: Update the TODO section**

Change the "MR-2" TODO line to a completed bullet: `- [x] **MR-2:** deploy automation (`deploy/`) + per-client provisioning templates` — **done in this MR**.

- [ ] **Step 3: Commit**

```bash
git add base/README.md
git commit -m "docs(base): add client onboarding section to module README"
```

### Task 2.8: Pre-MR checklist + push

- [ ] **Step 1: Secret scan**

Run:
```bash
cd /mnt/c/Users/david/TrueData/truedata-gitlab
git diff main...HEAD | grep -E '(airtrace|tenant@thingsboard\.org|tenantairtrace|sysadmin@thingsboard\.org|accessToken.*[A-Za-z0-9]{16,})' && echo "LEAK" || echo "CLEAN"
```
Expected: `CLEAN`.

- [ ] **Step 2: Compose validation still passes**

Run: `NODE_RED_CREDENTIAL_SECRET=dummy docker compose -f base/docker-compose.override.yml config > /dev/null && echo OK`
Expected: `OK`.

- [ ] **Step 3: Rebase onto `main`**

```bash
git fetch origin
git rebase origin/main
```

- [ ] **Step 4: Push and open MR**

```bash
git push -u origin feature/base/deploy-automation
```

Open MR (glab or web) with title `feat(base): deploy pipeline + client onboarding` and description describing the 5-script flow, TEMPLATE usage, and reference to `base/deploy/README.md`.

---

## MR-3: shared/simulator + OPC Client Contract

**Branch:** `feature/base/opc-client-contract` (named `base/` because the contract doc lives in `base/opc-client/`; the `shared/simulator/` addition rides along).
**Goal:** Ship a runnable DEMO simulator in `shared/simulator/` behind the `demo` Docker Compose profile, and document the **intended** OPC Client integration (OPC → Node-RED → TB) as a contract Neoradix can target.

**Before starting any task in this MR:** re-read `CONTRIBUTING.md`. This MR touches `shared/` for the first time in UCAM's contribution — verify whether `CONTRIBUTING.md` imposes any `shared/`-specific rules (maintainer ownership, different reviewer tagging) and adapt accordingly. Also: because this MR mixes two module areas (`base/` contract + `shared/` simulator) in a single branch, make sure the MR description explicitly calls that out so the reviewer does not flag it as scope creep.

### Task 3.1: Create the feature branch

- [ ] **Step 1**

```bash
cd /mnt/c/Users/david/TrueData/truedata-gitlab
git fetch origin
git checkout main && git pull origin main
git checkout -b feature/base/opc-client-contract
```

### Task 3.2: Create `shared/simulator/` service

**Files:**
- Create: `/mnt/c/Users/david/TrueData/truedata-gitlab/shared/simulator/Dockerfile`
- Create: `/mnt/c/Users/david/TrueData/truedata-gitlab/shared/simulator/src/simulador_sensores.py`
- Create: `/mnt/c/Users/david/TrueData/truedata-gitlab/shared/simulator/requirements.txt`
- Create: `/mnt/c/Users/david/TrueData/truedata-gitlab/shared/simulator/data/.gitkeep`
- Create: `/mnt/c/Users/david/TrueData/truedata-gitlab/shared/simulator/README.md`
- Source: `/mnt/c/Users/david/TrueData/TrueData-UCAM/src/dataloader/simulador_sensores.py`

- [ ] **Step 1: Port the simulator with sanitization**

```bash
cp /mnt/c/Users/david/TrueData/TrueData-UCAM/src/dataloader/simulador_sensores.py \
   /mnt/c/Users/david/TrueData/truedata-gitlab/shared/simulator/src/simulador_sensores.py
```

Apply edits:
- Replace hardcoded TB URL with `TB_URL = os.environ["TB_URL"]`.
- Replace hardcoded CSV path with `DATA_PATH = Path(os.environ.get("SIMULATOR_DATA_PATH", "/app/data/data.csv"))`.
- Replace hardcoded device token lookup (from `deploy/{Client}/DeviceimportCredentials_*.csv`) with either:
  - an env var `SIMULATOR_DEVICE_TOKEN` (simpler, one device per container), or
  - a container-mounted token CSV at `/app/tokens.csv` passed as `SIMULATOR_TOKENS_PATH`.

Pick the simpler path: single env var `SIMULATOR_DEVICE_TOKEN`. If a user wants multi-device simulation, they run multiple simulator containers with different tokens.

- Remove any code path that authenticates with `tenant@thingsboard.org` — the simulator needs only the device access token (the `/api/v1/{token}/telemetry` endpoint is token-auth, not user-auth).

- [ ] **Step 2: Create `requirements.txt`**

```text
requests>=2.31,<3
pandas>=2.0,<3
```

- [ ] **Step 3: Create Dockerfile**

```dockerfile
# Simulator for TRUEDATA DEMO mode.
# Reads a CSV of sensor readings and replays them to ThingsBoard.
# Lives in shared/ because it is a DEMO helper, not a production service.
# Activated by the `demo` Docker Compose profile.

FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

ENV TZ=UTC \
    TB_URL=http://thingsboard:9090 \
    SIMULATOR_DATA_PATH=/app/data/data.csv \
    SIMULATOR_DELAY_SECONDS=1.0

CMD ["python", "src/simulador_sensores.py"]
```

- [ ] **Step 4: Create `shared/simulator/README.md`**

```markdown
# Simulator (DEMO only)

**Purpose:** Replay a CSV of sensor readings into ThingsBoard for demos and local dev. Simulates what the OPC Client will eventually do in production — but **via a shortcut that diverges from the intended production path**.

## Known architectural divergence from PROD

The production data flow (per `../../base/opc-client/README.md`) is:

```
OPC Client ──HTTP POST──► Node-RED ──HTTP POST──► ThingsBoard
```

The simulator takes a shortcut:

```
Simulator ──HTTP POST /api/v1/{token}/telemetry──► ThingsBoard   (direct, bypasses Node-RED)
```

This is acceptable for DEMO because:
- It avoids depending on Node-RED's opc-ingest flow being populated
- It uses the same `/api/v1/{token}/telemetry` endpoint that the Rule Chain → Node-RED aggregation already expects downstream
- Aggregation (Node-RED medians/means) still runs because it is invoked by TB Rule Chains *after* ingestion, regardless of how data entered TB

It is **not acceptable for PROD** because:
- It doesn't exercise the OPC Client HTTP contract Neoradix will implement
- It would hide Node-RED integration issues

Replacing the simulator with the OPC Client is a one-container swap: Neoradix's container hits `${NODE_RED_URL}/api/opc-ingest` instead of `${TB_URL}/api/v1/{token}/telemetry`.

## Configuration

| Variable | Required | Description |
|---|---|---|
| `TB_URL` | yes | ThingsBoard base URL (e.g. `http://thingsboard:9090`) |
| `SIMULATOR_DEVICE_TOKEN` | yes | TB device access token to write telemetry to |
| `SIMULATOR_DATA_PATH` | no | CSV path inside container (default `/app/data/data.csv`) |
| `SIMULATOR_DELAY_SECONDS` | no | Pause between rows (default `1.0`) |

## Data file

Mount a CSV into `/app/data/data.csv`. Each row is one telemetry sample; each column is a metric. The first column should be timestamp (optional — the simulator will stamp with `now` if missing).

Example `data.csv`:

```csv
timestamp,flow,ph,chlorine
2026-04-14T12:00:00Z,120.5,7.2,0.8
2026-04-14T12:00:01Z,121.0,7.2,0.8
```

## Run standalone

```bash
docker build -t truedata-simulator:local .
docker run --rm \
  -e TB_URL=http://host.docker.internal:9090 \
  -e SIMULATOR_DEVICE_TOKEN=<token> \
  -v "$(pwd)/data:/app/data" \
  truedata-simulator:local
```

## Run as part of the demo stack

From repo root:

```bash
docker compose --profile base --profile demo up
```

The `demo` profile is defined in the root `docker-compose.yml` and includes this simulator.
```

- [ ] **Step 5: Validate Python parses**

Run: `python3 -c "import ast; ast.parse(open('/mnt/c/Users/david/TrueData/truedata-gitlab/shared/simulator/src/simulador_sensores.py').read())" && echo OK`
Expected: `OK`.

- [ ] **Step 6: Commit**

```bash
git add shared/simulator/
git commit -m "feat(shared): add simulator service for DEMO mode

Ports UCAM's simulador_sensores.py with env-based config. Lives in
shared/ because it's a DEMO helper. README explicitly documents the
architectural divergence from PROD (simulator goes direct to TB,
bypassing Node-RED) and the path Neoradix should follow instead."
```

### Task 3.3: Add `demo` profile to root `docker-compose.yml`

**Files:**
- Modify: `/mnt/c/Users/david/TrueData/truedata-gitlab/docker-compose.yml`

- [ ] **Step 1: Read current root compose**

Read: `/mnt/c/Users/david/TrueData/truedata-gitlab/docker-compose.yml` to confirm where to insert.

- [ ] **Step 2: Append the simulator service**

Before the `networks:` block at the bottom, insert:

```yaml
  # ============================================================================
  # SHARED: Simulator (DEMO only)
  # ============================================================================
  simulator:
    build:
      context: ./shared/simulator
    container_name: truedata-simulator
    environment:
      TB_URL: ${TB_URL:-http://thingsboard:9090}
      SIMULATOR_DEVICE_TOKEN: ${SIMULATOR_DEVICE_TOKEN:?SIMULATOR_DEVICE_TOKEN required in demo profile}
      SIMULATOR_DATA_PATH: /app/data/data.csv
      SIMULATOR_DELAY_SECONDS: ${SIMULATOR_DELAY_SECONDS:-1.0}
    volumes:
      - ./shared/simulator/data:/app/data:ro
    depends_on:
      thingsboard:
        condition: service_started
    networks: [truedata-net]
    profiles: [demo]
```

- [ ] **Step 3: Update root `.env.example`**

Append:

```bash
# ============================================================================
# SHARED: Simulator (DEMO only; --profile demo)
# ============================================================================
# TB device access token the simulator writes to
SIMULATOR_DEVICE_TOKEN=
# Pause between CSV rows (seconds)
SIMULATOR_DELAY_SECONDS=1.0
```

- [ ] **Step 4: Validate**

Run: `SIMULATOR_DEVICE_TOKEN=dummy NODE_RED_CREDENTIAL_SECRET=dummy docker compose --profile base --profile demo config > /dev/null && echo OK`
Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
git add docker-compose.yml .env.example
git commit -m "feat: add demo profile including simulator to root compose

Profile 'demo' activates shared/simulator service. Intended use:
  docker compose --profile base --profile demo up
Simulator requires SIMULATOR_DEVICE_TOKEN (fail-fast via :? operator)."
```

### Task 3.4: Create `base/node-red/flows/opc-ingest.json` skeleton

**Files:**
- Create: `/mnt/c/Users/david/TrueData/truedata-gitlab/base/node-red/flows/opc-ingest.json`

- [ ] **Step 1: Write a minimal Node-RED flow exposing the ingestion endpoint**

```json
[
  {
    "id": "opc-ingest-tab",
    "type": "tab",
    "label": "OPC Ingest (contract for Neoradix)",
    "disabled": false,
    "info": "Accepts HTTP POST from the OPC Client, validates schema, looks up device token, forwards to ThingsBoard. Contract documented in ../../opc-client/README.md"
  },
  {
    "id": "opc-ingest-http-in",
    "type": "http in",
    "z": "opc-ingest-tab",
    "name": "POST /api/opc-ingest",
    "url": "/api/opc-ingest",
    "method": "post",
    "upload": false,
    "swaggerDoc": "",
    "x": 140,
    "y": 100,
    "wires": [["opc-ingest-validate"]]
  },
  {
    "id": "opc-ingest-validate",
    "type": "function",
    "z": "opc-ingest-tab",
    "name": "validate schema",
    "func": "// Expected body: { device: string, measurements: { [metric]: number }, timestamp?: string }\nconst body = msg.payload || {};\nif (typeof body.device !== 'string' || typeof body.measurements !== 'object') {\n    msg.statusCode = 400;\n    msg.payload = { error: 'Invalid schema. Expected { device, measurements, timestamp? }' };\n    return [null, msg];\n}\nmsg.device = body.device;\nmsg.measurements = body.measurements;\nmsg.timestamp = body.timestamp;\nreturn [msg, null];",
    "outputs": 2,
    "x": 360,
    "y": 100,
    "wires": [["opc-ingest-lookup-token"], ["opc-ingest-http-response"]]
  },
  {
    "id": "opc-ingest-lookup-token",
    "type": "function",
    "z": "opc-ingest-tab",
    "name": "lookup device token (STUB)",
    "func": "// STUB — Neoradix or UCAM will replace with real token lookup.\n// Options:\n//   (a) Read a device->token map from a file/flow context populated at deploy time\n//   (b) Call TB REST API /api/tenant/devices?deviceName={x} + /api/device/{id}/credentials\n// For the contract documentation, returns 501 Not Implemented.\nmsg.statusCode = 501;\nmsg.payload = { error: 'OPC ingestion flow is a contract stub. Implement device-token lookup here.' };\nreturn msg;",
    "x": 620,
    "y": 100,
    "wires": [["opc-ingest-http-response"]]
  },
  {
    "id": "opc-ingest-http-response",
    "type": "http response",
    "z": "opc-ingest-tab",
    "name": "response",
    "x": 860,
    "y": 100,
    "wires": []
  }
]
```

- [ ] **Step 2: Validate JSON**

Run: `python3 -c "import json; json.load(open('/mnt/c/Users/david/TrueData/truedata-gitlab/base/node-red/flows/opc-ingest.json'))" && echo OK`
Expected: `OK`.

- [ ] **Step 3: Commit**

```bash
git add base/node-red/flows/opc-ingest.json
git commit -m "feat(base): add opc-ingest Node-RED flow skeleton

Implements http in → validate → (stub) lookup token → respond.
The token lookup is a STUB returning 501; real implementation will
come from UCAM or Neoradix once the deploy pipeline exposes a
device-token map to Node-RED."
```

### Task 3.5: Create `base/opc-client/README.md` contract

**Files:**
- Create: `/mnt/c/Users/david/TrueData/truedata-gitlab/base/opc-client/README.md`

- [ ] **Step 1: Write the contract document**

```markdown
# OPC Client (contract stub for Neoradix)

**Status:** NOT IMPLEMENTED. This folder contains only the integration contract UCAM expects Neoradix to target.

**Partner owning implementation:** Neoradix.
**Partner owning contract / target integration:** UCAM.

## Why this stub exists

The TRUEDATA `base/` module today runs on a DEMO simulator (`shared/simulator/`) that bypasses Node-RED and POSTs directly to ThingsBoard. That shortcut is acceptable for demos but does not exercise the intended production integration path.

This document defines the production path so Neoradix's OPC Client can be developed against a stable contract, and so UCAM can populate the Node-RED ingestion flow (`../node-red/flows/opc-ingest.json`) to match.

## Production data flow

```
┌──────────────────┐   HTTP POST /api/opc-ingest     ┌────────────────────┐
│   OPC Client     │ ──────────────────────────────► │     Node-RED       │
│   (Neoradix)     │                                 │  (opc-ingest flow) │
└──────────────────┘                                 └─────────┬──────────┘
                                                                │
                                                                │  HTTP POST
                                                                │  /api/v1/{token}/telemetry
                                                                ▼
                                                       ┌────────────────────┐
                                                       │   ThingsBoard      │
                                                       └─────────┬──────────┘
                                                                 │ (existing Rule Chain,
                                                                 │  unchanged)
                                                                 ▼
                                                       ┌────────────────────┐
                                                       │ Node-RED (agg)     │
                                                       └────────────────────┘
```

## HTTP contract

### Endpoint

`POST ${NODE_RED_URL}/api/opc-ingest`
Default: `http://node-red:1880/api/opc-ingest` inside the compose network.

### Request headers

- `Content-Type: application/json`
- Authentication: **TBD with Neoradix.** Options:
  - Shared token in `X-OPC-Token` header, validated by Node-RED against env var
  - Mutual TLS if the OPC Client runs in a different network segment
  - No auth (only acceptable if Node-RED's endpoint is bound to a private network)

### Request body

```json
{
  "device": "PUERTO.PLC11.CLORO_PLC11",
  "measurements": {
    "flow": 120.5,
    "ph": 7.2,
    "chlorine": 0.8
  },
  "timestamp": "2026-04-14T12:34:56Z"
}
```

Fields:
- `device` (string, required) — device name as registered in ThingsBoard. Node-RED looks up the corresponding TB access token.
- `measurements` (object, required) — flat map of metric name → numeric value. Keys must match the telemetry keys TB's Rule Chain expects.
- `timestamp` (string, optional) — ISO 8601. If omitted, Node-RED stamps with the current server time.

### Responses

| Code | Meaning |
|---|---|
| 200 | Accepted and forwarded to TB successfully |
| 400 | Invalid schema (missing `device` or `measurements`, wrong types) |
| 401 / 403 | Authentication failure (if auth is enabled) |
| 404 | Unknown device name (no token mapping found) |
| 501 | Endpoint present but token lookup not yet implemented (current state — see `../node-red/flows/opc-ingest.json`) |
| 502 | Node-RED reached but TB is unreachable or returned an error |

### Batch ingestion (future)

Single-device single-sample is the baseline. If Neoradix needs to send multi-device batches, we extend the contract:

```json
{
  "batch": [
    { "device": "...", "measurements": {...}, "timestamp": "..." },
    { "device": "...", "measurements": {...}, "timestamp": "..." }
  ]
}
```

This is a forward-compatible extension (the flow detects `batch` vs single-object shape).

## Neoradix integration checklist

When the OPC Client is ready:

- [ ] Neoradix delivers a container image that:
  - Reads OPC-UA (or OPC-DA via a Windows proxy) servers
  - Translates tags to the `device` / `measurements` schema above
  - POSTs to `${NODE_RED_URL}/api/opc-ingest` at the required frequency
- [ ] UCAM replaces the STUB in `../node-red/flows/opc-ingest.json` with real device-token lookup (reads from a map populated by `../deploy/2_Crear_Entorno_Cliente_ThingsBoard.py`)
- [ ] Add `opc-client` service to the root `docker-compose.yml` under a new `profile: opc` (mutually exclusive with `profile: demo`)
- [ ] Integration test: OPC Client container sends N samples → verify N appear as telemetry in TB

## Alternative paths considered (not chosen)

1. **OPC Client POSTs directly to TB** (what the simulator does today). Rejected for production because it bypasses Node-RED's opportunity to transform, enrich, or route; also bypasses the policy layer Node-RED can enforce (rate limiting, schema validation, dead-letter routing).

2. **OPC Client publishes to an MQTT broker, Node-RED subscribes.** Rejected because the rest of TRUEDATA `base/` is HTTP REST, partners confirmed HTTP for Neoradix, and adding an MQTT broker just for this path is overkill.
```

- [ ] **Step 2: Commit**

```bash
git add base/opc-client/README.md
git commit -m "docs(base): document OPC Client HTTP contract (stub)

Formalizes the integration point Neoradix will target:
POST /api/opc-ingest on Node-RED, JSON schema, response codes,
batch extension, and handoff checklist. Flags the DEMO simulator
as a documented divergence from this path."
```

### Task 3.6: Extend `base/README.md` with OPC Client section

**Files:**
- Modify: `/mnt/c/Users/david/TrueData/truedata-gitlab/base/README.md`

- [ ] **Step 1: Add a new top-level section "OPC Client integration (pending Neoradix)"**

Insert after "Client onboarding":

```markdown
## OPC Client integration (pending Neoradix)

Production data ingestion will flow from OPC Client → Node-RED → ThingsBoard over HTTP. The HTTP contract is documented in `opc-client/README.md`; the Node-RED skeleton flow lives at `node-red/flows/opc-ingest.json`.

Current state:

- ✅ Contract defined (`opc-client/README.md`)
- ✅ Node-RED endpoint skeleton (`node-red/flows/opc-ingest.json`) — responds with 501 until Neoradix and UCAM complete integration
- ⏳ Neoradix implementation pending
- ⏳ Device-token lookup in the Node-RED flow pending (needs `deploy/` to publish the mapping)

DEMO mode uses `shared/simulator/` which POSTs directly to ThingsBoard (bypassing Node-RED). This is explicitly documented as a known divergence — see `../shared/simulator/README.md`.
```

- [ ] **Step 2: Update TODO section**

Mark MR-3 complete: `- [x] **MR-3:** shared/simulator + opc-client contract`

- [ ] **Step 3: Commit**

```bash
git add base/README.md
git commit -m "docs(base): reference OPC Client integration in module README"
```

### Task 3.7: Smoke test the demo stack

- [ ] **Step 1: Prepare env**

```bash
cd /mnt/c/Users/david/TrueData/truedata-gitlab
cp .env.example .env
# Generate secrets
sed -i 's|^NODE_RED_CREDENTIAL_SECRET=$|NODE_RED_CREDENTIAL_SECRET='"$(openssl rand -hex 32)"'|' .env
# Provide a dummy simulator token (we'll replace after bringing TB up and creating a device)
sed -i 's|^SIMULATOR_DEVICE_TOKEN=$|SIMULATOR_DEVICE_TOKEN=placeholder-will-replace|' .env
```

- [ ] **Step 2: Bring up base only first (no simulator)**

```bash
docker compose --profile base up -d --build
sleep 120   # wait for TB
```

- [ ] **Step 3: Create a test device via TB UI or API, collect its token**

```bash
# Log in and create a device (adjust if TB defaults were rotated)
curl -s -c /tmp/tbcookies -X POST http://localhost:9090/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"tenant@thingsboard.org","password":"tenant"}' > /tmp/tblogin.json
TOKEN=$(python3 -c "import json; print(json.load(open('/tmp/tblogin.json'))['token'])")
curl -s -b /tmp/tbcookies -X POST http://localhost:9090/api/device \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"name":"simulator-test","type":"sensor"}' > /tmp/device.json
DEV_ID=$(python3 -c "import json; print(json.load(open('/tmp/device.json'))['id']['id'])")
curl -s -b /tmp/tbcookies http://localhost:9090/api/device/$DEV_ID/credentials \
  -H "Authorization: Bearer $TOKEN" > /tmp/creds.json
SIM_TOKEN=$(python3 -c "import json; print(json.load(open('/tmp/creds.json'))['credentialsId'])")
echo "Simulator token: $SIM_TOKEN"
```

- [ ] **Step 4: Update .env with the real token and restart with demo profile**

```bash
sed -i "s|^SIMULATOR_DEVICE_TOKEN=.*|SIMULATOR_DEVICE_TOKEN=$SIM_TOKEN|" .env
docker compose --profile base --profile demo up -d --build
```

- [ ] **Step 5: Put a sample CSV in shared/simulator/data/**

```bash
cat > shared/simulator/data/data.csv <<'EOF'
timestamp,flow,ph
2026-04-14T12:00:00Z,120.5,7.2
2026-04-14T12:00:01Z,121.0,7.3
2026-04-14T12:00:02Z,120.8,7.1
EOF
docker compose restart simulator
sleep 10
```

- [ ] **Step 6: Verify telemetry arrived in TB**

```bash
curl -s -b /tmp/tbcookies \
  "http://localhost:9090/api/plugins/telemetry/DEVICE/$DEV_ID/values/timeseries?keys=flow,ph" \
  -H "Authorization: Bearer $TOKEN"
```
Expected: JSON with flow and ph values matching the CSV.

- [ ] **Step 7: Teardown**

```bash
docker compose --profile base --profile demo down -v
rm shared/simulator/data/data.csv
```

- [ ] **Step 8: If smoke test failed, iterate; commit fixes as additional commits**

### Task 3.8: Pre-MR checklist + push MR-3

- [ ] **Step 1: Secret scan (especially since we generated tokens locally)**

Run:
```bash
cd /mnt/c/Users/david/TrueData/truedata-gitlab
git diff main...HEAD | grep -E '(airtrace|tenant@thingsboard\.org|accessToken.*[A-Za-z0-9]{16,}|SIMULATOR_DEVICE_TOKEN=[A-Za-z0-9])' && echo "LEAK" || echo "CLEAN"
```
Expected: `CLEAN`.

- [ ] **Step 2: Compose validation**

Run: `SIMULATOR_DEVICE_TOKEN=x NODE_RED_CREDENTIAL_SECRET=x docker compose --profile base --profile demo config > /dev/null && echo OK`
Expected: `OK`.

- [ ] **Step 3: Rebase on main**

```bash
git fetch origin
git rebase origin/main
```

- [ ] **Step 4: Push and open MR**

```bash
git push -u origin feature/base/opc-client-contract
```

MR title: `feat(base,shared): simulator (DEMO) + OPC Client contract stub`

MR description should include: the full demo stack smoke test commands from Task 3.7, the contract summary from `base/opc-client/README.md`, and an explicit callout that the Node-RED flow is a stub (returns 501) pending the device-token mapping work.

---

## Self-Review Checklist (mandatory before requesting review on each MR)

**This checklist is the minimum bar, not a replacement for CONTRIBUTING.md. Re-read `CONTRIBUTING.md` first; use this as a local cross-check.**

### CONTRIBUTING.md compliance

- [ ] Re-read `/mnt/c/Users/david/TrueData/truedata-gitlab/CONTRIBUTING.md` sections: "Branching Strategy", "Merge Request (MR) Process", "Module Development Guidelines", "Commit Message Guidelines", "Code Review Checklist"
- [ ] **Branch name** matches `feature/base/<short-description>` — no typos, hyphen-separated, lowercase
- [ ] **Branch created from latest `origin/main`** (not from an unmerged feature branch, unless unavoidable and noted in MR description)
- [ ] **All commits** use `<type>(<module>): <subject>` format with type in `{feat, fix, docs, refactor, test, chore}`
- [ ] **Rebased on latest `origin/main`** before pushing
- [ ] **Target branch of MR** is `main`
- [ ] **Module maintainer assigned** as reviewer (base module: `@ucam-lead` or `@neoradix-opc` per CONTRIBUTING.md "Assign Reviewer" subsection)
- [ ] **MR description** uses the template: What / Why / How to Test / Files Changed / Notes
- [ ] **Module README follows the 10-section schema**: purpose, responsible partner, technologies, I/O specs, integration points, how to build, how to run standalone, env vars, testing, TODO/roadmap
- [ ] If CSVs or config files are introduced, they respect `.gitignore` rules (real client data never committed; only `.example` files versioned)
- [ ] No force-push planned during review — feedback addressed via new commits

### Technical validation

- [ ] `NODE_RED_CREDENTIAL_SECRET=dummy docker compose -f base/docker-compose.override.yml config > /dev/null` passes
- [ ] `NODE_RED_CREDENTIAL_SECRET=dummy docker compose --profile base config > /dev/null` passes (and `--profile demo` with `SIMULATOR_DEVICE_TOKEN=x` if MR-3)
- [ ] **No secrets in diff:** `git diff main...HEAD | grep -E '(airtrace|tenant@thingsboard\.org|tenantairtrace|sysadmin@thingsboard\.org|accessToken.*[A-Za-z0-9]{16,}|AWS_[A-Z_]+=.*[A-Za-z0-9])'` returns nothing
- [ ] **No references to dropped files:** `grep -rn 'locustfile\|fetch_tokens_remote\|ParametrosConfiguracion' base/ shared/ 2>/dev/null` returns nothing
- [ ] **Env vars documented:** every env var referenced in compose files or Python scripts appears in root `.env.example` with a description
- [ ] Pre-commit hook (from PF.2) still installed and active

### Code quality & scope discipline

- [ ] No unrelated refactors bundled into the MR
- [ ] No comments explaining WHAT the code does (only WHY for non-obvious invariants)
- [ ] No TODOs for work that should be done in this MR (legitimate future-work TODOs are fine in README)
- [ ] If this MR diverges from `CONTRIBUTING.md` (e.g., mixes `base/` and `shared/` like MR-3), the divergence is explicitly called out in the MR description with justification

### Post-merge hygiene (after reviewer merges)

- [ ] Delete local branch: `git branch -d feature/base/<descr>`
- [ ] Delete remote branch: `git push origin --delete feature/base/<descr>`
- [ ] Update this plan file: mark the MR's tasks as complete, refresh the "Status" of the corresponding Appendix A divergence row

---

## Appendix A: Known divergences from the scaffold (living list)

| # | Divergence | Where documented | Status |
|---|---|---|---|
| 1 | HTTP REST throughout; no MQTT bus in `base/` | `base/README.md` purpose section + OPC Client README "alternatives considered" | MR-1 |
| 2 | Node-RED role is post-TB aggregator (+ future OPC ingestion), not primary hub | `base/node-red/README.md` + `base/README.md` I/O section | MR-1 |
| 3 | Simulator goes direct to TB (not through Node-RED) | `shared/simulator/README.md` + `base/README.md` OPC integration section | MR-3 |
| 4 | OPC Client contract is HTTP JSON to Node-RED; no OPC-UA→MQTT path | `base/opc-client/README.md` | MR-3 |
| 5 | `base/` delivered in DEMO state; production requires OPC Client + token lookup in Node-RED flow | `base/README.md` TODO section | all MRs |

## Appendix B: Files intentionally NOT ported

Documented for reviewers so they know the omissions are deliberate:

- **`src/` (ML pipelines)** — `ml-classical` module is standby per team decision. No contribution.
- **Root-level Dockerfiles** (`Dockerfile`, `DockerfileETL`, `DockerfileInferenceCPU`, `DockerfileTrainPipeline`, `DockerfileTest`, `DockerfileEnvClient`) — all ML-pipeline related or obsolete.
- **`locustfile.py`** — load test referencing a credential file; not deliverable material.
- **`entrypoint.sh`** — runs `pip freeze` at runtime, antipattern; superseded by our Dockerfiles.
- **`fetch_tokens_remote.py`** — offline recovery tool, kept in UCAM's private repo.
- **`INJECTION_SETUP.md`, `SIMULATION_GUIDE.md`** — dev-mode ad-hoc docs, superseded by `shared/simulator/README.md`.
- **`docs/openapi.yaml`, `swagger.html`, `redoc.html`** — misaligned with actual code; regenerate when stable.
- **`images/`** — screenshots, not deliverable.
- **`system_sizing/`** — potential separate contribution (`shared/system-sizing/` or `docs/`). Out of scope of this plan; will be decided with Libelium.
- **`deploy/MCT/`, `deploy/ESAMUR/`** — contain real client tokens in clear; **must not** enter the GitLab repo at any point.
- **`deploy/t`, `deploy/ParametrosConfiguracion.txt`, `deploy/2.2 Manual... .docx`** — artifacts/leftovers.

## Appendix C: Mapping of UCAM repo files → GitLab repo destinations

| Source (`TrueData-UCAM/`) | Destination (`truedata-gitlab/`) | MR |
|---|---|---|
| `truedata-thingsboard/docker-compose.yml` | merged into `base/docker-compose.override.yml` | MR-1 |
| `truedata-thingsboard/` config mounts (if any) | `base/thingsboard/config/` | MR-1 |
| `truedata-nodered/settings.js` | `base/node-red/settings.js` (sanitized) | MR-1 |
| `truedata-nodered/docker-compose.yml` | merged into `base/docker-compose.override.yml` | MR-1 |
| `deploy/APIThingsboard.py` | `base/deploy/APIThingsboard.py` (sanitized) | MR-2 |
| `deploy/env_client.py`, `deploy/1_*.py`, `deploy/2_*.py`, `deploy/3_*.py`, `deploy/4_*.py` | `base/deploy/` (sanitized) | MR-2 |
| `deploy/Plantillas/` | `base/deploy/Plantillas/` | MR-2 |
| `deploy/Client.json` | `base/deploy/TEMPLATE/Client.json` (genericized) | MR-2 |
| `src/dataloader/simulador_sensores.py` | `shared/simulator/src/simulador_sensores.py` (sanitized) | MR-3 |
| `src/dataloader/Credenciales.txt` | NOT ported (handled via env var) | — |

---

## Appendix D: Baseline verification log

Populated during Phase 0 Task 0.3 Step 9 and Pre-Flight Task PF.6 Step 3. Records which verification steps passed/failed, before and after cleanup. Useful to discern later whether a regression is our fault or pre-existing.

| Date | Phase | Step | Outcome | Notes |
|---|---|---|---|---|
| *TBD* | 0.3 | 1 — compose config | | |
| *TBD* | 0.3 | 2 — service list | | |
| *TBD* | 0.3 | 3 — TB + Node-RED up | | |
| *TBD* | 0.3 | 4 — TB HTTP ready | | |
| *TBD* | 0.3 | 5 — Node-RED HTTP | | |
| *TBD* | 0.3 | 6 — deploy pipeline (optional) | | |
| *TBD* | 0.3 | 7 — simulator (optional) | | |
| *TBD* | PF.6 | 1 — re-run 0.3 steps | | |
| *TBD* | PF.6 | 2 — diff against baseline | | |

If a row's outcome is FAIL, add a follow-up row describing the remediation decision (Option A fix, Option B accept, Option C escalate).

---

**End of plan.**
