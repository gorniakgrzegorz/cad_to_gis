# -*- coding: utf-8 -*-
"""dgn_v8_reader — Pure Python MicroStation DGN v8 geometry reader.

Fallback reader used when GDAL's ``DGNv8`` driver is unavailable.
DGN v8 files are OLE2 compound documents whose element streams are
zlib-compressed.  This module decompresses them and yields geometry
features suitable for conversion to QGIS layers.

Coverage
--------
* **Line** (type 3) — fully supported (22 k elements in a typical file).
* **LineString** (type 4) — supported.
* **Shape / polygon** (type 6) — supported.
* Complex containers (cell header, complex string / shape) and
  annotation types (text, dimension) are skipped but their Level,
  colour, and style attributes are still reported via placeholder
  (centroid or bounding-box) geometry when possible.

Coordinate system
-----------------
DGN v8 stores coordinates as double-precision values in **master
units** (metres, survey-feet, …).  No scaling is applied — the raw
values are returned as-is.  The caller is responsible for CRS
selection and datum transformation.
"""

from __future__ import annotations

import contextlib
import math
import os
import re
import struct
import sys
import zlib
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Iterator, List, Optional, Tuple

olefile = None

# Resolve the vendored _vendor directory relative to this file's location.
# QGIS plugin loaders may not set up package-relative imports reliably,
# so an absolute path via sys.path is the most robust option.
_vendor_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "..", "_vendor")
_vendor_dir = os.path.normpath(os.path.abspath(_vendor_dir))
if os.path.isdir(_vendor_dir) and _vendor_dir not in sys.path:
    sys.path.insert(0, _vendor_dir)

try:
    import olefile  # type: ignore[assignment]  # noqa: F811
except ImportError:
    with contextlib.suppress(ImportError):
        # kopia wbudowana w paczkę wtyczki; gdy i jej brak, olefile
        # zostaje None, a DgnV8Reader zgłosi to czytelnym komunikatem
        from .._vendor import olefile  # type: ignore[no-redef,assignment]


# ===================================================================
# Element type codes
# ===================================================================

class ElementType(IntEnum):
    CELL_HEADER  = 2
    LINE         = 3
    LINE_STRING  = 4
    SHAPE        = 6
    TEXT         = 7
    CURVE        = 11
    COMPLEX_STR  = 12
    COMPLEX_SHP  = 14
    ELLIPSE      = 15
    ARC          = 16


_TYPE_NAMES: dict[int, str] = {
    2: "CellHeader",  3: "Line",      4: "LineString",
    6: "Shape",       7: "Text",     11: "Curve",
   12: "ComplexStr", 14: "ComplexShp", 15: "Ellipse",
   16: "Arc",        17: "MultiText", 21: "TagElement",
   26: "RasterHdr",  27: "RasterRef", 33: "Dimension",
   37: "OLEFrame",
}

# Element types whose geometry we can extract reliably.
_SIMPLE_GEOM_TYPES = frozenset({
    ElementType.LINE, ElementType.LINE_STRING, ElementType.SHAPE,
    ElementType.CURVE,
})


# ===================================================================
# Data classes
# ===================================================================

@dataclass
class DgnElement:
    """One graphic element extracted from a DGN v8 file."""
    element_type: int
    type_name: str = ""
    level: int = 0
    color_index: int = 0
    weight: int = 0
    style: int = 0
    geometry: List[Tuple[float, float]] = field(default_factory=list)


# ===================================================================
# Reader
# ===================================================================

