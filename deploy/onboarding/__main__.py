"""Package entrypoint: python3 -m deploy.onboarding ..."""
import sys
from deploy.onboarding.cli import main

if __name__ == "__main__":
    sys.exit(main())
