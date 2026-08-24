# -*- coding: utf-8 -*-
"""
Główna klasa wtyczki "Konwerter CAD na GIS".

Stawia na pasku narzędzi jeden przycisk (ikona + napis), który
otwiera/zamyka panel wtyczki po prawej stronie okna QGIS.

Na bazie wtyczki zero2cadgis (GPL-2.0-or-later, © Yusuf Eminoğlu) —
patrz ATRYBUCJA.md. Wersja polska: © Grzegorz Górniak.
"""
from __future__ import annotations

import os

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import (QAction, QToolBar, QToolButton,
                                 QMessageBox)


class KonwerterCadGis:
    NAZWA_PASKA = "Konwerter CAD na GIS"

    def __init__(self, iface):
        self.iface = iface
        self.folder_wtyczki = os.path.dirname(__file__)
        self.folder_ikon = os.path.join(self.folder_wtyczki, "icons")
        self.akcja = None
        self.pasek: QToolBar | None = None
        self._panel = None

    # ───────────────────────── cykl życia w QGIS ─────────────────────────

    def initGui(self) -> None:
        """QGIS woła to przy starcie — dodajemy przycisk i pozycję w menu."""
        ikona = QIcon(os.path.join(self.folder_wtyczki, "icon.svg"))
        if ikona.isNull():
            ikona = QIcon(os.path.join(self.folder_wtyczki, "icon.png"))

        self.akcja = QAction(ikona, "Konwerter CAD na GIS",
                             self.iface.mainWindow())
        self.akcja.setCheckable(True)
        self.akcja.setToolTip(
            "Konwersja rysunków CAD i danych GIS do GeoPackage "
            "z polskimi oznaczeniami planistycznymi")
        self.akcja.triggered.connect(self._przelacz_panel)

        # własny pasek narzędzi z przyciskiem "ikona + napis"
        self.pasek = self.iface.addToolBar(self.NAZWA_PASKA)
        self.pasek.setObjectName("KonwerterCadGisToolbar")
        przycisk = QToolButton()
        przycisk.setDefaultAction(self.akcja)
        przycisk.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.pasek.addWidget(przycisk)

        self.iface.addPluginToMenu("&Konwerter CAD na GIS", self.akcja)

    def unload(self) -> None:
        """Sprzątanie przy wyłączaniu wtyczki."""
        if self._panel:
            self.iface.removeDockWidget(self._panel)
            self._panel.deleteLater()
            self._panel = None

        if self.akcja:
            self.iface.removePluginMenu("&Konwerter CAD na GIS", self.akcja)
        if self.pasek:
            self.pasek.deleteLater()
            self.pasek = None

    # ───────────────────────── panel wtyczki ─────────────────────────

    def _przelacz_panel(self) -> None:
        """Klik w przycisk: pokaż panel albo go schowaj."""
        utworzony = False
        if self._panel is None:
            try:
                from .dialogs.dock import PanelKonwertera

                self._panel = PanelKonwertera(
                    self.iface, self.folder_ikon,
                    self.iface.mainWindow())
                self._panel.setObjectName("KonwerterCadGisPanel")
                self._panel.visibilityChanged.connect(
                    self.akcja.setChecked)
                self.iface.addDockWidget(
                    Qt.DockWidgetArea.RightDockWidgetArea, self._panel)
                utworzony = True
            except Exception as blad:
                QMessageBox.critical(
                    self.iface.mainWindow(), "OJ, coś nie wyszło",
                    f"Nie udało się otworzyć panelu wtyczki:\n{blad}")
                self.akcja.setChecked(False)
                return

        if utworzony or not self._panel.isVisible():
            self._panel.setVisible(True)
            self.akcja.setChecked(True)
            self._panel.raise_()
        else:
            self._panel.setVisible(False)
            self.akcja.setChecked(False)
