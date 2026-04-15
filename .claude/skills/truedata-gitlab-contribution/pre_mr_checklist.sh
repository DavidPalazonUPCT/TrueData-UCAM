#!/usr/bin/env bash
# =============================================================================
# Pre-MR Checklist for TRUEDATA GitLab contribution
#
# Runs all validation checks required before pushing an MR branch.
# Maps directly to the Self-Review Checklist in the implementation plan
# and the Code Review Checklist from CONTRIBUTING.md.
#
# Usage:
#   bash pre_mr_checklist.sh                   # run all checks
#   bash pre_mr_checklist.sh --mr 1            # run checks specific to MR-1
#   bash pre_mr_checklist.sh --mr 2            # run checks specific to MR-2
#   bash pre_mr_checklist.sh --mr 3            # run checks specific to MR-3
#
# Exit codes:
#   0 = all checks pass
#   1 = one or more checks failed
# =============================================================================

set -uo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

MR_NUM="${1:-all}"
if [[ "$1" == "--mr" ]] && [[ -n "${2:-}" ]]; then
    MR_NUM="$2"
fi

FAIL_COUNT=0
PASS_COUNT=0
WARN_COUNT=0
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

check_pass() {
    echo -e "  ${GREEN}✅ PASS${NC}: $1"
    PASS_COUNT=$((PASS_COUNT + 1))
}

check_fail() {
    echo -e "  ${RED}❌ FAIL${NC}: $1"
    echo -e "       ${YELLOW}$2${NC}"
    FAIL_COUNT=$((FAIL_COUNT + 1))
}

check_warn() {
    echo -e "  ${YELLOW}⚠️  WARN${NC}: $1"
    echo -e "       $2"
    WARN_COUNT=$((WARN_COUNT + 1))
}

# --- Header ---
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  TRUEDATA Pre-MR Checklist"
echo "  Target: MR-${MR_NUM}"
echo "═══════════════════════════════════════════════════════════════"
echo ""

# --- 1. Git state checks ---
echo -e "${CYAN}[1/7] Git state${NC}"

