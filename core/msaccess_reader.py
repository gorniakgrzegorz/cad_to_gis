# -*- coding: utf-8 -*-
"""msaccess_reader — Reader for MS Access (.accdb / .mdb) databases.
Obsługuje geobazy personalne ESRI (PGeo) oraz zwykłe tabele GIS
zapisane w bazach MS Access.
"""
from __future__ import annotations

import contextlib
import json
import os
from typing import Any, Optional

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsVectorLayer,
    QgsWkbTypes,
)
from qgis.PyQt.QtCore import QMetaType

from .crs_detect import detect_crs
from .qgis_compat import add_features_or_raise, fix_mojibake

# Check pyodbc availability
try:
    import pyodbc
    HAS_PYODBC = True
except ImportError:
    pyodbc = None  # type: ignore[assignment]
    HAS_PYODBC = False


def get_msaccess_odbc_driver() -> Optional[str]:
    """Return an installed 64-bit/32-bit MS Access ODBC driver name, or None."""
    if not HAS_PYODBC or pyodbc is None:
        return None

    with contextlib.suppress(Exception):
        drivers = pyodbc.drivers()
        for d in drivers:
            if "Microsoft Access Driver" in d and "*.accdb" in d:
                return d
        for d in drivers:
            if "Microsoft Access Driver" in d:
                return d

    return None


def is_msaccess_available() -> bool:
    """Return True if MS Access database reading via ODBC is supported on this system."""
    return get_msaccess_odbc_driver() is not None


def _clean_attribute_value(val: Any) -> Any:
    """Safely convert attribute values to QGIS memory layer supported types."""
    if val is None:
        return None
    if isinstance(val, str):
        return fix_mojibake(val)
    if isinstance(val, (bytes, bytearray)):
        return "<binary>"
    if isinstance(val, (int, float, bool)):
        return val
    return str(val)


def _geom_from_geojson_dict(gdict: dict) -> QgsGeometry:
    """Build a QgsGeometry from a GeoJSON geometry dictionary."""
    if not isinstance(gdict, dict):
        return QgsGeometry()
    gtype = gdict.get("type", "")
    coords = gdict.get("coordinates", [])
    if not coords:
        return QgsGeometry()

    if gtype == "Point":
        if len(coords) >= 2:
            return QgsGeometry.fromPointXY(QgsPointXY(float(coords[0]), float(coords[1])))
    elif gtype == "LineString":
        pts = [QgsPointXY(float(p[0]), float(p[1])) for p in coords if len(p) >= 2]
        return QgsGeometry.fromPolylineXY(pts)
    elif gtype == "Polygon":
        rings = [[QgsPointXY(float(p[0]), float(p[1])) for p in ring if len(p) >= 2] for ring in coords]
        return QgsGeometry.fromPolygonXY(rings)
    elif gtype == "MultiPolygon":
        polys = [[[QgsPointXY(float(p[0]), float(p[1])) for p in ring if len(p) >= 2] for poly in coords] for ring in coords]
        return QgsGeometry.fromMultiPolygonXY(polys)
    elif gtype == "MultiLineString":
        lines = [[QgsPointXY(float(p[0]), float(p[1])) for p in line if len(p) >= 2] for line in coords]
        return QgsGeometry.fromMultiPolylineXY(lines)
    elif gtype == "MultiPoint":
        pts = [QgsPointXY(float(p[0]), float(p[1])) for p in coords if len(p) >= 2]
        return QgsGeometry.fromMultiPointXY(pts)

    return QgsGeometry()


def parse_geometry_value(val: Any, x_val: Any = None, y_val: Any = None) -> Optional[QgsGeometry]:
    """Parse a cell value or x/y coordinates into a QgsGeometry."""
    if val is None and x_val is not None and y_val is not None:
        with contextlib.suppress(ValueError, TypeError):
            return QgsGeometry.fromPointXY(QgsPointXY(float(x_val), float(y_val)))

    if isinstance(val, str):
        val_str = val.strip()
        if not val_str:
            return None
        # GeoJSON
        if val_str.startswith("{") and val_str.endswith("}"):
            with contextlib.suppress(Exception):
                gdict = json.loads(val_str)
                geom = _geom_from_geojson_dict(gdict)
                if geom and not geom.isEmpty():
                    return geom
        # WKT
        uval = val_str.upper()
        if any(uval.startswith(kw) for kw in (
            "POINT", "LINESTRING", "POLYGON", "MULTIPOINT",
            "MULTILINESTRING", "MULTIPOLYGON", "GEOMETRYCOLLECTION"
        )):
            with contextlib.suppress(Exception):
                geom = QgsGeometry.fromWkt(val_str)
                if geom and not geom.isEmpty():
                    return geom

    if isinstance(val, (bytes, bytearray)):
        # WKB
        with contextlib.suppress(Exception):
            g = QgsGeometry()
            g.fromWkb(bytes(val))
            if not g.isEmpty():
                return g

    return None


