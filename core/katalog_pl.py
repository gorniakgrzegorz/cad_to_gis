# -*- coding: utf-8 -*-
"""
KATALOG POLSKIEJ SYMBOLIZACJI PLANISTYCZNEJ I GEODEZYJNEJ
=========================================================

Ten plik to "słownik kolorów" wtyczki: mówi, jakim kolorem i jaką kreską
narysować warstwę o danej nazwie (np. "MN", "3_MW", "ZL", "sieć wodociągowa").

Podstawy prawne kolorów:

1. PLAN OGÓLNY GMINY — rozporządzenie Ministra Rozwoju i Technologii
   z 8 grudnia 2023 r. (Dz.U. 2023 poz. 2758), załącznik nr 2.
   Kolory stref planistycznych podane są tam WPROST w RGB — i takie
   dokładnie wartości znajdziesz poniżej.

2. MIEJSCOWY PLAN (MPZP) — rozporządzenie Ministra Infrastruktury
   z 26 sierpnia 2003 r. w sprawie wymaganego zakresu projektu MPZP
   (Dz.U. nr 164 poz. 1587), załącznik nr 1. Uwaga: rozporządzenie
   opisuje barwy SŁOWNIE ("jasnobrązowy", "czerwony", "kreskowanie
   żółto-czerwone"), bez wartości RGB. Kolory poniżej to wierne,
   powszechnie stosowane odwzorowanie tych opisów.

3. SIECI UZBROJENIA TERENU (GESUT) i mapa zasadnicza — rozporządzenie
   Ministra Rozwoju, Pracy i Technologii z 23 lipca 2021 r. w sprawie
   BDOT500, mapy zasadniczej i GESUT (Dz.U. 2021 poz. 1385):
   wodociąg — niebieski, kanalizacja — brązowy, gaz — żółtooliwkowy,
   elektroenergetyka — czerwony, ciepłownictwo — fioletowy/magenta,
   telekomunikacja — pomarańczowy.

4. EGiB — działki, budynki i użytki rysowane w konwencji mapy
   ewidencyjnej (rozporządzenie w sprawie EGiB).

© Grzegorz Górniak
"""

# rodzaje dokumentów rozpoznawane przez wtyczkę
RODZAJ_PLAN_OGOLNY = "PLAN_OGOLNY"
RODZAJ_MPZP = "MPZP"
RODZAJ_GESUT = "GESUT"
RODZAJ_EGIB = "EGIB"

# grupa dla warstw, których nie udało się rozpoznać
GRUPA_NIEROZPOZNANE = "POZOSTAŁE WARSTWY"


def _wpis(symbol, etykieta, grupa, rodzaj, *, wypelnienie=None,
          obrys="#333333", szerokosc=0.4, kreskowanie=None,
          kolor_kreskowania=None, kreska=None, geometria="poligon",
          slowa=()):
    """Pomocnik: buduje jeden wpis katalogu (żeby nie powtarzać kluczy)."""
    return {
        "symbol": symbol,
        "etykieta": etykieta,
        "grupa": grupa,
        "rodzaj": rodzaj,
        "wypelnienie": wypelnienie,
        "obrys": obrys,
        "szerokosc": szerokosc,
        "kreskowanie": kreskowanie,
        "kolor_kreskowania": kolor_kreskowania,
        "kreska": list(kreska) if kreska else None,
        "geometria": geometria,
        "slowa": [s.upper() for s in slowa],
    }


# =============================================================================
#  1. PLAN OGÓLNY GMINY — strefy planistyczne
#     (Dz.U. 2023 poz. 2758, zał. nr 2 — kolory RGB wprost z rozporządzenia)
# =============================================================================

GRUPA_STREFY = "PLAN OGÓLNY — STREFY PLANISTYCZNE"
GRUPA_OBSZARY_PO = "PLAN OGÓLNY — OBSZARY"