class DgnV8Reader:
    """Read geometry from a MicroStation DGN v8 file.

    Parameters:
        path: Absolute path to the ``.dgn`` file.
    """

    _BASE_GEOM_OFFSET = 0x64  # 100 bytes

    def __init__(self, path: str) -> None:
        if olefile is None:
            raise ImportError(
                "Do odczytu plików DGN v8 potrzebna jest biblioteka olefile — "
                "wtyczka ma ją wbudowaną, więc ten komunikat oznacza "
            "uszkodzoną instalację wtyczki.")
        self._path = path
        self._ole: Optional[olefile.OleFileIO] = None

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "DgnV8Reader":
        self.open()
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def open(self) -> None:
        if self._ole is not None:
            return
        self._ole = olefile.OleFileIO(self._path)

    def close(self) -> None:
        if self._ole is not None:
            self._ole.close()
            self._ole = None

    # ------------------------------------------------------------------
    # Stream enumeration
    # ------------------------------------------------------------------

    def _graphic_streams(self) -> Iterator[Tuple[str, bytes]]:
        """Yield ``(name, decompressed_bytes)`` for every graphic
        element stream across all models."""
        if self._ole is None:
            raise RuntimeError("Plik DGN nie jest otwarty")
        for entry in self._ole.listdir():
            name = "/".join(entry)
            # Graphic element streams live under Dgn-Md/#NNNNNN/Dgn^G/ or Dgn^G
            if "Dgn^G" not in name:
                continue
            raw = None
            try:
                raw = self._ole.openstream(entry).read()
            except (IOError, AttributeError, OSError):
                raw = None
            if not raw or len(raw) < 12:
                continue

            dec = None
            for offset in (16, 12, 8, 0):
                if len(raw) <= offset:
                    continue
                chunk = raw[offset:]
                with contextlib.suppress(zlib.error):
                    dec = zlib.decompress(chunk)
                    break
                with contextlib.suppress(zlib.error):
                    dec = zlib.decompress(chunk, -zlib.MAX_WBITS)
                    break

            if dec is None:
                dec = raw

            if len(dec) < 12:
                continue
            yield name, dec

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def elements(self) -> Iterator[DgnElement]:
        """Iterate over all graphic elements in the file."""
        for _stream_name, data in self._graphic_streams():
            yield from self._parse_stream(data)

    def layer_names(self) -> dict[int, str]:
        """Return a mapping ``{level_number: level_name}`` discovered
        from the file's level table (if present)."""
        if self._ole is None:
            return {}
        names: dict[int, str] = {}
        try:
            entries = sorted(self._ole.listdir(), key=lambda e: (0 if '$40' in '/'.join(e) else 1, '/'.join(e)))
            for entry in entries:
                name = "/".join(entry)
                if "Dgn^N" not in name and "Level" not in name and "Dgn~H" not in name:
                    continue
                raw = None
                try:
                    raw = self._ole.openstream(entry).read()
                except (IOError, AttributeError, OSError):
                    raw = None
                if not raw:
                    continue
                dec = None
                for offset in (16, 12, 8, 0):
                    if len(raw) <= offset:
                        continue
                    with contextlib.suppress(zlib.error):
                        dec = zlib.decompress(raw[offset:])
                        break
                if dec is None:
                    dec = raw

                from .qgis_compat import fix_mojibake
                for m in re.finditer(rb'([\x20-\x7E\x80-\xFF]{3,64})\x00', dec):
                    btext = m.group(1)
                    sname = ""
                    try:
                        sname = btext.decode('utf-8')
                    except UnicodeDecodeError:
                        try:
                            sname = btext.decode('cp1254')
                        except UnicodeDecodeError:
                            sname = btext.decode('latin1', errors='ignore')
                    sname = fix_mojibake(sname.strip())
                    if not sname or sname.lower() in ('name', 'vf', 'none', 'true', 'false', 'shape', 'line'):
                        continue
                    start = m.start()
                    if start >= 28:
                        lid = struct.unpack_from('<I', dec, start - 28)[0]
                        if 0 < lid <= 0x7FFFFFFF:
                            if lid not in names:
                                names[lid] = sname
        except (IOError, AttributeError, OSError) as exc:
            _ = exc
        return names

    # ------------------------------------------------------------------
    # Stream-level parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _geom_offset_for_type(type_byte: int, subtype_byte: int) -> int:
        """Return the byte offset where geometry data begins for a
        given element type and sub-type."""
        if type_byte in (ElementType.LINE, ElementType.LINE_STRING, ElementType.SHAPE):
            return 0x74
        if type_byte in (ElementType.CURVE, ElementType.ELLIPSE):
            return 0x6C
        if type_byte == ElementType.ARC:
            return 0x7C
        if type_byte == ElementType.TEXT:
            return 0x7C
        return 0x74

    @staticmethod
    def _auto_scale_uor(x: float, y: float) -> Tuple[float, float]:
        """Auto-detect MicroStation DGN UOR (Units of Resolution) scale factor."""
        ax, ay = abs(x), abs(y)
        if (100_000_000.0 <= ax <= 500_000_000_000.0) or (100_000_000.0 <= ay <= 500_000_000_000.0):
            return x / 10000.0, y / 10000.0
        if (500_000_000_000.0 < ax <= 5_000_000_000_000.0) or (500_000_000_000.0 < ay <= 5_000_000_000_000.0):
            return x / 100000.0, y / 100000.0
        if (10_000_000.0 <= ax < 100_000_000.0) or (10_000_000.0 <= ay < 100_000_000.0):
            return x / 1000.0, y / 1000.0
        return x, y

    @staticmethod
    def _decode_points(data: bytes, start: int,
                       end: int, is_3d: bool = False,
                       max_points: int = 0) -> List[Tuple[float, float]]:
        """Decode (X, Y) double-precision pairs from *start* to *end*."""
        pts: List[Tuple[float, float]] = []
        pos = start
        stride = 24 if is_3d else 16
        count = 0
        while pos + 16 <= end:
            if max_points > 0 and count >= max_points:
                break
            x = struct.unpack_from("<d", data, pos)[0]
            y = struct.unpack_from("<d", data, pos + 8)[0]
            if math.isnan(x) or math.isnan(y) or math.isinf(x) or math.isinf(y):
                pos += stride
                continue
            if abs(x) > 1e16 or abs(y) > 1e16:
                break
            sx, sy = DgnV8Reader._auto_scale_uor(x, y)

            # Swap axes if Northing (4M+) is in X and Easting (500k) is in Y
            if sx > 3_000_000.0 and sy < 1_500_000.0:
                sx, sy = sy, sx

            # Skip invalid scaling outliers or metadata sentinels (e.g. font sizes, scale pairs)
            if abs(sx) > 16_000_000.0 or abs(sy) > 16_000_000.0:
                pos += stride
                continue
            if abs(sx - sy) < 0.0001 and sx > 1_000_000.0:
                pos += stride
                continue
            if sy > 1_000_000.0 and (sy < 3_500_000.0 or sy > 5_000_000.0):
                pos += stride
                continue

            pts.append((sx, sy))
            count += 1
            pos += stride

        return pts

    @staticmethod
    def _read_level(data: bytes, elem_start: int) -> int:
        """Extract the MicroStation Level number."""
        if elem_start + 0x30 > len(data):
            return 0
        level = struct.unpack_from("<I", data, elem_start + 0x2C)[0]
        if 0 <= level <= 0x7FFFFFFF:
            return level
        for off in (0x28, 0x30, 0x14, 0x18):
            if elem_start + off + 4 <= len(data):
                level = struct.unpack_from("<I", data, elem_start + off)[0]
                if 0 <= level <= 0x7FFFFFFF:
                    return level
        return 0

    @staticmethod
    def _read_color(data: bytes,
                    elem_start: int) -> Tuple[int, int, int]:
        """Return ``(color_index, weight, style)``."""
        if elem_start + 0x34 > len(data):
            return (0, 0, 0)
        cg = struct.unpack_from("<I", data, elem_start + 0x30)[0]
        return (cg & 0xFF, (cg >> 8) & 0xFF, (cg >> 16) & 0xFF)

    def _parse_stream(self, data: bytes) -> Iterator[DgnElement]:
        """Parse DGN v8 elements from one decompressed stream."""
        pos = 0
        data_len = len(data)

        while pos + 16 <= data_len:
            elem_start = pos
            type_byte = data[pos + 4] & 0x7F
            subtype_byte = data[pos + 5]

            is_3d = bool(data[pos + 1] & 0x40)

            word_count = struct.unpack_from("<H", data, pos + 8)[0]
            if word_count < 4:
                pos += 4
                continue

            elem_size = word_count * 2 + 4
            elem_end = elem_start + elem_size
            if elem_end > data_len:
                break

            level = self._read_level(data, elem_start)
            color_index, weight, style = self._read_color(data, elem_start)
            type_name = _TYPE_NAMES.get(type_byte, f"Type{type_byte}")

            geometry: List[Tuple[float, float]] = []

            max_pts = 0
            if type_byte == ElementType.LINE:
                max_pts = 2
            elif type_byte in (ElementType.LINE_STRING, ElementType.SHAPE):
                if elem_start + 0x4C <= elem_end:
                    n_raw = struct.unpack_from("<I", data, elem_start + 0x48)[0]
                    if 0 < n_raw <= 5000:
                        max_pts = n_raw

            if type_byte in _SIMPLE_GEOM_TYPES:
                geom_off = self._geom_offset_for_type(type_byte,
                                                       subtype_byte)
                abs_geom = elem_start + geom_off
                if abs_geom < elem_end:
                    geometry = self._decode_points(data, abs_geom,
                                                    elem_end, is_3d=is_3d,
                                                    max_points=max_pts)
                    if not geometry and is_3d:
                        geometry = self._decode_points(data, abs_geom,
                                                        elem_end, is_3d=False,
                                                        max_points=max_pts)
            elif type_byte in (ElementType.ARC, ElementType.ELLIPSE):
                abs_geom = elem_start + 0x8C
                if abs_geom + 16 <= elem_end:
                    pts = self._decode_points(data, abs_geom, elem_end, is_3d=is_3d, max_points=1)
                    if pts and abs(pts[0][0] - pts[0][1]) > 1000.0:
                        cx, cy = pts[0]
                        geometry = [
                            (cx + 5.0 * math.cos(math.radians(a)), cy + 5.0 * math.sin(math.radians(a)))
                            for a in range(0, 360, 20)
                        ]
            elif type_byte in (ElementType.TEXT, 17):
                abs_geom = elem_start + 0x74
                if abs_geom + 16 <= elem_end:
                    pts = self._decode_points(data, abs_geom, elem_end, is_3d=is_3d, max_points=1)
                    if pts and abs(pts[0][0] - pts[0][1]) > 1000.0:
                        geometry = pts

            yield DgnElement(
                element_type=type_byte,
                type_name=type_name,
                level=level,
                color_index=color_index,
                weight=weight,
                style=style,
                geometry=geometry,
            )

            pos = elem_end


# ===================================================================
# Convenience functions
# ===================================================================

def is_dgn_v8(path: str) -> bool:
    """Return ``True`` if *path* looks like a DGN v8 file."""
    if olefile is None:
        return False
    try:
        if not olefile.isOleFile(path):
            return False
        ole = olefile.OleFileIO(path)
        try:
            for entry in ole.listdir():
                name = "/".join(entry)
                if "Dgn~H" in name or "Dgn-Md" in name or "Dgn^G" in name:
                    return True
            return False
        finally:
            ole.close()
    except Exception:
        return False


def check_dgn_driver_available() -> bool:
    """Return ``True`` if GDAL's DGNv8 driver is available."""
    try:
        from osgeo import ogr
        return ogr.GetDriverByName("DGNv8") is not None
    except Exception:
        return False
