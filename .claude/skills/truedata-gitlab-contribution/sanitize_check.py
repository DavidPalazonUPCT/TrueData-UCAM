#!/usr/bin/env python3
"""
Sanitization checker for TRUEDATA GitLab contribution.

Scans a file for patterns that should have been replaced during porting
from the UCAM repo to the GitLab repo. Returns exit code 0 if clean,
1 if violations found.

Usage:
    python sanitize_check.py <file_path> [--fix-preview]

The --fix-preview flag shows what the replacements would look like
(does NOT modify the file).
"""

import re
import sys
import argparse
from pathlib import Path

# Patterns that indicate CORRECT sanitization (allowlisted, never flagged)
ALLOWLIST_PATTERNS = [
    # os.environ.get("VAR", "default") — the default value is intentional
    r'os\.environ\.get\(\s*["\'][A-Z_]+["\']\s*,\s*["\']',
    # os.environ["VAR"] — reading from env, no default
    r'os\.environ\[\s*["\'][A-Z_]+["\']\s*\]',
    # process.env.VAR — JS env var access
    r'process\.env\.[A-Z_]+',
    # ${VAR:-default} — Docker Compose env var syntax
    r'\$\{[A-Z_]+(:-|:?\?)',
    # os.environ.get("TB_URL", ...) on the same line as the URL
    r'os\.environ\.get\([^)]*localhost',
]

# Each rule: (pattern_regex, description, severity, suggestion)
RULES = [
    # --- SECRETS (severity: CRITICAL) ---
    (
        r'credentialSecret\s*[:=]\s*["\']airtrace["\']',
        "Hardcoded Node-RED credentialSecret 'airtrace'",
        "CRITICAL",
        "Replace with: process.env.NODE_RED_CREDENTIAL_SECRET (JS) or os.environ['NODE_RED_CREDENTIAL_SECRET'] (Python)"
    ),
    (
        r'(?:password|passwd)\s*[:=]\s*["\'](?:tenant|tenantairtrace|sysadmin)["\']',
        "Hardcoded password (tenant/tenantairtrace/sysadmin)",
        "CRITICAL",
        "Replace with env var: TB_ADMIN_PASSWORD or NODE_RED_PASSWORD"
    ),
    (
        r'accessToken\s*[:=]\s*["\'][A-Za-z0-9]{16,}["\']',
        "Hardcoded ThingsBoard device access token",
        "CRITICAL",
        "Replace with env var or remove (tokens are generated at deploy time)"
    ),
    (
        r'AWS_ACCESS_KEY_ID\s*[:=]\s*["\'][^X"\'][A-Za-z0-9]',
        "AWS access key (non-placeholder)",
        "CRITICAL",
        "Delete entirely (unused by UCAM contribution)"
    ),

    # --- HARDCODED URLS (severity: HIGH) ---
    (
        r'https?://localhost:9090',
        "Hardcoded ThingsBoard URL (localhost:9090)",
        "HIGH",
        "Replace with: os.environ.get('TB_URL', 'http://localhost:9090') or ${TB_URL:-http://thingsboard:9090}"
    ),
    (
        r'https?://localhost:1880',
        "Hardcoded Node-RED URL (localhost:1880)",
        "HIGH",
        "Replace with: os.environ.get('NODE_RED_URL', 'http://localhost:1880') or ${NODE_RED_URL:-http://node-red:1880}"
    ),
    (
        r'https?://172\.25\.0\.\d+',
        "Hardcoded Docker network IP (172.25.0.x)",
        "HIGH",
        "Replace with Docker service hostname (thingsboard, node-red, postgres)"
    ),

    # --- HARDCODED CREDENTIALS (severity: HIGH) ---
    (
        r'["\']tenant@thingsboard\.org["\']',
        "Hardcoded TB admin email",
        "HIGH",
        "Replace with: os.environ.get('TB_ADMIN_USER', 'tenant@thingsboard.org')"
    ),
    (
        r'["\']sysadmin@thingsboard\.org["\']',
        "Hardcoded TB sysadmin email",
        "HIGH",
        "Replace with: os.environ.get('TB_SYSADMIN_USER', 'sysadmin@thingsboard.org')"
    ),

    # --- EXCLUDED FILE REFERENCES (severity: MEDIUM) ---
    (
        r'(?:deploy/MCT|deploy/ESAMUR)',
        "Reference to excluded client directories (MCT/ESAMUR)",
        "MEDIUM",
        "Replace with TEMPLATE or parameterize via CLIENT_DIR"
    ),
    (
        r'Credenciales\.txt',
        "Reference to credentials file",
        "MEDIUM",
        "Remove reference; credentials are handled via env vars"
    ),
    (
        r'ParametrosConfiguracion\.txt',
        "Reference to deleted config file",
        "MEDIUM",
        "Remove reference; config is handled via .env"
    ),
    (
        r'locustfile\.py',
        "Reference to excluded load test file",
        "MEDIUM",
        "Remove reference (file not ported)"
    ),
]

