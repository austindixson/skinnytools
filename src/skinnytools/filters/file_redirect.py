"""Auto-redirect large outputs to temp files."""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

from skinnytools.config.defaults import REDIRECT_DIR, REDIRECT_MAX_AGE_SECONDS
from skinnytools.models.config import FilterConfig
from skinnytools.models.filter_result import FilterResult
from skinnytools.utils.text import format_size


class FileRedirectFilter:
    """Write oversized content to temp file, return pointer + summary."""

    @property
    def name(self) -> str:
        return "file_redirect"

    def apply(self, content: str, config: FilterConfig) -> FilterResult:
        original_size = len(content)

        if original_size <= config.redirect_threshold:
            return FilterResult(
                content=content,
                original_size=original_size,
                filtered_size=original_size,
                filter_name=self.name,
            )

        # Clean up old redirects
        _cleanup_old_redirects()

        # Write to temp file
        REDIRECT_DIR.mkdir(parents=True, exist_ok=True)
        fd, path = tempfile.mkstemp(
            prefix="skinnytools_",
            suffix=".txt",
            dir=str(REDIRECT_DIR),
        )
        with open(fd, "w") as f:
            f.write(content)

        # Build pointer with summary
        preview = content[:500].replace("\n", " ")
        pointer = (
            f"[Full output saved to {path} ({format_size(original_size)} chars)]\n"
            f"Preview: {preview}..."
        )
        filtered_size = len(pointer)

        return FilterResult(
            content=pointer,
            original_size=original_size,
            filtered_size=filtered_size,
            filter_name=self.name,
            was_redirected=True,
            redirect_path=path,
        )


def _cleanup_old_redirects() -> None:
    """Remove redirect files older than REDIRECT_MAX_AGE_SECONDS."""
    if not REDIRECT_DIR.exists():
        return
    now = time.time()
    for f in REDIRECT_DIR.iterdir():
        if f.is_file() and f.name.startswith("skinnytools_"):
            age = now - f.stat().st_mtime
            if age > REDIRECT_MAX_AGE_SECONDS:
                f.unlink(missing_ok=True)
