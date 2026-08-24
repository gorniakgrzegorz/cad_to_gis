# -*- coding: utf-8 -*-
# Copyright (C) 2026 Yusuf Eminoğlu
# SPDX-License-Identifier: GPL-2.0-or-later
"""Small, QGIS-independent helpers for reliable dataset exports."""
from __future__ import annotations

import os
import tempfile
from contextlib import contextmanager, suppress
from dataclasses import dataclass


@dataclass(frozen=True)
class ExportResult:
    """Verified details of a completed export."""

    path: str
    driver: str
    feature_count: int
    target_crs: str
    bytes_written: int


@contextmanager
def atomic_output(output_path: str, sidecar_exts: tuple[str, ...] = ()):
    """Zapisuje najpierw do pliku tymczasowego obok celu i dopiero po
    udanym zapisie podmienia go na właściwy — dzięki temu przerwany
    eksport nie zostawia nadpsutego pliku.

    ``sidecar_exts`` to rozszerzenia plików towarzyszących (np. ``.xsd``
    przy GML), które trzeba przenieść razem z plikiem głównym.
    """
    final_path = os.path.abspath(output_path)
    folder = os.path.dirname(final_path)
    if not os.path.isdir(folder):
        raise ValueError(f"Folder docelowy nie istnieje: {folder}")

    extension = os.path.splitext(final_path)[1]
    fd, temporary_path = tempfile.mkstemp(
        prefix=".konwerter-cad-gis-export-", suffix=extension, dir=folder)
    os.close(fd)
    with suppress(OSError):
        os.remove(temporary_path)

    try:
        yield temporary_path
        if not os.path.isfile(temporary_path):
            raise ValueError("Eksport nie utworzył pliku wynikowego.")
        if os.path.getsize(temporary_path) <= 0:
            raise ValueError("Eksport utworzył pusty plik.")
        os.replace(temporary_path, final_path)
        # pliki towarzyszące (np. schemat .xsd dla GML) dostają nazwę
        # zgodną z plikiem głównym
        temp_stem = os.path.splitext(temporary_path)[0]
        final_stem = os.path.splitext(final_path)[0]
        for ext in sidecar_exts:
            temp_side = f"{temp_stem}{ext}"
            if os.path.isfile(temp_side):
                with suppress(OSError):
                    os.replace(temp_side, f"{final_stem}{ext}")
    finally:
        with suppress(OSError):
            os.remove(temporary_path)
        temp_stem = os.path.splitext(temporary_path)[0]
        for ext in sidecar_exts:
            with suppress(OSError):
                os.remove(f"{temp_stem}{ext}")


def exported_feature_count(layer, selected_only: bool) -> int:
    """Return the intended export count using QGIS' inexpensive counters."""
    if selected_only:
        return int(layer.selectedFeatureCount())
    return int(layer.featureCount())


def verified_export_result(
        output_path: str,
        driver: str,
        feature_count: int,
        target_crs: str) -> ExportResult:
    """Build a result only after the final file is present and non-empty."""
    final_path = os.path.abspath(output_path)
    size = os.path.getsize(final_path)
    if size <= 0:
        raise ValueError("Wyeksportowany plik jest pusty.")
    return ExportResult(
        path=final_path,
        driver=driver,
        feature_count=feature_count,
        target_crs=target_crs,
        bytes_written=size,
    )
