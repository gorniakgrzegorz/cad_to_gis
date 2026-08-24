# -*- coding: utf-8 -*-
"""Small QGIS 3/4 compatibility helpers used by conversion engines."""
from __future__ import annotations

import contextlib
import re
from qgis.core import QgsWkbTypes


def fix_mojibake(text: str | None) -> str:
    """Naprawia "krzaki" w tekstach z rysunków CAD i rozwija zapisy DXF.

    Rysunki bywają zapisane w starszych kodowaniach (CP1250, ISO-8859-2)
    albo przechodzą przez podwójne kodowanie w drodze między programami.
    Efekt: zamiast "Łąka" widzimy "Åka" albo "Ĺka". Ta funkcja próbuje
    odwrócić taką zamianę i przywrócić polskie ogonki.
    """
    if not text or not isinstance(text, str):
        return str(text) if text is not None else ""

    # 1. rozwinięcie zapisów DXF \U+XXXX / \u+XXXX (np. \U+0141 -> Ł)
    if "\\U+" in text or "\\u+" in text:
        text = re.sub(r"\\?[Uu]\+([0-9A-Fa-f]{4})",
                      lambda m: chr(int(m.group(1), 16)), text)

    # 2. odwrócenie podwójnego kodowania: tekst w UTF-8 odczytany jako
    #    latin1/CP1252 (najczęstszy przypadek) albo jako CP1250/ISO-8859-2
    PODEJRZANE = ("Ã", "Â", "Å", "Ä", "Ĺ", "Ĺ¼", "Å¼", "â", "ï", "Ĺ›")
    if any(c in text for c in PODEJRZANE):
        for src_enc in ("latin1", "cp1252", "cp1250", "iso-8859-2"):
            for dst_enc in ("utf-8", "cp1250", "iso-8859-2"):
                with contextlib.suppress(UnicodeEncodeError,
                                         UnicodeDecodeError):
                    kandydat = text.encode(src_enc).decode(dst_enc)
                    # przyjmujemy tylko wtedy, gdy krzaki zniknęły,
                    # a tekst wygląda "po polsku" albo przynajmniej czysto
                    if not any(c in kandydat for c in PODEJRZANE):
                        text = kandydat
                        break
            else:
                continue
            break

    # 3. ostatnia deska ratunku — najczęstsze pary "krzaków" dla polskich
    #    znaków, gdy dekodowanie po kolei nie pomogło
    PODMIANY = {
        "Ä…": "ą", "Ä„": "Ą",
        "Ä‡": "ć", "Ä†": "Ć",
        "Ä™": "ę", "Ä˜": "Ę",
        "Å‚": "ł", "Å": "Ł",
        "Å„": "ń", "Åƒ": "Ń",
        "Ã³": "ó", "Ã“": "Ó",
        "Å›": "ś", "Åš": "Ś",
        "Åº": "ź", "Å¹": "Ź",
        "Å¼": "ż", "Å»": "Ż",
    }
    for krzak, poprawny in PODMIANY.items():
        if krzak in text:
            text = text.replace(krzak, poprawny)

    return text


def _value_text(value) -> str:
    parts = [str(value).lower()]
    name = getattr(value, "name", "")
    if name:
        parts.append(str(name).lower())
    return " ".join(parts)


def _value_number(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        enum_value = getattr(value, "value", None)
        if enum_value is not None:
            try:
                return int(enum_value)
            except (TypeError, ValueError):
                return None
    return None


def _geometry_name_from_text(text: str) -> str | None:
    text = (text or "").lower()
    if "multipoint" in text:
        return "MultiPoint"
    if "multiline" in text or ("multi" in text and "line" in text):
        return "MultiLineString"
    if "multipolygon" in text or ("multi" in text and "polygon" in text):
        return "MultiPolygon"
    if "point" in text:
        return "Point"
    if "line" in text or "curve" in text:
        return "LineString"
    if "polygon" in text or "surface" in text:
        return "Polygon"
    return None


def memory_geometry_type_name(layer) -> str:
    """Return a memory-provider geometry token for a QGIS 3 or QGIS 4 layer."""
    try:
        wkb_name = QgsWkbTypes.displayString(layer.wkbType())
        geometry_name = _geometry_name_from_text(wkb_name)
        if geometry_name:
            return geometry_name
    except Exception:
        geometry_name = None

    try:
        geometry_type = layer.geometryType()
    except Exception:
        geometry_type = None

    geometry_name = _geometry_name_from_text(_value_text(geometry_type))
    if geometry_name:
        return geometry_name

    geometry_number = _value_number(geometry_type)
    if geometry_number == 0:
        return "Point"
    if geometry_number == 1:
        return "LineString"
    if geometry_number == 2:
        return "Polygon"

    return "Point"


def _feature_count(layer) -> int | None:
    try:
        count = layer.featureCount()
    except Exception:
        return None
    return count if isinstance(count, int) else None


def add_features_or_raise(layer, features: list, context: str = "Add features") -> None:
    """Add features and fail loudly if QGIS rejects any feature silently."""
    if not features:
        layer.updateExtents()
        return

    # Filter features to valid non-empty geometry objects for spatial layers
    is_spatial = True
    with contextlib.suppress(Exception):
        is_spatial = (layer.geometryType() != QgsWkbTypes.GeometryType.NullGeometry)

    target_features = []
    for f in features:
        if is_spatial:
            g = f.geometry()
            if g and not g.isEmpty():
                target_features.append(f)
        else:
            target_features.append(f)

    if not target_features:
        layer.updateExtents()
        return

    before = _feature_count(layer)
    provider = layer.dataProvider()
    result = provider.addFeatures(target_features)

    ok = True
    if isinstance(result, tuple):
        ok = bool(result[0])
    elif result is not None:
        ok = bool(result)

    layer.updateExtents()
    after = _feature_count(layer)
    if before is not None and after is not None:
        added = after - before
    else:
        added = len(target_features) if ok else 0

    if not ok or added < len(target_features):
        # Fallback: attempt coercing / dropping Z / segmentizing curves / single-multi conversion
        with contextlib.suppress(Exception):
            from qgis.core import QgsWkbTypes, QgsGeometry, QgsFeature
            coerced_features = []
            layer_wkb = layer.wkbType()
            for feat in target_features:
                new_f = QgsFeature(feat)
                g = feat.geometry()
                if g and not g.isEmpty():
                    g_copy = QgsGeometry(g)
                    if QgsWkbTypes.isCurved(g_copy.wkbType()):
                        g_copy = g_copy.constrainedStraightSegmentedGeometry()
                    if QgsWkbTypes.hasZ(g_copy.wkbType()) and g_copy.get():
                        g_copy.get().dropZValue()
                    if QgsWkbTypes.isMultiType(layer_wkb) and not QgsWkbTypes.isMultiType(g_copy.wkbType()):
                        g_copy.convertToMultiType()
                    elif not QgsWkbTypes.isMultiType(layer_wkb) and QgsWkbTypes.isMultiType(g_copy.wkbType()):
                        g_copy.convertToSingleType()
                    new_f.setGeometry(g_copy)
                coerced_features.append(new_f)

            provider.addFeatures(coerced_features)
            layer.updateExtents()
            after2 = _feature_count(layer)
            if before is not None and after2 is not None:
                added = after2 - before
                if added >= len(target_features):
                    ok = True

    if not ok or added < len(target_features):
        added = max(0, added)
        raise ValueError(
            f"{context}: only {added} of {len(target_features)} features were "
            f"accepted by layer '{layer.name()}'."
        )
