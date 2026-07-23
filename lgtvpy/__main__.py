"""Allow ``python -m lgtvpy <command>``."""

import sys

from .cli import main

sys.exit(main())
