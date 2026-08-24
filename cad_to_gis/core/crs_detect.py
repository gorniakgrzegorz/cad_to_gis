# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-2.0-or-later
"""
ROZPOZNAWANIE UKŁADU WSPÓŁRZĘDNYCH — wersja polska.

Rysunki CAD prawie nigdy nie mówią wprost, w jakim układzie są zapisane.
Ten moduł zgaduje to po samych liczbach — po tym, jak wyglądają
współrzędne. W Polsce mamy szczęście: układy państwowe mają bardzo
charakterystyczne zakresy, więc rozpoznanie bywa pewne.

Co rozpoznajemy:
  • PUWG 2000 (EPSG:2176/2177/2178/2179) — strefy 5, 6, 7, 8; numer
    strefy widać wprost w pierwszej cyfrze współrzędnej wschodniej,
  • PUWG 1992 (EPSG:2180) — jeden pas na cały kraj, wartości 6-cyfrowe,
  • WGS 84 (EPSG:4326) — stopnie,
  • UTM 33N / 34N — sygnalizujemy, ale nie zgadujemy strefy.

Zasada nadrzędna: jeśli nie ma pewności, NIE zgadujemy. Cicho wpisany
zły układ przesuwa dane o dziesiątki kilometrów, a użytkownik dowiaduje
się o tym dopiero przy uzgodnieniach — lepiej zapytać.

© Grzegorz Górniak. Na bazie wtyczki zero2cadgis (GPL-2.0-or-later).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Tuple

# ── nazwy układów pokazywane użytkownikowi ────────────────────────────
NAZWY = {
    2176: "PUWG 2000 strefa 5 (południk 15°E)",
    2177: "PUWG 2000 strefa 6 (południk 18°E)",
    2178: "PUWG 2000 strefa 7 (południk 21°E)",
    2179: "PUWG 2000 strefa 8 (południk 24°E)",
    2180: "PUWG 1992 (cała Polska)",
    4326: "WGS 84 — współrzędne geograficzne",
    32633: "UTM strefa 33N (WGS 84)",
    32634: "UTM strefa 34N (WGS 84)",
}
LABELS = NAZWY   # zgodność z dawną nazwą stałej

# ── zakresy współrzędnych (metry) ─────────────────────────────────────
# PUWG 2000: północ ok. 5 400 000 - 6 120 000 dla całej Polski.
PUWG2000_POLNOC = (5_390_000.0, 6_130_000.0)
# wschód: pierwsza cyfra = numer strefy, dalej ok. 3xx xxx - 6xx xxx
PUWG2000_STREFY = {
    5: (2176, 5_380_000.0, 5_720_000.0),
    6: (2177, 6_330_000.0, 6_690_000.0),
    7: (2178, 7_280_000.0, 7_650_000.0),
    8: (2179, 8_230_000.0, 8_610_000.0),
}
# PUWG 1992: wschód ok. 171-862 km, północ ok. 133-795 km.
PUWG1992_WSCHOD = (140_000.0, 890_000.0)
PUWG1992_POLNOC = (100_000.0, 820_000.0)
# UTM w zasięgu Polski: wschód 6-cyfrowy, północ jak w PUWG 2000.
UTM_WSCHOD = (180_000.0, 900_000.0)
UTM_POLNOC = (5_390_000.0, 6_130_000.0)

# słowa, które w opisie rysunku wskazują układ wprost
SLOWA_UKLADOW = (
    ("2000/15", 2176), ("2000 STREFA 5", 2176), ("EPSG:2176", 2176),
    ("2000/18", 2177), ("2000 STREFA 6", 2177), ("EPSG:2177", 2177),
    ("2000/21", 2178), ("2000 STREFA 7", 2178), ("EPSG:2178", 2178),
    ("2000/24", 2179), ("2000 STREFA 8", 2179), ("EPSG:2179", 2179),
    ("1992", 2180), ("PUWG92", 2180), ("EPSG:2180", 2180),
    ("WGS84", 4326), ("WGS 84", 4326), ("EPSG:4326", 4326),
    ("UTM 33", 32633), ("UTM33", 32633), ("EPSG:32633", 32633),
    ("UTM 34", 32634), ("UTM34", 32634), ("EPSG:32634", 32634),
)


@dataclass(frozen=True)
class CrsDetection:
    """Co ustaliliśmy, jak bardzo jesteśmy pewni i dlaczego."""

    epsg: Optional[int] = None
    label: str = ""
    confidence: str = "none"          # "high" | "medium" | "none"
    reason: str = "Rysunek nie zdradza, w jakim jest układzie."

    @property
    def authid(self) -> str:
        return f"EPSG:{self.epsg}" if self.epsg else ""

    def __bool__(self) -> bool:
        return self.epsg is not None


def _wynik(epsg: int, pewnosc: str, powod: str) -> CrsDetection:
    return CrsDetection(epsg, NAZWY.get(epsg, f"EPSG:{epsg}"),
                        pewnosc, powod)


def _probka(coordinates: Optional[Iterable[Tuple[float, float]]],
            ile: int = 40) -> tuple[Optional[float], Optional[float]]:
    """Bierze medianę z kilkudziesięciu pierwszych punktów — pojedynczy
    punkt bywa pomyłką w rysunku, mediana nie da się nabrać."""
    if coordinates is None:
        return None, None
    xs, ys = [], []
    for para in coordinates:
        try:
            x, y = float(para[0]), float(para[1])
        except (TypeError, ValueError, IndexError):
            continue
        if x == 0 and y == 0:
            continue      # punkt "zerowy" to zwykle śmieć w rysunku
        xs.append(x)
        ys.append(y)
        if len(xs) >= ile:
            break
    if not xs:
        return None, None
    xs.sort()
    ys.sort()
    return xs[len(xs) // 2], ys[len(ys) // 2]


def _w(wartosc: float, zakres: tuple[float, float]) -> bool:
    return zakres[0] <= wartosc <= zakres[1]


def _z_opisu(tekst: Optional[str]) -> Optional[int]:
    """Szuka nazwy układu wprost w opisie rysunku."""
    if not tekst:
        return None
    duze = str(tekst).upper().replace("_", " ")
    for slowo, epsg in SLOWA_UKLADOW:
        if slowo in duze:
            return epsg
    return None


def detect_crs(
    projection_text: Optional[str] = None,
    coordinates: Optional[Iterable[Tuple[float, float]]] = None,
) -> CrsDetection:
    """
    Rozpoznaje układ współrzędnych z opisu rysunku i z samych liczb.

    ``coordinates`` to dowolny ciąg par ``(x, y)`` — czytamy tylko próbkę.
    Zwracamy EPSG tylko wtedy, gdy naprawdę pasuje; przy wątpliwościach
    oddajemy pusty wynik i decyzję zostawiamy użytkownikowi.
    """
    z_opisu = _z_opisu(projection_text)
    a, b = _probka(coordinates)

    if a is None or b is None:
        if z_opisu:
            return _wynik(z_opisu, "medium",
                          f"Układ odczytany z opisu rysunku "
                          f"({NAZWY.get(z_opisu, z_opisu)}).")
        return CrsDetection()

    # ── 1. stopnie → WGS 84 ────────────────────────────────────────────
    if abs(a) <= 180.0 and abs(b) <= 90.0:
        return _wynik(4326, "high",
                      "Współrzędne mieszczą się w zakresie stopni, więc "
                      "rysunek jest w układzie geograficznym WGS 84.")

    # sprawdzamy obie kolejności — pliki CAD bywają zapisane i tak, i tak
    for wschod, polnoc, uwaga in ((a, b, ""),
                                  (b, a, " (X i Y zapisane odwrotnie)")):
        # ── 2. PUWG 2000 — numer strefy wprost w pierwszej cyfrze ──────
        strefa = int(wschod // 1_000_000)
        if strefa in PUWG2000_STREFY and _w(polnoc, PUWG2000_POLNOC):
            epsg, dol, gora = PUWG2000_STREFY[strefa]
            if _w(wschod, (dol, gora)):
                return _wynik(
                    epsg, "high",
                    f"Współrzędna wschodnia zaczyna się od {strefa}, "
                    f"a północna mieści się w zakresie dla Polski — to "
                    f"{NAZWY[epsg]}{uwaga}.")

        # ── 3. UTM 33N / 34N — sygnalizujemy, ale nie zgadujemy ────────
        if _w(wschod, UTM_WSCHOD) and _w(polnoc, UTM_POLNOC):
            return CrsDetection(
                None, "", "none",
                "Współrzędne wyglądają na UTM w zasięgu Polski (strefa "
                "33N albo 34N), ale z samych liczb nie da się rozstrzygnąć "
                "która. Wskaż układ ręcznie: EPSG:32633 dla zachodniej "
                "części kraju, EPSG:32634 dla wschodniej.")

        # ── 4. PUWG 1992 ───────────────────────────────────────────────
        if _w(wschod, PUWG1992_WSCHOD) and _w(polnoc, PUWG1992_POLNOC):
            return _wynik(
                2180, "high",
                f"Sześciocyfrowe współrzędne w zakresie właściwym dla "
                f"Polski — to PUWG 1992 (EPSG:2180){uwaga}.")

    # ── 5. nic nie pasuje ──────────────────────────────────────────────
    if z_opisu:
        return _wynik(
            z_opisu, "medium",
            f"Liczby nie pasują do żadnego polskiego układu, ale opis "
            f"rysunku wskazuje na {NAZWY.get(z_opisu, z_opisu)}. "
            f"Warto to sprawdzić.")

    return CrsDetection(
        None, "", "none",
        f"Współrzędne ({a:.0f}, {b:.0f}) nie pasują do żadnego z polskich "
        f"układów państwowych. Wskaż układ ręcznie — zgadywanie "
        f"przesunęłoby dane o dziesiątki kilometrów.")


def opis_wykrycia(det: CrsDetection) -> str:
    """Jedno zdanie do pokazania w oknie wtyczki."""
    if not det:
        return det.reason
    pewnosc = {"high": "pewne", "medium": "prawdopodobne"}.get(
        det.confidence, "niepewne")
    return f"{det.label} ({det.authid}) — rozpoznanie {pewnosc}. {det.reason}"
