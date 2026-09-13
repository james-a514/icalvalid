"""Allow `python -m icalvalid` to run the CLI without installing the package."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
