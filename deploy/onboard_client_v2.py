"""onboard_client_v2.py — backwards-compat shim. Real logic in deploy/onboarding/.

Invoke via `python3 -m deploy.onboarding --manifest ...` for new code.
"""
import sys
from pathlib import Path

# Ensure repo root on sys.path when running this script directly
# (python3 deploy/onboard_client_v2.py) rather than via `python -m deploy.onboarding`.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from deploy.onboarding.cli import main  # noqa: E402


if __name__ == "__main__":
    sys.exit(main())