STREFY_PLANISTYCZNE = [
    _wpis("SW", "Strefa wielofunkcyjna z zabudową mieszkaniową wielorodzinną",
          GRUPA_STREFY, RODZAJ_PLAN_OGOLNY, wypelnienie="#B89578",
          obrys="#7A5C42", szerokosc=0.5,
          slowa=("SW", "WIELOFUNKCYJNA WIELORODZINNA",
                 "STREFA WIELORODZINNA")),
    _wpis("SJ", "Strefa wielofunkcyjna z zabudową mieszkaniową jednorodzinną",
          GRUPA_STREFY, RODZAJ_PLAN_OGOLNY, wypelnienie="#EEC97A",
          obrys="#A6862F", szerokosc=0.5,
          slowa=("SJ", "WIELOFUNKCYJNA JEDNORODZINNA",
                 "STREFA JEDNORODZINNA")),
    _wpis("SZ", "Strefa wielofunkcyjna z zabudową zagrodową",
          GRUPA_STREFY, RODZAJ_PLAN_OGOLNY, wypelnienie="#FEE88B",
          obrys="#B39B33", szerokosc=0.5,
          slowa=("SZ", "ZAGRODOWA", "STREFA ZAGRODOWA")),
    _wpis("SU", "Strefa usługowa", GRUPA_STREFY, RODZAJ_PLAN_OGOLNY,
          wypelnienie="#FFAA99", obrys="#B3564A", szerokosc=0.5,
          slowa=("SU", "STREFA USLUGOWA")),
    _wpis("SH", "Strefa handlu wielkopowierzchniowego",
          GRUPA_STREFY, RODZAJ_PLAN_OGOLNY, wypelnienie="#FF93D3",
          obrys="#B34C90", szerokosc=0.5,
          slowa=("SH", "HANDLU WIELKOPOWIERZCHNIOWEGO",
                 "WIELKOPOWIERZCHNIOWY")),
    _wpis("SP", "Strefa gospodarcza", GRUPA_STREFY, RODZAJ_PLAN_OGOLNY,
          wypelnienie="#C590DE", obrys="#7A4C99", szerokosc=0.5,
          slowa=("SP", "STREFA GOSPODARCZA")),
    _wpis("SR", "Strefa produkcji rolniczej", GRUPA_STREFY,
          RODZAJ_PLAN_OGOLNY, wypelnienie="#FEEF64", obrys="#B0A32C",
          szerokosc=0.5,
          slowa=("SR", "PRODUKCJI ROLNICZEJ", "STREFA ROLNICZA")),
    _wpis("SI", "Strefa infrastrukturalna", GRUPA_STREFY,
          RODZAJ_PLAN_OGOLNY, wypelnienie="#CCCCCC", obrys="#7A7A7A",
          szerokosc=0.5,
          slowa=("SI", "STREFA INFRASTRUKTURALNA")),
    _wpis("SN", "Strefa zieleni i rekreacji", GRUPA_STREFY,
          RODZAJ_PLAN_OGOLNY, wypelnienie="#BBF58B", obrys="#5E9E3C",
          szerokosc=0.5,
          slowa=("SN", "ZIELENI I REKREACJI", "STREFA ZIELENI")),
    _wpis("SC", "Strefa cmentarzy", GRUPA_STREFY, RODZAJ_PLAN_OGOLNY,
          wypelnienie="#94D4C4", obrys="#4C8B7A", szerokosc=0.5,
          slowa=("SC", "STREFA CMENTARZY")),
    _wpis("SG", "Strefa górnictwa", GRUPA_STREFY, RODZAJ_PLAN_OGOLNY,
          wypelnienie="#FCCCFF", obrys="#A66BA8", szerokosc=0.5,
          slowa=("SG", "STREFA GORNICTWA", "GORNICZA")),
    _wpis("SO", "Strefa otwarta", GRUPA_STREFY, RODZAJ_PLAN_OGOLNY,
          wypelnienie="#F0FFCC", obrys="#9EAD70", szerokosc=0.5,
          slowa=("SO", "STREFA OTWARTA")),
    _wpis("SK", "Strefa komunikacyjna", GRUPA_STREFY, RODZAJ_PLAN_OGOLNY,
          wypelnienie="#F2F2F2", obrys="#8C8C8C", szerokosc=0.5,
          slowa=("SK", "STREFA KOMUNIKACYJNA")),
]

