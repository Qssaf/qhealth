#!/usr/bin/env python3
"""Run QHealth straight from a source checkout. Installed copies use the `qhealth` command instead."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.resolve()))

from qhealth_core.cli import main

if __name__ == "__main__":
    main()
