#!/usr/bin/env bash
# =============================================================================
# Commit message validator for TRUEDATA GitLab contribution
#
# Validates that the last N commits follow the conventional commit format
# required by CONTRIBUTING.md: <type>(<module>): <subject>
#
# Usage:
#   bash validate_commit_msg.sh              # validate last commit
#   bash validate_commit_msg.sh 5            # validate last 5 commits
#   bash validate_commit_msg.sh --message "feat(base): add TB service"  # validate a string
#
# Exit codes:
#   0 = all valid
#   1 = validation error
# =============================================================================

set -uo pipefail

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Valid types per CONTRIBUTING.md
VALID_TYPES="feat|fix|docs|refactor|test|chore"
# Valid modules (known at time of contribution)
VALID_MODULES="base|shared|root"

# Full pattern: type(module): subject
# Also accepts type: subject (for root-level changes)
PATTERN="^(${VALID_TYPES})(\([a-z][a-z0-9\-]*\))?: .+"

validate_message() {
    local msg="$1"
    local source="$2"

    # Extract first line only
    local first_line
    first_line=$(echo "$msg" | head -1)

    if [[ -z "$first_line" ]]; then
        echo -e "  ${RED}❌${NC} $source: Empty commit message"
        return 1
    fi

    if echo "$first_line" | grep -qE "$PATTERN"; then
        echo -e "  ${GREEN}✅${NC} $source: $first_line"
        return 0
    else
        echo -e "  ${RED}❌${NC} $source: $first_line"
        echo -e "     ${YELLOW}Expected format: <type>(<module>): <subject>${NC}"
        echo -e "     ${YELLOW}Types: feat, fix, docs, refactor, test, chore${NC}"
        echo -e "     ${YELLOW}Example: feat(base): add ThingsBoard service scaffolding${NC}"
        return 1
    fi
}

# --- Parse arguments ---
if [[ "${1:-}" == "--message" ]]; then
    echo "Validating message:"
    validate_message "${2:-}" "input"
    exit $?
fi

COUNT="${1:-1}"

echo ""
echo "Validating last $COUNT commit(s):"
echo ""

ERRORS=0
while IFS= read -r line; do
    HASH=$(echo "$line" | cut -d' ' -f1)
    MSG=$(echo "$line" | cut -d' ' -f2-)
    validate_message "$MSG" "$HASH" || ERRORS=$((ERRORS + 1))
done < <(git log --oneline -"$COUNT" 2>/dev/null)

echo ""
if [[ $ERRORS -eq 0 ]]; then
    echo -e "${GREEN}All $COUNT commit(s) valid.${NC}"
    exit 0
else
    echo -e "${RED}$ERRORS commit(s) have invalid messages.${NC}"
    exit 1
fi
