# -*- coding: utf-8 -*-
"""
SILNIK KONWERSJI GIS — czyta pliki źródłowe i zapisuje wyniki.

Obsługuje DXF, DWG, DGN, GML, KML/KMZ, GeoJSON, GPX, SpatiaLite,
geobazy ArcGIS (.gdb) i MS Access oraz pliki tekstowe CSV/TSV.
Zapisuje do GeoPackage, a przy eksporcie do GML, KML i KMZ.

Na bazie wtyczki zero2cadgis (GPL-2.0-or-later) — patrz ATRYBUCJA.md.
"""
from __future__ import annotations

import contextlib
import os
import re
import zipfile
import tempfile
import shutil
from typing import Optional

from osgeo import ogr, osr, gdal
from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsRasterLayer,
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsPointXY,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsVectorFileWriter,
    QgsFields,
    QgsWkbTypes
)
from qgis.PyQt.QtCore import QMetaType
from qgis.PyQt.QtXml import QDomDocument

from .qgis_compat import add_features_or_raise, memory_geometry_type_name, fix_mojibake
from .csv_sniffer import (
    CsvGeometryProfile,
    build_delimitedtext_uri,
    is_delimited_dataset,
    sniff_delimited_dataset,
)
from . import ogr_catalog_cache
from .dgn_v8_reader import DgnV8Reader, is_dgn_v8 as _is_dgn_v8, check_dgn_driver_available
from .msaccess_reader import MsAccessDbReader, is_msaccess_available
from .crs_detect import detect_crs
from .export_utils import (
    atomic_output,
    exported_feature_count,
    verified_export_result,
)

# CAD source families whose OGR "entities"/"elements" layer carries an
# embedded per-CAD-layer field (DXF ``Layer`` name, DGN ``Level`` number).
CAD_LAYER_FIELDS = ("Layer", "Level")

# Rozszerzenia plików GML — także spakowanych, bo tak bywają
# udostępniane zbiory danych przestrzennych aktów planowania.
GML_EXTENSIONS = (".gml", ".xml")


def _przygotuj_gdal_do_gml(sciezka: str) -> None:
    """Ustawia GDAL tak, żeby dobrze czytał polskie pliki GML.

    Zbiory APP (akty planowania przestrzennego), dane z GESUT czy
    z usług INSPIRE potrafią być mocno zagnieżdżone i pełne odsyłaczy
    xlink. Bez tych ustawień część atrybutów (w tym identyfikatory
    gml:id) po prostu nie trafiłaby do tabeli.
    """
    if not str(sciezka).lower().endswith(GML_EXTENSIONS):
        return
    with contextlib.suppress(Exception):
        # atrybuty XML jako zwykłe kolumny — inaczej giną
        gdal.SetConfigOption("GML_ATTRIBUTES_TO_OGR_FIELDS", "YES")
        # identyfikator obiektu widoczny w tabeli
        gdal.SetConfigOption("GML_EXPOSE_GML_ID", "YES")
        # nie rozwijamy odsyłaczy xlink — przy dużych zbiorach APP
        # potrafi to trwać w nieskończoność
        gdal.SetConfigOption("GML_SKIP_RESOLVE_ELEMS", "ALL")
        # pozwól zapisać plik pomocniczy .gfs obok źródła; dzięki niemu
        # kolejne otwarcie tego samego GML-a jest błyskawiczne
        gdal.SetConfigOption("GML_SAVE_RESOLVED_TO", "SAME")


MAX_KML_XML_BYTES = 64 * 1024 * 1024


class SourceLayerInfo:
    """Lightweight description of one discoverable source layer.

    ``name`` is the display label; ``key`` is the value used to select the
    layer for conversion (the OGR layer name, or a CAD-layer value when a DXF
    or DGN source is split by its ``Layer`` / ``Level`` field). They are equal
    except for the CAD split, where the display may differ (e.g. "(no layer)"
    for an empty CAD-layer value whose key is the empty string).
    """

    __slots__ = ("name", "geometry", "feature_count", "key")

    def __init__(self, name: str, geometry: str, feature_count: int,
                 key: str | None = None):
        self.name = name
        self.geometry = geometry
        self.feature_count = feature_count
        self.key = name if key is None else key


def parse_kml_html_table(html_content: str) -> dict[str, str]:
    """Parses KML balloon descriptions (HTML tables) into structured attributes."""
    attributes = {}
    if not html_content:
        return attributes

    html = html_content.replace("\r", "").replace("\n", " ")

    # tr td lookup
    tr_matches = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.IGNORECASE)
    for tr in tr_matches:
        td_matches = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.IGNORECASE)
        if len(td_matches) >= 2:
            key = re.sub('<[^<]+?>', '', td_matches[0]).strip()
            val = re.sub('<[^<]+?>', '', td_matches[1]).strip()
            clean_key = re.sub(r'\W+', '_', key).lower().strip("_")
            if clean_key and len(clean_key) < 64:
                attributes[clean_key] = val

    if not attributes:
        li_matches = re.findall(r"<li[^>]*>(.*?)</li>", html, re.IGNORECASE)
        for li in li_matches:
            label_match = re.match(
                r"<(b|strong)>(.*?)</\1>\s*:?\s*(.*)", li, re.IGNORECASE)
            if label_match:
                key = re.sub('<[^<]+?>', '', label_match.group(2)).strip()
                val = re.sub('<[^<]+?>', '', label_match.group(3)).strip()
                clean_key = re.sub(r'\W+', '_', key).lower().strip("_")
                if clean_key and len(clean_key) < 64:
                    attributes[clean_key] = val

    return attributes


def _get_geom_type_str(geom) -> str:
    """Helper to detect memory layer compatible geometry type string from QgsGeometry."""
    if not geom or geom.isEmpty():
        return "NoGeometry"

    t = geom.type()
    try:
        t_val = int(t)
    except (TypeError, ValueError):
        t_val = getattr(t, "value", None)
        if t_val is None:
            t_str = str(t).lower()
            if "point" in t_str:
                t_val = 0
            elif "line" in t_str:
                t_val = 1
            elif "polygon" in t_str:
                t_val = 2
            else:
                t_val = 3

    wkb = geom.wkbType()
    is_multi = False
    try:
        is_multi = QgsWkbTypes.isMultiType(wkb)
    except Exception:
        is_multi = False

    if t_val == 0:
        return "MultiPoint" if is_multi else "Point"
    elif t_val == 1:
        return "MultiLineString" if is_multi else "LineString"
    elif t_val == 2:
        return "MultiPolygon" if is_multi else "Polygon"

    return "NoGeometry"


