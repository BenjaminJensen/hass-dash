"""Pytest configuration and shared fixtures."""

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent

# Application code, and the development tools, which are tested but not shipped.
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))
