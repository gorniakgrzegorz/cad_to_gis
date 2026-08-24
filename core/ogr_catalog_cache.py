# -*- coding: utf-8 -*-
# Copyright (C) 2026 Yusuf Eminoğlu
# SPDX-License-Identifier: GPL-2.0-or-later
"""Fingerprinted on-disk cache for OGR multi-layer source catalogs.

Opening some multi-layer OGR datasets just to list their layers is not free:
a large ArcGIS Personal Geodatabase (``.mdb``) opens through the PGeo/ODBC
driver in a couple of seconds, and a File Geodatabase scans its table
directory. This cache stores the layer catalog (name, geometry type, feature
count) the first time a dataset is inspected, so reopening the same unchanged
source shows its layer preview instantly.

To optymalizacja typu best-effort: any read, write,
or validation error is swallowed and the caller simply rescans the dataset.
Content is stored as JSON (never pickle) under a per-user cache directory, and
invalidation is by a content fingerprint plus a bumped :data:`CACHE_VERSION`.

The fingerprint covers both single-file sources (``.mdb``, ``.sqlite``,
``.gml`` …) and directory datasets (``.gdb``): for a directory it aggregates
the file count, total byte size, and newest modification time of the files it
contains, so any edit to the geodatabase invalidates the entry.
"""
from __future__ import annotations

import hashlib
import json
import os
from contextlib import suppress
from pathlib import Path

# Bump when the cached catalog shape changes.
CACHE_VERSION = 1

_DISABLE_ENV = "ZERO2CADGIS_OGR_CACHE_DISABLE"

# Directories larger than this many files are fingerprinted from their top
# level only, to keep the stat walk cheap on huge geodatabases.
_MAX_WALK_ENTRIES = 4096


def _cache_root() -> Path:
    base = (os.environ.get("LOCALAPPDATA")
            or os.environ.get("XDG_CACHE_HOME")
            or os.path.join(os.path.expanduser("~"), ".cache"))
    return Path(base) / "konwerter_cad_gis" / "ogr_catalog"


def _is_disabled() -> bool:
    return os.environ.get(_DISABLE_ENV, "").strip().lower() in (
        "1", "true", "yes")


def _cache_file(source_path: str) -> Path:
    digest = hashlib.sha256(
        os.path.abspath(source_path).encode("utf-8", "surrogatepass")
    ).hexdigest()[:20]
    return _cache_root() / f"{digest}.json"


def fingerprint(source_path: str) -> dict:
    """Return a content fingerprint for a file or directory dataset."""
    if os.path.isdir(source_path):
        count = 0
        total = 0
        newest = 0
        with os.scandir(source_path) as entries:
            for entry in entries:
                if count >= _MAX_WALK_ENTRIES:
                    break
                try:
                    stat = entry.stat()
                except OSError:
                    continue
                if entry.is_file():
                    count += 1
                    total += stat.st_size
                    if stat.st_mtime_ns > newest:
                        newest = stat.st_mtime_ns
        return {"kind": "dir", "files": count,
                "size": total, "mtime_ns": newest}
    stat = os.stat(source_path)
    return {"kind": "file", "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns}


def load(source_path: str) -> list[dict] | None:
    """Return the cached layer catalog for *source_path*, or None on a miss.

    Each catalog entry is a dict with ``name``, ``geometry`` and
    ``feature_count`` keys.
    """
    if _is_disabled():
        return None
    try:
        current = fingerprint(source_path)
    except OSError:
        return None

    cache_file = _cache_file(source_path)
    try:
        with open(cache_file, "r", encoding="utf-8") as handle:
            stored = json.load(handle)
    except (OSError, ValueError):
        return None

    if stored.get("cache_version") != CACHE_VERSION:
        return None
    if stored.get("fingerprint") != current:
        return None

    layers = stored.get("layers")
    if not isinstance(layers, list):
        return None
    return layers


def save(source_path: str, layers: list[dict]) -> None:
    """Persist a layer catalog for *source_path*. Silent on any failure."""
    if _is_disabled():
        return
    try:
        current = fingerprint(source_path)
    except OSError:
        return

    payload = {
        "cache_version": CACHE_VERSION,
        "fingerprint": current,
        "source": os.path.basename(source_path.rstrip("\\/")),
        "layers": layers,
    }

    cache_file = _cache_file(source_path)
    with suppress(OSError, TypeError, ValueError):
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache_file.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False)
        os.replace(tmp, cache_file)


def clear() -> int:
    """Delete all cached OGR catalogs. Returns the number of files removed."""
    removed = 0
    root = _cache_root()
    if not root.is_dir():
        return 0
    for entry in root.glob("*.json"):
        with suppress(OSError):
            entry.unlink()
            removed += 1
    return removed