# obszary wyznaczane w planie ogólnym — rysowane linią przerywaną
# i kreskowaniem w kolorze RGB(83,83,83) = #535353
OBSZARY_PLANU_OGOLNEGO = [
    _wpis("POG", "Obszar objęty planem ogólnym gminy", GRUPA_OBSZARY_PO,
          RODZAJ_PLAN_OGOLNY, obrys="#535353", szerokosc=3.0,
          kreska=(14.0, 10.0),
          slowa=("POG", "GRANICA PLANU OGOLNEGO", "OBSZAR PLANU OGOLNEGO")),
    _wpis("OSD", "Obszar standardów dostępności infrastruktury społecznej",
          GRUPA_OBSZARY_PO, RODZAJ_PLAN_OGOLNY, obrys="#535353",
          szerokosc=0.4, kreska=(2.0, 1.0), kreskowanie="ukosne_wstecz",
          kolor_kreskowania="#535353",
          slowa=("OSD", "STANDARDOW DOSTEPNOSCI")),
    _wpis("OZS", "Obszar zabudowy śródmiejskiej", GRUPA_OBSZARY_PO,
          RODZAJ_PLAN_OGOLNY, obrys="#535353", szerokosc=0.4,
          kreska=(2.0, 1.0), kreskowanie="poziome",
          kolor_kreskowania="#535353",
          slowa=("OZS", "ZABUDOWY SRODMIEJSKIEJ", "SRODMIEJSKA")),
    _wpis("OUZ", "Obszar uzupełnienia zabudowy", GRUPA_OBSZARY_PO,
          RODZAJ_PLAN_OGOLNY, obrys="#535353", szerokosc=0.4,
          kreska=(2.0, 1.0), kreskowanie="pionowe",
          kolor_kreskowania="#535353",
          slowa=("OUZ", "UZUPELNIENIA ZABUDOWY")),
]


# =============================================================================
#  2. MIEJSCOWY PLAN (MPZP) — przeznaczenia terenów
#     (Dz.U. 2003 nr 164 poz. 1587, zał. nr 1 — barwy opisane słownie)
# =============================================================================

GRUPA_MIESZKANIOWE = "MPZP — TERENY ZABUDOWY MIESZKANIOWEJ"
GRUPA_USLUGOWE = "MPZP — TERENY ZABUDOWY USŁUGOWEJ"
GRUPA_ROLNICZE = "MPZP — TERENY ROLNICZE"
GRUPA_PRODUKCYJNE = "MPZP — TERENY TECHNICZNO-PRODUKCYJNE"
GRUPA_ZIELEN_WODY = "MPZP — TERENY ZIELENI I WÓD"
GRUPA_KOMUNIKACJA = "MPZP — TERENY KOMUNIKACJI"
GRUPA_INFRASTRUKTURA = "MPZP — INFRASTRUKTURA TECHNICZNA"
GRUPA_RYSUNEK = "MPZP — ELEMENTY RYSUNKU PLANU"

