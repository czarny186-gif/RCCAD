# RCCAD Desktop 0.1 — Windows 10/11 x64

Nowy program desktopowy: natywne okno Qt i modelowanie bryłowe OpenCascade.
Nie uruchamia przeglądarki ani serwera WWW. To pierwsza wersja rozwojowa,
nie pełny zamiennik wszystkich narzędzi starszego pliku HTML.

## Pobranie EXE

W repozytorium otwórz **Actions → RCCAD Desktop - Windows EXE → najnowszy udany
przebieg → Artifacts → RCCAD-Desktop-Windows-x64**. Pobranie artefaktu GitHub
wymaga zalogowania. Rozpakuj pobrany plik ZIP, a następnie zawarte w nim archiwum
aplikacji. Uruchom **RCCAD Desktop.exe**. Zachowaj obok niego cały katalog
`_internal`; sam plik EXE nie zawiera bibliotek aplikacji.

Wydanie nie jest podpisane certyfikatem wydawcy. Nie wymaga lokalnego Pythona.
Wymagany jest sterownik obsługujący OpenGL 2.1 lub nowszy. Zestaw budowania
sprawdza rzeczywisty plik EXE, silnik CAD, zapis projektu i import/eksport.
Widok GPU na konkretnym komputerze zależy od sterownika.

## Dostępne funkcje

- Prostopadłościan i walec z wymiarów.
- Szkic prostokąta, okręgu i wielokąta na XY/XZ/YZ; wyciągnięcie szkicu.
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
Nie ma jeszcze rysowania szkicu myszą, więzów parametrycznych, tekstu, SVG ani
pełnej historii cech. Szkice w tej wersji tworzy się z okna wymiarów.

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
