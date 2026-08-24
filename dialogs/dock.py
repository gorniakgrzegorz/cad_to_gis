# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-2.0-or-later
"""
OKNO WTYCZKI "Konwerter CAD na GIS" — panel z zakładkami.

Dwie zakładki: konwersja plików CAD/GIS do GeoPackage oraz eksport
warstw z QGIS do DXF, GML, KML i KMZ. Kolory i oznaczenia warstw
planistycznych dobiera moduł ``core/symbology.py`` na podstawie
polskich rozporządzeń.

Na bazie wtyczki zero2cadgis (GPL-2.0-or-later, © Yusuf Eminoğlu) —
patrz ATRYBUCJA.md. Wersja polska: © Grzegorz Górniak.
"""
from __future__ import annotations

import os
import re
from contextlib import suppress
from dataclasses import dataclass

from qgis.PyQt.QtCore import QMetaType, Qt, QSettings, QSize
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import (
    QApplication,
    QDockWidget,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QCheckBox,
    QRadioButton,
    QButtonGroup,
    QProgressBar,
    QMessageBox,
    QFileDialog,
    QTabWidget,
    QComboBox,
    QDialog,
    QTextBrowser,
    QDialogButtonBox,
    QScrollArea,
)
from qgis.core import (
    Qgis,
    QgsProject,
    QgsVectorLayer,
    QgsField,
    QgsCoordinateReferenceSystem,
)
from qgis.gui import QgsProjectionSelectionWidget

# Core services imports
from ..core.gis_engine import GisConverterEngine
from ..core.csv_sniffer import (
    CsvGeometryProfile,
    sniff_delimited_dataset,
)
from ..core.cad_engine import CadExportEngine
from ..core.symbology import apply_plan_symbology
from ..core.schemat_pl import znajdz_oznaczenie
from ..core.path_utils import ensure_extension, has_extension
from ..core.qgis_compat import fix_mojibake

# ──────────────────────────────────────────────────────────────────────────────
# Dock stylesheet — every text colour, background and border is *pinned* so
# the panel reads identically under QGIS 3 (Qt5 / light host palette) and
# QGIS 4 (Qt6 / often-dark host palette).  Without pinning, combo-box popups
# render solid-black and labels vanish against the white cards on dark themes.
# This follows the same remedy applied in the zero2viz studio.
# ──────────────────────────────────────────────────────────────────────────────
DOCK_STYLE = """
/* ── root & font ── */
QWidget {
    font-family: 'Segoe UI', Arial, sans-serif;
    font-size: 12px;
    color: #263238;
    background: transparent;
}

/* ── tabs ── */
QTabWidget::pane {
    border: 1px solid #cfd8dc;
    border-radius: 4px;
    top: -1px;
    background: #ffffff;
}
QTabBar::tab {
    background: #eceff1;
    color: #546e7a;
    border: 1px solid #cfd8dc;
    padding: 6px 12px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
}
QTabBar::tab:selected {
    background: #ffffff;
    border-bottom-color: transparent;
    font-weight: bold;
    color: #00bde7;
}
QTabBar::tab:hover {
    color: #009ec2;
}

/* ── group boxes ── */
QGroupBox {
    font-weight: bold;
    color: #37474f;
    background: #ffffff;
    border: 1px solid #cfd8dc;
    border-radius: 6px;
    margin-top: 6px;
    padding-top: 12px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 8px;
    padding: 0 4px;
    color: #00bde7;
}

/* ── scroll area ── */
QScrollArea {
    border: none;
    background: transparent;
}
QScrollArea > QWidget > QWidget {
    background: transparent;
}

/* ── labels: pinned dark so they never inherit a host-palette light/dark
      colour and become invisible on white cards ── */
QLabel {
    color: #37474f;
    background: transparent;
}
QLabel#dock_title {
    color: #263238;
    font-size: 15px;
    font-weight: bold;
}
QLabel#dock_subtitle {
    color: #607d8b;
    font-size: 11px;
}

QLabel#dock_signature {
    color: #000000;
    font-size: 10px;
    padding: 2px 4px 0 0;
}

/* ── checkboxes ── */
QCheckBox {
    color: #37474f;
    background: transparent;
    spacing: 6px;
}
QCheckBox::indicator {
    width: 14px;
    height: 14px;
    border: 1px solid #546e7a;
    border-radius: 2px;
    background: #ffffff;
}
QCheckBox::indicator:hover {
    border-color: #00bde7;
}
QCheckBox::indicator:checked {
    background: #00bde7;
    border-color: #00bde7;
    image: url(__CHECKBOX_CHECKED_ICON__);
}
QCheckBox::indicator:checked:hover {
    background: #009ec2;
    border-color: #009ec2;
}
QCheckBox::indicator:disabled {
    border-color: #b0bec5;
}
QCheckBox::indicator:checked:disabled {
    background: #b0bec5;
    border-color: #b0bec5;
}
QCheckBox:disabled {
    color: #90a4ae;
}

/* ── inputs: white field, dark text, teal selection — independent of the
      host palette so the dropdown popup is never black ── */
QLineEdit {
    border: 1px solid #cfd8dc;
    border-radius: 4px;
    padding: 4px;
    background-color: #ffffff;
    color: #263238;
    selection-background-color: #00bde7;
    selection-color: #ffffff;
}
QLineEdit:focus {
    border: 1px solid #00bde7;
}
QLineEdit:disabled {
    background: #eceff1;
    color: #90a4ae;
    border-color: #dde2e6;
}

QComboBox {
    background: #ffffff;
    color: #263238;
    border: 1px solid #cfd8dc;
    border-radius: 4px;
    padding: 4px 6px;
    selection-background-color: #00bde7;
    selection-color: #ffffff;
}
QComboBox:focus {
    border: 1px solid #00bde7;
}
QComboBox:disabled {
    background: #eceff1;
    color: #90a4ae;
    border-color: #dde2e6;
}
/* the drop-down list popup — without pinning this was solid black on
   dark-themed QGIS 4 */
QComboBox QAbstractItemView {
    background: #ffffff;
    color: #263238;
    border: 1px solid #cfd8dc;
    selection-background-color: #00bde7;
    selection-color: #ffffff;
    outline: 0;
}
QComboBox QAbstractItemView::item {
    min-height: 22px;
    padding: 2px 4px;
}

QDoubleSpinBox, QSpinBox {
    background: #ffffff;
    color: #263238;
    border: 1px solid #cfd8dc;
    border-radius: 4px;
    padding: 3px 6px;
    selection-background-color: #00bde7;
    selection-color: #ffffff;
}
QDoubleSpinBox:focus, QSpinBox:focus {
    border: 1px solid #00bde7;
}
QDoubleSpinBox:disabled, QSpinBox:disabled {
    background: #eceff1;
    color: #90a4ae;
    border-color: #dde2e6;
}

/* ── tree widget ── */
QTreeWidget {
    border: 1px solid #cfd8dc;
    border-radius: 4px;
    background-color: #ffffff;
    color: #263238;
}
QTreeWidget::item {
    color: #263238;
}
QTreeWidget::item:selected {
    background: #00bde7;
    color: #ffffff;
}
QHeaderView::section {
    background: #eceff1;
    color: #37474f;
    border: 1px solid #cfd8dc;
    padding: 4px;
    font-weight: bold;
}

/* ── primary action buttons ── */
QPushButton#convert_btn {
    background-color: #00bde7;
    color: white;
    font-weight: bold;
    font-size: 13px;
    border-radius: 4px;
    padding: 8px;
    border: none;
}
QPushButton#convert_btn:hover {
    background-color: #009ec2;
}
QPushButton#convert_btn:disabled {
    background-color: #b0bec5;
    color: #78909c;
}

/* ── browse / save-as buttons ── */
QPushButton#browse_btn {
    background-color: #00bde7;
    color: white;
    font-weight: bold;
    border-radius: 4px;
    padding: 5px 12px;
    border: none;
}
QPushButton#browse_btn:hover {
    background-color: #009ec2;
}

/* ── secondary / generic buttons (Zaznacz wszystkie, Odznacz wszystkie, etc.) ── */
QPushButton {
    background: #eceff1;
    color: #263238;
    border: 1px solid #cfd8dc;
    border-radius: 4px;
    padding: 5px 10px;
}
QPushButton:hover {
    background: #e0e4e8;
}
QPushButton:disabled {
    background: #f5f5f5;
    color: #90a4ae;
    border-color: #e0e4e8;
}

/* ── progress bar ── */
QProgressBar {
    border: 1px solid #cfd8dc;
    border-radius: 4px;
    text-align: center;
    font-weight: bold;
    background: #ffffff;
    color: #263238;
}
QProgressBar::chunk {
    background-color: #00bde7;
}

/* ── dock header card ── */
QWidget#dock_header {
    background: #f8fafc;
    border: 1px solid #d7e0e7;
    border-radius: 6px;
}

/* ── guide button & body ── */
QPushButton#guide_btn {
    background-color: #263238;
    color: #ffffff;
    border: none;
    border-radius: 4px;
    padding: 5px 12px;
    font-weight: bold;
}
QPushButton#guide_btn:hover {
    background-color: #111827;
}
QTextBrowser#guide_body {
    border: 1px solid #d7e0e7;
    border-radius: 6px;
    background: #ffffff;
    color: #263238;
    padding: 8px;
}

/* ── tooltips ── */
QToolTip {
    background: #263238;
    color: #ffffff;
    border: 1px solid #263238;
    padding: 4px 6px;
}

/* ── splitter handle ── */
QSplitter::handle {
    background: #cfd8dc;
}
QSplitter::handle:hover {
    background: #00bde7;
}
"""