PRZEZNACZENIA_MPZP = [
    # --- zabudowa mieszkaniowa ---
    _wpis("MN", "Tereny zabudowy mieszkaniowej jednorodzinnej",
          GRUPA_MIESZKANIOWE, RODZAJ_MPZP, wypelnienie="#F2CE9E",
          obrys="#8C6239", szerokosc=0.5,
          slowa=("MN", "MIESZKANIOWA JEDNORODZINNA", "JEDNORODZINNA")),
    _wpis("MW", "Tereny zabudowy mieszkaniowej wielorodzinnej",
          GRUPA_MIESZKANIOWE, RODZAJ_MPZP, wypelnienie="#B5651D",
          obrys="#6B3D11", szerokosc=0.5,
          slowa=("MW", "MIESZKANIOWA WIELORODZINNA", "WIELORODZINNA")),
    _wpis("MU", "Tereny zabudowy mieszkaniowo-usługowej",
          GRUPA_MIESZKANIOWE, RODZAJ_MPZP, wypelnienie="#E8A87C",
          obrys="#8C5A32", szerokosc=0.5,
          slowa=("MU", "MIESZKANIOWO USLUGOWA", "MN/U", "MW/U")),
    # --- zabudowa usługowa ---
    _wpis("U", "Tereny zabudowy usługowej", GRUPA_USLUGOWE, RODZAJ_MPZP,
          wypelnienie="#E8342A", obrys="#8C1F19", szerokosc=0.5,
          slowa=("U", "USLUGI", "USLUGOWA")),
    _wpis("UC", "Tereny obiektów handlowych powyżej 2000 m2",
          GRUPA_USLUGOWE, RODZAJ_MPZP, wypelnienie="#E8342A",
          obrys="#4D4D4D", szerokosc=0.5, kreskowanie="ukosne",
          kolor_kreskowania="#4D4D4D",
          slowa=("UC", "HANDLOWYCH", "WIELKOPOWIERZCHNIOWE")),
    _wpis("US", "Tereny sportu i rekreacji", GRUPA_USLUGOWE, RODZAJ_MPZP,
          wypelnienie="#7CC576", obrys="#E8342A", szerokosc=0.5,
          kreskowanie="ukosne", kolor_kreskowania="#E8342A",
          slowa=("US", "SPORTU I REKREACJI", "SPORT")),
    _wpis("UO", "Tereny usług oświaty", GRUPA_USLUGOWE, RODZAJ_MPZP,
          wypelnienie="#F08A80", obrys="#8C1F19", szerokosc=0.5,
          slowa=("UO", "OSWIATY", "SZKOLA")),
    _wpis("UZ", "Tereny usług zdrowia", GRUPA_USLUGOWE, RODZAJ_MPZP,
          wypelnienie="#F5A6A0", obrys="#8C1F19", szerokosc=0.5,
          slowa=("UZ", "ZDROWIA", "SZPITAL", "PRZYCHODNIA")),
    _wpis("UK", "Tereny usług kultury i kultu religijnego",
          GRUPA_USLUGOWE, RODZAJ_MPZP, wypelnienie="#EFA3B8",
          obrys="#8C1F19", szerokosc=0.5,
          slowa=("UK", "KULTURY", "KULTU RELIGIJNEGO", "KOSCIOL")),
    _wpis("UA", "Tereny usług administracji", GRUPA_USLUGOWE, RODZAJ_MPZP,
          wypelnienie="#F2B5AE", obrys="#8C1F19", szerokosc=0.5,
          slowa=("UA", "ADMINISTRACJI", "URZAD")),
    # --- tereny rolnicze ---
    _wpis("R", "Tereny rolnicze", GRUPA_ROLNICZE, RODZAJ_MPZP,
          wypelnienie="#FFF200", obrys="#B3A800", szerokosc=0.5,
          slowa=("R", "ROLNE", "ROLNICZE", "GRUNTY ORNE")),
    _wpis("RU", "Tereny obsługi produkcji w gospodarstwach rolnych",
          GRUPA_ROLNICZE, RODZAJ_MPZP, wypelnienie="#FFF200",
          obrys="#E8342A", szerokosc=0.5, kreskowanie="ukosne",
          kolor_kreskowania="#E8342A",
          slowa=("RU", "OBSLUGI PRODUKCJI ROLNEJ")),
    _wpis("RM", "Tereny zabudowy zagrodowej", GRUPA_ROLNICZE,
          RODZAJ_MPZP, wypelnienie="#FFF200", obrys="#8C6239",
          szerokosc=0.5, kreskowanie="ukosne",
          kolor_kreskowania="#C8935A",
          slowa=("RM", "ZAGRODOWA", "SIEDLISKO")),
    # --- tereny techniczno-produkcyjne ---
    _wpis("P", "Tereny obiektów produkcyjnych, składów i magazynów",
          GRUPA_PRODUKCYJNE, RODZAJ_MPZP, wypelnienie="#B266B2",
          obrys="#663366", szerokosc=0.5,
          slowa=("P", "PRODUKCYJNE", "SKLADY", "MAGAZYNY", "PRZEMYSL")),
    _wpis("PG", "Obszary i tereny górnicze", GRUPA_PRODUKCYJNE,
          RODZAJ_MPZP, wypelnienie="#D9A6D9", obrys="#663366",
          szerokosc=0.5, kreskowanie="krzyzowe",
          kolor_kreskowania="#663366",
          slowa=("PG", "GORNICZE", "KOPALNIA", "ZLOZE")),
    _wpis("PU", "Tereny produkcyjno-usługowe", GRUPA_PRODUKCYJNE,
          RODZAJ_MPZP, wypelnienie="#C98FC9", obrys="#663366",
          szerokosc=0.5, slowa=("PU", "PRODUKCYJNO USLUGOWE", "P/U")),
    # --- zieleń i wody ---
    _wpis("ZN", "Tereny zieleni objęte formami ochrony przyrody",
          GRUPA_ZIELEN_WODY, RODZAJ_MPZP, wypelnienie="#2E7D32",
          obrys="#1B5E20", szerokosc=0.5,
          slowa=("ZN", "OCHRONY PRZYRODY", "REZERWAT", "PARK NARODOWY")),
    _wpis("ZL", "Lasy", GRUPA_ZIELEN_WODY, RODZAJ_MPZP,
          wypelnienie="#3E8E41", obrys="#1B5E20", szerokosc=0.5,
          slowa=("ZL", "LAS", "LASY", "LESNE")),
    _wpis("ZP", "Tereny zieleni urządzonej (parki, skwery)",
          GRUPA_ZIELEN_WODY, RODZAJ_MPZP, wypelnienie="#7CC576",
          obrys="#3E8E41", szerokosc=0.5,
          slowa=("ZP", "Z", "ZIELEN URZADZONA", "PARK", "SKWER")),
    _wpis("ZD", "Tereny ogrodów działkowych", GRUPA_ZIELEN_WODY,
          RODZAJ_MPZP, wypelnienie="#A5D6A7", obrys="#3E8E41",
          szerokosc=0.5, kreskowanie="krzyzowe",
          kolor_kreskowania="#3E8E41",
          slowa=("ZD", "OGRODY DZIALKOWE", "ROD")),
    _wpis("ZC", "Cmentarze", GRUPA_ZIELEN_WODY, RODZAJ_MPZP,
          wypelnienie="#94D4C4", obrys="#3E8E41", szerokosc=0.5,
          slowa=("ZC", "CMENTARZ")),
    _wpis("ZZ", "Obszary zagrożone powodzią", GRUPA_ZIELEN_WODY,
          RODZAJ_MPZP, wypelnienie="#D6F5C8", obrys="#3E8E41",
          szerokosc=0.5, kreskowanie="ukosne",
          kolor_kreskowania="#7CC576",
          slowa=("ZZ", "ZAGROZONE POWODZIA", "POWODZ", "ZALEWOWE")),
    _wpis("WS", "Tereny wód powierzchniowych śródlądowych",
          GRUPA_ZIELEN_WODY, RODZAJ_MPZP, wypelnienie="#A6DDF0",
          obrys="#3D8FB0", szerokosc=0.5,
          slowa=("WS", "W", "WODY", "RZEKA", "JEZIORO", "STAW",
                 "KANAL")),
    _wpis("WM", "Tereny wód powierzchniowych morskich",
          GRUPA_ZIELEN_WODY, RODZAJ_MPZP, wypelnienie="#8ACFE8",
          obrys="#2E7D9E", szerokosc=0.5,
          slowa=("WM", "MORSKIE", "MORZE")),
    # --- komunikacja ---
    _wpis("KD", "Tereny dróg publicznych", GRUPA_KOMUNIKACJA,
          RODZAJ_MPZP, wypelnienie="#FFFFFF", obrys="#4D4D4D",
          szerokosc=0.5,
          slowa=("KD", "KDL", "KDD", "KDZ", "KDG", "KDS", "KDA",
                 "DROGA PUBLICZNA", "ULICA", "DROGI")),
    _wpis("KDW", "Tereny dróg wewnętrznych", GRUPA_KOMUNIKACJA,
          RODZAJ_MPZP, wypelnienie="#E0E0E0", obrys="#4D4D4D",
          szerokosc=0.4,
          slowa=("KDW", "KW", "DROGA WEWNETRZNA", "WEWNETRZNE")),
    _wpis("KS", "Tereny obsługi komunikacji i parkingów",
          GRUPA_KOMUNIKACJA, RODZAJ_MPZP, wypelnienie="#D9D9D9",
          obrys="#4D4D4D", szerokosc=0.5,
          slowa=("KS", "KP", "PARKING", "OBSLUGI KOMUNIKACJI")),
    _wpis("KK", "Tereny komunikacji kolejowej", GRUPA_KOMUNIKACJA,
          RODZAJ_MPZP, wypelnienie="#BFBFBF", obrys="#1A1A1A",
          szerokosc=0.5, kreska=(4.0, 2.0),
          slowa=("KK", "KOLEJ", "KOLEJOWA", "TOROWISKO")),
    _wpis("KWO", "Tereny komunikacji wodnej", GRUPA_KOMUNIKACJA,
          RODZAJ_MPZP, wypelnienie="#1F4E9C", obrys="#12305E",
          szerokosc=0.5,
          slowa=("KWO", "SZLAK WODNY", "PORT", "PRZYSTAN")),
    # --- infrastruktura techniczna (MPZP) ---
    _wpis("E", "Tereny infrastruktury — elektroenergetyka",
          GRUPA_INFRASTRUKTURA, RODZAJ_MPZP, wypelnienie="#808080",
          obrys="#404040", szerokosc=0.5,
          slowa=("E", "IE", "ELEKTROENERGETYKA", "GPZ", "TRAFO")),
    _wpis("G", "Tereny infrastruktury — gazownictwo",
          GRUPA_INFRASTRUKTURA, RODZAJ_MPZP, wypelnienie="#8C8C8C",
          obrys="#404040", szerokosc=0.5,
          slowa=("G", "IG", "GAZOWNICTWO", "GAZ")),
    _wpis("W", "Tereny infrastruktury — wodociągi",
          GRUPA_INFRASTRUKTURA, RODZAJ_MPZP, wypelnienie="#999999",
          obrys="#404040", szerokosc=0.5,
          slowa=("IW", "WODOCIAGI", "UJECIE WODY", "SUW")),
    _wpis("K", "Tereny infrastruktury — kanalizacja",
          GRUPA_INFRASTRUKTURA, RODZAJ_MPZP, wypelnienie="#A6A6A6",
          obrys="#404040", szerokosc=0.5,
          slowa=("K", "IK", "KANALIZACJA", "OCZYSZCZALNIA")),
    _wpis("T", "Tereny infrastruktury — telekomunikacja",
          GRUPA_INFRASTRUKTURA, RODZAJ_MPZP, wypelnienie="#B3B3B3",
          obrys="#404040", szerokosc=0.5,
          slowa=("T", "IT", "TELEKOMUNIKACJA", "MASZT")),
    _wpis("O", "Tereny infrastruktury — gospodarowanie odpadami",
          GRUPA_INFRASTRUKTURA, RODZAJ_MPZP, wypelnienie="#737373",
          obrys="#404040", szerokosc=0.5,
          slowa=("O", "IO", "ODPADY", "SKLADOWISKO", "PSZOK")),
    _wpis("C", "Tereny infrastruktury — ciepłownictwo",
          GRUPA_INFRASTRUKTURA, RODZAJ_MPZP, wypelnienie="#8C8C8C",
          obrys="#404040", szerokosc=0.5,
          slowa=("C", "IC", "CIEPLOWNICTWO", "CIEPLOWNIA")),
    # --- elementy rysunku planu ---
    _wpis("GRANICA_PLANU", "Granica obszaru objętego planem",
          GRUPA_RYSUNEK, RODZAJ_MPZP, obrys="#000000", szerokosc=1.2,
          kreska=(8.0, 3.0), geometria="linia",
          slowa=("GRANICA PLANU", "GRANICA OPRACOWANIA",
                 "OBSZAR OPRACOWANIA")),
    _wpis("LINIA_ROZGR", "Linia rozgraniczająca tereny",
          GRUPA_RYSUNEK, RODZAJ_MPZP, obrys="#000000", szerokosc=0.8,
          geometria="linia",
          slowa=("LINIA ROZGRANICZAJACA", "ROZGRANICZENIE",
                 "LINIE ROZGRANICZAJACE")),
    _wpis("LINIA_ZAB_OBOW", "Obowiązująca linia zabudowy",
          GRUPA_RYSUNEK, RODZAJ_MPZP, obrys="#E8342A", szerokosc=0.6,
          geometria="linia",
          slowa=("OBOWIAZUJACA LINIA ZABUDOWY", "LINIA ZABUDOWY OBOW")),
    _wpis("LINIA_ZAB_NIEP", "Nieprzekraczalna linia zabudowy",
          GRUPA_RYSUNEK, RODZAJ_MPZP, obrys="#E8342A", szerokosc=0.6,
          kreska=(4.0, 2.0), geometria="linia",
          slowa=("NIEPRZEKRACZALNA LINIA ZABUDOWY", "LINIA ZABUDOWY")),
    _wpis("STREFA_OCHR", "Strefa ochrony konserwatorskiej",
          GRUPA_RYSUNEK, RODZAJ_MPZP, obrys="#7A4C99", szerokosc=0.6,
          kreska=(6.0, 2.0, 1.0, 2.0), kreskowanie="ukosne",
          kolor_kreskowania="#7A4C99",
          slowa=("STREFA OCHRONY", "KONSERWATORSKA", "ZABYTEK",
                 "OCHRONA ZABYTKOW")),
]


