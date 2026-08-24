# -*- coding: utf-8 -*-
"""Path helpers shared by UI and tests."""
from __future__ import annotations


def has_extension(path: str, *extensions: str) -> bool:
    """Return True when path ends with any extension, case-insensitively."""
    lowered = path.strip().lower()
    return any(lowered.endswith(ext.lower()) for ext in extensions)


def ensure_extension(path: str, extension: str) -> str:
    """Append extension when the path does not already have it."""
    if not path or has_extension(path, extension):
        return path
    return f"{path}{extension}"
