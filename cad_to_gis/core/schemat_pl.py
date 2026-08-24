# -*- coding: utf-8 -*-
"""
SCHEMAT POLSKICH OZNACZEŃ — rozpoznawanie, co dana warstwa CAD znaczy.

Do czego to służy: rysunek CAD ma warstwy nazwane po ludzku ("MN",
"3_MW", "linia rozgraniczajaca", "wodociag"). Ten moduł mówi, jakie
polskie oznaczenie za tym stoi (symbol, pełna nazwa przeznaczenia,
grupa tematyczna) — dzięki temu wtyczka może wpisać te informacje do
tabeli atrybutów i pogrupować warstwy w drzewie QGIS.

© Grzegorz Górniak
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from .katalog_pl import KATALOG, GRUPA_NIEROZPOZNANE

_MAPA_OGONKOW = str.maketrans({
    "Ą": "A", "Ć": "C", "Ę": "E", "Ł": "L", "Ń": "N", "Ó": "O",
    "Ś": "S", "Ź": "Z", "Ż": "Z",
    "ą": "A", "ć": "C", "ę": "E", "ł": "L", "ń": "N", "ó": "O",
    "ś": "S", "ź": "Z", "ż": "Z",
})


@dataclass(frozen=True)
class Oznaczenie:
    """Jedno rozpoznane oznaczenie planistyczne lub geodezyjne."""

    symbol: str          # np. "MN"
    nazwa: str           # np. "Tereny zabudowy mieszkaniowej jednorodzinnej"
    grupa: str           # np. "MPZP — TERENY ZABUDOWY MIESZKANIOWEJ"
    rodzaj: str          # MPZP / PLAN_OGOLNY / GESUT / EGIB
    geometria: str       # poligon / linia / punkt
    dopasowanie: str     # "symbol" albo "slowa"


def _uprosc(nazwa: Optional[str]) -> str:
    """Sprowadza nazwę warstwy do porównywalnej postaci."""
    if not nazwa:
        return ""
    tekst = str(nazwa).strip().translate(_MAPA_OGONKOW).upper()
    return re.sub(r"[^A-Z0-9]+", "_", tekst).strip("_")


def _zbuduj_indeks_symboli() -> dict:
    """Krótkie, "symbolowe" słowa kluczowe (MN, KDL, KDZ, SW...) w jednym
    słowniku — żeby oznaczenie z numerem porządkowym typu "1KDL" też
    było rozpoznawane."""
    indeks = {}
    for wpis in KATALOG.values():
        for slowo in wpis.get("slowa", ()):
            klucz = _uprosc(slowo).replace("_", "")
            # symbolem nazywamy krótki, wyłącznie literowy ciąg
            if 1 <= len(klucz) <= 5 and klucz.isalpha() \
                    and klucz not in KATALOG:
                indeks.setdefault(klucz, wpis)
    return indeks


_INDEKS_SYMBOLI = _zbuduj_indeks_symboli()


def znajdz_oznaczenie(nazwa: Optional[str]) -> Optional[Oznaczenie]:
    """
    Rozpoznaje oznaczenie po nazwie warstwy. Zwraca None, gdy nazwa
    nic nie mówi (np. warstwa pomocnicza CAD "ramka", "opis") — wtedy
    lepiej zostawić puste pola niż wpisać zmyślone.
    """
    klucz = _uprosc(nazwa)
    if not klucz:
        return None
    czlony = [c for c in klucz.split("_") if c]

    # 1. symbol wprost w nazwie (z numerem porządkowym lub bez)
    for czlon in czlony:
        goly = re.sub(r"^\d+|\d+$", "", czlon)
        if goly and goly in KATALOG:
            wpis = KATALOG[goly]
            return Oznaczenie(
                symbol=wpis["symbol"], nazwa=wpis["etykieta"],
                grupa=wpis["grupa"], rodzaj=wpis["rodzaj"],
                geometria=wpis["geometria"], dopasowanie="symbol")

    # 1b. odmiany symbolu wymienione w katalogu jako słowa kluczowe
    #     (np. "1KDL" -> KDL -> wpis KD, "2KDZ" -> KDZ)
    for czlon in czlony:
        goly = re.sub(r"^\d+|\d+$", "", czlon)
        wpis = _INDEKS_SYMBOLI.get(goly) if goly else None
        if wpis is not None:
            return Oznaczenie(
                symbol=goly, nazwa=wpis["etykieta"],
                grupa=wpis["grupa"], rodzaj=wpis["rodzaj"],
                geometria=wpis["geometria"], dopasowanie="symbol")

    # 2. słowa kluczowe (najdłuższe najpierw — precyzyjniejsze wygrywa)
    for wpis in sorted(KATALOG.values(),
                       key=lambda w: -max((len(s) for s in w["slowa"]),
                                          default=0)):
        for slowo in wpis["slowa"]:
            klucz_slowa = _uprosc(slowo)
            if not klucz_slowa:
                continue
            if klucz_slowa == klucz or f"_{klucz_slowa}_" in f"_{klucz}_":
                return Oznaczenie(
                    symbol=wpis["symbol"], nazwa=wpis["etykieta"],
                    grupa=wpis["grupa"], rodzaj=wpis["rodzaj"],
                    geometria=wpis["geometria"], dopasowanie="slowa")
    return None


def grupa_warstwy(nazwa: Optional[str]) -> str:
    """
    Grupa tematyczna warstwy — po niej wtyczka układa drzewo warstw
    w QGIS. Zawsze zwraca jakąś nazwę: rozpoznaną albo "POZOSTAŁE
    WARSTWY".
    """
    oznaczenie = znajdz_oznaczenie(nazwa)
    return oznaczenie.grupa if oznaczenie else GRUPA_NIEROZPOZNANE