# =============================================================================
#  3. SIECI UZBROJENIA TERENU (GESUT) — mapa zasadnicza
#     (Dz.U. 2021 poz. 1385 — kolory branżowe)
# =============================================================================

GRUPA_SIECI = "GEODEZJA — SIECI UZBROJENIA TERENU (GESUT)"

SIECI_GESUT = [
    _wpis("SIEC_W", "Sieć wodociągowa", GRUPA_SIECI, RODZAJ_GESUT,
          obrys="#0066CC", szerokosc=0.5, geometria="linia",
          slowa=("SIEC WODOCIAGOWA", "WODOCIAG", "WODA", "PRZEWOD W",
                 "W_SIEC")),
    _wpis("SIEC_K", "Sieć kanalizacyjna", GRUPA_SIECI, RODZAJ_GESUT,
          obrys="#8B5A2B", szerokosc=0.5, geometria="linia",
          slowa=("SIEC KANALIZACYJNA", "KANALIZACJA", "KANAL SANITARNY",
                 "PRZEWOD K", "KD_SIEC")),
    _wpis("SIEC_G", "Sieć gazowa", GRUPA_SIECI, RODZAJ_GESUT,
          obrys="#B8B400", szerokosc=0.5, geometria="linia",
          slowa=("SIEC GAZOWA", "GAZOCIAG", "PRZEWOD G", "G_SIEC")),
    _wpis("SIEC_E", "Sieć elektroenergetyczna", GRUPA_SIECI,
          RODZAJ_GESUT, obrys="#E60000", szerokosc=0.5,
          geometria="linia",
          slowa=("SIEC ELEKTROENERGETYCZNA", "ENERGETYCZNA", "KABEL",
                 "LINIA NN", "LINIA SN", "PRZEWOD E", "E_SIEC")),
    _wpis("SIEC_C", "Sieć ciepłownicza", GRUPA_SIECI, RODZAJ_GESUT,
          obrys="#CC00CC", szerokosc=0.5, geometria="linia",
          slowa=("SIEC CIEPLOWNICZA", "CIEPLOCIAG", "PRZEWOD C",
                 "C_SIEC")),
    _wpis("SIEC_T", "Sieć telekomunikacyjna", GRUPA_SIECI, RODZAJ_GESUT,
          obrys="#FF8000", szerokosc=0.5, geometria="linia",
          slowa=("SIEC TELEKOMUNIKACYJNA", "TELETECHNICZNA",
                 "SWIATLOWOD", "PRZEWOD T", "T_SIEC")),
    _wpis("SIEC_N", "Sieć niezidentyfikowana / inna", GRUPA_SIECI,
          RODZAJ_GESUT, obrys="#666666", szerokosc=0.4,
          kreska=(3.0, 2.0), geometria="linia",
          slowa=("SIEC NIEZIDENTYFIKOWANA", "SIEC INNA", "PRZEWOD N")),
]


