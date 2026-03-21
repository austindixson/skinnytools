"""Default paths and constants."""

from __future__ import annotations

from pathlib import Path

# Directories
CONFIG_DIR = Path.home() / ".config" / "skinnytools"
CACHE_DIR = Path.home() / ".cache" / "skinnytools"
STATS_FILE = CACHE_DIR / "last_stats.json"
REDIRECT_DIR = CACHE_DIR / "redirects"

# Size limits
DEFAULT_MAX_SIZE = 50_000
DEFAULT_REDIRECT_THRESHOLD = 100_000
DEFAULT_TOKEN_BUDGET = 500_000
MAX_INPUT_SIZE = 100_000_000  # 100MB hard cap on stdin

# Redirect cleanup
REDIRECT_MAX_AGE_SECONDS = 3600  # 1 hour

# Fast-path: skip filtering if input is smaller than this
FAST_PATH_THRESHOLD = 1024  # 1KB
