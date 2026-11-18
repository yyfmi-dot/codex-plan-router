#!/usr/bin/env python3
"""Codex desktop plugin entry point. Requires Python 3.9+; no pip install."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "vendor"))
from cpr.cli import main

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as error:
        # Operational exceptions deliberately contain no upstream response bodies.
        print(str(error), file=sys.stderr)
        sys.exit(1)