def find_best_geometry_column(cols: list[str], rows: list[Any]) -> tuple[Optional[str], Optional[str], Optional[str], str]:
    """Find column name(s) and geometry family that yields valid QgsGeometry."""
    priority = ("geom", "geometry", "geojson", "wkt", "the_geom", "poly", "shape", "wkb")

    cand_cols = [c for c in cols if c.lower() in priority]
    cand_cols.sort(key=lambda c: priority.index(c.lower()) if c.lower() in priority else 99)

    for g_col in cand_cols:
        col_idx = cols.index(g_col)
        for r in rows:
            val = r[col_idx]
            geom = parse_geometry_value(val)
            if geom and not geom.isEmpty():
                gt = geom.type()
                if gt == QgsWkbTypes.GeometryType.PolygonGeometry:
                    return g_col, None, None, "MultiPolygon"
                elif gt == QgsWkbTypes.GeometryType.LineGeometry:
                    return g_col, None, None, "MultiLineString"
                elif gt == QgsWkbTypes.GeometryType.PointGeometry:
                    return g_col, None, None, "Point"

    x_candidates = ("x", "lon", "longitude", "easting", "x_coord", "koord_x", "x_koord")
    y_candidates = ("y", "lat", "latitude", "northing", "y_coord", "koord_y", "y_koord")
    x_col = next((c for c in cols if c.lower() in x_candidates), None)
    y_col = next((c for c in cols if c.lower() in y_candidates), None)

    if x_col and y_col:
        x_idx = cols.index(x_col)
        y_idx = cols.index(y_col)
        for r in rows:
            geom = parse_geometry_value(None, r[x_idx], r[y_idx])
            if geom and not geom.isEmpty():
                return None, x_col, y_col, "Point"

    return None, None, None, "NoGeometry"


def _coerce_geometry(geom: QgsGeometry, target_family: str) -> Optional[QgsGeometry]:
    """Coerce geometry to match layer geometry type (MultiPolygon, MultiLineString, Point)."""
    if not geom or geom.isEmpty():
        return None

    gt = geom.type()
    g_out = QgsGeometry(geom)

    if target_family in ("MultiPolygon", "Polygon"):
        if gt == QgsWkbTypes.GeometryType.PolygonGeometry:
            if not QgsWkbTypes.isMultiType(g_out.wkbType()):
                g_out.convertToMultiType()
            return g_out
        elif gt == QgsWkbTypes.GeometryType.LineGeometry:
            pts = geom.asPolyline()
            if len(pts) >= 3:
                if pts[0] != pts[-1]:
                    pts = list(pts) + [pts[0]]
                poly_g = QgsGeometry.fromPolygonXY([pts])
                poly_g.convertToMultiType()
                return poly_g
            return None
        return None

    elif target_family in ("MultiLineString", "LineString"):
        if gt == QgsWkbTypes.GeometryType.LineGeometry:
            if not QgsWkbTypes.isMultiType(g_out.wkbType()):
                g_out.convertToMultiType()
            return g_out
        elif gt == QgsWkbTypes.GeometryType.PolygonGeometry:
            poly = geom.asPolygon()
            if poly and poly[0]:
                line_g = QgsGeometry.fromPolylineXY(poly[0])
                line_g.convertToMultiType()
                return line_g
            return None
        return None

    elif target_family in ("Point", "MultiPoint"):
        if gt == QgsWkbTypes.GeometryType.PointGeometry:
            return g_out
        else:
            c = geom.centroid()
            return c if c and not c.isEmpty() else None

    return None