@dataclass(frozen=True)
class SourceFormat:
    """One selectable source dataset family in the converter tab."""
    key: str
    label: str
    dialog_title: str
    file_filter: str
    extensions: tuple[str, ...]
    is_dir: bool = False


SOURCE_FORMATS: list[SourceFormat] = [
    SourceFormat("dxf", "AutoCAD DXF (*.dxf)", "Wybierz plik DXF",
                 "AutoCAD DXF (*.dxf)", (".dxf",)),
    SourceFormat("dwg", "AutoCAD DWG (*.dwg)", "Wybierz plik AutoCAD DWG",
                 "AutoCAD DWG (*.dwg)", (".dwg",)),
    SourceFormat("kml", "KML / KMZ (*.kml, *.kmz)", "Wybierz plik KML lub KMZ",
                 "Keyhole Markup Language (*.kml *.kmz)", (".kml", ".kmz")),
    SourceFormat("gml", "GML / APP (*.gml, *.xml)",
                 "Wybierz plik GML (także zbiór danych APP)",
                 "Geography Markup Language (*.gml *.xml)", (".gml", ".xml")),
    SourceFormat("geojson", "GeoJSON (*.geojson, *.json)",
                 "Wybierz plik GeoJSON",
                 "GeoJSON (*.geojson *.json)", (".geojson", ".json")),
    SourceFormat("csv", "Delimited Text / CSV (*.csv, *.tsv, *.txt)",
                 "Wybierz plik tekstowy (CSV/TSV)",
                 "Delimited Text (*.csv *.tsv *.txt)",
                 (".csv", ".tsv", ".txt")),
    SourceFormat("sqlite", "SpatiaLite / SQLite (*.sqlite, *.db)",
                 "Wybierz bazę SpatiaLite/SQLite",
                 "SpatiaLite / SQLite (*.sqlite *.db)", (".sqlite", ".db")),
    SourceFormat("gpx", "GPS Exchange GPX (*.gpx)", "Wybierz plik GPX",
                 "GPS Exchange Format (*.gpx)", (".gpx",)),
    SourceFormat("dgn", "Microstation DGN (*.dgn)",
                 "Wybierz plik Microstation DGN",
                 "Rysunki Microstation (*.dgn)", (".dgn",)),
    SourceFormat("gdb", "ArcGIS File Geodatabase (*.gdb)",
                 "Wskaż folder geobazy ArcGIS (.gdb)",
                 "", (".gdb",), is_dir=True),
    SourceFormat("mdb", "MS Access / Personal Geodatabase (*.accdb, *.mdb)",
                 "Wybierz bazę MS Access",
                 "MS Access / Personal Geodatabase (*.accdb *.mdb)", (".accdb", ".mdb")),
]


def format_for_path(path: str) -> SourceFormat | None:
    """Return the SourceFormat matching *path*'s extension, if any."""
    lower = path.lower().rstrip("\\/")
    for fmt in SOURCE_FORMATS:
        if any(lower.endswith(ext) for ext in fmt.extensions):
            return fmt
    return None


def all_supported_filter() -> str:
    exts = " ".join(
        f"*{ext}" for fmt in SOURCE_FORMATS if not fmt.is_dir
        for ext in fmt.extensions)
    return f"Wszystkie obsługiwane ({exts})"


