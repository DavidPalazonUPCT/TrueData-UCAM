# Phase & Task Reference

Quick reference for navigating the contribution plan. Use this to determine
where you are, what's next, and what can be parallelized.

## Phase overview

```
Phase 0: Baseline Audit (UCAM repo, read-only)
  └─ Task 0.1: File inventory
  └─ Task 0.2: Git tag (rollback safety)
  └─ Task 0.3: Verify existing stack runs

Pre-Flight (local only, zero push to GitLab)
  └─ PF.1: Verify both workspaces ready
  └─ PF.2: Install pre-commit secret hook
  └─ PF.3: Rotate credentials (USER TASK, offline)
  └─ PF.4: Delete SECRETS (Tier 1, auto)
  └─ PF.5: Delete RUIDO (Tier 2, needs user confirmation)
  └─ PF.6: Re-verify after cleanup
  └─ PF.7: Update .gitignore
  └─ PF.8: Merge cleanup branch (user decides)

MR-1: base/ Infrastructure
  └─ Task 1.1: Create feature branch
  └─ Task 1.2: Create base/thingsboard/          ─┐ PARALLELIZABLE
  └─ Task 1.3: Create base/node-red/             ─┘
  └─ Task 1.4: Create docker-compose.override.yml  (after 1.2+1.3)
  └─ Task 1.5: Update .env.example                 (after 1.4)
  └─ Task 1.6: Smoke test                          (after 1.5)
  └─ Task 1.7: Write base/README.md                (after 1.6)
  └─ Task 1.8: Pre-MR checklist
  └─ Task 1.9: Push and open MR

MR-2: base/deploy/ Automation
  └─ Task 2.1: Create feature branch
  └─ Task 2.2: Port APIThingsboard.py              (FIRST — other scripts import it)
  └─ Task 2.3: Port numbered deploy scripts        (after 2.2, per-file parallelizable)
  └─ Task 2.4: Port Plantillas/                  ─┐ PARALLELIZABLE
  └─ Task 2.5: Create TEMPLATE/                  ─┘
  └─ Task 2.6: Create requirements.txt + README
  └─ Task 2.7: Extend base/README.md
  └─ Task 2.8: Pre-MR checklist + push

MR-3: shared/simulator + OPC Contract
  └─ Task 3.1: Create feature branch
  └─ Task 3.2: Create shared/simulator/          ─┐ PARALLELIZABLE
  └─ Task 3.4: Create opc-ingest.json skeleton   ─│
  └─ Task 3.5: Create opc-client/README.md       ─┘
  └─ Task 3.3: Add demo profile to root compose    (after 3.2)
  └─ Task 3.6: Extend base/README.md
  └─ Task 3.7: Smoke test demo stack
  └─ Task 3.8: Pre-MR checklist + push
```

## Subagent delegation patterns

### Pattern: fork for independent file creation

When two tasks create files in separate directories with no cross-dependencies,
fork them. Example for MR-1:

```
Master:
  1. Complete Task 1.1 (create branch) — sequential
  2. Fork Task 1.2 (thingsboard/) and Task 1.3 (node-red/) — parallel
  3. Wait for both to complete
  4. Review their output, commit (with user confirmation)
  5. Continue with Task 1.4 (compose) — sequential
```

### Subagent prompt template

When delegating to a fork/subagent, include:

```
You are working on the TRUEDATA GitLab contribution, specifically Task X.Y.

## Context
- Target repo: /mnt/c/Users/david/TrueData/truedata-gitlab
- Source repo (read-only): /mnt/c/Users/david/TrueData/TrueData-UCAM
- Branch: feature/base/<current-branch>

## Your task
<paste the full task from the plan>

## Sanitization rules
<paste the sanitization table from SKILL.md>

## Important
- Do NOT commit. Create/modify files only.
- Do NOT push anything.
- Run sanitize_check.py on every file you create/modify.
- Report back what you created and any issues encountered.
```

### Pattern: sequential with confirmation gates

For tasks that involve commits:

```
1. Execute the task (create/modify files)
2. Run sanitize_check.py on modified files
3. Run secret_scan.sh --staged
4. Show the user: staged files + proposed commit message
5. Wait for user confirmation
6. Commit
7. Proceed to next task
```

## Confirmation gates (moderate autonomy)

The following actions require explicit user confirmation:

| Action | What to show the user |
|---|---|
| `git commit` | Staged files list + full commit message |
| `git push` | Branch name + remote + number of commits |
| `git rebase` | Current branch + target + warning about conflicts |
| Opening an MR | Title + description draft |
| Deleting files (PF.4/PF.5) | List of files to delete + rationale |
| Merging branches (PF.8) | Source → target + commit count |

The following actions can proceed automatically:

| Action | Why auto |
|---|---|
| Creating files | Reversible, no side effects |
| Reading files | Read-only |
| Running validation scripts | Read-only checks |
| `git add` (staging) | Reversible with `git reset` |
| `docker compose config` | Validation only, no containers started |
| `docker compose up/down` | Local dev, user expects it |

## Task status tracking

When executing tasks, maintain a status log. After each task, record:

```markdown
### Task X.Y: <name>
- **Status:** ✅ Complete / ⏳ In progress / ❌ Blocked / ⏭️ Skipped
- **Commits:** <hash> <message> (if any)
- **Issues:** <any problems encountered>
- **Notes:** <anything the next task should know>
```