# =============================================================================
#  4. EGiB i mapa zasadnicza — działki, budynki, użytki, osnowa
# =============================================================================

GRUPA_EGIB = "GEODEZJA — EWIDENCJA GRUNTÓW I BUDYNKÓW"

EGIB = [
    _wpis("DZIALKA", "Działki ewidencyjne", GRUPA_EGIB, RODZAJ_EGIB,
          wypelnienie=None, obrys="#B32D00", szerokosc=0.4,
          slowa=("DZIALKA", "DZIALKI", "EGIB DZIALKI", "GRANICE DZIALEK",
                 "PARCELA")),
    _wpis("BUDYNEK", "Budynki", GRUPA_EGIB, RODZAJ_EGIB,
          wypelnienie="#C9C9C9", obrys="#1A1A1A", szerokosc=0.5,
          slowa=("BUDYNEK", "BUDYNKI", "OBRYS BUDYNKU", "KONTUR BUDYNKU")),
    _wpis("UZYTEK", "Kontury użytków gruntowych", GRUPA_EGIB,
          RODZAJ_EGIB, wypelnienie=None, obrys="#4D7A00",
          szerokosc=0.3, kreska=(3.0, 1.5),
          slowa=("UZYTEK", "UZYTKI", "KONTUR UZYTKU", "KLASOUZYTEK")),
    _wpis("OSNOWA", "Punkty osnowy geodezyjnej", GRUPA_EGIB,
          RODZAJ_EGIB, wypelnienie="#000000", obrys="#000000",
          szerokosc=0.4, geometria="punkt",
          slowa=("OSNOWA", "PUNKT OSNOWY", "REPER", "PUNKT GEODEZYJNY")),
    _wpis("PIKIETA", "Pikiety i rzędne terenu", GRUPA_EGIB, RODZAJ_EGIB,
          wypelnienie="#996633", obrys="#663300", szerokosc=0.3,
          geometria="punkt",
          slowa=("PIKIETA", "RZEDNA", "WYSOKOSC", "PUNKT WYSOKOSCIOWY")),
    _wpis("OBREB", "Granice obrębów ewidencyjnych", GRUPA_EGIB,
          RODZAJ_EGIB, obrys="#801A00", szerokosc=0.8,
          kreska=(6.0, 2.0, 1.0, 2.0), geometria="linia",
          slowa=("OBREB", "GRANICA OBREBU", "OBREBY")),
    _wpis("GRANICA_ADM", "Granice administracyjne", GRUPA_EGIB,
          RODZAJ_EGIB, obrys="#660066", szerokosc=1.0,
          kreska=(8.0, 2.0, 2.0, 2.0), geometria="linia",
          slowa=("GRANICA GMINY", "GRANICA POWIATU",
                 "GRANICA WOJEWODZTWA", "GRANICA ADMINISTRACYJNA")),
]


