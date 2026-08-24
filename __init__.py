# -*- coding: utf-8 -*-
"""
Punkt startowy wtyczki "Konwerter CAD na GIS".
QGIS woła tę funkcję przy włączaniu wtyczki. © Grzegorz Górniak
"""


def classFactory(iface):
    from .main_plugin import KonwerterCadGis
    return KonwerterCadGis(iface)