BRANCH=$(git branch --show-current 2>/dev/null || echo "DETACHED")
if [[ "$BRANCH" == feature/base/* ]] || [[ "$BRANCH" == feature/shared/* ]]; then
    check_pass "Branch name follows convention: $BRANCH"
else
    check_fail "Branch name doesn't match 'feature/base/<desc>' or 'feature/shared/<desc>'" \
        "Current branch: $BRANCH"
fi

if git diff --quiet 2>/dev/null; then
    check_pass "Working tree is clean"
else
    check_warn "Working tree has uncommitted changes" \
        "Run 'git status' to see pending changes"
fi

# Check rebase status
if git merge-base --is-ancestor origin/main HEAD 2>/dev/null; then
    check_pass "Branch includes latest origin/main"
else
    check_warn "Branch may not be rebased on latest origin/main" \
        "Run: git fetch origin && git rebase origin/main"
fi

echo ""

# --- 2. Commit message format ---
echo -e "${CYAN}[2/7] Commit messages${NC}"

BAD_COMMITS=0
while IFS= read -r commit_line; do
    HASH=$(echo "$commit_line" | cut -d' ' -f1)
    MSG=$(echo "$commit_line" | cut -d' ' -f2-)

    if echo "$MSG" | grep -qE '^(feat|fix|docs|refactor|test|chore)\([a-z\-]+\):'; then
        continue
    elif echo "$MSG" | grep -qE '^(feat|fix|docs|refactor|test|chore):'; then
        continue  # Root-level change without module scope is acceptable
    else
        check_fail "Commit $HASH: message doesn't follow convention" \
            "Message: '$MSG' — Expected: <type>(<module>): <subject>"
        BAD_COMMITS=$((BAD_COMMITS + 1))
    fi
done < <(git log --oneline main..HEAD 2>/dev/null || true)

if [[ $BAD_COMMITS -eq 0 ]]; then
    COMMIT_COUNT=$(git rev-list --count main..HEAD 2>/dev/null || echo 0)
    check_pass "All $COMMIT_COUNT commits follow convention"
fi

echo ""

# --- 3. Secret scan ---
echo -e "${CYAN}[3/7] Secret scan${NC}"

if bash "$SCRIPT_DIR/secret_scan.sh" > /dev/null 2>&1; then
    check_pass "No secrets detected in diff"
else
    check_fail "Secrets detected in diff" \
        "Run: bash $SCRIPT_DIR/secret_scan.sh for details"
fi

# Extra: check for references to dropped files
DROPPED_REFS=$(grep -rnE 'locustfile|fetch_tokens_remote|ParametrosConfiguracion' \
    base/ shared/ 2>/dev/null | grep -v '\.git/' || true)
if [[ -z "$DROPPED_REFS" ]]; then
    check_pass "No references to dropped files"
else
    check_fail "References to dropped files found" \
        "$(echo "$DROPPED_REFS" | head -3)"
fi

echo ""

# --- 4. Docker Compose validation ---
echo -e "${CYAN}[4/7] Docker Compose validation${NC}"

# Base standalone
if NODE_RED_CREDENTIAL_SECRET=dummy \
   docker compose -f base/docker-compose.override.yml config > /dev/null 2>&1; then
    check_pass "base/docker-compose.override.yml validates"
else
    check_fail "base/docker-compose.override.yml fails validation" \
        "Run: NODE_RED_CREDENTIAL_SECRET=dummy docker compose -f base/docker-compose.override.yml config"
fi

# Root compose (may warn for missing modules — that's OK)
if NODE_RED_CREDENTIAL_SECRET=dummy \
   docker compose config > /dev/null 2>&1; then
    check_pass "Root docker-compose.yml validates"
else
    check_warn "Root docker-compose.yml has validation issues" \
        "May be expected if other modules aren't ported yet"
fi

# MR-3 specific: demo profile
if [[ "$MR_NUM" == "3" ]] || [[ "$MR_NUM" == "all" ]]; then
    if SIMULATOR_DEVICE_TOKEN=x NODE_RED_CREDENTIAL_SECRET=x \
       docker compose --profile base --profile demo config > /dev/null 2>&1; then
        check_pass "Demo profile (--profile base --profile demo) validates"
    else
        check_fail "Demo profile fails validation" \
            "Run: SIMULATOR_DEVICE_TOKEN=x NODE_RED_CREDENTIAL_SECRET=x docker compose --profile base --profile demo config"
    fi
fi

echo ""

# --- 5. .env.example completeness ---
echo -e "${CYAN}[5/7] Environment variable documentation${NC}"

if [[ -f .env.example ]]; then
    # Extract env vars from compose files and check they're documented
    COMPOSE_VARS=$(grep -ohE '\$\{[A-Z_]+' base/docker-compose.override.yml 2>/dev/null \
        | sed 's/\${//' | sort -u || true)

    MISSING_VARS=""
    for var in $COMPOSE_VARS; do
        if ! grep -q "^${var}=" .env.example 2>/dev/null && \
           ! grep -q "^# .*${var}" .env.example 2>/dev/null; then
            MISSING_VARS+="$var "
        fi
    done

    if [[ -z "$MISSING_VARS" ]]; then
        check_pass "All compose env vars documented in .env.example"
    else
        check_fail "Env vars missing from .env.example" \
            "Missing: $MISSING_VARS"
    fi
else
    check_fail ".env.example not found" \
        "Create .env.example at the repo root with all required variables"
fi

echo ""

# --- 6. Module README check ---
echo -e "${CYAN}[6/7] Module README schema${NC}"

README_FILE="base/README.md"
if [[ -f "$README_FILE" ]]; then
    SECTIONS_FOUND=0
    SECTIONS_MISSING=""

    for section in "Purpose" "partner" "Technologies" "Input" "Integration" \
                   "build" "run" "Environment" "Testing" "TODO"; do
        if grep -qi "$section" "$README_FILE" 2>/dev/null; then
            SECTIONS_FOUND=$((SECTIONS_FOUND + 1))
        else
            SECTIONS_MISSING+="$section "
        fi
    done

    if [[ $SECTIONS_FOUND -ge 9 ]]; then
        check_pass "base/README.md has $SECTIONS_FOUND/10 required sections"
    else
        check_fail "base/README.md missing sections" \
            "Missing: $SECTIONS_MISSING"
    fi
else
    check_warn "base/README.md not found" \
        "Expected for MR-1+"
fi

echo ""

# --- 7. Python syntax check ---
echo -e "${CYAN}[7/7] Python file syntax${NC}"

PY_ERRORS=0
while IFS= read -r pyfile; do
    if ! python3 -c "import ast; ast.parse(open('$pyfile').read())" 2>/dev/null; then
        check_fail "Syntax error in $pyfile" \
            "Run: python3 -c \"import ast; ast.parse(open('$pyfile').read())\""
        PY_ERRORS=$((PY_ERRORS + 1))
    fi
done < <(find base/ shared/ -name '*.py' -type f 2>/dev/null || true)

if [[ $PY_ERRORS -eq 0 ]]; then
    PY_COUNT=$(find base/ shared/ -name '*.py' -type f 2>/dev/null | wc -l || echo 0)
    check_pass "All $PY_COUNT Python files parse successfully"
fi

# --- Summary ---
echo ""
echo "═══════════════════════════════════════════════════════════════"
TOTAL=$((PASS_COUNT + FAIL_COUNT + WARN_COUNT))
echo -e "  Results: ${GREEN}${PASS_COUNT} passed${NC}, ${RED}${FAIL_COUNT} failed${NC}, ${YELLOW}${WARN_COUNT} warnings${NC} (${TOTAL} total)"

if [[ $FAIL_COUNT -eq 0 ]]; then
    echo -e "  ${GREEN}✅ Ready to push${NC}"
    echo "═══════════════════════════════════════════════════════════════"
    exit 0
else
    echo -e "  ${RED}❌ Fix ${FAIL_COUNT} failure(s) before pushing${NC}"
    echo "═══════════════════════════════════════════════════════════════"
    exit 1
fi