# Patterns that are OK inside comments (relaxed check)
COMMENT_PREFIXES_PY = (r'^\s*#',)
COMMENT_PREFIXES_JS = (r'^\s*//',  r'^\s*\*')
COMMENT_PREFIXES_YAML = (r'^\s*#',)
COMMENT_PREFIXES_MD = ()  # Markdown content is always "live"


def detect_language(filepath: Path) -> str:
    ext = filepath.suffix.lower()
    if ext in ('.py',):
        return 'python'
    elif ext in ('.js', '.ts'):
        return 'javascript'
    elif ext in ('.yml', '.yaml'):
        return 'yaml'
    elif ext in ('.md',):
        return 'markdown'
    elif ext in ('.json',):
        return 'json'
    elif ext in ('.dockerfile',) or filepath.name == 'Dockerfile':
        return 'dockerfile'
    return 'unknown'


def is_comment_line(line: str, lang: str) -> bool:
    if lang == 'python':
        prefixes = COMMENT_PREFIXES_PY
    elif lang == 'javascript':
        prefixes = COMMENT_PREFIXES_JS
    elif lang in ('yaml', 'dockerfile'):
        prefixes = COMMENT_PREFIXES_YAML
    elif lang == 'markdown':
        return False  # All markdown is "live" content
    else:
        return False

    for prefix in prefixes:
        if re.match(prefix, line):
            return True
    return False


def scan_file(filepath: Path, strict: bool = False) -> list[dict]:
    """Scan a file for sanitization violations.

    Args:
        filepath: Path to the file to scan
        strict: If True, also flag violations in comments

    Returns:
        List of violation dicts with keys: line_num, line, rule, severity, suggestion
    """
    violations = []
    lang = detect_language(filepath)

    try:
        content = filepath.read_text(encoding='utf-8', errors='replace')
    except Exception as e:
        return [{"line_num": 0, "line": "", "rule": f"Cannot read file: {e}",
                 "severity": "ERROR", "suggestion": "Check file permissions"}]

    for line_num, line in enumerate(content.splitlines(), 1):
        for pattern, desc, severity, suggestion in RULES:
            if re.search(pattern, line, re.IGNORECASE):
                # Check if the line matches an allowlist pattern (correct sanitization)
                is_allowlisted = any(
                    re.search(ap, line) for ap in ALLOWLIST_PATTERNS
                )
                if is_allowlisted and severity != "CRITICAL":
                    continue

                # Skip if it's a comment and we're not in strict mode
                if not strict and is_comment_line(line, lang):
                    # Still flag CRITICAL in comments (secrets should never appear)
                    if severity != "CRITICAL":
                        continue

                violations.append({
                    "line_num": line_num,
                    "line": line.rstrip(),
                    "rule": desc,
                    "severity": severity,
                    "suggestion": suggestion,
                })

    return violations


def main():
    parser = argparse.ArgumentParser(description="Check a file for unsanitized TRUEDATA patterns")
    parser.add_argument("filepath", help="Path to the file to scan")
    parser.add_argument("--strict", action="store_true",
                        help="Also flag violations in comments (default: skip non-CRITICAL in comments)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    filepath = Path(args.filepath)
    if not filepath.exists():
        print(f"ERROR: File not found: {filepath}")
        sys.exit(2)

    violations = scan_file(filepath, strict=args.strict)

    if args.json:
        import json
        print(json.dumps(violations, indent=2))
    else:
        if not violations:
            print(f"✅ CLEAN: {filepath}")
        else:
            severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "ERROR": 3}
            violations.sort(key=lambda v: severity_order.get(v["severity"], 99))

            print(f"❌ VIOLATIONS in {filepath}:")
            print()
            for v in violations:
                marker = "🔴" if v["severity"] == "CRITICAL" else "🟠" if v["severity"] == "HIGH" else "🟡"
                print(f"  {marker} [{v['severity']}] Line {v['line_num']}: {v['rule']}")
                print(f"     │ {v['line'][:120]}")
                print(f"     └─ Fix: {v['suggestion']}")
                print()

    sys.exit(1 if violations else 0)


if __name__ == "__main__":
    main()
