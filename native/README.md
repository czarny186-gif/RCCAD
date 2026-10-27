# RCCAD Desktop 0.3 — Windows 10/11 x64

Nowy program desktopowy: natywne okno Qt i modelowanie bryłowe OpenCascade.
Nie uruchamia przeglądarki ani serwera WWW. To wersja rozwojowa,
nie pełny zamiennik wszystkich narzędzi starszego pliku HTML.

## Pobranie EXE

W repozytorium otwórz **Releases → RCCAD Desktop 0.3 — Windows x64** i pobierz
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
Nie ma jeszcze więzów parametrycznych, tekstu, SVG ani pełnej historii cech.
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

## Interfejs 0.3 — sposób pracy z HTML

Sześć głównych przycisków i pływające panele nawiązują do programu HTML.
„Model” pokazuje drzewo obiektów. Prawy przycisk otwiera menu kontekstowe.
„Wiele” pozwala dodawać bryły i krawędzie bez Ctrl/Shift.

1. Kliknij **Szkic**, wybierz płaszczyznę lub wskaż płaską ścianę bryły.
2. Wybierz figurę i klikaj jej punkty w widoku. Prostokąt: dwa narożniki;
   okrąg: środek i punkt promienia; fasolka: dwa środki i punkt szerokości.
   Profil łamany zamknij kliknięciem pierwszego punktu albo przyciskiem.
3. Wybierz **Zakończ szkic**, następnie **Wyciągnij**. Kliknij wnętrze profilu,
   wybierz operację, bryłę docelową i odległość. Pomarańczową strzałkę można przeciągać.
4. Przy wycinaniu dodatnia odległość prowadzi w głąb ściany; ujemna odwraca kierunek.
   Domyślnie wewnętrzne kontury są otworami (bez zagnieżdżonych wysp).
5. **Zastosuj** zapisuje wynik. Podgląd i Zamknij nie zmieniają geometrii.

W szkicu: siatka i przyciąganie, Esc anuluje bieżącą figurę, Cofnij punkt usuwa
ostatni wierzchołek. Dokładną figurę możesz też utworzyć z pól wymiarów od
pierwszego klikniętego punktu. Dłuższy panel przewija się rolką.
Przyciski Obrót i Przesuń widok umożliwiają nawigację bez przerywania szkicu.

Zaokrąglenie/faza: kliknij krawędzie, ustaw rozmiar uchwytem lub polem, wybierz
**Podgląd**, a potem **Zastosuj**. Podgląd rozwiązuje oryginalny silnik OpenCascade.
Przesunięcie i obrót mają osobny panel oraz uchwyt aktywnej osi.

Proste bryły i dawny szkic z wymiarów są też w menu pod pierwszym przyciskiem.
Wersja 0.3 zachowuje silnik, format BREP i moduł `kernel.py` z wcześniejszego EXE.

Testy z rzeczywistym widokiem OpenGL (na maszynie z ekranem):

```sh
PYTHONPATH=.:tests python tests/studio_smoke.py /tmp/rccad-screenshots
```
