# Konwerter CAD na GIS

Wtyczka QGIS, która zamienia rysunki CAD i pliki wymiany danych na gotowe
warstwy QGIS — od razu pokolorowane zgodnie z polskimi przepisami
planistycznymi i geodezyjnymi.

**Autor wersji polskiej:** Grzegorz Górniak (gorniakgrzegorz@gmail.com)
**Licencja:** GPL-2.0-or-later
**Na bazie:** wtyczki zero2cadgis © Yusuf Eminoğlu — wykaz zmian
w pliku [ATRYBUCJA.md](ATRYBUCJA.md)

---

## Co potrafi

**Wczytuje:** AutoCAD DXF i DWG, Microstation DGN (także v8), GML
(w tym zbiory APP i dane INSPIRE), KML, KMZ, GeoJSON, CSV/TSV,
SpatiaLite/SQLite, GPX, geobazy ArcGIS `.gdb` i bazy MS Access.

**Zapisuje:** GeoPackage z całą symbolizacją, warstwy tymczasowe albo
podgląd na żywo bez konwersji.

**Eksportuje z QGIS:** DXF (powrót do CAD-a), GML 3.2 wraz z plikiem
schematu `.xsd`, KML i KMZ.

**Koloruje automatycznie** wg polskiego stanu prawnego:

| Rodzaj opracowania | Podstawa |
|---|---|
| MPZP — przeznaczenia terenów | rozporządzenie z 26 sierpnia 2003 r. (Dz.U. 2003 nr 164 poz. 1587, zał. 1) |
| Plan ogólny gminy — 13 stref | rozporządzenie z 8 grudnia 2023 r. (Dz.U. 2023 poz. 2758, zał. 2) — kolory RGB wprost z załącznika |
| GESUT — sieci uzbrojenia | rozporządzenie z 23 lipca 2021 r. (Dz.U. 2021 poz. 1385) |
| EGiB — działki, budynki, użytki | konwencje ewidencyjne |

**Rozpoznaje polskie układy współrzędnych** po samych współrzędnych:
PUWG 2000 (strefy 5, 6, 7, 8), PUWG 1992 i WGS 84.

## Instalacja

1. QGIS → Wtyczki → Zarządzanie wtyczkami…
2. Zakładka **Zainstaluj z pliku ZIP**
3. Wskaż `cad_to_gis.zip` → **Zainstaluj wtyczkę**
4. Na pasku narzędzi pojawi się przycisk **Konwerter CAD na GIS**

## Wymagania

QGIS 3.22 lub nowszy — i nic więcej. Żadnych dodatkowych programów,
kont ani kluczy API.

Rysunki DWG czyta wbudowany w QGIS sterownik CAD, który obsługuje
starsze zapisy (do R2000 włącznie). Nowszy plik DWG wystarczy zapisać
w CAD-zie jako **DXF** — ten format wtyczka obsługuje w całości, razem
z symbolizacją.

## Jak używać

1. Przeciągnij plik na panel wtyczki albo wskaż go przyciskiem.
2. Odznacz warstwy, których nie potrzebujesz.
3. Przy rysunkach CAD zostaw **Rozbij na osobne warstwy CAD** — każda
   warstwa rysunku stanie się osobną warstwą QGIS.
4. Ustaw układ współrzędnych i rodzaj opracowania (albo zostaw
   rozpoznawanie automatyczne).
5. Kliknij **KONWERTUJ DO GEOPACKAGE**.

Warstwy pomocnicze rysunku (ramki, opisy, tabelki) celowo nie dostają
przeznaczenia — lepiej puste pole niż zmyślone.

## Struktura

```
cad_to_gis/
├── metadata.txt          dane wtyczki dla QGIS
├── main_plugin.py        przycisk na pasku, otwieranie panelu
├── dialogs/dock.py       panel z zakładkami
└── core/
    ├── gis_engine.py     odczyt źródeł i zapis wyników
    ├── cad_engine.py     czyszczenie geometrii CAD, eksport DXF
    ├── katalog_pl.py     katalog polskich oznaczeń (72 pozycje)
    ├── symbology.py      dobór stylu do warstwy
    ├── schemat_pl.py     rozpoznawanie oznaczenia z nazwy warstwy
    ├── crs_detect.py     rozpoznawanie polskich układów współrzędnych
    ├── dgn_v8_reader.py  własny czytnik DGN v8
    └── msaccess_reader.py odczyt baz MS Access
```