# =============================================================================
#  KATALOG ZBIORCZY + wyszukiwanie
# =============================================================================

KATALOG = {}
for _lista in (STREFY_PLANISTYCZNE, OBSZARY_PLANU_OGOLNEGO,
               PRZEZNACZENIA_MPZP, SIECI_GESUT, EGIB):
    for _w in _lista:
        KATALOG[_w["symbol"]] = _w

# rodzaje dokumentów, jakie wtyczka rozpoznaje w nazwach plików/warstw
RODZAJE = (RODZAJ_MPZP, RODZAJ_PLAN_OGOLNY, RODZAJ_GESUT, RODZAJ_EGIB)

# słowa w nazwie pliku/warstwy wskazujące na rodzaj dokumentu
SLOWA_RODZAJU = {
    "MPZP": RODZAJ_MPZP,
    "PLAN MIEJSCOWY": RODZAJ_MPZP,
    "MIEJSCOWY": RODZAJ_MPZP,
    "PLAN OGOLNY": RODZAJ_PLAN_OGOLNY,
    "POG": RODZAJ_PLAN_OGOLNY,
    "STUDIUM": RODZAJ_PLAN_OGOLNY,
    "SUIKZP": RODZAJ_PLAN_OGOLNY,
    "GESUT": RODZAJ_GESUT,
    "UZBROJENIE": RODZAJ_GESUT,
    "MAPA ZASADNICZA": RODZAJ_GESUT,
    "EGIB": RODZAJ_EGIB,
    "EWIDENCJA": RODZAJ_EGIB,
    "MAPA EWIDENCYJNA": RODZAJ_EGIB,
}


def wpis_dla_symbolu(symbol):
    """Zwraca wpis katalogu dla symbolu (np. 'MN'), albo None."""
    if not symbol:
        return None
    return KATALOG.get(str(symbol).strip().upper())


def wszystkie_wpisy():
    """Cały katalog jako lista — do budowania reguł stylu."""
    return list(KATALOG.values())
