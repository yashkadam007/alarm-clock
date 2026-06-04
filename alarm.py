#!/usr/bin/env python3

"""
Alarm Clock CLI Application
A lightweight terminal alarm clock that runs entirely in the terminal.
"""

import sys
from pathlib import Path

# Add src to path so we can import modules
sys.path.insert(0, str(Path(__file__).parent / "src"))

from alarm_clock.cli import main

if __name__ == "__main__":
    sys.exit(main())