class MsAccessDbReader:
    """Pure-Python / ODBC reader for MS Access (.accdb and .mdb) databases."""

    def __init__(self, source_path: str, source_crs: Optional[QgsCoordinateReferenceSystem] = None):
        self.source_path = source_path
        self.source_crs = source_crs

    def _connect(self):
        driver = get_msaccess_odbc_driver()
        if not driver:
            raise ValueError(
                f"Cannot open '{os.path.basename(self.source_path)}': Microsoft Access ODBC driver is not installed on Windows."
            )
        conn_str = f"DRIVER={{{driver}}};DBQ={self.source_path};"
        return pyodbc.connect(conn_str)

    def list_tables(self) -> list[dict[str, Any]]:
        """List user tables with feature count and geometry type."""
        conn = self._connect()
        try:
            cur = conn.cursor()
            tables = [
                row.table_name for row in cur.tables(tableType="TABLE")
                if not row.table_name.startswith("MSys") and row.table_name.upper() != "NCSPATINFO"
            ]

            results = []
            for tname in sorted(tables):
                clean_tname = tname.replace("]", "]]")
                cur.execute(f"SELECT COUNT(*) FROM [{clean_tname}]")  # nosec B608
                count_row = cur.fetchone()
                fc = count_row[0] if count_row else 0

                cur.execute(f"SELECT TOP 10 * FROM [{clean_tname}]")  # nosec B608
                cols = [c[0] for c in cur.description] if cur.description else []
                rows = cur.fetchall()

                g_col, x_col, y_col, geom_family = find_best_geometry_column(cols, rows)

                results.append({
                    "name": tname,
                    "geometry": geom_family,
                    "feature_count": fc,
                    "geom_col": g_col,
                    "x_col": x_col,
                    "y_col": y_col,
                })
            return results
        finally:
            conn.close()

    def read_layer(self, table_name: str) -> Optional[QgsVectorLayer]:
        """Convert an MS Access table to a QGIS memory vector layer."""
        conn = self._connect()
        try:
            cur = conn.cursor()
            clean_tname = table_name.replace("]", "]]")
            cur.execute(f"SELECT * FROM [{clean_tname}]")  # nosec B608
            if not cur.description:
                return None

            col_names = [c[0] for c in cur.description]
            col_types = [c[1] for c in cur.description]

            rows = cur.fetchall()
            g_col, x_col, y_col, layer_geom_family = find_best_geometry_column(col_names, rows[:20])

            attr_cols = [c for c in col_names if c != g_col and c not in (x_col, y_col)]

            sample_coords = []
            for r in rows:
                g_val = r[col_names.index(g_col)] if g_col else None
                x_val = r[col_names.index(x_col)] if x_col else None
                y_val = r[col_names.index(y_col)] if y_col else None
                geom = parse_geometry_value(g_val, x_val, y_val)
                if geom and not geom.isEmpty():
                    with contextlib.suppress(Exception):
                        pt = geom.centroid().asPoint()
                        sample_coords.append((pt.x(), pt.y()))
                    if len(sample_coords) >= 50:
                        break

            effective_crs = self.source_crs
            if effective_crs is None or not effective_crs.isValid():
                if sample_coords:
                    with contextlib.suppress(Exception):
                        det = detect_crs(coordinates=sample_coords)
                        if det.epsg:
                            c = QgsCoordinateReferenceSystem(det.authid)
                            if c.isValid():
                                effective_crs = c
                if effective_crs is None or not effective_crs.isValid():
                    prj_c = QgsProject.instance().crs()
                    if prj_c and prj_c.isValid():
                        effective_crs = prj_c

            is_metric = False
            if sample_coords:
                x_avg = sum(p[0] for p in sample_coords) / len(sample_coords)
                y_avg = sum(p[1] for p in sample_coords) / len(sample_coords)
                if abs(x_avg) > 180.0 or abs(y_avg) > 90.0:
                    is_metric = True

            if effective_crs is None or not effective_crs.isValid():
                if not is_metric:
                    effective_crs = QgsCoordinateReferenceSystem("EPSG:4326")

            uri_crs = f"?crs={effective_crs.authid()}" if (effective_crs and effective_crs.isValid()) else ""
            layer_uri = f"{layer_geom_family}{uri_crs}"
            vlayer = QgsVectorLayer(layer_uri, table_name, "memory")
            if not vlayer.isValid():
                return None

            if effective_crs and effective_crs.isValid():
                vlayer.setCrs(effective_crs)

            qgs_fields = []
            for col_name, col_type in zip(col_names, col_types):
                if col_name == g_col or col_name in (x_col, y_col):
                    continue
                sanitized_name = fix_mojibake(col_name)
                if col_type in (int, float):
                    qtype = QMetaType.Type.Double if col_type == float else QMetaType.Type.Int
                else:
                    qtype = QMetaType.Type.QString
                qgs_fields.append(QgsField(sanitized_name, qtype))

            pr = vlayer.dataProvider()
            pr.addAttributes(qgs_fields)
            vlayer.updateFields()

            features = []
            for r in rows:
                g_val = r[col_names.index(g_col)] if g_col else None
                x_val = r[col_names.index(x_col)] if x_col else None
                y_val = r[col_names.index(y_col)] if y_col else None
                geom = parse_geometry_value(g_val, x_val, y_val)

                feat = QgsFeature(vlayer.fields())
                if geom and not geom.isEmpty():
                    c_geom = _coerce_geometry(geom, layer_geom_family)
                    if c_geom and not c_geom.isEmpty():
                        feat.setGeometry(c_geom)

                attrs = [_clean_attribute_value(r[col_names.index(c)]) for c in attr_cols]
                feat.setAttributes(attrs)
                features.append(feat)

                if len(features) >= 50000:
                    add_features_or_raise(vlayer, features, f"MS Access layer {table_name}")
                    features.clear()

            if features:
                add_features_or_raise(vlayer, features, f"MS Access layer {table_name}")

            vlayer.updateExtents()
            return vlayer
        finally:
            conn.close()
