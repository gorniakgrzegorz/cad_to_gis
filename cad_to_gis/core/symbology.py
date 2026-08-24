# -*- coding: utf-8 -*-
"""
SYMBOLIZACJA — automatyczne kolorowanie warstw po polsku.

Co robi ten moduł: dostaje warstwę (np. z rysunku CAD o nazwie "MN",
"3_MW_zabudowa" albo "sieć wodociągowa") i dobiera do niej kolor,
kreskę i legendę zgodne z polskimi przepisami. Katalog kolorów siedzi
w pliku ``katalog_pl.py`` (tam też podstawy prawne).

Silnik zbudowany na katalogu polskim; szkielet i pomysł na dopasowywanie
stylu do nazwy warstwy pochodzą z wtyczki zero2cadgis (GPL-2.0-or-later,
© Yusuf Eminoğlu) — patrz plik ATRYBUCJA.md.

© Grzegorz Górniak
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Optional

from .katalog_pl import (
    KATALOG,
    GRUPA_NIEROZPOZNANE,
    RODZAJE,
    RODZAJ_MPZP,
    RODZAJ_PLAN_OGOLNY,
    RODZAJ_GESUT,
    RODZAJ_EGIB,
    SLOWA_RODZAJU,
    wszystkie_wpisy,
)

# grubość obrysu terenu, gdy wpis katalogu nic o niej nie mówi
OBRYS_DOMYSLNY_MM = 0.5


@dataclass
class PlanStyleRule:
    """Jedna gotowa reguła stylu: czym i jak pomalować warstwę."""

    category_id: str                  # np. "MN"
    display_name: str                 # etykieta do legendy
    fill_color: str                   # kolor wypełnienia (#RRGGBB)
    fill_opacity: float               # 0.0 - 1.0
    stroke_color: str                 # kolor obrysu
    stroke_width: float               # grubość obrysu w mm
    keywords: List[str] = field(default_factory=list)
    ust_grup_adi: str = GRUPA_NIEROZPOZNANE   # grupa (do drzewa warstw)
    alt_grup_adi: str = ""                    # nazwa szczegółowa
    stroke_style: str = "solid"       # solid / dash
    hatch_pattern: Optional[str] = None       # rodzaj kreskowania
    hatch_color: Optional[str] = None         # kolor kreskowania
    hatch_distance: float = 2.5       # odstęp kreskowania w mm
    hatch_angle: float = 45.0         # kąt kreskowania w stopniach
    marker_shape: str = "circle"      # kształt punktu
    dash_pattern: Optional[List[float]] = None   # wzór kreski (mm)
    official: bool = False            # czy z katalogu przepisów
    plan_type: str = ""               # MPZP / PLAN_OGOLNY / GESUT / EGIB
    geometry_hint: str = "poligon"    # podpowiedź geometrii


# kąty kreskowania (stopnie) dla nazw używanych w katalogu
_KATY_KRESKOWANIA = {
    "ukosne": 45.0,
    "ukosne_wstecz": 135.0,
    "poziome": 0.0,
    "pionowe": 90.0,
    "krzyzowe": 45.0,     # krzyżowe rysujemy jako dwie warstwy kreskowania
}


def _regula_z_wpisu(wpis: Dict[str, Any]) -> PlanStyleRule:
    """Zamienia wpis katalogu (słownik) na gotową regułę stylu."""
    kreskowanie = wpis.get("kreskowanie")
    wypelnienie = wpis.get("wypelnienie")
    return PlanStyleRule(
        category_id=wpis["symbol"],
        display_name=wpis["etykieta"],
        fill_color=wypelnienie or "#FFFFFF",
        fill_opacity=1.0 if wypelnienie else 0.0,
        stroke_color=wpis.get("obrys") or "#333333",
        stroke_width=float(wpis.get("szerokosc") or OBRYS_DOMYSLNY_MM),
        keywords=[wpis["symbol"]] + list(wpis.get("slowa") or []),
        ust_grup_adi=wpis.get("grupa") or GRUPA_NIEROZPOZNANE,
        alt_grup_adi=wpis["etykieta"],
        stroke_style="dash" if wpis.get("kreska") else "solid",
        hatch_pattern=kreskowanie,
        hatch_color=wpis.get("kolor_kreskowania") or wpis.get("obrys"),
        hatch_angle=_KATY_KRESKOWANIA.get(kreskowanie or "", 45.0),
        dash_pattern=list(wpis["kreska"]) if wpis.get("kreska") else None,
        official=True,
        plan_type=wpis.get("rodzaj") or "",
        geometry_hint=wpis.get("geometria") or "poligon",
    )


# cały katalog przeliczony na reguły stylu (raz, przy imporcie modułu)
PLAN_SYMBOLOGY_CATALOG: List[PlanStyleRule] = [
    _regula_z_wpisu(w) for w in wszystkie_wpisy()
]


def detect_plan_type(name: Optional[str]) -> Optional[str]:
    """
    Zgaduje rodzaj dokumentu z nazwy pliku lub warstwy:
    MPZP, PLAN_OGOLNY, GESUT albo EGIB. Zwraca None, gdy nie wiadomo.
    """
    if not name:
        return None
    # podkreślenia, myślniki i kropki traktujemy jak spacje — nazwy
    # plików bywają zapisane na każdy z tych sposobów
    tekst = _bez_ogonkow(str(name)).upper()
    tekst = re.sub(r"[^A-Z0-9]+", " ", tekst)
    for slowo, rodzaj in SLOWA_RODZAJU.items():
        if slowo in tekst:
            return rodzaj
    return None


def _bez_ogonkow(tekst: str) -> str:
    """Zamienia polskie znaki na podstawowe (ą->A, ł->L itd.), żeby
    dopasowanie nazw działało niezależnie od zapisu."""
    mapa = str.maketrans({
        "Ą": "A", "Ć": "C", "Ę": "E", "Ł": "L", "Ń": "N", "Ó": "O",
        "Ś": "S", "Ź": "Z", "Ż": "Z",
        "ą": "A", "ć": "C", "ę": "E", "ł": "L", "ń": "N", "ó": "O",
        "ś": "S", "ź": "Z", "ż": "Z",
    })
    return tekst.translate(mapa)


def _zbuduj_indeks_odmian() -> dict:
    """Krótkie słowa kluczowe wyglądające jak symbol (KDL, KDZ, KDD...),
    żeby oznaczenia z numerem porządkowym też dostawały kolor."""
    indeks = {}
    for wpis in KATALOG.values():
        for slowo in wpis.get("slowa", ()):
            klucz = PlanSymbologyMatcher.normalize_string(slowo).replace("_", "")
            if 1 <= len(klucz) <= 5 and klucz.isalpha() \
                    and klucz not in KATALOG:
                indeks.setdefault(klucz, wpis)
    return indeks


_INDEKS_ODMIAN: Optional[dict] = None


def _indeks_odmian() -> dict:
    """Buduje indeks przy pierwszym użyciu (klasa matchera jest
    zdefiniowana niżej w pliku)."""
    global _INDEKS_ODMIAN
    if _INDEKS_ODMIAN is None:
        _INDEKS_ODMIAN = _zbuduj_indeks_odmian()
    return _INDEKS_ODMIAN


def match_official_rule(layer_name: str,
                        plan_type: str = RODZAJ_MPZP
                        ) -> Optional[PlanStyleRule]:
    """
    Szuka w katalogu reguły pasującej do nazwy warstwy.

    Kolejność dopasowania (od najpewniejszego):
      1. sam symbol na początku nazwy, np. "MN", "3MN", "1.MW", "KDW_2",
      2. symbol jako osobny człon nazwy, np. "TEREN_MN_1",
      3. słowa kluczowe, np. "zabudowa mieszkaniowa jednorodzinna".
    """
    if not layer_name:
        return None

    nazwa = PlanSymbologyMatcher.normalize_string(layer_name)
    if not nazwa:
        return None
    czlony = [c for c in nazwa.split("_") if c]

    # 1. symbol na początku nazwy (z ewentualnym numerem porządkowym)
    pierwszy = czlony[0] if czlony else ""
    kandydat = re.sub(r"^\d+", "", pierwszy)      # "3MN" -> "MN"
    kandydat = re.sub(r"\d+$", "", kandydat)      # "MN1" -> "MN"
    if kandydat and kandydat in KATALOG:
        return _regula_z_wpisu(KATALOG[kandydat])

    # 2. symbol jako osobny człon nazwy
    for czlon in czlony:
        goly = re.sub(r"^\d+|\d+$", "", czlon)
        if goly and goly in KATALOG:
            return _regula_z_wpisu(KATALOG[goly])

    # 2b. odmiany symbolu wymienione w katalogu (np. "1KDL" -> KD,
    #     "2KDZ" -> KD) — dostają kolor wpisu nadrzędnego
    for czlon in [pierwszy] + czlony:
        goly = re.sub(r"^\d+|\d+$", "", czlon)
        wpis = _indeks_odmian().get(goly) if goly else None
        if wpis is not None:
            regula = _regula_z_wpisu(wpis)
            return replace(regula, category_id=goly)

    # 3. słowa kluczowe (najdłuższe najpierw, żeby "MIESZKANIOWA
    #    WIELORODZINNA" wygrało z samym "MIESZKANIOWA")
    for wpis in sorted(KATALOG.values(),
                       key=lambda w: -max((len(s) for s in w["slowa"]),
                                          default=0)):
        for slowo in wpis["slowa"]:
            klucz = PlanSymbologyMatcher.normalize_string(slowo)
            if not klucz:
                continue
            if klucz == nazwa or f"_{klucz}_" in f"_{nazwa}_":
                return _regula_z_wpisu(wpis)
    return None


class PlanSymbologyMatcher:
    """Dopasowuje styl do nazwy warstwy i jej atrybutów."""

    @staticmethod
    def normalize_string(val: str) -> str:
        """Sprowadza nazwę do postaci porównywalnej: WIELKIE LITERY,
        bez ogonków, bez przedrostków typu 'PL_' i końcówek '_POLYGON'."""
        if not val:
            return ""
        s = _bez_ogonkow(str(val).strip()).upper()
        s = re.sub(
            r"^(\d+[\._-]*)?(MPZP_|PLANU_|PLAN_|POG_|WARSTWA_|LAYER_)",
            "", s, flags=re.IGNORECASE)
        s = re.sub(
            r"(_POLYGON|_POLIGON|_LINESTRING|_LINIA|_LINE|_PUNKT|"
            r"_POINT|_TEXT|_TEKST|_TABLE)$", "", s, flags=re.IGNORECASE)
        s = re.sub(r"[^A-Z0-9]+", "_", s)
        return s.strip("_")

    @classmethod
    def match_rule(cls, layer_name: str, scale: str = "1000",
                   attributes: Optional[Dict[str, Any]] = None,
                   plan_type: Optional[str] = None) -> PlanStyleRule:
        """
        Zwraca regułę stylu dla warstwy. Gdy nic nie pasuje, oddaje
        neutralny styl (szare wypełnienie), żeby warstwa i tak była
        widoczna i podpisana.
        """
        regula = match_official_rule(
            layer_name, plan_type or detect_plan_type(layer_name)
            or RODZAJ_MPZP)
        if regula is not None:
            return regula

        # próba po atrybutach (np. kolumna SYMBOL / PRZEZNACZENIE)
        if attributes:
            pola = ("SYMBOL", "PRZEZNACZENIE", "OZNACZENIE", "STREFA",
                    "FUNKCJA", "LAYER_NAME", "WARSTWA")
            for klucz, wartosc in attributes.items():
                if str(klucz).upper() in pola and wartosc:
                    regula = match_official_rule(str(wartosc),
                                                 plan_type or RODZAJ_MPZP)
                    if regula is not None:
                        return regula

        return PlanStyleRule(
            category_id="NIEROZPOZNANA",
            display_name=layer_name or "Warstwa",
            fill_color="#E0E0E0",
            fill_opacity=0.5,
            stroke_color="#4D4D4D",
            stroke_width=0.35,
            keywords=[],
            ust_grup_adi=GRUPA_NIEROZPOZNANE,
            alt_grup_adi=layer_name or "Warstwa",
        )


# =============================================================================
#  Budowanie symboli QGIS
#  Używamy słownikowego API (createSimple), bo jest odporne na różnice
#  między QGIS-em na Qt5 i Qt6 — żadnych enumów.
# =============================================================================

def _styl_kreski(rule: PlanStyleRule) -> str:
    return "dash" if rule.dash_pattern else "solid"


def create_qgis_fill_symbol(rule: PlanStyleRule) -> Any:
    """Symbol powierzchniowy: wypełnienie + obrys + ewentualne
    kreskowanie (zgodnie z katalogiem)."""
    from qgis.core import (QgsFillSymbol, QgsLinePatternFillSymbolLayer,
                           QgsLineSymbol)

    ma_wypelnienie = rule.fill_opacity > 0
    symbol = QgsFillSymbol.createSimple({
        "color": rule.fill_color if ma_wypelnienie else "0,0,0,0",
        "style": "solid" if ma_wypelnienie else "no",
        "outline_color": rule.stroke_color,
        "outline_width": str(max(rule.stroke_width, 0.1)),
        "outline_style": _styl_kreski(rule),
    })

    if rule.hatch_pattern:
        katy = [rule.hatch_angle]
        if rule.hatch_pattern == "krzyzowe":
            katy = [45.0, 135.0]
        for kat in katy:
            warstwa = QgsLinePatternFillSymbolLayer()
            warstwa.setLineAngle(kat)
            warstwa.setDistance(rule.hatch_distance)
            warstwa.setLineWidth(0.4)
            linia = QgsLineSymbol.createSimple({
                "color": rule.hatch_color or rule.stroke_color,
                "width": "0.4",
            })
            warstwa.setSubSymbol(linia)
            symbol.appendSymbolLayer(warstwa)
    return symbol


def create_qgis_line_symbol(rule: PlanStyleRule) -> Any:
    """Symbol liniowy (granice, sieci, linie zabudowy)."""
    from qgis.core import QgsLineSymbol

    ustawienia = {
        "color": rule.stroke_color,
        "width": str(max(rule.stroke_width, 0.1)),
        "line_style": _styl_kreski(rule),
    }
    if rule.dash_pattern:
        ustawienia["use_custom_dash"] = "1"
        ustawienia["customdash"] = ";".join(
            str(x) for x in rule.dash_pattern)
    return QgsLineSymbol.createSimple(ustawienia)


def create_qgis_marker_symbol(rule: PlanStyleRule,
                              text_anchor: bool = False) -> Any:
    """Symbol punktowy. Gdy punkt niesie tekst (etykietę), rysujemy
    tylko malutką kropkę-kotwicę, żeby nie zasłaniać napisu."""
    from qgis.core import QgsMarkerSymbol

    return QgsMarkerSymbol.createSimple({
        "name": rule.marker_shape or "circle",
        "color": rule.stroke_color if text_anchor else rule.fill_color,
        "outline_color": rule.stroke_color,
        "outline_width": "0.2",
        "size": "0.8" if text_anchor else "2.0",
    })


def pick_label_field(qgis_layer: Any) -> Optional[str]:
    """Wybiera pole, z którego robimy etykiety (napisy na mapie)."""
    kandydaci = ("label", "etykieta", "name", "nazwa", "text", "tekst",
                 "SYMBOL", "OZNACZENIE", "PRZEZNACZENIE", "layer_name")
    try:
        nazwy = [f.name() for f in qgis_layer.fields()]
    except Exception:
        return None
    for kandydat in kandydaci:
        for nazwa in nazwy:
            if nazwa.lower() == kandydat.lower():
                # pole ma sens tylko wtedy, gdy cokolwiek w nim jest
                try:
                    wartosci = qgis_layer.uniqueValues(
                        nazwy.index(nazwa), 5)
                    if any(str(w).strip() for w in wartosci
                           if w is not None):
                        return nazwa
                except Exception:
                    return nazwa
    return None


def apply_plan_symbology(qgis_layer: Any, plan_scale: str = "1:1000",
                         override_rule: Optional[PlanStyleRule] = None,
                         plan_type: str = "AUTO",
                         source_name: Optional[str] = None) -> bool:
    """
    Nadaje warstwie gotowy styl (kolor, obrys, kreskowanie, etykiety)
    zgodny z polskimi oznaczeniami. Zwraca True, gdy się udało.
    """
    nazwa_warstwy = qgis_layer.name() if hasattr(qgis_layer, "name") else ""
    if plan_type not in RODZAJE:
        plan_type = (detect_plan_type(source_name)
                     or detect_plan_type(nazwa_warstwy)
                     or RODZAJ_MPZP)

    rule = override_rule
    if rule is None and nazwa_warstwy:
        rule = PlanSymbologyMatcher.match_rule(
            nazwa_warstwy, scale=plan_scale, plan_type=plan_type)
    if rule is None:
        return False

    try:
        from qgis.core import (QgsSingleSymbolRenderer,
                               QgsPalLayerSettings,
                               QgsVectorLayerSimpleLabeling,
                               QgsTextFormat, QgsTextBufferSettings)
        from qgis.PyQt.QtGui import QColor
    except ImportError:
        return False   # uruchomienie poza QGIS-em (np. w testach)

    if not hasattr(qgis_layer, "geometryType") \
            or not hasattr(qgis_layer, "setRenderer"):
        return False

    typ_geometrii = qgis_layer.geometryType()   # 0 punkt, 1 linia, 2 poligon
    pole_etykiety = pick_label_field(qgis_layer)
    kotwica_tekstu = typ_geometrii == 0 and pole_etykiety is not None

    try:
        if typ_geometrii == 2:
            symbol = create_qgis_fill_symbol(rule)
        elif typ_geometrii == 1:
            symbol = create_qgis_line_symbol(rule)
        else:
            symbol = create_qgis_marker_symbol(rule, kotwica_tekstu)
        qgis_layer.setRenderer(QgsSingleSymbolRenderer(symbol))
    except Exception:
        return False

    # etykiety — z białą otoczką, żeby były czytelne na każdym tle
    if pole_etykiety:
        try:
            ustawienia = QgsPalLayerSettings()
            ustawienia.fieldName = pole_etykiety
            ustawienia.enabled = True
            format_tekstu = QgsTextFormat()
            format_tekstu.setSize(8)
            format_tekstu.setColor(QColor("#1A1A1A"))
            otoczka = QgsTextBufferSettings()
            otoczka.setEnabled(True)
            otoczka.setSize(0.8)
            otoczka.setColor(QColor("#FFFFFF"))
            format_tekstu.setBuffer(otoczka)
            ustawienia.setFormat(format_tekstu)
            qgis_layer.setLabeling(
                QgsVectorLayerSimpleLabeling(ustawienia))
            qgis_layer.setLabelsEnabled(True)
        except Exception:
            pass   # brak etykiet to nie powód, żeby przerywać

    with_repaint = getattr(qgis_layer, "triggerRepaint", None)
    if callable(with_repaint):
        with_repaint()
    return True
