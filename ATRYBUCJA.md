# Atrybucja i informacja o zmianach

Wtyczka **Konwerter CAD na GIS** jest zmodyfikowaną wersją (forkiem)
wtyczki **zero2cadgis**.

## Utwór pierwotny

- **Nazwa:** zero2cadgis (02CadGis)
- **Autor:** Yusuf Eminoğlu
- **Licencja:** GNU General Public License v2.0 lub późniejsza
  (GPL-2.0-or-later)
- **Copyright:** © 2026 Yusuf Eminoğlu

## Wersja niniejsza

- **Nazwa:** Konwerter CAD na GIS
- **Autor zmian:** Grzegorz Górniak <gorniakgrzegorz@gmail.com>
- **Copyright zmian:** © 2026 Grzegorz Górniak
- **Licencja:** GPL-2.0-or-later (bez zmian — licencja pierwotna
  wymaga zachowania tych samych warunków)

## Wykaz zmian względem utworu pierwotnego

Zgodnie z art. 2 lit. a) licencji GPL-2.0 poniżej wymieniono
wprowadzone zmiany.

### Interfejs i dokumentacja
- cały interfejs, komunikaty, podpowiedzi i instrukcja przetłumaczone
  na język polski i napisane od nowa pod polską praktykę planistyczną
  i geodezyjną,
- nowa identyfikacja graficzna (ikony, kolor wiodący #00bde7),
  podpis autora wersji polskiej.

### Symbolizacja
- **usunięto** tureckie katalogi symbolizacji e-Plan / MPYY wraz
  z rastrowymi kafelkami kreskowań (ok. 6,5 MB),
- **dodano** moduł `core/katalog_pl.py` z polskim katalogiem oznaczeń
  (72 pozycje): przeznaczenia MPZP wg rozporządzenia z 26 sierpnia
  2003 r., strefy planu ogólnego wraz z wartościami RGB wprost
  z rozporządzenia z 8 grudnia 2023 r. (Dz.U. 2023 poz. 2758, zał. 2),
  barwy sieci GESUT wg rozporządzenia z 23 lipca 2021 r.
  (Dz.U. 2021 poz. 1385) oraz warstwy EGiB,
- **napisano od nowa** `core/symbology.py` — kreskowania rysowane
  wektorowo przez QGIS zamiast kafelków rastrowych,
- **dodano** `core/schemat_pl.py` — rozpoznawanie oznaczenia
  z nazwy warstwy rysunku i polskie kolumny opisowe.

### Układy współrzędnych
- **napisano od nowa** `core/crs_detect.py`: rozpoznawanie tureckich
  układów TUREF/ITRF zastąpiono rozpoznawaniem polskich układów
  państwowych (PUWG 2000 strefy 5-8, PUWG 1992, WGS 84),
- domyślny układ awaryjny zmieniono z EPSG:5253 (Turcja)
  na EPSG:2180 (PUWG 1992).

### Zakres funkcji
- **usunięto** cały moduł obsługi rysunków Netcad NCZ/NCA
  (`core/netcad_parser.py`, pakiet `core/ncz_engine/`, zakładka
  importu) — format nieużywany w Polsce. Tym samym przestała
  obowiązywać atrybucja dla *Jeomatik NCZ Reader* (© Erdinç Örsan
  Ünal), z którego pochodziły fragmenty tego modułu,
- **usunięto** zależność od zewnętrznego programu ODA File Converter
  oraz od `dwg2dxf` — wtyczka nie uruchamia żadnych programów spoza
  QGIS-a,
- **dodano** eksport do GML 3.2 wraz z plikiem schematu `.xsd`,
- **dodano** ustawienia GDAL poprawiające odczyt polskich plików GML
  (zbiory APP, dane INSPIRE).

### Poprawki techniczne
- naprawiono f-string działający wyłącznie w Pythonie 3.12+
  (`dialogs/dock.py`), przez który wtyczka nie wczytywała się
  na starszych wydaniach QGIS,
- wszystkie wyliczenia Qt zapisano w postaci pełnej (zgodność z Qt6),
- rozmiar paczki zmniejszony z 7,2 MB do ok. 0,2 MB.

## Tekst licencji

Pełny tekst GNU GPL v2 znajduje się w pliku `LICENSE`.

Program rozpowszechniany jest w nadziei, że okaże się przydatny,
ale BEZ JAKIEJKOLWIEK GWARANCJI, nawet domyślnej gwarancji
PRZYDATNOŚCI HANDLOWEJ albo PRZYDATNOŚCI DO OKREŚLONYCH ZASTOSOWAŃ.