class PanelKonwertera(QDockWidget):
    """Panel wtyczki: konwersja plików CAD/GIS oraz eksport z QGIS."""

    CAD_FIELD_DEFINITIONS = [
        QgsField("source_file", QMetaType.Type.QString),
        QgsField("layer_code", QMetaType.Type.Int),
        QgsField("layer_name", QMetaType.Type.QString),
        QgsField("entity_type", QMetaType.Type.QString),
        QgsField("name", QMetaType.Type.QString),
        QgsField("label", QMetaType.Type.QString),
        QgsField("color_argb", QMetaType.Type.QString),
        QgsField("radius", QMetaType.Type.Double),
        QgsField("start_ang", QMetaType.Type.Double),
        QgsField("end_ang", QMetaType.Type.Double),
        QgsField("text_h", QMetaType.Type.Double),
        QgsField("rotation", QMetaType.Type.Double),
        QgsField("box_width", QMetaType.Type.Double),
        QgsField("box_height", QMetaType.Type.Double),
        QgsField("scale", QMetaType.Type.Double),
        QgsField("grid_x", QMetaType.Type.Double),
        QgsField("grid_y", QMetaType.Type.Double),
    ]

    # Kolumny dokładane w trybie planistycznym — nazwy po polsku,
    # żeby tabela atrybutów była czytelna dla planisty i geodety.
    PLANGML_FIELD_DEFINITIONS = [
        QgsField("SYMBOL", QMetaType.Type.QString),        # np. MN, SW, ZL
        QgsField("PRZEZNACZENIE", QMetaType.Type.QString),  # pełna nazwa
        QgsField("GRUPA", QMetaType.Type.QString),          # grupa tematyczna
        QgsField("RODZAJ_DOK", QMetaType.Type.QString),     # MPZP / plan ogólny
        QgsField("OZNACZENIE", QMetaType.Type.QString),     # jak rysowane
        QgsField("WARSTWA_CAD", QMetaType.Type.QString),    # nazwa z rysunku
    ]

    FIELD_DEFINITIONS = CAD_FIELD_DEFINITIONS + PLANGML_FIELD_DEFINITIONS

    def __init__(self, iface, icon_dir: str, parent=None):
        super().__init__("Konwerter CAD na GIS", parent)
        self.iface = iface
        self.icon_dir = icon_dir

        self.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        checkbox_icon = os.path.join(
            self.icon_dir, "checkbox_checked.png").replace("\\", "/")
        self.setStyleSheet(
            DOCK_STYLE.replace("__CHECKBOX_CHECKED_ICON__", checkbox_icon))

        self.gis_converter = None
        self.src_csv_profile: CsvGeometryProfile | None = None
        self._cad_split_field: str = ""
        self._export_selection_connections: set[str] = set()

        self._build_ui()
        self._restore_persistent_options()
        self.setAcceptDrops(True)

        project = QgsProject.instance()
        with suppress(Exception):
            project.layersAdded.connect(self._populate_layers_combo)
            project.layersRemoved.connect(self._populate_layers_combo)

    def closeEvent(self, event):
        if self.gis_converter:
            self.gis_converter.cleanup()
        super().closeEvent(event)

    # ───────────────────────── Drag & drop ─────────────────────────

    def dragEnterEvent(self, event):
        if self._droppable_paths(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        paths = self._droppable_paths(event)
        if not paths:
            event.ignore()
            return
        event.acceptProposedAction()

        fmt = format_for_path(paths[0])
        if fmt is None:
            return
        self.main_tab.setCurrentIndex(0)
        self._apply_source_path(paths[0], fmt)

    def _droppable_paths(self, event) -> list[str]:
        mime = event.mimeData()
        if not mime.hasUrls():
            return []
        paths = []
        for url in mime.urls():
            local = url.toLocalFile()
            if not local:
                continue
            if format_for_path(local) is not None:
                paths.append(local)
        return paths

    # ───────────────────────── Option persistence ─────────────────────────

    _PERSISTENT_CHECKBOXES = (
        "chk_conv_simplify", "chk_conv_clean", "chk_conv_kml_expand",
        "chk_conv_raster", "chk_conv_load", "chk_conv_symbology",
        "chk_conv_plan_fields",
    )

    def _restore_persistent_options(self) -> None:
        settings = QSettings()
        for name in self._PERSISTENT_CHECKBOXES:
            widget = getattr(self, name, None)
            if widget is None:
                continue
            stored = settings.value(f"konwerter_cad_gis/opts/{name}")
            if stored is not None:
                widget.setChecked(str(stored).lower() in ("true", "1"))
            widget.toggled.connect(
                lambda checked, key=name: QSettings().setValue(
                    f"konwerter_cad_gis/opts/{key}", checked))
        stored_type = settings.value("konwerter_cad_gis/opts/plan_type")
        if stored_type is not None:
            with suppress(TypeError, ValueError):
                self.cmb_plan_type.setCurrentIndex(int(stored_type))
        self.cmb_plan_type.currentIndexChanged.connect(
            lambda value: QSettings().setValue(
                "konwerter_cad_gis/opts/plan_type", value))

    def _build_ui(self) -> None:
        self.main_tab = main_tab = QTabWidget()
        # ikony zakładek to podłużne plakietki (CAD / GPKG), więc dajemy
        # im szerokość proporcjonalną do wysokości — inaczej byłyby
        # ściśnięte do nieczytelnego paska
        main_tab.setIconSize(QSize(46, 17))

        # ───────────────────────── TAB 1: Konwersja CAD/GIS ────────────────
        tab1_inner = QWidget()
        cad_gis_layout = QVBoxLayout(tab1_inner)
        cad_gis_layout.setContentsMargins(4, 4, 4, 4)
        cad_gis_layout.setSpacing(2)

        # Source Selection
        src_group = QGroupBox("Plik źródłowy CAD / GIS")
        src_layout = QVBoxLayout(src_group)
        src_layout.setContentsMargins(6, 10, 6, 6)
        src_layout.setSpacing(3)

        type_layout = QHBoxLayout()
        type_layout.addWidget(QLabel("Rodzaj danych:"))
        self.cmb_src_type = QComboBox()
        for fmt in SOURCE_FORMATS:
            self.cmb_src_type.addItem(fmt.label, fmt.key)
        self.cmb_src_type.currentIndexChanged.connect(
            self._on_source_type_changed)
        type_layout.addWidget(self.cmb_src_type, 1)
        src_layout.addLayout(type_layout)

        path_layout = QHBoxLayout()
        self.txt_src_path = QLineEdit()
        self.txt_src_path.setReadOnly(True)
        self.txt_src_path.setPlaceholderText(
            "Wskaż plik albo przeciągnij go tutaj...")
        path_layout.addWidget(self.txt_src_path)

        self.btn_browse_src = QPushButton("Przeglądaj...")
        self.btn_browse_src.setObjectName("browse_btn")
        self.btn_browse_src.clicked.connect(self._browse_src_dataset)
        path_layout.addWidget(self.btn_browse_src)
        src_layout.addLayout(path_layout)

        self.lbl_src_status = QLabel(
            "Wskazówka: plik możesz też przeciągnąć prosto na to okno.")
        self.lbl_src_status.setObjectName("dock_subtitle")
        self.lbl_src_status.setWordWrap(True)
        src_layout.addWidget(self.lbl_src_status)

        cad_row = QHBoxLayout()
        cad_row.setSpacing(4)
        self.chk_cad_split = QCheckBox("Rozbij na osobne warstwy CAD (wg Layer/Level)")
        self.chk_cad_split.setToolTip(
            "Pliki DXF, DWG i DGN trzymają wszystkie obiekty w jednej "
            "tabeli, opisane nazwą warstwy (DXF/DWG) albo poziomem (DGN). "
            "Po włączeniu każda warstwa rysunku stanie się osobną warstwą "
            "QGIS — zamiast jednej wielkiej mieszanki.")
        self.chk_cad_split.setChecked(True)
        self.chk_cad_split.setVisible(False)
        self.chk_cad_split.toggled.connect(self._on_cad_split_toggled)
        cad_row.addWidget(self.chk_cad_split)

        self.btn_clear_ogr_cache = QPushButton("Wyczyść pamięć podręczną katalogu")
        self.btn_clear_ogr_cache.setToolTip(
            "Kasuje zapamiętane listy warstw, dzięki którym geobazy "
            "otwierają się błyskawicznie. Pamięć i tak odbuduje się sama, "
            "gdy plik źródłowy się zmieni.")
        self.btn_clear_ogr_cache.clicked.connect(self._clear_ogr_cache)
        cad_row.addStretch(1)
        cad_row.addWidget(self.btn_clear_ogr_cache)
        src_layout.addLayout(cad_row)

        cad_gis_layout.addWidget(src_group)

        # Delimited text geometry (visible only for CSV/TSV/TXT sources)
        self.csv_group = QGroupBox("Geometria z pliku tekstowego (CSV/TSV)")
        csv_form = QFormLayout(self.csv_group)
        csv_form.setContentsMargins(6, 10, 6, 6)
        csv_form.setSpacing(3)

        self.lbl_csv_summary = QLabel("-")
        self.lbl_csv_summary.setWordWrap(True)
        csv_form.addRow("Co rozpoznaliśmy:", self.lbl_csv_summary)

        self.cmb_csv_x = QComboBox()
        csv_form.addRow("Kolumna X / długość geogr.:", self.cmb_csv_x)
        self.cmb_csv_y = QComboBox()
        csv_form.addRow("Kolumna Y / szerokość geogr.:", self.cmb_csv_y)
        self.cmb_csv_wkt = QComboBox()
        self.cmb_csv_wkt.setToolTip(
            "Wybranie kolumny WKT wyłącza kolumny X/Y — geometria "
            "zostanie odczytana z zapisu WKT.")
        csv_form.addRow("Kolumna z geometrią WKT:", self.cmb_csv_wkt)

        self.csv_src_crs = QgsProjectionSelectionWidget()
        self.csv_src_crs.setOptionVisible(
            QgsProjectionSelectionWidget.CrsOption.ProjectCrs, True)
        csv_form.addRow("Układ współrzędnych źródła:", self.csv_src_crs)

        self.csv_group.setVisible(False)
        cad_gis_layout.addWidget(self.csv_group)

        # Source layer preview (populated after a dataset is chosen)
        self.src_preview_group = QGroupBox("Warstwy znalezione w pliku")
        src_preview_layout = QVBoxLayout(self.src_preview_group)
        src_preview_layout.setContentsMargins(4, 8, 4, 4)
        src_preview_layout.setSpacing(2)

        self.src_layer_tree = QTreeWidget()
        self.src_layer_tree.setHeaderLabels(
            ["Nazwa warstwy", "Geometria", "Obiekty"])
        self.src_layer_tree.setColumnWidth(0, 150)
        self.src_layer_tree.setColumnWidth(1, 90)
        self.src_layer_tree.setRootIsDecorated(False)
        self.src_layer_tree.setMinimumHeight(90)
        src_preview_layout.addWidget(self.src_layer_tree)

        src_sel_layout = QHBoxLayout()
        src_sel_layout.setSpacing(4)
        btn_src_all = QPushButton("Zaznacz wszystkie")
        btn_src_all.clicked.connect(
            lambda: self._set_src_tree_checked(Qt.CheckState.Checked))
        btn_src_none = QPushButton("Odznacz wszystkie")
        btn_src_none.clicked.connect(
            lambda: self._set_src_tree_checked(Qt.CheckState.Unchecked))
        src_sel_layout.addWidget(btn_src_all)
        src_sel_layout.addWidget(btn_src_none)
        src_preview_layout.addLayout(src_sel_layout)

        self.src_preview_group.setVisible(False)
        cad_gis_layout.addWidget(self.src_preview_group)

        # Destination GPKG Selection
        dst_group = QGroupBox("Plik docelowy GeoPackage (.gpkg)")
        dst_layout = QHBoxLayout(dst_group)
        dst_layout.setContentsMargins(6, 10, 6, 6)

        self.txt_gpkg_path = QLineEdit()
        self.txt_gpkg_path.setReadOnly(True)
        self.txt_gpkg_path.setPlaceholderText("Wskaż plik wynikowy .gpkg...")
        dst_layout.addWidget(self.txt_gpkg_path)

        self.btn_browse_gpkg = QPushButton("Zapisz jako...")
        self.btn_browse_gpkg.setObjectName("browse_btn")
        self.btn_browse_gpkg.clicked.connect(self._browse_gpkg_destination)
        dst_layout.addWidget(self.btn_browse_gpkg)
        cad_gis_layout.addWidget(dst_group)

        # Options
        opt_group = QGroupBox("Parametry konwersji")
        opt_form = QFormLayout(opt_group)
        opt_form.setContentsMargins(6, 10, 6, 6)
        opt_form.setSpacing(3)

        self.converter_crs = QgsProjectionSelectionWidget()
        self.converter_crs.setOptionVisible(
            QgsProjectionSelectionWidget.CrsOption.ProjectCrs, True)
        self.converter_crs.setCrs(QgsProject.instance().crs())
        opt_form.addRow("Docelowy układ współrzędnych:", self.converter_crs)

        self.chk_conv_simplify = QCheckBox("Uprość punkty na odcinkach współliniowych")
        self.chk_conv_simplify.setChecked(True)
        opt_form.addRow(self.chk_conv_simplify)

        self.chk_conv_clean = QCheckBox(
            "Usuń zdublowane geometrie i punkty")
        self.chk_conv_clean.setChecked(True)
        opt_form.addRow(self.chk_conv_clean)

        self.chk_conv_kml_expand = QCheckBox(
            "Rozpakuj tabele z dymków KML do atrybutów")
        self.chk_conv_kml_expand.setChecked(True)
        opt_form.addRow(self.chk_conv_kml_expand)

        self.chk_conv_raster = QCheckBox(
            "Wyodrębnij podkłady rastrowe KML do GeoTIFF")
        self.chk_conv_raster.setChecked(True)
        opt_form.addRow(self.chk_conv_raster)

        self.chk_conv_load = QCheckBox(
            "Wczytaj gotowe warstwy do projektu QGIS")
        self.chk_conv_load.setChecked(True)
        opt_form.addRow(self.chk_conv_load)

        self.chk_conv_symbology = QCheckBox(
            "Nadaj gotową symbolizację zgodną z polskimi przepisami")
        self.chk_conv_symbology.setToolTip(
            "Wtyczka rozpoznaje oznaczenia po nazwach warstw rysunku "
            "(np. 3MN, TEREN_ZL, SW, wodociąg) i od razu koloruje je "
            "wg rozporządzeń: strefy planu ogólnego, przeznaczenia "
            "MPZP, barwy GESUT i konwencje EGiB.")
        self.chk_conv_symbology.setChecked(True)
        opt_form.addRow(self.chk_conv_symbology)

        self.cmb_plan_type = QComboBox()
        self.cmb_plan_type.addItems([
            "Rozpoznaj automatycznie (z nazwy pliku i warstw)",
            "MPZP — miejscowy plan zagospodarowania",
            "Plan ogólny gminy (strefy planistyczne)",
            "GESUT — sieci uzbrojenia terenu",
            "EGiB — ewidencja gruntów i budynków",
        ])
        self.cmb_plan_type.setToolTip(
            "Podpowiedz wtyczce, z jakim dokumentem pracujesz — wtedy "
            "kolory dobiera z właściwego katalogu.")
        opt_form.addRow("Rodzaj opracowania:", self.cmb_plan_type)

        self.chk_conv_plan_fields = QCheckBox(
            "Dopisz kolumny opisowe (SYMBOL, PRZEZNACZENIE, GRUPA)")
        self.chk_conv_plan_fields.setToolTip(
            "Do każdej rozpoznanej warstwy dokłada kolumny z symbolem "
            "i pełną nazwą przeznaczenia — tabela atrybutów od razu "
            "czytelna dla planisty i geodety.")
        self.chk_conv_plan_fields.setChecked(True)
        opt_form.addRow(self.chk_conv_plan_fields)

        cad_gis_layout.addWidget(opt_group)

        # Output mode — three mutually exclusive destinations
        out_group = QGroupBox("Sposób zapisu wyniku")
        out_layout = QVBoxLayout(out_group)
        out_layout.setContentsMargins(6, 10, 6, 6)
        out_layout.setSpacing(2)

        self.rb_out_gpkg = QRadioButton("Plik GeoPackage (trwały, przeliczony do wybranego układu)")
        self.rb_out_gpkg.setChecked(True)
        self.rb_out_scratch = QRadioButton(
            "Warstwy tymczasowe (w pamięci, bez pliku)")
        self.rb_out_live = QRadioButton(
            "Podgląd na żywo — bez konwersji, prosto ze źródła")
        self.rb_out_live.setToolTip(
            "Dodaje zaznaczone warstwy prosto do QGIS jako podgląd na żywo "
            "ze źródła. Nic nie jest zapisywane ani kopiowane, więc nawet "
            "ogromne geobazy otwierają się w ułamku sekundy. QGIS czyta "
            "obiekty na bieżąco i sam przelicza układ współrzędnych.")

        self.output_mode_group = QButtonGroup(self)
        for rb in (self.rb_out_gpkg, self.rb_out_scratch, self.rb_out_live):
            self.output_mode_group.addButton(rb)
            out_layout.addWidget(rb)
        self.output_mode_group.buttonToggled.connect(
            lambda *_: self._sync_output_mode())

        cad_gis_layout.addWidget(out_group)

        # Progress Bar & Trigger
        self.progress_conv = QProgressBar()
        self.progress_conv.setVisible(False)
        cad_gis_layout.addWidget(self.progress_conv)

        self.btn_convert_gis = QPushButton("KONWERTUJ DO GEOPACKAGE")
        self.btn_convert_gis.setObjectName("convert_btn")
        self.btn_convert_gis.setEnabled(False)
        self.btn_convert_gis.clicked.connect(self._convert_gis_dataset)
        cad_gis_layout.addWidget(self.btn_convert_gis)

        self._on_source_type_changed(self.cmb_src_type.currentIndex())

        tab_cad_gis = self._make_scroll_tab(tab1_inner)
        main_tab.addTab(
            tab_cad_gis,
            QIcon(
                os.path.join(
                    self.icon_dir,
                    "icon_cad.png")),
            "Konwersja CAD/GIS")

        # ───────────────────────── TAB 3: Eksport z QGIS ─────────────────
        tab3_inner = QWidget()
        exp_layout = QVBoxLayout(tab3_inner)
        exp_layout.setContentsMargins(4, 4, 4, 4)
        exp_layout.setSpacing(2)

        exp_group = QGroupBox("Eksport warstw z projektu QGIS")
        exp_form = QFormLayout(exp_group)
        exp_form.setContentsMargins(6, 10, 6, 6)
        exp_form.setSpacing(3)

        self.cmb_exp_layer = QComboBox()
        self.cmb_exp_layer.currentIndexChanged.connect(
            self._on_export_layer_changed)
        exp_form.addRow("Warstwa do eksportu:", self.cmb_exp_layer)

        self.cmb_exp_format = QComboBox()
        self.cmb_exp_format.addItems([
            "AutoCAD DXF (*.dxf) — z powrotem do CAD-a",
            "GML 3.2 (*.gml) — wymiana danych, INSPIRE, APP",
            "Google Earth KML (*.kml)",
            "Google Earth KMZ (*.kmz)",
        ])
        self.cmb_exp_format.currentIndexChanged.connect(
            self._on_export_format_changed)
        exp_form.addRow("Format eksportu:", self.cmb_exp_format)

        self.export_crs = QgsProjectionSelectionWidget()
        self.export_crs.setOptionVisible(
            QgsProjectionSelectionWidget.CrsOption.ProjectCrs, True)
        self.export_crs.setCrs(QgsProject.instance().crs())
        exp_form.addRow("Układ współrzędnych wyniku:", self.export_crs)

        self.lbl_export_crs_hint = QLabel(
            "DXF zapisujemy w wybranym układzie współrzędnych (np. PUWG 1992/2000).")
        self.lbl_export_crs_hint.setObjectName("dock_subtitle")
        self.lbl_export_crs_hint.setWordWrap(True)
        exp_form.addRow("", self.lbl_export_crs_hint)

        self.chk_export_selected = QCheckBox("Tylko zaznaczone obiekty")
        self.chk_export_selected.setToolTip(
            "Eksportuje tylko obiekty zaznaczone na warstwie źródłowej. "
            "Przy wyłączonej opcji zapisujemy całą warstwę.")
        exp_form.addRow("Zakres obiektów:", self.chk_export_selected)

        self.txt_exp_path = QLineEdit()
        self.txt_exp_path.setReadOnly(True)
        self.txt_exp_path.setPlaceholderText(
            "Wskaż plik docelowy eksportu...")

        self.btn_browse_exp = QPushButton("Zapisz jako...")
        self.btn_browse_exp.setObjectName("browse_btn")
        self.btn_browse_exp.clicked.connect(self._browse_export_destination)

        browse_layout = QHBoxLayout()
        browse_layout.addWidget(self.txt_exp_path)
        browse_layout.addWidget(self.btn_browse_exp)
        exp_form.addRow("Miejsce zapisu:", browse_layout)

        exp_layout.addWidget(exp_group)

        self.btn_run_export = QPushButton("EKSPORTUJ DANE")
        self.btn_run_export.setObjectName("convert_btn")
        self.btn_run_export.setEnabled(False)
        self.btn_run_export.clicked.connect(self._run_export_layer)
        exp_layout.addWidget(self.btn_run_export)
        exp_layout.addStretch(1)

        tab_exp = self._make_scroll_tab(tab3_inner)
        main_tab.addTab(
            tab_exp,
            QIcon(
                os.path.join(
                    self.icon_dir,
                    "icon_gis.png")),
            "Eksport z QGIS")

        # Set main layout
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(3, 3, 3, 3)
        main_layout.setSpacing(3)
        main_layout.addWidget(self._build_header())
        main_layout.addWidget(main_tab, 1)
        main_layout.addWidget(self._build_signature(), 0,
                              Qt.AlignmentFlag.AlignRight)

        central_widget = QWidget()
        central_widget.setLayout(main_layout)
        self.setWidget(central_widget)

        # Populate layers after UI elements are fully constructed
        self._populate_layers_combo()
        self._sync_output_mode()

    @staticmethod
    def _make_scroll_tab(inner_widget: QWidget) -> QScrollArea:
        """Wrap *inner_widget* in a QScrollArea so the tab content scrolls."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(inner_widget)
        return scroll

    def _build_header(self) -> QWidget:
        header = QWidget()
        header.setObjectName("dock_header")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(8, 5, 8, 5)
        layout.setSpacing(6)

        title_box = QWidget()
        title_layout = QVBoxLayout(title_box)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(0)

        title = QLabel("Konwerter CAD na GIS")
        title.setObjectName("dock_title")
        subtitle = QLabel("Rysunki CAD i dane GIS → warstwy QGIS z polskimi oznaczeniami")
        subtitle.setObjectName("dock_subtitle")
        title_layout.addWidget(title)
        title_layout.addWidget(subtitle)

        self.btn_guide = QPushButton("Instrukcja")
        self.btn_guide.setObjectName("guide_btn")
        self.btn_guide.clicked.connect(self._show_guide)

        layout.addWidget(title_box, 1)
        layout.addWidget(self.btn_guide, 0)
        return header

    def _build_signature(self) -> QWidget:
        """Mały podpis autora na dole panelu — klik otwiera nową wiadomość."""
        podpis = QLabel(
            '<a href="mailto:gorniakgrzegorz@gmail.com" '
            'style="color:#000000; text-decoration:none;">'
            '© Grzegorz Górniak</a>')
        podpis.setObjectName("dock_signature")
        podpis.setOpenExternalLinks(True)
        podpis.setToolTip("Masz pomysł albo znalazłeś błąd? Napisz do mnie.")
        podpis.setCursor(Qt.CursorShape.PointingHandCursor)
        return podpis

    def _show_guide(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Instrukcja — Konwerter CAD na GIS")
        dialog.resize(560, 520)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        guide = QTextBrowser(dialog)
        guide.setObjectName("guide_body")
        guide.setOpenExternalLinks(True)
        guide.setHtml("""
        <h2>Konwerter CAD na GIS — jak to działa</h2>
        <p>Wtyczka zamienia rysunki CAD i pliki wymiany danych na gotowe
        warstwy QGIS, pokolorowane zgodnie z polskimi przepisami
        planistycznymi i geodezyjnymi. Czyta DXF, DWG, DGN, GML, KML,
        KMZ, GeoJSON, CSV/TSV, SpatiaLite, GPX, geobazy ArcGIS (.gdb)
        i bazy MS Access. Nie potrzebuje żadnych dodatkowych programów
        — wszystko robi sama.</p>
        <p><b>Najszybsza droga:</b> przeciągnij plik prosto na ten panel.
        Rodzaj danych rozpoznamy po rozszerzeniu, a warstwy z pliku
        pokażemy na liście do zaznaczenia.</p>

        <h3>1. Konwersja do GeoPackage</h3>
        <ol>
          <li>Wskaż plik albo folder <code>.gdb</code> — rodzaj danych
          ustawi się sam.</li>
          <li>Przejrzyj listę <b>Warstwy znalezione w pliku</b> i odznacz
          to, czego nie potrzebujesz. Dla geobaz lista jest zapamiętywana,
          więc kolejne otwarcie tego samego pliku jest natychmiastowe
          (przycisk <b>Wyczyść pamięć podręczną</b> ją kasuje).</li>
          <li>Przy <b>DXF, DWG i DGN</b> zostaw włączone
          <b>Rozbij na osobne warstwy CAD</b> — każda warstwa rysunku
          stanie się osobną warstwą QGIS zamiast jednej wielkiej tabeli.</li>
          <li>Ustaw <b>układ współrzędnych</b>. Dla polskich danych zwykle
          PUWG 1992 (EPSG:2180) albo PUWG 2000 — strefa 5, 6, 7 lub 8
          (EPSG:2176-2179). Gdy plik nie mówi, w jakim jest układzie,
          wtyczka próbuje rozpoznać go po samych współrzędnych.</li>
          <li>Przy plikach tekstowych sprawdź kartę
          <b>Geometria z pliku tekstowego</b>: separator i kolumny X/Y albo
          WKT wykrywamy automatycznie, ale możesz je poprawić.</li>
          <li>Wybierz <b>sposób zapisu</b>: plik GeoPackage (trwały),
          warstwy tymczasowe (do szybkiego podejrzenia) albo podgląd
          na żywo, czyli wczytanie bez konwersji.</li>
          <li>Kliknij <b>KONWERTUJ DO GEOPACKAGE</b>.</li>
        </ol>

        <h3>2. Polskie oznaczenia planistyczne</h3>
        <p>Zostaw włączone <b>Nadaj gotową symbolizację zgodną z polskimi
        przepisami</b>, a wtyczka:</p>
        <ul>
          <li>rozpozna symbol terenu z nazwy warstwy (np. <b>MN</b>,
          <b>3MW</b>, <b>KDW</b>, <b>ZL</b>, <b>SJ</b>, „sieć wodociągowa",
          „działki"),</li>
          <li>nada kolor zgodny z przepisem:
          <b>MPZP</b> — rozporządzenie z 26 sierpnia 2003 r. w sprawie
          wymaganego zakresu projektu planu miejscowego;
          <b>plan ogólny gminy</b> — rozporządzenie z 8 grudnia 2023 r.
          (Dz.U. 2023 poz. 2758), kolory RGB stref wprost z załącznika;
          <b>GESUT / mapa zasadnicza</b> — rozporządzenie z 23 lipca
          2021 r. (barwy branżowe sieci); <b>EGiB</b> — działki, budynki,
          użytki i osnowa,</li>
          <li>dopisze kolumny <b>SYMBOL</b>, <b>PRZEZNACZENIE</b>,
          <b>GRUPA</b>, <b>RODZAJ_DOK</b>, <b>OZNACZENIE</b>
          i <b>WARSTWA_CAD</b> (opcja <b>Dopisz kolumny opisowe</b>).</li>
        </ul>
        <p>Rodzaj opracowania możesz wskazać ręcznie (MPZP, plan ogólny,
        GESUT, EGiB) albo zostawić „rozpoznaj automatycznie" — wtedy
        wtyczka wyczyta go z nazwy pliku i warstw. Warstwy pomocnicze
        rysunku (ramki, opisy, symbole) celowo nie dostają przeznaczenia
        — lepiej puste pole niż zmyślone.</p>

        <h3>3. Eksport warstw z QGIS</h3>
        <ol>
          <li>Wybierz warstwę wektorową z projektu.</li>
          <li>Wskaż format:
          <b>DXF</b> — powrót do CAD-a, w wybranym układzie współrzędnych;
          <b>GML 3.2</b> — wymiana danych z systemami dziedzinowymi,
          usługami INSPIRE i zbiorami danych przestrzennych aktów
          planowania przestrzennego (APP);
          <b>KML / KMZ</b> — Google Earth, zawsze w WGS 84 (EPSG:4326).</li>
          <li>Zaznacz <b>Tylko zaznaczone obiekty</b>, jeśli eksportujesz
          fragment warstwy.</li>
          <li>Podaj miejsce zapisu i kliknij <b>EKSPORTUJ DANE</b>.</li>
        </ol>
        <p>Przy GML obok pliku <code>.gml</code> powstaje schemat
        <code>.xsd</code> z typami kolumn — przekazując dane, wyślij
        oba pliki razem.</p>

        <h3>Uwagi praktyczne</h3>
        <ul>
          <li>Rysunki DWG czytamy wbudowanym sterownikiem QGIS, który
          radzi sobie ze starszymi zapisami (do R2000). Nowszy plik DWG
          wystarczy zapisać w CAD-zie jako <b>DXF</b> — ten format
          obsługujemy w całości, razem z symbolizacją.</li>
          <li>Warstwy tymczasowe są świetne do oglądania, ale znikają
          po zamknięciu projektu; do przekazania danych zapisz
          GeoPackage.</li>
          <li>Kolory MPZP odwzorowują opisy słowne z rozporządzenia
          („jasnobrązowy", „kreskowanie żółto-czerwone"), bo przepis nie
          podaje wartości RGB. Kolory stref planu ogólnego są dokładnie
          takie, jak w załączniku do rozporządzenia z 2023 r.</li>
        </ul>
        """)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(guide, 1)
        layout.addWidget(buttons)
        dialog.exec()

    # ───────────────────────── TAB 1: GIS/CAD CONVERTER CONTROLS ────────────

    def _current_source_format(self) -> SourceFormat | None:
        key = self.cmb_src_type.currentData()
        for fmt in SOURCE_FORMATS:
            if fmt.key == key:
                return fmt
        return None

    @staticmethod
    def _is_cad_format(fmt: SourceFormat | None) -> bool:
        return fmt is not None and fmt.key in ("dxf", "dwg", "dgn")

    _RODZAJE_OPRACOWANIA = {
        0: "AUTO", 1: "MPZP", 2: "PLAN_OGOLNY", 3: "GESUT", 4: "EGIB",
    }

    def _selected_plan_type(self) -> str:
        """Rodzaj dokumentu wybrany na liście (albo AUTO)."""
        combo = getattr(self, "cmb_plan_type", None)
        if combo is None:
            return "AUTO"
        return self._RODZAJE_OPRACOWANIA.get(combo.currentIndex(), "AUTO")

    def _dopisz_kolumny_planistyczne(self, layer, source_name: str) -> None:
        """Dokłada do warstwy kolumny SYMBOL / PRZEZNACZENIE / GRUPA...
        wypełnione na podstawie rozpoznanego oznaczenia."""
        nazwa = layer.name() if hasattr(layer, "name") else ""
        oznaczenie = znajdz_oznaczenie(nazwa) or znajdz_oznaczenie(source_name)
        if oznaczenie is None:
            return

        provider = layer.dataProvider()
        istniejace = {f.name() for f in layer.fields()}
        do_dodania = [f for f in self.PLANGML_FIELD_DEFINITIONS
                      if f.name() not in istniejace]
        if do_dodania:
            provider.addAttributes(do_dodania)
            layer.updateFields()

        wartosci = {
            "SYMBOL": oznaczenie.symbol,
            "PRZEZNACZENIE": oznaczenie.nazwa,
            "GRUPA": oznaczenie.grupa,
            "RODZAJ_DOK": oznaczenie.rodzaj,
            "OZNACZENIE": oznaczenie.geometria,
            "WARSTWA_CAD": nazwa,
        }
        indeksy = {k: layer.fields().indexOf(k) for k in wartosci}
        zmiany = {}
        for feature in layer.getFeatures():
            zmiany[feature.id()] = {
                idx: wartosci[k] for k, idx in indeksy.items() if idx >= 0}
        if zmiany:
            provider.changeAttributeValues(zmiany)
            layer.updateFields()
            layer.triggerRepaint()

    def _dwg_pomoc(self, file_path: str) -> None:
        """Podpowiedź, gdy GDAL nie poradzi sobie z nowszym plikiem DWG."""
        QMessageBox.information(
            self,
            "Nie mogę odczytać tego pliku DWG",
            f"Plik: {os.path.basename(file_path)}\n\n"
            "QGIS czyta bezpośrednio tylko starsze rysunki DWG (format "
            "R2000 i wcześniejsze). Ten plik jest zapisany w nowszej "
            "wersji.\n\n"
            "Najprostsze wyjście — poproś o plik DXF albo zrób go sam:\n"
            "  • AutoCAD / BricsCAD / ZWCAD: Plik → Zapisz jako → "
            "AutoCAD DXF (*.dxf)\n"
            "  • darmowy LibreCAD lub przeglądarka Autodesk Viewer "
            "(viewer.autodesk.com) też zapiszą DXF\n\n"
            "DXF wtyczka obsłuży w całości — z warstwami, kolorami "
            "i symbolizacją planistyczną.")

    def _on_source_type_changed(self, index: int) -> None:
        self.txt_src_path.clear()
        self.btn_convert_gis.setEnabled(False)
        fmt = self._current_source_format()
        is_kml = fmt is not None and fmt.key == "kml"
        self.chk_conv_kml_expand.setEnabled(is_kml)
        self.chk_conv_raster.setEnabled(is_kml)
        self.csv_group.setVisible(fmt is not None and fmt.key == "csv")
        self.chk_cad_split.setVisible(self._is_cad_format(fmt))
        self.src_layer_tree.clear()
        self.src_preview_group.setVisible(False)
        self.src_csv_profile = None
        self._cad_split_field = ""
        self.lbl_src_status.setText(
            "Wskazówka: możesz przeciągnąć plik prosto na to okno.")

    def _on_cad_split_toggled(self, _checked: bool) -> None:
        path = self.txt_src_path.text().strip()
        fmt = self._current_source_format()
        if path and fmt is not None:
            self._refresh_source_preview(path, fmt)
            self._update_convert_gis_button_state()

    def _clear_ogr_cache(self) -> None:
        from ..core import ogr_catalog_cache
        removed = ogr_catalog_cache.clear()
        self.iface.messageBar().pushMessage(
            "Konwerter CAD na GIS",
            f"Wyczyszczono {removed} zapisanych katalogów warstw.",
            Qgis.MessageLevel.Info, 5)

    def _browse_src_dataset(self) -> None:
        fmt = self._current_source_format()
        start_dir = self._last_import_dir()
        if fmt is None:
            fmt = SOURCE_FORMATS[0]

        if fmt.is_dir:
            file_path = QFileDialog.getExistingDirectory(
                self, fmt.dialog_title, start_dir,
                QFileDialog.Option.ShowDirsOnly)
            if file_path and not has_extension(file_path, ".gdb"):
                QMessageBox.warning(
                    self,
                    "Nieprawidłowy folder",
                    "Wskaż folder z rozszerzeniem '.gdb'.")
                return
        else:
            dialog_filter = (
                f"{fmt.file_filter};;{all_supported_filter()};;Wszystkie pliki (*.*)")
            file_path, _ = QFileDialog.getOpenFileName(
                self, fmt.dialog_title, start_dir, dialog_filter)

        if not file_path:
            return
        detected = format_for_path(file_path) or fmt
        self._apply_source_path(file_path, detected)

    def _apply_source_path(self, file_path: str, fmt: SourceFormat) -> None:
        """Set the source path/type and refresh the layer preview."""
        target_index = self.cmb_src_type.findData(fmt.key)
        if target_index >= 0 and target_index != self.cmb_src_type.currentIndex():
            self.cmb_src_type.blockSignals(True)
            self.cmb_src_type.setCurrentIndex(target_index)
            self.cmb_src_type.blockSignals(False)
            is_kml = fmt.key == "kml"
            self.chk_conv_kml_expand.setEnabled(is_kml)
            self.chk_conv_raster.setEnabled(is_kml)
            self.csv_group.setVisible(fmt.key == "csv")
        self.chk_cad_split.setVisible(self._is_cad_format(fmt))

        self.txt_src_path.setText(file_path)
        self._remember_import_dir(file_path)
        self._suggest_gpkg_destination(file_path)
        self._refresh_source_preview(file_path, fmt)
        self._update_convert_gis_button_state()

    def _suggest_gpkg_destination(self, source_path: str) -> None:
        """Prefill the target GPKG from the source name when still empty."""
        if self.txt_gpkg_path.text().strip() \
                or self.rb_out_scratch.isChecked() \
                or self.rb_out_live.isChecked():
            return
        stem = os.path.splitext(os.path.basename(
            source_path.rstrip("\\/")))[0] or "converted"
        suggestion = os.path.join(self._last_export_dir(), f"{stem}.gpkg")
        self.txt_gpkg_path.setText(suggestion)

    def _refresh_source_preview(self, file_path: str,
                                fmt: SourceFormat) -> None:
        self.src_layer_tree.clear()
        self.src_csv_profile = None
        self._cad_split_field = ""
        cad_split = self._is_cad_format(fmt) and self.chk_cad_split.isChecked()
        try:
            if fmt.key == "csv":
                self.src_csv_profile = sniff_delimited_dataset(file_path)
                self._populate_csv_controls(self.src_csv_profile)

            probe = GisConverterEngine(
                file_path, "", QgsProject.instance().crs(),
                csv_profile=self.src_csv_profile)
            if cad_split:
                infos, field = probe.discover_cad_layers()
                self._cad_split_field = field
                if not field:
                    # Source had no CAD-layer field; fall back to plain view.
                    infos = probe.discover_layers()
            else:
                infos = probe.discover_layers(
                    is_kmz=has_extension(file_path, ".kmz"))
            from_cache = probe.catalog_from_cache
            probe.cleanup()
        except Exception as exc:
            if fmt and fmt.key == "dwg":
                self._dwg_pomoc(file_path)
            self.src_preview_group.setVisible(False)
            self.lbl_src_status.setText(f"Nie udało się zajrzeć do pliku: {exc}")
            return

        header = ("Warstwa rysunku CAD" if self._cad_split_field else "Nazwa warstwy")
        self.src_layer_tree.setHeaderLabels([header, "Geometria", "Obiekty"])
        for info in infos:
            item = QTreeWidgetItem(self.src_layer_tree)
            item.setText(0, fix_mojibake(info.name))
            item.setText(1, info.geometry)
            item.setText(2, "?" if info.feature_count < 0
                         else str(info.feature_count))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(0, Qt.CheckState.Checked)
            item.setData(0, Qt.ItemDataRole.UserRole, info.key)

        self.src_preview_group.setVisible(bool(infos))
        total = sum(max(info.feature_count, 0) for info in infos)
        unit = ("warstw rysunku" if self._cad_split_field else "warstw")
        cache_note = " (z pamięci podręcznej)" if from_cache else ""
        self.lbl_src_status.setText(
            f"Znaleziono {len(infos)} {unit}, razem ok. {total} "
            f"obiektów{cache_note}. Odznacz to, czego nie potrzebujesz.")

    def _populate_csv_controls(self, profile: CsvGeometryProfile) -> None:
        for combo in (self.cmb_csv_x, self.cmb_csv_y, self.cmb_csv_wkt):
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("(brak)", "")
            for name in profile.fields:
                combo.addItem(name, name)
            combo.blockSignals(False)

        def select(combo: QComboBox, value: str) -> None:
            index = combo.findData(value)
            combo.setCurrentIndex(index if index >= 0 else 0)

        select(self.cmb_csv_x, profile.x_field)
        select(self.cmb_csv_y, profile.y_field)
        select(self.cmb_csv_wkt, profile.wkt_field)

        if profile.crs_authid:
            crs = QgsCoordinateReferenceSystem(profile.crs_authid)
            if crs.isValid():
                self.csv_src_crs.setCrs(crs)
        elif not self.csv_src_crs.crs().isValid():
            self.csv_src_crs.setCrs(QgsProject.instance().crs())

        self.lbl_csv_summary.setText(
            f"Delimiter '{profile.delimiter}' — {profile.geometry_summary}")

    def _effective_csv_profile(self) -> CsvGeometryProfile | None:
        """CSV profile with the user's current field overrides applied."""
        if self.src_csv_profile is None:
            return None
        profile = CsvGeometryProfile(
            delimiter=self.src_csv_profile.delimiter,
            fields=list(self.src_csv_profile.fields),
            x_field=self.cmb_csv_x.currentData() or "",
            y_field=self.cmb_csv_y.currentData() or "",
            wkt_field=self.cmb_csv_wkt.currentData() or "",
            crs_authid=self.src_csv_profile.crs_authid,
            row_count=self.src_csv_profile.row_count,
        )
        if profile.wkt_field:
            profile.x_field = ""
            profile.y_field = ""
        return profile

    def _selected_source_layers(self) -> list[str] | None:
        """Checked layer names from the preview tree; None = everything."""
        count = self.src_layer_tree.topLevelItemCount()
        if count == 0:
            return None
        selected = []
        for index in range(count):
            item = self.src_layer_tree.topLevelItem(index)
            if item.checkState(0) == Qt.CheckState.Checked:
                selected.append(item.data(0, Qt.ItemDataRole.UserRole))
        return selected

    def _set_src_tree_checked(self, state: Qt.CheckState) -> None:
        for index in range(self.src_layer_tree.topLevelItemCount()):
            self.src_layer_tree.topLevelItem(index).setCheckState(0, state)

    def _browse_gpkg_destination(self) -> None:
        start = self.txt_gpkg_path.text().strip() or self._last_export_dir()
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Wskaż plik wynikowy GeoPackage", start, "GeoPackage (*.gpkg)"
        )
        if file_path:
            file_path = ensure_extension(file_path, ".gpkg")
            self.txt_gpkg_path.setText(file_path)
            QSettings().setValue(
                "konwerter_cad_gis/last_export_dir", os.path.dirname(file_path))
            self._update_convert_gis_button_state()

    def _sync_output_mode(self) -> None:
        """Keep the destination widgets and button label in sync with the
        selected output mode (GeoPackage / scratch / live)."""
        is_temp = self.rb_out_scratch.isChecked()
        is_live = self.rb_out_live.isChecked()
        writes_gpkg = not (is_temp or is_live)

        self.txt_gpkg_path.setEnabled(writes_gpkg)
        self.btn_browse_gpkg.setEnabled(writes_gpkg)
        if not writes_gpkg:
            self.txt_gpkg_path.clear()
            self.chk_conv_load.setChecked(True)
        self.chk_conv_load.setEnabled(writes_gpkg)

        if is_live:
            self.btn_convert_gis.setText("DODAJ WARSTWY BEZ KONWERSJI")
        elif is_temp:
            self.btn_convert_gis.setText("IMPORTUJ JAKO WARSTWY TYMCZASOWE")
        else:
            self.btn_convert_gis.setText("KONWERTUJ DO GEOPACKAGE")
        self._update_convert_gis_button_state()

    def _update_convert_gis_button_state(self) -> None:
        has_src = bool(self.txt_src_path.text().strip())
        is_temp = self.rb_out_scratch.isChecked()
        is_live = self.rb_out_live.isChecked()
        has_dst = bool(self.txt_gpkg_path.text().strip())
        self.btn_convert_gis.setEnabled(
            has_src and (is_temp or is_live or has_dst))

    def _convert_gis_dataset(self) -> None:
        src = self.txt_src_path.text()
        dst = self.txt_gpkg_path.text()
        fmt = self._current_source_format()
        if fmt is None:
            fmt = format_for_path(src) or SOURCE_FORMATS[0]

        selected_layers = self._selected_source_layers()
        if selected_layers is not None and not selected_layers:
            QMessageBox.warning(
                self, "Uwaga",
                "Zaznacz przynajmniej jedną warstwę do konwersji.")
            return

        crs = self.converter_crs.crs()
        if not crs.isValid():
            crs = QgsProject.instance().crs()

        self.progress_conv.setVisible(True)
        self.progress_conv.setValue(5)
        self.progress_conv.setFormat("Uruchamiam konwerter...")
        QApplication.processEvents()

        try:
            is_kml = fmt.key == "kml"
            is_kmz = is_kml and has_extension(src, ".kmz")
            is_temp = self.rb_out_scratch.isChecked()
            is_live = self.rb_out_live.isChecked()

            csv_profile = None
            csv_crs = ""
            if fmt.key == "csv":
                csv_profile = self._effective_csv_profile()
                if self.csv_src_crs.crs().isValid():
                    csv_crs = self.csv_src_crs.crs().authid()

            src_crs_param = self.csv_src_crs.crs() if self.csv_src_crs.crs().isValid() else None
            self.gis_converter = GisConverterEngine(
                src, dst, crs,
                csv_profile=csv_profile, csv_source_crs=csv_crs,
                source_crs=src_crs_param)
            if self._cad_split_field and self._is_cad_format(fmt):
                self.gis_converter.cad_split_field = self._cad_split_field

            layer_total = max(
                len(selected_layers) if selected_layers is not None else 1, 1)
            progress_state = {"done": 0}

            verb = "Dodaję" if is_live else "Konwertuję"

            def layer_progress(layer_name: str) -> None:
                progress_state["done"] += 1
                share = min(progress_state["done"] / layer_total, 1.0)
                self.progress_conv.setValue(10 + int(share * 55))
                self.progress_conv.setFormat(f"{verb} {layer_name}...")
                QApplication.processEvents()

            if is_live:
                loaded_layers = self.gis_converter.load_layers_live(
                    is_kmz=is_kmz,
                    selected_layers=selected_layers,
                    progress_cb=layer_progress,
                )
            elif is_temp:
                loaded_layers = self.gis_converter.convert_to_memory(
                    is_kmz=is_kmz,
                    html_expansion=self.chk_conv_kml_expand.isChecked(),
                    selected_layers=selected_layers,
                    progress_cb=layer_progress,
                )
            else:
                loaded_layers = self.gis_converter.convert(
                    is_kmz=is_kmz,
                    html_expansion=self.chk_conv_kml_expand.isChecked(),
                    selected_layers=selected_layers,
                    progress_cb=layer_progress,
                )

            # GroundOverlay Extraction
            if self.chk_conv_raster.isChecked() and is_kml:
                self.progress_conv.setValue(70)
                self.progress_conv.setFormat(
                    "Wyodrębniam podkłady rastrowe z KML...")
                QApplication.processEvents()
                raster_layers = self.gis_converter.extract_ground_overlays(
                    is_kmz=is_kmz)
                for rl in raster_layers:
                    QgsProject.instance().addMapLayer(rl)

            self.progress_conv.setValue(85)
            self.progress_conv.setFormat("Dodaję warstwy do projektu...")
            QApplication.processEvents()

            if (is_live or self.chk_conv_load.isChecked()) and loaded_layers:
                root = QgsProject.instance().layerTreeRoot()
                suffix = ("LIVE" if is_live
                          else "TEMP" if is_temp else "GPKG")
                nazwa_pliku = self._sanitize_name(
                    os.path.basename(src))
                group_name = f"{nazwa_pliku}_{suffix}"

                existing = root.findGroup(group_name)
                if existing:
                    root.removeChildNode(existing)

                group = root.addGroup(group_name)
                plan_type = self._selected_plan_type()
                zrodlo = os.path.basename(src)
                for cl in loaded_layers:
                    if self.chk_conv_plan_fields.isChecked() and not is_live:
                        with suppress(Exception):
                            self._dopisz_kolumny_planistyczne(cl, zrodlo)
                    if self.chk_conv_symbology.isChecked():
                        with suppress(Exception):
                            apply_plan_symbology(cl, plan_type=plan_type,
                                                 source_name=zrodlo)
                    QgsProject.instance().addMapLayer(cl, False)
                    group.addLayer(cl)

            self.progress_conv.setValue(100)
            self.progress_conv.setVisible(False)

            # Refresh exporter layer combo list
            self._populate_layers_combo()

            src_label = os.path.basename(src.rstrip(chr(92) + '/'))
            if is_live:
                message = (
                    f"Dodano {len(loaded_layers)} live warstw z pliku "
                    f"{src_label} bez konwersji (podgląd prosto ze źródła).")
            else:
                destination = ("warstwy tymczasowe" if is_temp
                               else os.path.basename(dst))
                message = (
                    f"Skonwertowano {len(loaded_layers)} warstw z pliku "
                    f"{src_label} to {destination}.")
            self.iface.messageBar().pushMessage(
                "Konwerter CAD na GIS", message, Qgis.MessageLevel.Success, 7)

            notes = getattr(self.gis_converter, "last_warnings", [])
            for note in notes:
                self.iface.messageBar().pushMessage(
                    "Konwerter CAD na GIS", note, Qgis.MessageLevel.Uwaga, 10)

        except Exception as exc:
            self.progress_conv.setVisible(False)
            if fmt and fmt.key == "dwg":
                self._dwg_pomoc(src)
                return
            QMessageBox.critical(
                self,
                "Błąd konwersji",
                f"Konwersja się nie powiodła:\n\n{exc}")

    # ───────────────────────── Narzędzia pomocnicze ─────────────────────────

    @staticmethod
    def _sanitize_name(value: str) -> str:
        """Zamienia nazwę na bezpieczną dla warstwy/pliku (bez dziwnych znaków)."""
        cleaned = re.sub(r"[^0-9A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż_\- ]+", "_", str(value or ""))
        cleaned = re.sub(r"\s+", "_", cleaned).strip("_")
        return cleaned or "warstwa"


    # ───────────────────────── TAB 3: EXPORTER CONTROLS ─────────────────────

    def _populate_layers_combo(self) -> None:
        """Wypełnia listę warstw do eksportu."""
        previous_id = self.cmb_exp_layer.currentData()
        self.cmb_exp_layer.clear()
        layers = QgsProject.instance().mapLayers().values()
        for layer in layers:
            if isinstance(layer, QgsVectorLayer) and layer.isValid():
                self.cmb_exp_layer.addItem(layer.name(), layer.id())
                if layer.id() not in self._export_selection_connections:
                    layer.selectionChanged.connect(
                        self._update_export_selection_scope)
                    self._export_selection_connections.add(layer.id())
        previous_index = self.cmb_exp_layer.findData(previous_id)
        if previous_index >= 0:
            self.cmb_exp_layer.setCurrentIndex(previous_index)
        self._on_export_layer_changed(self.cmb_exp_layer.currentIndex())
        self._update_export_button_state()

    def _on_export_format_changed(self, index: int) -> None:
        self.txt_exp_path.clear()
        if index in (2, 3):          # KML / KMZ
            self.export_crs.setCrs(QgsCoordinateReferenceSystem("EPSG:4326"))
            self.export_crs.setEnabled(False)
            self.lbl_export_crs_hint.setText(
                "KML/KMZ zapisujemy zawsze w układzie WGS 84 "
                "(EPSG:4326) — tego wymaga Google Earth.")
        else:
            self.export_crs.setEnabled(True)
            layer = self._selected_export_layer()
            if layer is not None and layer.crs().isValid():
                self.export_crs.setCrs(layer.crs())
            if index == 1:           # GML
                self.lbl_export_crs_hint.setText(
                    "GML 3.2 z opisem układu w postaci urn:ogc:def:crs "
                    "(np. PUWG 2000). Obok pliku .gml powstanie schemat "
                    ".xsd — wysyłaj oba razem.")
            else:                    # DXF
                self.lbl_export_crs_hint.setText(
                    "DXF zapisujemy w wybranym układzie współrzędnych "
                    "(np. PUWG 1992 lub 2000).")
        self._update_export_button_state()

    def _selected_export_layer(self) -> QgsVectorLayer | None:
        layer = QgsProject.instance().mapLayer(self.cmb_exp_layer.currentData())
        if isinstance(layer, QgsVectorLayer) and layer.isValid():
            return layer
        return None

    def _on_export_layer_changed(self, _index: int) -> None:
        layer = self._selected_export_layer()
        self._update_export_selection_scope()
        if self.cmb_exp_format.currentIndex() in (0, 1) and layer is not None \
                and layer.crs().isValid():
            self.export_crs.setCrs(layer.crs())
        self._update_export_button_state()

    def _update_export_selection_scope(self, *_signal_args) -> None:
        """Keep selected-feature scope live as the canvas selection changes."""
        layer = self._selected_export_layer()
        selected_count = layer.selectedFeatureCount() if layer else 0
        self.chk_export_selected.setText(
            f"Tylko zaznaczone obiekty ({selected_count} zaznaczonych)")
        self.chk_export_selected.setEnabled(selected_count > 0)
        if selected_count == 0:
            self.chk_export_selected.setChecked(False)
        self._update_export_button_state()

    def _last_export_dir(self) -> str:
        """Return the last export folder, falling back to the user home."""
        value = QSettings().value("konwerter_cad_gis/last_export_dir", "")
        return value if isinstance(value, str) and os.path.isdir(value) else os.path.expanduser("~")

    def _last_import_dir(self) -> str:
        """Return the last import (source dataset) folder, falling back to the user home."""
        value = QSettings().value("konwerter_cad_gis/last_import_dir", "")
        return value if isinstance(value, str) and os.path.isdir(value) else os.path.expanduser("~")

    def _remember_import_dir(self, file_path: str) -> None:
        folder = file_path if os.path.isdir(file_path) else os.path.dirname(file_path)
        if folder and os.path.isdir(folder):
            QSettings().setValue("konwerter_cad_gis/last_import_dir", folder)

    def _browse_export_destination(self) -> None:
        idx = self.cmb_exp_format.currentIndex()
        okna = {
            0: ("Zapisz jako rysunek DXF", "AutoCAD DXF (*.dxf)", ".dxf"),
            1: ("Zapisz jako plik GML", "Geography Markup Language (*.gml)", ".gml"),
            2: ("Zapisz jako plik KML", "Google Earth KML (*.kml)", ".kml"),
            3: ("Zapisz jako paczkę KMZ", "Google Earth KMZ (*.kmz)", ".kmz"),
        }
        tytul, filtr, rozszerzenie = okna.get(idx, okna[0])
        file_path, _ = QFileDialog.getSaveFileName(
            self, tytul, self._last_export_dir(), filtr)
        file_path = ensure_extension(file_path, rozszerzenie)

        if file_path:
            self.txt_exp_path.setText(file_path)
            QSettings().setValue("konwerter_cad_gis/last_export_dir", os.path.dirname(file_path))
            self._update_export_button_state()

    def _update_export_button_state(self) -> None:
        has_layer = self.cmb_exp_layer.currentIndex() >= 0
        has_path = bool(self.txt_exp_path.text().strip())
        self.btn_run_export.setEnabled(has_layer and has_path)

    def _run_export_layer(self) -> None:
        layer_id = self.cmb_exp_layer.currentData()
        output_path = self.txt_exp_path.text()
        format_idx = self.cmb_exp_format.currentIndex()

        layer = QgsProject.instance().mapLayer(layer_id)
        if not layer or not isinstance(layer, QgsVectorLayer):
            QMessageBox.warning(
                self,
                "Uwaga przy eksporcie",
                "Warstwa źródłowa nie jest już dostępna.")
            return

        try:
            selected_only = self.chk_export_selected.isChecked()
            if selected_only and layer.selectedFeatureCount() == 0:
                raise ValueError(
                    "Włączony jest tryb \"tylko zaznaczone obiekty\", "
                    "ale na warstwie nic już nie jest zaznaczone.")
            target_crs = self.export_crs.crs()
            if not target_crs.isValid():
                raise ValueError("Wybierz poprawny układ współrzędnych przed eksportem.")

            if format_idx == 0:  # DXF
                result = CadExportEngine.export_layer_to_dxf(
                    layer, output_path,
                    target_crs=target_crs,
                    selected_only=selected_only)
            else:
                format_nazwa = {1: "GML", 2: "KML", 3: "KMZ"}[format_idx]
                result = GisConverterEngine.export_layer_to_gis(
                    layer, output_path, format_nazwa,
                    target_crs=target_crs,
                    selected_only=selected_only)

            size_mb = result.bytes_written / (1024 * 1024)
            zakres = ("tylko zaznaczone obiekty" if selected_only
                      else "cała warstwa")
            dopisek = ""
            if result.driver == "GML":
                dopisek = ("\n\nObok pliku .gml zapisaliśmy schemat .xsd "
                           "— przy wysyłce dołącz oba pliki.")
            QMessageBox.information(
                self,
                "Gotowe — dane zapisane",
                f"Eksport do formatu {result.driver} zakończony.\n\n"
                f"Warstwa: {layer.name()}\n"
                f"Zakres: {zakres}\n"
                f"Obiekty: {result.feature_count:,}\n"
                f"Układ współrzędnych: {result.target_crs}\n"
                f"Rozmiar pliku: {size_mb:.2f} MB\n"
                f"Plik: {result.path}{dopisek}")

        except Exception as exc:
            QMessageBox.critical(
                self,
                "Błąd eksportu",
                f"Nie udało się wyeksportować warstwy:\n\n{exc}")
