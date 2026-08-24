# -*- coding: utf-8 -*-
"""csv_sniffer — Delimited-text geometry detection for 02CadGis.

Pure-Python (no QGIS imports) so it is unit-testable outside QGIS.
Detects the delimiter, header fields, and the most likely geometry
columns (X/Y pair or a WKT column) of a CSV/TSV/TXT dataset, and builds
the QGIS ``delimitedtext`` provider URI for it.
"""
from __future__ import annotations

import csv
import io
import os
from dataclasses import dataclass, field
from urllib.parse import quote

SNIFF_BYTES = 256 * 1024
SAMPLE_ROWS = 50
CANDIDATE_DELIMITERS = [",", ";", "\t", "|"]

X_FIELD_NAMES = (
    "x", "lon", "long", "longitude", "easting", "east", "x_coord",
    "xcoord", "coord_x", "boylam", "saga", "saga_deger", "point_x",
)
Y_FIELD_NAMES = (
    "y", "lat", "latitude", "northing", "north", "y_coord",
    "ycoord", "coord_y", "enlem", "yukari", "yukari_deger", "point_y",
)
WKT_FIELD_NAMES = ("wkt", "geometry", "geom", "the_geom", "shape", "wkt_geom")
GEOGRAPHIC_NAMES = ("lon", "long", "longitude", "lat", "latitude",
                    "boylam", "enlem")

DELIMITED_EXTENSIONS = (".csv", ".tsv", ".txt")


@dataclass
class CsvGeometryProfile:
    """Detected structure of a delimited text dataset."""

    delimiter: str = ","
    fields: list[str] = field(default_factory=list)
    x_field: str = ""
    y_field: str = ""
    wkt_field: str = ""
    crs_authid: str = ""
    row_count: int = 0

    @property
    def has_point_geometry(self) -> bool:
        return bool(self.x_field and self.y_field)

    @property
    def has_wkt_geometry(self) -> bool:
        return bool(self.wkt_field)

    @property
    def geometry_summary(self) -> str:
        if self.has_wkt_geometry:
            return f"WKT column '{self.wkt_field}'"
        if self.has_point_geometry:
            return f"Point from '{self.x_field}' / '{self.y_field}'"
        return "No geometry (attribute table)"


def is_delimited_dataset(path: str) -> bool:
    return path.lower().endswith(DELIMITED_EXTENSIONS)


def _normalize(name: str) -> str:
    return name.strip().strip('"').strip("'").lower().replace(" ", "_")


def _detect_delimiter(sample_text: str) -> str:
    try:
        dialect = csv.Sniffer().sniff(
            sample_text, delimiters="".join(CANDIDATE_DELIMITERS))
        return dialect.delimiter
    except csv.Error:
        first_line = sample_text.splitlines()[0] if sample_text else ""
        counts = {d: first_line.count(d) for d in CANDIDATE_DELIMITERS}
        best = max(counts, key=counts.get)
        return best if counts[best] > 0 else ","


def _looks_numeric(values: list[str]) -> bool:
    seen = 0
    for value in values:
        value = value.strip().replace(",", ".")
        if not value:
            continue
        try:
            float(value)
            seen += 1
        except ValueError:
            return False
    return seen > 0


def _pick_field(fields: list[str], candidates: tuple[str, ...],
                numeric_ok: dict[str, bool] | None = None) -> str:
    normalized = {_normalize(f): f for f in fields}
    for candidate in candidates:
        original = normalized.get(candidate)
        if original is None:
            continue
        if numeric_ok is not None and not numeric_ok.get(original, False):
            continue
        return original
    return ""


def sniff_delimited_dataset(path: str) -> CsvGeometryProfile:
    """Inspect *path* and return the detected geometry profile."""
    with open(path, "r", encoding="utf-8-sig", errors="replace",
              newline="") as handle:
        sample_text = handle.read(SNIFF_BYTES)

    if path.lower().endswith(".tsv"):
        delimiter = "\t"
    else:
        delimiter = _detect_delimiter(sample_text)

    reader = csv.reader(io.StringIO(sample_text), delimiter=delimiter)
    rows = []
    for row in reader:
        rows.append(row)
        if len(rows) > SAMPLE_ROWS:
            break

    profile = CsvGeometryProfile(delimiter=delimiter)
    if not rows:
        return profile

    header = [cell.strip() for cell in rows[0]]
    profile.fields = header

    sample_data = rows[1:]
    column_samples: dict[str, list[str]] = {name: [] for name in header}
    for row in sample_data:
        for index, name in enumerate(header):
            if index < len(row):
                column_samples[name].append(row[index])
    numeric_ok = {name: _looks_numeric(values)
                  for name, values in column_samples.items()}

    profile.wkt_field = _pick_field(header, WKT_FIELD_NAMES)
    if not profile.wkt_field:
        profile.x_field = _pick_field(header, X_FIELD_NAMES, numeric_ok)
        profile.y_field = _pick_field(header, Y_FIELD_NAMES, numeric_ok)
        if not (profile.x_field and profile.y_field):
            profile.x_field = ""
            profile.y_field = ""

    if profile.has_point_geometry:
        x_norm = _normalize(profile.x_field)
        y_norm = _normalize(profile.y_field)
        if x_norm in GEOGRAPHIC_NAMES or y_norm in GEOGRAPHIC_NAMES:
            profile.crs_authid = "EPSG:4326"

    profile.row_count = _count_data_rows(path)
    return profile


def _count_data_rows(path: str) -> int:
    count = 0
    try:
        with open(path, "r", encoding="utf-8-sig", errors="replace") as handle:
            for count, _ in enumerate(handle):
                pass
    except OSError:
        return 0
    return count


def _uri_value(value: str) -> str:
    """Escape a delimitedtext query value.

    The provider does not fully percent-decode query values (a ``%2C``
    delimiter or ``EPSG%3A4326`` crs invalidates the layer — probed on
    QGIS 3.44), so values are passed raw; tabs use the provider's own
    ``\\t`` token and only URL-structural characters are escaped.
    """
    if value == "\t":
        return "\\t"
    return (value.replace("%", "%25").replace("&", "%26")
            .replace("=", "%3D").replace("#", "%23"))


def build_delimitedtext_uri(path: str, profile: CsvGeometryProfile,
                            crs_authid: str = "") -> str:
    """Build a QGIS ``delimitedtext`` provider URI for *path*."""
    params: list[tuple[str, str]] = [
        ("type", "csv"),
        ("delimiter", profile.delimiter),
        ("detectTypes", "yes"),
    ]
    if profile.has_wkt_geometry:
        params.append(("wktField", profile.wkt_field))
    elif profile.has_point_geometry:
        params.append(("xField", profile.x_field))
        params.append(("yField", profile.y_field))
    else:
        params.append(("geomType", "none"))

    effective_crs = crs_authid or profile.crs_authid
    if effective_crs and (profile.has_wkt_geometry
                          or profile.has_point_geometry):
        params.append(("crs", effective_crs))

    file_url = "file:///" + quote(
        os.path.abspath(path).replace("\\", "/"), safe="/:")
    query = "&".join(f"{key}={_uri_value(value)}" for key, value in params)
    return f"{file_url}?{query}"
