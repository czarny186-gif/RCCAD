# RCCAD Desktop 0.4 — Windows 10/11 x64

Nowy program desktopowy: natywne okno Qt i modelowanie bryłowe OpenCascade.
Nie uruchamia przeglądarki ani serwera WWW. To wersja rozwojowa,
nie pełny zamiennik wszystkich narzędzi starszego pliku HTML.

## Pobranie EXE

W repozytorium otwórz **Releases → RCCAD Desktop 0.4 — Windows x64** i pobierz
**RCCAD-Desktop-Windows-x64.zip**. Rozpakuj archiwum w całości i uruchom
**RCCAD Desktop.exe** z folderu `RCCAD Desktop`. Zachowaj obok niego cały katalog
`_internal`; sam plik EXE nie zawiera bibliotek aplikacji.

Każdy build jest także dostępny w **Actions → RCCAD Desktop - Windows EXE →
udany przebieg → Artifacts** (ten wariant pobrania wymaga zalogowania na GitHub).

Wydanie nie jest podpisane certyfikatem wydawcy. Nie wymaga lokalnego Pythona.
Wymagany jest sterownik obsługujący OpenGL 2.1 lub nowszy. Zestaw budowania
sprawdza rzeczywisty plik EXE, silnik CAD, zapis projektu i import/eksport.
Widok GPU na konkretnym komputerze zależy od sterownika.

## Dostępne funkcje

- Prostopadłościan i walec z wymiarów.
- Szkice rysowane myszą na płaszczyznach i płaskich ścianach brył; wyciągnięcie, połączenie i wycięcie profilu.
- Otwór w osi Z, przelotowy lub o zadanej głębokości.
- Suma, różnica i część wspólna brył.
- Zaokrąglanie i fazowanie rzeczywistych krawędzi CAD; Shift + klik dodaje
  kolejne krawędzie. Wspólne narożniki oblicza OpenCascade.
- Przesunięcie i obrót XYZ, odbicie względem XY/XZ/YZ, duplikowanie, usuwanie.
- Drzewo obiektów, widoczność, wymiary i objętość, cofanie i ponawianie.
- Projekt `.rccadx` przechowujący geometrię BREP; bezpieczny zapis przez plik
  tymczasowy i zastąpienie dopiero po powodzeniu.
- Import STEP/BREP jako bryły, DXF jako szkice, STL jako siatka podglądowa.
- Eksport STEP, BREP, STL i DXF (szkice).

Modelowanie odbywa się w osobnym wątku; błąd operacji nie zastępuje poprzedniej
bryły. Zaznaczone krawędzie odpowiadają topologii CAD, a nie krawędziom trójkątów.

## Przeniesienie starego modelu

W programie HTML wyeksportuj **STEP**, a następnie użyj **Importuj** w RCCAD
Desktop. Pliki projektu JSON ze starego programu nie są nowym formatem
`.rccadx`. STL jest siatką: nie daje takich samych możliwości edycji jak STEP.
Nie ma jeszcze więzów parametrycznych, importera plików SVG ani pełnej historii cech.
Odcinki i łuki są otwartymi krzywymi; bryłę wyciąga się z zamkniętego profilu.

## Uruchomienie ze źródeł

Python 3.12, 64-bit:

```sh
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
python main.py
```

Przykład bryły z otworem i zaokrągleniami: `python main.py --demo`.

```sh
python -m unittest discover -s tests -v
python main.py --self-test --report selftest.json
```

## Budowanie Windows

Na Windows, z aktywnym środowiskiem Python:

```sh
python -m pip install -r requirements-build.txt
python -m PyInstaller --noconfirm RCCAD.spec
```

Wynik: `dist/RCCAD Desktop/RCCAD Desktop.exe`. PyInstaller wymaga budowania
na docelowym systemie: uruchomienie go na Linuksie nie tworzy pliku Windows EXE.
Automatyczny proces Windows znajduje się w `.github/workflows/native-windows.yml`.

## Interfejs 0.4 — projektowanie jak w HTML

[Zakres przeniesionych grafik, gestów i efektów](HTML_PARITY.md).

1. Kliknij **Szkic**, a następnie płaszczyznę XY/XZ/YZ albo płaską ścianę.
2. Z pionowego paska wybierz narzędzie. Strzałka obok prostokąta/okręgu rozwija warianty.
3. Wskaż punkty figury. **Tab** otwiera wymiary przy kursorze; **Enter** zatwierdza.
   Dwuklik istniejącego wymiaru pozwala go zmienić. Nożyczki usuwają fragment krzywej.
4. Kliknij **Wyciągnij** i wskaż zamknięty obszar. Przecięcia odcinków i figur tworzą
   osobne obszary; **Shift + klik** pozwala wybrać kilka.
5. Ustaw operację i kierunek po lewej, odległości w pasku obok albo uchwytem.
   Przy wycinaniu dodatnia odległość prowadzi w głąb ściany.
6. **Zastosuj** zapisuje jedną transakcję. Anulowanie podglądu nie zmienia geometrii.

Tekst ma wysokość, obrót, krój i wyrównanie. Dołączone czcionki DejaVu tworzą
prawdziwe kontury CAD z otworami liter. Linie konstrukcyjne i punkty nie są wyciągane.

Dolne przyciski przesunięcia/obrotu otwierają pasek XYZ. Kolorowe uchwyty działają
również na szkicach. Odbicie: wybierz obiekt, wskaż płaską ścianę i zastosuj
kopię, zastąpienie albo połączenie. Boolean ma opcję zachowania brył-narzędzi.

Prawy przycisk lub Shift + lewy przesuwa widok; rolka przybliża. Esc anuluje
pole/figurę, a kolejny Esc zamyka narzędzie. Przycisk domu odtwarza widok startowy.
Dodatkowe polecenia i lista obiektów są w menu pod ikoną pliku.

Podglądy liczy ten sam silnik CAD co wynik. Błędy są komunikatami w rogu okna;
poprzednia bryła pozostaje bez zmian. Zaokrąglenia i fazy mają podgląd automatyczny.

Testy w rzeczywistym oknie OpenGL:

```sh
PYTHONPATH=.:tests python tests/studio_smoke.py /tmp/rccad-screenshots
PYTHONPATH=.:tests python tests/classic_smoke.py /tmp/rccad-screenshots
```