class GisConverterEngine:
    """Core GIS conversion service with HTML parser and GroundOverlay extraction."""

    def __init__(self, source_path: str, target_gpkg: str,
                 target_crs: QgsCoordinateReferenceSystem,
                 csv_profile: CsvGeometryProfile | None = None,
                 csv_source_crs: str = "",
                 source_crs: QgsCoordinateReferenceSystem | str | None = None):
        self.source_path = source_path
        self.target_gpkg = target_gpkg
        self.target_crs = target_crs
        self.temp_dirs = []
        self.last_warnings: list[str] = []
        self.csv_profile = csv_profile
        self.csv_source_crs = csv_source_crs
        self._resolved_src: str | None = None
        self.catalog_from_cache = False
        # When set (to "Layer"/"Level"), the single CAD entities layer is
        # split into one output layer per distinct CAD-layer value.
        self.cad_split_field: str = ""

        self.source_crs: Optional[QgsCoordinateReferenceSystem] = None
        if source_crs:
            if isinstance(source_crs, QgsCoordinateReferenceSystem):
                if source_crs.isValid():
                    self.source_crs = source_crs
            elif isinstance(source_crs, str) and source_crs.strip():
                c = QgsCoordinateReferenceSystem(source_crs)
                if c.isValid():
                    self.source_crs = c
        if self.source_crs is None and csv_source_crs:
            c = QgsCoordinateReferenceSystem(csv_source_crs)
            if c.isValid():
                self.source_crs = c

    def _effective_source_crs(
            self,
            layer: Optional[QgsVectorLayer] = None,
            sample_coords: Optional[list] = None) -> QgsCoordinateReferenceSystem:
        """Resolve a valid source CRS for layer transformation.

        If layer has a valid CRS and its coordinate scale matches (e.g. not EPSG:4326
        when coordinates are clearly metric), return it.
        Otherwise, if explicit source_crs / csv_source_crs is set and valid, use it.
        Otherwise, attempt coordinate auto-detection (detect_crs).
        Fallback to target_crs or active project CRS so CRS is guaranteed valid.
        """
        coords = sample_coords or []
        if not coords and layer is not None:
            with contextlib.suppress(Exception):
                ext = layer.extent()
                if ext and not ext.isEmpty():
                    if abs(ext.xMinimum()) > 180.0 or abs(ext.yMinimum()) > 90.0 or abs(ext.xMaximum()) > 180.0 or abs(ext.yMaximum()) > 90.0:
                        coords = [(ext.center().x(), ext.center().y())]
                if not coords:
                    for feat in layer.getFeatures():
                        geom = feat.geometry()
                        if geom and not geom.isEmpty():
                            pt = geom.centroid().asPoint()
                            coords.append((pt.x(), pt.y()))
                            if len(coords) >= 50:
                                break

        is_metric_coords = False
        if coords:
            x_avg = sum(p[0] for p in coords) / len(coords)
            y_avg = sum(p[1] for p in coords) / len(coords)
            if abs(x_avg) > 180.0 or abs(y_avg) > 90.0:
                is_metric_coords = True

        if layer is not None and layer.crs().isValid():
            if not (is_metric_coords and layer.crs().authid() == "EPSG:4326"):
                return layer.crs()

        if self.source_crs is not None and self.source_crs.isValid():
            return self.source_crs

        if self.csv_source_crs:
            c = QgsCoordinateReferenceSystem(self.csv_source_crs)
            if c.isValid():
                return c

        if coords:
            with contextlib.suppress(Exception):
                detection = detect_crs(coordinates=coords)
                if detection.epsg:
                    c = QgsCoordinateReferenceSystem(detection.authid)
                    if c.isValid():
                        return c

        if self.target_crs and self.target_crs.isValid():
            return self.target_crs

        prj_c = QgsProject.instance().crs()
        if prj_c and prj_c.isValid():
            return prj_c

        # ostatnia deska ratunku: PUWG 1992 przy współrzędnych metrowych,
        # WGS 84 przy stopniach
        return (QgsCoordinateReferenceSystem("EPSG:2180")
                if is_metric_coords
                else QgsCoordinateReferenceSystem("EPSG:4326"))

    # ── source resolution & discovery ────────────────────────────────

    @property
    def is_delimited(self) -> bool:
        return is_delimited_dataset(self.source_path)

    def _resolve_source(self, is_kmz: bool) -> str:
        """Zwraca ścieżkę gotową do odczytu — rozpakowuje KMZ, sprawdza DWG.

        Wtyczka nie korzysta z żadnych zewnętrznych programów: pliki DWG
        czyta wbudowany w QGIS sterownik CAD (GDAL). Radzi sobie ze
        starszymi zapisami (do R2000 włącznie); nowsze trzeba podać jako
        DXF — o czym mówimy wprost, zamiast kazać cokolwiek instalować.
        """
        if self._resolved_src is None:
            raw_path = self.extract_kmz() if is_kmz else self.source_path
            _przygotuj_gdal_do_gml(raw_path)
            if raw_path.lower().endswith(".dwg"):
                czytelny = False
                cad_ds = None
                try:
                    cad_ds = ogr.Open(raw_path)
                except Exception:
                    cad_ds = None
                if cad_ds is not None and cad_ds.GetLayerCount() > 0:
                    with contextlib.suppress(Exception):
                        lyr = cad_ds.GetLayerByIndex(0)
                        fc = lyr.GetFeatureCount()
                        # nowsze DWG dają 0 obiektów albo wyjątek
                        if fc > 0 or (fc == -1
                                      and lyr.GetNextFeature() is not None):
                            czytelny = True
                cad_ds = None

                if not czytelny:
                    raise ValueError(
                        f"Nie udało się odczytać rysunku DWG "
                        f"'{os.path.basename(raw_path)}'.\n\n"
                        f"QGIS czyta bezpośrednio tylko starsze pliki DWG "
                        f"(do wersji R2000). Ten jest zapisany nowszym "
                        f"formatem.\n\n"
                        f"Poproś o ten sam rysunek w formacie DXF albo "
                        f"zapisz go sam: w AutoCAD/BricsCAD/ZWCAD wybierz "
                        f"Plik → Zapisz jako → AutoCAD DXF (*.dxf). "
                        f"DXF wtyczka obsłuży w całości.")

            self._resolved_src = raw_path
        return self._resolved_src

    def _ensure_csv_profile(self) -> CsvGeometryProfile:
        if self.csv_profile is None:
            self.csv_profile = sniff_delimited_dataset(self.source_path)
        return self.csv_profile

    def discover_layers(self, is_kmz: bool = False,
                         use_cache: bool = True) -> list[SourceLayerInfo]:
        """List source layers with geometry type and feature counts.

        Multi-layer OGR sources are cached by a content fingerprint (see
        :mod:`ogr_catalog_cache`), so reopening an unchanged Geodatabase or
        database returns its catalog without reopening the driver.
        """
        if self.is_delimited:
            profile = self._ensure_csv_profile()
            stem = os.path.splitext(os.path.basename(self.source_path))[0]
            geometry = ("Point" if profile.has_point_geometry
                        else "WKT" if profile.has_wkt_geometry
                        else "Table")
            return [SourceLayerInfo(stem, geometry, profile.row_count)]

        if use_cache:
            cached = ogr_catalog_cache.load(self.source_path)
            if cached is not None:
                self.catalog_from_cache = True
                return [SourceLayerInfo(
                    row.get("name", ""), row.get("geometry", "Unknown"),
                    int(row.get("feature_count", -1))) for row in cached]

        infos = []
        for prefix, src in self._ogr_sources(is_kmz):
            ogr_ds = None
            if not src.lower().endswith(".dgn") or check_dgn_driver_available() or not _is_dgn_v8(src):
                try:
                    ogr_ds = ogr.Open(src)
                except Exception:
                    ogr_ds = None

            # --- MS Access (.accdb / .mdb) fallback (if ogr.Open failed or returned 0 layers) ---
            if (ogr_ds is None or ogr_ds.GetLayerCount() == 0) and src.lower().endswith((".accdb", ".mdb")) and is_msaccess_available():
                ms_reader = MsAccessDbReader(src, self.source_crs)
                with contextlib.suppress(Exception):
                    ms_tables = ms_reader.list_tables()
                    for t in ms_tables:
                        infos.append(SourceLayerInfo(f"{prefix}{t['name']}", t["geometry"], int(t["feature_count"])))
                    if ogr_ds:
                        ogr_ds = None
                    continue

            # --- DGN fallback (if ogr.Open failed or returned 0 layers on DGN) ---
            if (ogr_ds is None or (src.lower().endswith(".dgn") and ogr_ds.GetLayerCount() == 0)) \
                    and src.lower().endswith(".dgn") and self._try_dgn_fallback(src):
                infos.append(SourceLayerInfo(
                    "DGN Entities", "LineString/Polygon",
                    self._dgn_count_elements(src)))
                if ogr_ds:
                    ogr_ds = None
                continue

            if ogr_ds is None:
                raise ValueError(self._open_error_message(src))
            for i in range(ogr_ds.GetLayerCount()):
                ogr_layer = ogr_ds.GetLayerByIndex(i)
                try:
                    geometry = ogr.GeometryTypeToName(ogr_layer.GetGeomType())
                except Exception:
                    geometry = "Unknown"
                try:
                    count = ogr_layer.GetFeatureCount()
                except Exception:
                    count = -1
                infos.append(SourceLayerInfo(
                    f"{prefix}{ogr_layer.GetName()}", geometry, count))
            ogr_ds = None

        if use_cache:
            ogr_catalog_cache.save(self.source_path, [
                {"name": i.name, "geometry": i.geometry,
                 "feature_count": i.feature_count} for i in infos])
        return infos

    @staticmethod
    def _ogr_geom_family(geom_name: str) -> str:
        name = (geom_name or "").upper()
        if "POINT" in name:
            return "Point"
        if "POLYGON" in name:
            return "Polygon"
        if "LINE" in name or "CURVE" in name:
            return "LineString"
        return "Other"

    # ------------------------------------------------------------------
    # DGN v8 pure-Python fallback
    # ------------------------------------------------------------------

    @staticmethod
    def _try_dgn_fallback(src: str) -> Optional[DgnV8Reader]:
        """Return an open :class:`DgnV8Reader` if *src* is a DGN file
        the pure-Python reader can handle, or ``None``.

        Unlike :func:`is_dgn_v8` this does not pre-flight the OLE2
        signature — it just tries to open the file and returns the
        reader on success so the caller can use it immediately.
        """
        if not src.lower().endswith(".dgn"):
            return None
        try:
            reader = DgnV8Reader(src)
            reader.open()
            # Consume elements (up to 1) to verify reader works
            for _elem in reader.elements():
                reader.close()
                return DgnV8Reader(src)
            reader.close()
            return None  # file opened but zero elements
        except Exception:
            return None

    def _dgn_fallback_discover_cad(
            self, src: str) -> tuple[list[SourceLayerInfo], str]:
        """Discover CAD layers from a DGN v8 file using the pure-Python
        reader when GDAL's DGNv8 driver is unavailable."""
        field = "Level"
        self.cad_split_field = field
        groups: dict[str, dict] = {}
        layer_names: dict[int, str] = {}

        with DgnV8Reader(src) as reader:
            try:
                layer_names = reader.layer_names()
            except Exception:
                layer_names = {}
            for elem in reader.elements():
                key = str(elem.level)
                rec = groups.setdefault(key, {"count": 0, "families": set()})
                rec["count"] += 1
                if elem.geometry:
                    if len(elem.geometry) == 1:
                        fam = "Point"
                    elif (elem.element_type == 6
                          and elem.geometry
                          and self._is_closed(elem.geometry)):
                        fam = "Polygon"
                    else:
                        fam = "LineString"
                    rec["families"].add(fam)

        infos: list[SourceLayerInfo] = []
        for key in sorted(groups, key=lambda k: int(k) if k.isdigit() else 0):
            rec = groups[key]
            fam_str = "/".join(sorted(rec["families"])) or "LineString"
            lvl_num = int(key) if key.isdigit() else -1
            lname = layer_names.get(lvl_num, "")
            display_name = f"{lname} (Level {key})" if lname else f"Level {key}"
            infos.append(SourceLayerInfo(
                display_name, fam_str, rec["count"], key=key))
        return infos, field

    def _dgn_fallback_iter_layers(
            self, src: str,
            selected_levels: list[str] | None = None):
        """Yield ``(level_display, QgsVectorLayer)`` for each DGN Level
        using the pure-Python reader."""
        import collections

        # Group elements by Level
        level_elems: dict[str, list] = collections.defaultdict(list)
        layer_names = {}
        with DgnV8Reader(src) as reader:
            try:
                layer_names = reader.layer_names()
            except Exception:
                layer_names = {}
            for elem in reader.elements():
                level_elems[str(elem.level)].append(elem)

        if selected_levels is None:
            levels_to_yield = list(level_elems.keys())
        else:
            levels_to_yield = []
            for key in level_elems.keys():
                lvl_num = int(key) if key.isdigit() else -1
                lname = layer_names.get(lvl_num, "")
                disp = f"{lname} (Level {key})" if lname else f"Level {key}"
                if (key in selected_levels or
                        disp in selected_levels or
                        f"Level {key}" in selected_levels or
                        (lname and lname in selected_levels)):
                    levels_to_yield.append(key)

        for level_key in levels_to_yield:
            elems = level_elems.get(level_key, [])
            if not elems:
                continue
            lvl_num = int(level_key) if level_key.isdigit() else -1
            lname = layer_names.get(lvl_num, "")
            display = f"{lname} (Level {level_key})" if lname else f"Level {level_key}"
            vlayer = self._dgn_elements_to_memory_layer(
                display, elems, level_key, level_name=lname)
            if vlayer is not None and vlayer.isValid():
                yield display, vlayer

    @staticmethod
    def _coerce_geometry_for_layer(
            geom: Optional[QgsGeometry],
            target_type: str) -> Optional[QgsGeometry]:
        """Coerce a QgsGeometry to match the memory layer's WKB geometry family."""
        if not geom or geom.isEmpty():
            return None

        # Flatten 3D (Z) coordinates and segmentize curved geometries for 2D memory layers
        with contextlib.suppress(Exception):
            if QgsWkbTypes.isCurved(geom.wkbType()):
                geom = geom.constrainedStraightSegmentedGeometry()
            if QgsWkbTypes.hasZ(geom.wkbType()) and geom.get():
                g_copy = QgsGeometry(geom)
                g_copy.get().dropZValue()
                geom = g_copy

        try:
            gt = geom.type()
        except Exception:
            return geom

        try:
            is_line_geom = (gt == QgsWkbTypes.GeometryType.LineGeometry)
            is_poly_geom = (gt == QgsWkbTypes.GeometryType.PolygonGeometry)
            is_point_geom = (gt == QgsWkbTypes.GeometryType.PointGeometry)
        except Exception:
            t_str = str(gt).lower()
            is_line_geom = "line" in t_str
            is_poly_geom = "polygon" in t_str
            is_point_geom = "point" in t_str

        if target_type in ("LineString", "MultiLineString"):
            if is_line_geom:
                g_out = geom
            elif is_poly_geom:
                poly = geom.asPolygon()
                if poly and poly[0]:
                    g_out = QgsGeometry.fromPolylineXY(poly[0])
                else:
                    mpoly = geom.asMultiPolygon()
                    g_out = QgsGeometry.fromPolylineXY(mpoly[0][0]) if (mpoly and mpoly[0] and mpoly[0][0]) else None
            elif is_point_geom:
                pt = geom.asPoint()
                g_out = QgsGeometry.fromPolylineXY([pt, pt])
            else:
                g_out = geom

            if g_out and not g_out.isEmpty():
                if target_type == "MultiLineString" and not QgsWkbTypes.isMultiType(g_out.wkbType()):
                    g_copy = QgsGeometry(g_out)
                    g_copy.convertToMultiType()
                    return g_copy
                elif target_type == "LineString" and QgsWkbTypes.isMultiType(g_out.wkbType()):
                    g_copy = QgsGeometry(g_out)
                    g_copy.convertToSingleType()
                    return g_copy
            return g_out

        elif target_type in ("Polygon", "MultiPolygon"):
            if is_poly_geom:
                g_out = geom
            elif is_line_geom:
                pts = geom.asPolyline()
                if len(pts) >= 3:
                    if pts[0] != pts[-1]:
                        pts = list(pts) + [pts[0]]
                    g_out = QgsGeometry.fromPolygonXY([pts])
                else:
                    g_out = None
            else:
                g_out = geom

            if g_out and not g_out.isEmpty():
                if target_type == "MultiPolygon" and not QgsWkbTypes.isMultiType(g_out.wkbType()):
                    g_copy = QgsGeometry(g_out)
                    g_copy.convertToMultiType()
                    return g_copy
                elif target_type == "Polygon" and QgsWkbTypes.isMultiType(g_out.wkbType()):
                    g_copy = QgsGeometry(g_out)
                    g_copy.convertToSingleType()
                    return g_copy
            return g_out

        elif target_type in ("Point", "MultiPoint"):
            if is_point_geom:
                g_out = geom
            else:
                c = geom.centroid()
                g_out = c if c and not c.isEmpty() else None

            if g_out and not g_out.isEmpty():
                if target_type == "MultiPoint" and not QgsWkbTypes.isMultiType(g_out.wkbType()):
                    g_copy = QgsGeometry(g_out)
                    g_copy.convertToMultiType()
                    return g_copy
                elif target_type == "Point" and QgsWkbTypes.isMultiType(g_out.wkbType()):
                    g_copy = QgsGeometry(g_out)
                    g_copy.convertToSingleType()
                    return g_copy
            return g_out

        return geom

    def _dgn_elements_to_memory_layer(
            self, name: str, elements: list,
            level_key: str, level_name: str = "") -> Optional[QgsVectorLayer]:
        """Convert a list of :class:`DgnElement` objects into a QGIS
        memory layer."""
        if not elements:
            return None

        has_polygon = False
        has_line = False
        has_point = False
        for elem in elements:
            n = len(elem.geometry)
            if n == 0:
                continue
            if (elem.element_type == 6 and n >= 3
                    and self._is_closed(elem.geometry)):
                has_polygon = True
            elif n >= 3 and self._is_closed(elem.geometry):
                has_polygon = True
            elif n >= 2:
                has_line = True
            elif n == 1:
                has_point = True

        if has_polygon and not has_line:
            geom_type = "Polygon"
        elif has_polygon or has_line:
            geom_type = "LineString"
        elif has_point:
            geom_type = "Point"
        else:
            geom_type = "LineString"

        all_pts = []
        for elem in elements:
            if elem.geometry:
                all_pts.extend(elem.geometry[:2])
                if len(all_pts) >= 50:
                    break

        src_crs = self._effective_source_crs(sample_coords=all_pts)

        wkt_prefix = f"{geom_type}?crs={src_crs.authid()}"
        vlayer = QgsVectorLayer(wkt_prefix, name, "memory")
        if not vlayer.isValid():
            return None
        vlayer.setCrs(src_crs)

        pr = vlayer.dataProvider()
        pr.addAttributes([
            QgsField("dgn_level", QMetaType.Type.Int),
            QgsField("dgn_level_name", QMetaType.Type.QString),
            QgsField("dgn_color", QMetaType.Type.Int),
            QgsField("dgn_weight", QMetaType.Type.Int),
            QgsField("dgn_style", QMetaType.Type.Int),
            QgsField("dgn_type", QMetaType.Type.QString),
        ])
        vlayer.updateFields()

        features: list[QgsFeature] = []
        for elem in elements:
            if not elem.geometry:
                continue
            valid_pts = [
                pt for pt in elem.geometry
                if 100_000.0 <= pt[0] <= 16_000_000.0
                and 100_000.0 <= pt[1] <= 16_000_000.0
                and abs(pt[0] - pt[1]) >= 1.0
            ]
            if not valid_pts:
                continue
            raw_geom = self._points_to_qgs_geometry(
                valid_pts, elem.element_type == 6, geom_type)
            if raw_geom is None:
                continue
            geom = self._coerce_geometry_for_layer(raw_geom, geom_type)
            if geom is None:
                continue
            feat = QgsFeature(vlayer.fields())
            feat.setGeometry(geom)
            feat.setAttributes([
                elem.level, level_name or elem.type_name, elem.color_index,
                elem.weight, elem.style, elem.type_name,
            ])
            features.append(feat)
            if len(features) >= 50000:
                add_features_or_raise(vlayer, features, "DGN memory layer")
                features.clear()
        if features:
            add_features_or_raise(vlayer, features, "DGN memory layer")

        vlayer.updateExtents()
        return vlayer

    @staticmethod
    def _points_to_qgs_geometry(
            points: list, is_shape: bool,
            fallback_geom_type: str) -> Optional[QgsGeometry]:
        """Convert a list of (x, y) pairs to a :class:`QgsGeometry`."""
        n = len(points)
        if n == 0:
            return None
        if n == 1:
            return QgsGeometry.fromPointXY(
                QgsPointXY(points[0][0], points[0][1]))
        if n >= 3 and is_shape:
            # Ensure the ring is closed
            if points[0] != points[-1]:
                pts = list(points) + [points[0]]
            else:
                pts = list(points)
            return QgsGeometry.fromPolygonXY([
                [QgsPointXY(x, y) for x, y in pts]])
        return QgsGeometry.fromPolylineXY(
            [QgsPointXY(x, y) for x, y in points])

    @staticmethod
    def _is_closed(points: list) -> bool:
        """Return ``True`` if the first and last points coincide."""
        if len(points) < 3:
            return False
        p0, pn = points[0], points[-1]
        dx = abs(p0[0] - pn[0])
        dy = abs(p0[1] - pn[1])
        return dx < 1e-6 and dy < 1e-6

    @staticmethod
    def _dgn_count_elements(src: str) -> int:
        """Count elements in a DGN v8 file (fast — just counts streams)."""
        try:
            with DgnV8Reader(src) as reader:
                return sum(1 for _ in reader.elements())
        except Exception:
            return -1

    def discover_cad_layers(
            self, is_kmz: bool = False) -> tuple[list[SourceLayerInfo], str]:
        """Group a CAD entities layer by its embedded CAD-layer field.

        DXF and DGN files expose a single OGR layer whose features each carry
        a CAD-layer name (DXF ``Layer``) or level number (DGN ``Level``). This
        returns one :class:`SourceLayerInfo` per distinct CAD-layer value,
        with its geometry families and feature count, plus the field name that
        was used (empty string if the source has no such field). The field is
        remembered so a later :meth:`convert` splits by it.
        """
        src = self._resolve_source(is_kmz)

        # --- DGN v8 fallback (GDAL lacks the DGNv8 driver) ---
        if src.lower().endswith(".dgn"):
            if not check_dgn_driver_available() and _is_dgn_v8(src):
                if self._try_dgn_fallback(src):
                    return self._dgn_fallback_discover_cad(src)
            else:
                dgn_ds = ogr.Open(src)
                if (dgn_ds is None or dgn_ds.GetLayerCount() == 0) and self._try_dgn_fallback(src):
                    return self._dgn_fallback_discover_cad(src)
                dgn_ds = None

        ogr_ds = ogr.Open(src)
        if ogr_ds is None:
            raise ValueError(self._open_error_message(src))
        if ogr_ds.GetLayerCount() == 0:
            ogr_ds = None
            return [], ""

        layer = ogr_ds.GetLayerByIndex(0)
        defn = layer.GetLayerDefn()
        field_names = [defn.GetFieldDefn(i).GetName()
                       for i in range(defn.GetFieldCount())]
        field = next((f for f in CAD_LAYER_FIELDS if f in field_names), "")
        if not field:
            ogr_ds = None
            return [], ""

        groups: dict[str, dict] = {}
        layer.ResetReading()
        for feat in layer:
            value = feat.GetField(field)
            key = "" if value is None else fix_mojibake(str(value))
            geom = feat.GetGeometryRef()
            gname = geom.GetGeometryName() if geom else "NONE"
            rec = groups.setdefault(key, {"count": 0, "families": set()})
            rec["count"] += 1
            rec["families"].add(self._ogr_geom_family(gname))
        ogr_ds = None

        dgn_layer_names = {}
        if src.lower().endswith(".dgn"):
            with contextlib.suppress(Exception):
                with DgnV8Reader(src) as reader:
                    dgn_layer_names = reader.layer_names()

        self.cad_split_field = field
        infos = []
        for key in sorted(groups):
            rec = groups[key]
            lvl_num = int(key) if key.isdigit() else -1
            lname = fix_mojibake(dgn_layer_names.get(lvl_num, ""))
            display_name = f"{lname} (Level {key})" if lname else (key or "(no layer)")
            display_name = fix_mojibake(display_name)
            infos.append(SourceLayerInfo(
                display_name,
                "/".join(sorted(rec["families"])),
                rec["count"],
                key=key))
        return infos, field

    def _iter_cad_layers(self, src: str,
                         selected_values: list[str] | None):
        """Yield ``(cad_layer_value, QgsVectorLayer)`` per CAD-layer subset."""
        field = self.cad_split_field

        # --- DGN v8 fallback ---
        if src.lower().endswith(".dgn"):
            if not check_dgn_driver_available() and _is_dgn_v8(src):
                if self._try_dgn_fallback(src):
                    yield from self._dgn_fallback_iter_layers(
                        src, selected_values)
                    return
            else:
                test_ds = ogr.Open(src)
                if (test_ds is None or test_ds.GetLayerCount() == 0) and self._try_dgn_fallback(src):
                    yield from self._dgn_fallback_iter_layers(
                        src, selected_values)
                    return
                test_ds = None

        ogr_ds = ogr.Open(src)
        if ogr_ds is None or ogr_ds.GetLayerCount() == 0:
            raise ValueError(self._open_error_message(src))
        base_layer = ogr_ds.GetLayerByIndex(0)
        entities_name = base_layer.GetName()
        defn = base_layer.GetLayerDefn()
        is_numeric = False
        for i in range(defn.GetFieldCount()):
            fd = defn.GetFieldDefn(i)
            if fd.GetName() == field:
                is_numeric = fd.GetType() in (
                    ogr.OFTInteger, ogr.OFTInteger64, ogr.OFTReal)
                break
        ogr_ds = None

        if selected_values is None:
            infos, _ = self.discover_cad_layers(is_kmz=False)
            values = [i.key for i in infos] if infos else [None]
        else:
            values = selected_values

        dgn_layer_names = {}
        if src.lower().endswith(".dgn"):
            with contextlib.suppress(Exception):
                with DgnV8Reader(src) as reader:
                    dgn_layer_names = reader.layer_names()

        for value in values:
            uri = f"{src}|layername={entities_name}"
            lvl_num = int(value) if str(value).isdigit() else -1
            lname = fix_mojibake(dgn_layer_names.get(lvl_num, ""))
            if lname and value not in (None, ""):
                display = f"{lname} (Level {value})"
            elif value not in (None, ""):
                display = f"Level {value}"
            else:
                display = "NO_LAYER"
            display = fix_mojibake(display)
            vlayer = QgsVectorLayer(uri, display, "ogr")
            if not vlayer.isValid():
                self.last_warnings.append(
                    f"Warstwy rysunku '{display}' nie dało się odczytać — pominięta.")
                continue
            if not vlayer.crs().isValid():
                vlayer.setCrs(self._effective_source_crs(vlayer))
            if value is None:
                pass
            elif value == "":
                vlayer.setSubsetString(
                    f'"{field}" IS NULL')
            elif is_numeric:
                vlayer.setSubsetString(f'"{field}" = {value}')
            else:
                escaped = str(value).replace("'", "''")
                vlayer.setSubsetString(f"\"{field}\" = '{escaped}'")
            yield display, vlayer

    @staticmethod
    def _check_dgn_driver(src: str) -> str | None:
        """Wyjaśnia po polsku, czemu nie da się otworzyć pliku DGN.

        Standardowy QGIS ma sterownik DGN v7, ale nie ma DGNv8. Wtyczka
        ma własny czytnik plików DGN v8 — ta wiadomość pojawia się
        dopiero wtedy, gdy i on nie da rady.
        """
        if not src.lower().endswith(".dgn"):
            return None
        if ogr.GetDriverByName("DGNv8") is not None:
            return None
        return (
            "Nie udało się odczytać pliku Microstation DGN.\n\n"
            "QGIS otwiera bezpośrednio starsze rysunki DGN (v7). Ten plik "
            "wygląda na nowszy zapis (v8) — wtyczka próbowała go odczytać "
            "własnym czytnikiem, ale rysunek okazał się dla niego za "
            "nietypowy.\n\n"
            "Najprościej: poproś o ten rysunek w formacie DXF albo zapisz "
            "go jako DXF w Microstation (Plik → Eksport → DXF). "
            "DXF wtyczka obsłuży w całości."
        )

    def _open_error_message(self, src: str) -> str:
        dgn_msg = self._check_dgn_driver(src)
        if dgn_msg is not None:
            return dgn_msg
        if src.lower().endswith((".mdb", ".accdb")):
            return (
                f"Nie udało się otworzyć bazy MS Access: {src}\n\n"
                "Bazy .accdb / .mdb (w tym geobazy personalne) Windows "
                "otwiera przez sterownik Microsoft Access Database Engine. "
                "Jeśli go nie masz, pobierz wersję 64-bitową ze stron "
                "Microsoftu — musi być zgodna z QGIS-em (zwykle 64 bity)."
            )
        return f"Nie udało się otworzyć pliku źródłowego (GDAL/OGR): {src}"

    def _iter_source_layers(self, is_kmz: bool,
                            selected_layers: list[str] | None):
        """Yield ``(layer_name, QgsVectorLayer)`` for each requested layer."""
        if self.is_delimited:
            profile = self._ensure_csv_profile()
            stem = os.path.splitext(os.path.basename(self.source_path))[0]
            if selected_layers is not None and stem not in selected_layers:
                return
            uri = build_delimitedtext_uri(
                self.source_path, profile, self.csv_source_crs)
            vlayer = QgsVectorLayer(uri, stem, "delimitedtext")
            if not vlayer.isValid():
                raise ValueError(
                    "Nie udało się wczytać pliku tekstowego. Sprawdź "
                    "wykryty separator oraz kolumny z geometrią.")
            yield stem, vlayer
            return

        if self.cad_split_field:
            yield from self._iter_cad_layers(
                self._resolve_source(is_kmz), selected_layers)
            return

        found_any = False
        for prefix, src in self._ogr_sources(is_kmz):
            ogr_ds = None
            if not src.lower().endswith(".dgn") or check_dgn_driver_available() or not _is_dgn_v8(src):
                try:
                    ogr_ds = ogr.Open(src)
                except Exception:
                    ogr_ds = None

            # --- MS Access (.accdb / .mdb) fallback (non-CAD-split mode) ---
            if (ogr_ds is None or ogr_ds.GetLayerCount() == 0) and src.lower().endswith((".accdb", ".mdb")) and is_msaccess_available():
                ms_reader = MsAccessDbReader(src, self.source_crs)
                with contextlib.suppress(Exception):
                    ms_tables = ms_reader.list_tables()
                    for t in ms_tables:
                        layer_name = t["name"]
                        display = f"{prefix}{layer_name}"
                        if selected_layers is not None and display not in selected_layers:
                            continue
                        vlayer = ms_reader.read_layer(layer_name)
                        if vlayer is not None and vlayer.isValid():
                            found_any = True
                            yield display, vlayer
                    continue

            # --- DGN v8 fallback (non-CAD-split mode) ---
            if (ogr_ds is None or (src.lower().endswith(".dgn") and ogr_ds.GetLayerCount() == 0)) \
                    and src.lower().endswith(".dgn"):
                dgn_reader = self._try_dgn_fallback(src)
                if dgn_reader is not None:
                    layer_name = "DGN Entities"
                    display = f"{prefix}{layer_name}"
                    if selected_layers is not None \
                            and display not in selected_layers:
                        dgn_reader.close()
                        continue
                    with dgn_reader:
                        elems = list(dgn_reader.elements())
                    vlayer = self._dgn_elements_to_memory_layer(
                        layer_name, elems, "0")
                    if vlayer is not None and vlayer.isValid():
                        found_any = True
                        yield display, vlayer
                    continue

            if ogr_ds is None:
                raise ValueError(self._open_error_message(src))
            layer_names = [ogr_ds.GetLayerByIndex(i).GetName()
                           for i in range(ogr_ds.GetLayerCount())]
            ogr_ds = None

            for layer_name in layer_names:
                found_any = True
                display = f"{prefix}{layer_name}"
                if selected_layers is not None \
                        and display not in selected_layers:
                    continue
                uri = f"{src}|layername={layer_name}"
                vlayer = QgsVectorLayer(uri, display, "ogr")
                if not vlayer.isValid():
                    self.last_warnings.append(
                        f"Warstwy '{display}' nie dało się odczytać — pominięta.")
                    continue
                yield display, vlayer

        if not found_any:
            raise ValueError(
                "W pliku źródłowym nie ma żadnych warstw do wczytania.")

    def cleanup(self):
        for temp_dir in self.temp_dirs:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)

    def extract_kmz(self) -> str:
        """Extract a KMZ archive and return the primary KML path.

        ``doc.kml`` is the KMZ convention for the main document, so it is
        preferred; otherwise the first KML in sorted order is used. All KML
        documents are extracted, so :meth:`_kml_docs` can enumerate the rest.
        """
        temp_dir = tempfile.mkdtemp(prefix="gis_kmz_")
        self.temp_dirs.append(temp_dir)

        with zipfile.ZipFile(self.source_path, 'r') as zip_ref:
            kml_files = [
                n for n in zip_ref.namelist() if n.lower().endswith(".kml")]
            if not kml_files:
                raise ValueError("W paczce KMZ nie znaleziono pliku KML.")
            zip_ref.extractall(temp_dir)

        doc = next((n for n in kml_files
                    if os.path.basename(n).lower() == "doc.kml"), None)
        primary = doc if doc is not None else sorted(kml_files)[0]
        return os.path.join(temp_dir, primary)

    def _kml_docs(self, is_kmz: bool) -> list[str]:
        """Return every KML document to read for the current source.

        For a plain KML this is just the file; for a KMZ it is every extracted
        ``.kml`` with the primary document first, so additional KML documents
        inside a multi-document KMZ are not silently dropped.
        """
        primary = self._resolve_source(is_kmz)
        if not is_kmz:
            return [primary]
        folder = os.path.dirname(primary)
        docs = []
        for root, _dirs, files in os.walk(folder):
            for name in sorted(files):
                if name.lower().endswith(".kml"):
                    docs.append(os.path.join(root, name))
        ordered = [primary] + [d for d in docs if d != primary]
        return ordered or [primary]

    def _ogr_sources(self, is_kmz: bool) -> list[tuple[str, str]]:
        """Yield ``(name_prefix, dataset_path)`` for each OGR source to open.

        A single dataset yields one entry with an empty prefix. A
        multi-document KMZ yields one entry per KML document, each prefixed
        with its document stem so layers from different documents stay
        distinct.
        """
        if is_kmz:
            docs = self._kml_docs(is_kmz)
            multi = len(docs) > 1
            sources = []
            for path in docs:
                stem = os.path.splitext(os.path.basename(path))[0]
                prefix = f"{stem}_" if multi else ""
                sources.append((prefix, path))
            return sources
        return [("", self._resolve_source(is_kmz))]

    def convert(
            self,
            is_kmz: bool = False,
            html_expansion: bool = True,
            selected_layers: list[str] | None = None,
            progress_cb=None) -> list[QgsVectorLayer]:
        """Converts GIS layers to GPKG and returns list of loaded vector layers."""
        # Re-create target GPKG
        if os.path.exists(self.target_gpkg):
            # gdy pliku nie da się skasować (np. jest otwarty w QGIS),
            # zapis i tak spróbuje go nadpisać
            with contextlib.suppress(OSError):
                os.remove(self.target_gpkg)

        loaded_layers = []
        transform_context = QgsProject.instance().transformContext()
        wrote_any = False

        for layer_name, vlayer in self._iter_source_layers(
                is_kmz, selected_layers):
            if progress_cb:
                progress_cb(layer_name)

            processed_layer = vlayer
            if html_expansion and "description" in [
                    f.name() for f in vlayer.fields()]:
                processed_layer = self._expand_html_descriptions(vlayer)

            # CAD layer subsets can mix geometry types; a GeoPackage layer
            # holds one geometry type, so split them before writing.
            if self.cad_split_field:
                wrote_any = self._write_cad_layer_gpkg(
                    processed_layer, layer_name, wrote_any,
                    transform_context, loaded_layers)
                continue

            # Define writer options
            options = QgsVectorFileWriter.SaveVectorOptions()
            options.driverName = "GPKG"
            options.layerName = self._sanitize_column_name(layer_name)

            # GML/GeoJSON sources may carry a non-integer "fid" attribute;
            # GPKG reserves fid for its integer primary key, so move the
            # primary key to another column in that case.
            fid_index = processed_layer.fields().lookupField("fid")
            if fid_index >= 0:
                fid_type = processed_layer.fields()[fid_index] \
                    .typeName().lower()
                if fid_type not in (
                        "integer", "integer64", "int", "int2", "int4",
                        "int8", "int16", "int32", "int64", "long",
                        "longlong"):
                    options.layerOptions = ["FID=cadgis_fid"]
            options.actionOnExistingFile = (
                QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteLayer
                if wrote_any
                else QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteFile
            )

            src_crs = self._effective_source_crs(processed_layer)
            processed_layer.setCrs(src_crs)
            if src_crs != self.target_crs:
                options.ct = QgsCoordinateTransform(
                    src_crs, self.target_crs, QgsProject.instance())

            err, err_msg, _, _ = QgsVectorFileWriter.writeAsVectorFormatV3(
                processed_layer,
                self.target_gpkg,
                transform_context,
                options
            )
            if err != QgsVectorFileWriter.WriterError.NoError:
                raise ValueError(
                    f"Nie udało się zapisać warstwy '{layer_name}' do GeoPackage: {err_msg}")
            wrote_any = True

            gpkg_uri = f"{self.target_gpkg}|layername={options.layerName}"
            gpkg_layer = QgsVectorLayer(gpkg_uri, layer_name, "ogr")
            if gpkg_layer.isValid():
                loaded_layers.append(gpkg_layer)

        if not wrote_any:
            raise ValueError(
                "Żadna z zaznaczonych warstw nie nadaje się do odczytu.")
        return loaded_layers

    def _write_cad_layer_gpkg(self, processed_layer, layer_name, wrote_any,
                              transform_context, loaded_layers) -> bool:
        """Write one CAD-layer subset to GPKG, split by geometry type."""
        src_crs = self._effective_source_crs(processed_layer)
        if not processed_layer.crs().isValid():
            processed_layer.setCrs(src_crs)

        transform = None
        if src_crs.isValid() and src_crs != self.target_crs:
            transform = QgsCoordinateTransform(
                src_crs, self.target_crs, QgsProject.instance())

        groups: dict[str, list] = {}
        for feat in processed_layer.getFeatures():
            geom = feat.geometry()
            if geom and not geom.isEmpty() and transform:
                geom.transform(transform)
            geom_type_str = _get_geom_type_str(geom)
            if geom_type_str == "NoGeometry":
                continue
            groups.setdefault(geom_type_str, []).append((geom, feat))

        dgn_layer_names = {}
        if self.source_path.lower().endswith(".dgn"):
            with contextlib.suppress(Exception):
                with DgnV8Reader(self.source_path) as reader:
                    dgn_layer_names = reader.layer_names()

        for geom_type_str, type_data in sorted(groups.items()):
            mem_uri = f"{geom_type_str}?crs={self.target_crs.authid()}"
            mem_layer = QgsVectorLayer(mem_uri, layer_name, "memory")
            prov = mem_layer.dataProvider()
            fields = QgsFields(processed_layer.fields())
            if dgn_layer_names and "dgn_level_name" not in fields.names():
                fields.append(QgsField("dgn_level_name", QMetaType.Type.QString))
            prov.addAttributes(fields)
            mem_layer.updateFields()

            features = []
            for geom, original_feat in type_data:
                new_feat = QgsFeature(mem_layer.fields())
                coerced = self._coerce_geometry_for_layer(geom, geom_type_str)
                new_feat.setGeometry(coerced or geom)
                attrs = [
                    fix_mojibake(a) if isinstance(a, str) else a
                    for a in original_feat.attributes()
                ]
                if len(attrs) < len(mem_layer.fields()):
                    attrs.extend([None] * (len(mem_layer.fields()) - len(attrs)))

                lvl_val = None
                if "Level" in original_feat.fields().names():
                    lvl_val = original_feat["Level"]
                elif "dgn_level" in original_feat.fields().names():
                    lvl_val = original_feat["dgn_level"]

                if lvl_val is not None:
                    lvl_num = int(lvl_val) if str(lvl_val).isdigit() else -1
                    lname = fix_mojibake(dgn_layer_names.get(lvl_num, ""))
                    if lname:
                        if "dgn_level_name" in mem_layer.fields().names():
                            idx = mem_layer.fields().indexOf("dgn_level_name")
                            attrs[idx] = lname
                        if "Layer" in mem_layer.fields().names():
                            idx = mem_layer.fields().indexOf("Layer")
                            attrs[idx] = lname

                attrs = [
                    fix_mojibake(a) if isinstance(a, str) else a
                    for a in attrs
                ]
                new_feat.setAttributes(attrs)
                features.append(new_feat)
            add_features_or_raise(mem_layer, features, "CAD layer split")

            base = self._sanitize_column_name(layer_name)
            gpkg_layer_name = (
                base if len(groups) == 1
                else f"{base}_{geom_type_str.upper()}")

            options = QgsVectorFileWriter.SaveVectorOptions()
            options.driverName = "GPKG"
            options.layerName = gpkg_layer_name
            options.actionOnExistingFile = (
                QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteLayer
                if wrote_any
                else QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteFile
            )
            err, err_msg, _, _ = QgsVectorFileWriter.writeAsVectorFormatV3(
                mem_layer, self.target_gpkg, transform_context, options)
            if err != QgsVectorFileWriter.WriterError.NoError:
                raise ValueError(
                    f"Nie udało się zapisać warstwy rysunku '{layer_name}' do GeoPackage: "
                    f"{err_msg}")
            wrote_any = True

            gpkg_uri = f"{self.target_gpkg}|layername={gpkg_layer_name}"
            gpkg_layer = QgsVectorLayer(gpkg_uri, gpkg_layer_name, "ogr")
            if gpkg_layer.isValid():
                loaded_layers.append(gpkg_layer)
        return wrote_any

    def load_layers_live(
            self,
            is_kmz: bool = False,
            selected_layers: list[str] | None = None,
            progress_cb=None) -> list[QgsVectorLayer]:
        """Return the selected source layers as live, zero-copy references.

        Unlike :meth:`convert` (which writes a GeoPackage) and
        :meth:`convert_to_memory` (which copies every feature into RAM), this
        hands back the source-referencing ``QgsVectorLayer`` objects directly.
        No geometry is read, copied, or reprojected, so even a multi-million
        feature Geodatabase layer becomes usable in milliseconds; QGIS reads
        features lazily from the source and reprojects on the fly using each
        layer's own CRS.
        """
        loaded_layers = []
        for layer_name, vlayer in self._iter_source_layers(
                is_kmz, selected_layers):
            if progress_cb:
                progress_cb(layer_name)
            loaded_layers.append(vlayer)

        if not loaded_layers:
            raise ValueError(
                "Żadna z zaznaczonych warstw nie nadaje się do podglądu.")
        return loaded_layers

    def extract_ground_overlays(
            self, is_kmz: bool = False) -> list[QgsRasterLayer]:
        """Discovers GroundOverlay elements from KML/KMZ, georeferences images as GeoTiff layers.
        Feyz taken from kmltools.
        """
        loaded_rasters = []
        try:
            docs = self._kml_docs(is_kmz)
        except ValueError as exc:
            self.last_warnings.append(str(exc))
            return loaded_rasters

        for src in docs:
            if os.path.exists(src):
                self._scan_ground_overlays(src, loaded_rasters)
        return loaded_rasters

    def _scan_ground_overlays(self, src: str,
                              loaded_rasters: list) -> None:
        """Georeference every GroundOverlay in one KML document."""
        try:
            root = self._read_kml_dom(src)
            overlays = self._dom_descendants(root, "GroundOverlay")

            for overlay in overlays:
                name = self._dom_child_text(overlay, "name") or "GroundOverlay"
                image_ref = self._dom_child_text(
                    overlay, "href", recursive=True)
                if not image_ref:
                    continue

                # Locate relative image file
                base_dir = os.path.dirname(src)
                image_path = os.path.join(base_dir, image_ref)
                if not os.path.exists(image_path):
                    # Check in root if relative path contains directories
                    image_path = os.path.join(
                        base_dir, os.path.basename(image_ref))
                    if not os.path.exists(image_path):
                        continue

                latlonbox = self._dom_child(
                    overlay, "LatLonBox", recursive=True)
                if latlonbox is None:
                    continue

                north = float(self._dom_child_text(latlonbox, "north"))
                south = float(self._dom_child_text(latlonbox, "south"))
                east = float(self._dom_child_text(latlonbox, "east"))
                west = float(self._dom_child_text(latlonbox, "west"))

                # Use GDAL to georeference and copy image to GeoTiff
                output_tiff = os.path.splitext(image_path)[0] + "_georef.tif"

                src_ds = gdal.Open(image_path)
                if src_ds is None:
                    continue

                width = src_ds.RasterXSize
                height = src_ds.RasterYSize

                # Calculate pixel resolution sizes
                pixel_width = (east - west) / width
                pixel_height = (north - south) / height

                # Create destination georeferenced GeoTiff
                driver = gdal.GetDriverByName("GTiff")
                dst_ds = driver.CreateCopy(output_tiff, src_ds)
                if dst_ds is None:
                    self.last_warnings.append(
                        f"Nie udało się zbudować podkładu rastrowego dla {image_ref}.")
                    src_ds = None
                    continue

                # Apply geotransform coordinates
                # [West limits, pixel width, rotationX, North limits, rotationY, -pixel height]
                dst_ds.SetGeoTransform(
                    [west, pixel_width, 0.0, north, 0.0, -pixel_height])

                # Set projection reference
                srs = osr.SpatialReference()
                srs.ImportFromEPSG(4326)  # KML default
                dst_ds.SetProjection(srs.ExportToWkt())

                dst_ds = None
                src_ds = None

                # Load as QGIS Raster Layer
                raster_layer = QgsRasterLayer(output_tiff, name)
                if raster_layer.isValid():
                    loaded_rasters.append(raster_layer)

        except Exception as exc:
            self.last_warnings.append(
                f"GroundOverlay extraction skipped: {exc}")

    def _read_kml_dom(self, path: str):
        with open(path, "rb") as handle:
            raw = handle.read(MAX_KML_XML_BYTES + 1)

        if len(raw) > MAX_KML_XML_BYTES:
            raise ValueError(
                "Plik KML jest za duży, żeby przeszukać go pod kątem "
                "podkładów rastrowych.")
        if b"<!DOCTYPE" in raw.upper():
            raise ValueError(
                "Plik KML zawiera deklarację DOCTYPE — dla bezpieczeństwa "
                "takich plików nie otwieramy.")

        document = QDomDocument()
        result = document.setContent(raw.decode("utf-8-sig", errors="replace"))
        ok = result[0] if isinstance(result, tuple) else bool(result)
        if not ok:
            raise ValueError("Nie udało się odczytać struktury pliku KML.")
        return document.documentElement()

    def _dom_descendants(self, node, local_name: str):
        matches = []
        child = node.firstChild()
        while not child.isNull():
            if child.isElement():
                element = child.toElement()
                if self._dom_local_name(element) == local_name:
                    matches.append(element)
                matches.extend(self._dom_descendants(element, local_name))
            child = child.nextSibling()
        return matches

    def _dom_child(self, node, local_name: str, recursive: bool = False):
        child = node.firstChild()
        while not child.isNull():
            if child.isElement():
                element = child.toElement()
                if self._dom_local_name(element) == local_name:
                    return element
                if recursive:
                    found = self._dom_child(
                        element, local_name, recursive=True)
                    if found is not None:
                        return found
            child = child.nextSibling()
        return None

    def _dom_child_text(
            self,
            node,
            local_name: str,
            recursive: bool = False) -> str:
        child = self._dom_child(node, local_name, recursive=recursive)
        if child is None:
            return ""
        return child.text().strip()

    def _dom_local_name(self, element) -> str:
        local_name = element.localName()
        if local_name:
            return local_name
        return element.tagName().split(":")[-1]

    @staticmethod
    def export_layer_to_gis(
            layer: QgsVectorLayer,
            output_path: str,
            format_name: str,
            target_crs=None,
            selected_only: bool = False):
        """Zapisuje warstwę wektorową do GML, KML albo KMZ."""
        transform_context = QgsProject.instance().transformContext()
        options = QgsVectorFileWriter.SaveVectorOptions()
        options.onlySelectedFeatures = selected_only

        source_crs = layer.crs()
        if not source_crs.isValid():
            raise ValueError(
                "Warstwa źródłowa nie ma przypisanego układu współrzędnych. "
                "Ustaw go przed eksportem, inaczej współrzędne trafią "
                "w niewłaściwe miejsce.")
        effective_crs = (
            target_crs if target_crs and target_crs.isValid() else source_crs)
        if source_crs.isValid() and effective_crs.isValid() \
                and source_crs != effective_crs:
            options.ct = QgsCoordinateTransform(
                source_crs, effective_crs, QgsProject.instance())

        feature_count = exported_feature_count(layer, selected_only)
        if selected_only and feature_count == 0:
            raise ValueError("Na warstwie źródłowej nie zaznaczono żadnych obiektów.")

        if format_name.upper() == "GML":
            # GML 3.2 — taki zapis przyjmują polskie systemy planistyczne
            # i geodezyjne (m.in. zbiory danych przestrzennych APP).
            options.driverName = "GML"
            options.layerOptions = [
                "FORMAT=GML3.2",
                "GML3_LONGSRS=YES",
                "SRSDIMENSION_LOC=POSLIST",
                "WRITE_FEATURE_BOUNDED_BY=NO",
            ]
            with atomic_output(output_path, (".xsd",)) as temporary_path:
                err, err_msg, _, _ = QgsVectorFileWriter.writeAsVectorFormatV3(
                    layer, temporary_path, transform_context, options)
                if err != QgsVectorFileWriter.WriterError.NoError:
                    raise ValueError(f"Zapis GML nie powiódł się: {err_msg}")
            # GDAL dokłada obok pliku schemat .xsd — zostawiamy go,
            # bo bez niego odbiorca traci typy kolumn.

        elif format_name.upper() == "KML":
            options.driverName = "KML"
            with atomic_output(output_path) as temporary_path:
                err, err_msg, _, _ = QgsVectorFileWriter.writeAsVectorFormatV3(
                    layer, temporary_path, transform_context, options)
                if err != QgsVectorFileWriter.WriterError.NoError:
                    raise ValueError(f"Zapis KML nie powiódł się: {err_msg}")

        elif format_name.upper() == "KMZ":
            # Write to a temporary KML first, then package as KMZ zip
            temp_dir = tempfile.mkdtemp(prefix="kmz_export_")
            temp_kml = os.path.join(temp_dir, "doc.kml")
            options.driverName = "KML"
            try:
                err, err_msg, _, _ = QgsVectorFileWriter.writeAsVectorFormatV3(
                    layer, temp_kml, transform_context, options)
                if err != QgsVectorFileWriter.WriterError.NoError:
                    raise ValueError(f"Zapis KMZ nie powiódł się: {err_msg}")
                with atomic_output(output_path) as temporary_path:
                    with zipfile.ZipFile(
                            temporary_path, "w",
                            zipfile.ZIP_DEFLATED) as archive:
                        archive.write(temp_kml, "doc.kml")
            finally:
                shutil.rmtree(temp_dir, ignore_errors=True)
        else:
            raise ValueError(f"Nieobsługiwany format eksportu: {format_name}")

        authid = (effective_crs.authid() if effective_crs.isValid()
                  else "nieznany")
        return verified_export_result(
            output_path, format_name.upper(), feature_count, authid)

    def _expand_html_descriptions(
            self, layer: QgsVectorLayer) -> QgsVectorLayer:
        new_field_definitions = {}
        for feat in layer.getFeatures():
            desc = feat["description"]
            if desc:
                attrs = parse_kml_html_table(str(desc))
                for k in attrs.keys():
                    new_field_definitions[k] = QMetaType.Type.QString

        fields = QgsFields()
        for field in layer.fields():
            fields.append(field)
        for k, vtype in sorted(new_field_definitions.items()):
            if k not in [f.name() for f in layer.fields()]:
                fields.append(QgsField(k, vtype))

        geom_type_str = memory_geometry_type_name(layer)

        uri = f"{geom_type_str}?crs={layer.crs().authid()}"
        expanded_layer = QgsVectorLayer(uri, layer.name(), "memory")
        prov = expanded_layer.dataProvider()
        prov.addAttributes(fields)
        expanded_layer.updateFields()

        features = []
        for feat in layer.getFeatures():
            new_feat = QgsFeature(expanded_layer.fields())
            new_feat.setGeometry(feat.geometry())

            for field in layer.fields():
                new_feat[field.name()] = feat[field.name()]

            desc = feat["description"]
            if desc:
                attrs = parse_kml_html_table(str(desc))
                for k, v in attrs.items():
                    new_feat[k] = v
            features.append(new_feat)

        add_features_or_raise(
            expanded_layer, features, "KML attribute expansion")
        return expanded_layer

    def _sanitize_column_name(self, value: str) -> str:
        text = re.sub(r"\W+", "_", str(value).strip(), flags=re.UNICODE)
        return text.strip("_").upper() or "LAYER"

    def convert_to_memory(
            self,
            is_kmz: bool = False,
            html_expansion: bool = True,
            selected_layers: list[str] | None = None,
            progress_cb=None) -> list[QgsVectorLayer]:
        """Converts GIS layers directly to memory layers without writing a GPKG file."""
        loaded_layers = []
        for layer_name, vlayer in self._iter_source_layers(
                is_kmz, selected_layers):
            if progress_cb:
                progress_cb(layer_name)

            processed_layer = vlayer
            if html_expansion and "description" in [
                    f.name() for f in vlayer.fields()]:
                processed_layer = self._expand_html_descriptions(vlayer)

            # Group features by geometry type to support layers with mixed geometry types (e.g. DXF layers)
            default_geom_type = memory_geometry_type_name(processed_layer)
            features_by_type = {}

            src_crs = self._effective_source_crs(processed_layer)
            if not processed_layer.crs().isValid():
                processed_layer.setCrs(src_crs)

            transform = None
            if src_crs.isValid() and src_crs != self.target_crs:
                transform = QgsCoordinateTransform(
                    src_crs, self.target_crs, QgsProject.instance())

            for feat in processed_layer.getFeatures():
                geom = feat.geometry()
                if geom and not geom.isEmpty() and transform:
                    geom.transform(transform)

                geom_type_str = _get_geom_type_str(geom)
                if geom_type_str == "NoGeometry":
                    geom_type_str = default_geom_type

                # Store geometry and original feature for later reconstruction
                features_by_type.setdefault(geom_type_str, []).append((geom, feat))

            if not features_by_type:
                features_by_type[default_geom_type] = []

            for geom_type_str, type_data in sorted(features_by_type.items()):
                mem_uri = f"{geom_type_str}?crs={self.target_crs.authid()}"
                mem_layer_name = (
                    layer_name
                    if len(features_by_type) == 1
                    else f"{layer_name}_{geom_type_str}"
                )
                mem_layer = QgsVectorLayer(mem_uri, mem_layer_name, "memory")
                prov = mem_layer.dataProvider()
                prov.addAttributes(processed_layer.fields())
                mem_layer.updateFields()

                # Reconstruct features with target memory layer's fields
                features = []
                for geom, original_feat in type_data:
                    new_feat = QgsFeature(mem_layer.fields())
                    coerced = self._coerce_geometry_for_layer(geom, geom_type_str)
                    new_feat.setGeometry(coerced or geom)
                    fixed_attrs = [
                        fix_mojibake(a) if isinstance(a, str) else a
                        for a in original_feat.attributes()
                    ]
                    new_feat.setAttributes(fixed_attrs)
                    features.append(new_feat)

                add_features_or_raise(
                    mem_layer, features, "GIS scratch layer clone")
                loaded_layers.append(mem_layer)

        if not loaded_layers:
            raise ValueError(
                "Żadna z zaznaczonych warstw nie nadaje się do odczytu.")
        return loaded_layers
