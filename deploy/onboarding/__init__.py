"""TRUEDATA onboarding pipeline v2 — modular package.

Public entry point: `main()` (returns exit code).
Invoke via: `python3 -m deploy.onboarding --manifest <path>`.
"""
from deploy.onboarding.cli import EXIT_OK, main

__all__ = ["EXIT_OK", "main"]
