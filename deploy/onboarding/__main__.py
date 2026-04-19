"""Package entrypoint: `python3 -m deploy.onboarding ...`"""
import sys

# Until R8 extracts cli.py, delegate to the monolithic script's main().
from deploy.onboard_client_v2 import main

if __name__ == "__main__":
    sys.exit(main())
