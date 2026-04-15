#!/usr/bin/env bash
# =============================================================================
# Secret scanner for TRUEDATA GitLab contribution
#
# Scans the git diff between current branch and main for patterns that
# indicate leaked secrets. Run before every commit and before pushing MRs.
#
# Usage:
#   bash secret_scan.sh                    # scan diff vs main
#   bash secret_scan.sh --staged           # scan only staged changes
#   bash secret_scan.sh --file <path>      # scan a specific file
#
# Exit codes:
#   0 = clean (no secrets found)
#   1 = secrets detected
#   2 = not in a git repo
# =============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# --- Parse arguments ---
MODE="diff"
TARGET=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --staged) MODE="staged"; shift ;;
        --file)   MODE="file"; TARGET="$2"; shift 2 ;;
        *)        echo "Unknown option: $1"; exit 2 ;;
    esac
done

# --- Verify we're in a git repo ---
if ! git rev-parse --is-inside-work-tree &>/dev/null; then
    echo -e "${RED}ERROR: Not inside a git repository${NC}"
    exit 2
fi

# --- Get the content to scan ---
case $MODE in
    diff)
        CONTENT=$(git diff main...HEAD 2>/dev/null || git diff HEAD 2>/dev/null || echo "")
        SCAN_DESC="diff main...HEAD"
        ;;
    staged)
        CONTENT=$(git diff --cached 2>/dev/null || echo "")
        SCAN_DESC="staged changes"
        ;;
    file)
        if [[ ! -f "$TARGET" ]]; then
            echo -e "${RED}ERROR: File not found: $TARGET${NC}"
            exit 2
        fi
        CONTENT=$(cat "$TARGET")
        SCAN_DESC="file $TARGET"
        ;;
esac

if [[ -z "$CONTENT" ]]; then
    echo -e "${GREEN}✅ No content to scan ($SCAN_DESC is empty)${NC}"
    exit 0
fi

# --- Define secret patterns ---
# Each pattern: REGEX|SEVERITY|DESCRIPTION
PATTERNS=(
    'credentialSecret.*["'"'"']airtrace["'"'"']|CRITICAL|Node-RED credentialSecret "airtrace"'
    'tenant@thingsboard\.org|HIGH|Hardcoded TB admin email'
    'sysadmin@thingsboard\.org|HIGH|Hardcoded TB sysadmin email'
    'tenantairtrace|HIGH|Hardcoded Node-RED password "tenantairtrace"'
    'accessToken.*[A-Za-z0-9]{16,}|HIGH|Possible TB device access token'
    'AWS_ACCESS_KEY_ID.*=.*[A-Za-z0-9]{10,}|CRITICAL|AWS access key'
    'AWS_SECRET_ACCESS_KEY.*=.*[A-Za-z0-9]{10,}|CRITICAL|AWS secret key'
    'glpat-[A-Za-z0-9_\-]{20,}|CRITICAL|GitLab Personal Access Token'
    'ghp_[A-Za-z0-9]{36,}|CRITICAL|GitHub Personal Access Token'
    'PRIVATE.KEY|HIGH|Private key marker'
    'password.*=.*["'"'"'][^${"'"'"']{8,}["'"'"']|MEDIUM|Possible hardcoded password (non-env-var)'
)

# --- Scan ---
FOUND=0
FINDINGS=""

for entry in "${PATTERNS[@]}"; do
    IFS='|' read -r PATTERN SEVERITY DESC <<< "$entry"

    MATCHES=$(echo "$CONTENT" | grep -nE "$PATTERN" 2>/dev/null || true)

    if [[ -n "$MATCHES" ]]; then
        FOUND=1
        # Color based on severity
        case $SEVERITY in
            CRITICAL) COLOR=$RED ;;
            HIGH)     COLOR=$YELLOW ;;
            *)        COLOR=$YELLOW ;;
        esac
        FINDINGS+=$(printf "\n  ${COLOR}[${SEVERITY}]${NC} ${DESC}\n")

        # Show first 3 matches (truncated to avoid dumping entire secrets)
        COUNT=0
        while IFS= read -r match; do
            COUNT=$((COUNT + 1))
            if [[ $COUNT -le 3 ]]; then
                # Truncate long lines and mask potential secrets
                TRUNCATED=$(echo "$match" | head -c 120)
                FINDINGS+=$(printf "    │ %s\n" "$TRUNCATED")
            fi
        done <<< "$MATCHES"

        TOTAL=$(echo "$MATCHES" | wc -l)
        if [[ $TOTAL -gt 3 ]]; then
            FINDINGS+=$(printf "    └─ ... and %d more matches\n" $((TOTAL - 3)))
        fi
    fi
done

# --- Report ---
echo ""
echo "═══════════════════════════════════════════════════════"
echo "  TRUEDATA Secret Scan — $SCAN_DESC"
echo "═══════════════════════════════════════════════════════"
echo ""

if [[ $FOUND -eq 0 ]]; then
    echo -e "${GREEN}  ✅ CLEAN — no secrets detected${NC}"
    echo ""
    exit 0
else
    echo -e "${RED}  ❌ SECRETS DETECTED — do NOT commit/push${NC}"
    echo -e "$FINDINGS"
    echo ""
    echo -e "  ${YELLOW}Fix the issues above before proceeding.${NC}"
    echo -e "  ${YELLOW}Run 'python sanitize_check.py <file>' for specific fix suggestions.${NC}"
    echo ""
    exit 1
fi
