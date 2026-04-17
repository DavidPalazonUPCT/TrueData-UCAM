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
