## RCCAD Desktop 0.1 — pierwsza wersja rozwojowa

Natywna aplikacja Windows x64, bez przeglądarki i bez instalowania Pythona.
Silnik geometrii: OpenCascade. Interfejs: Qt.

### Uruchomienie

1. Pobierz **RCCAD-Desktop-Windows-x64.zip** poniżej.
2. Rozpakuj archiwum w całości.
3. Otwórz folder `RCCAD Desktop` i uruchom **RCCAD Desktop.exe**.
4. Nie przenoś samego EXE — potrzebuje sąsiedniego folderu `_internal`.

### Funkcje

Bryły i szkice z wymiarów, wyciągnięcie, otwory, operacje Boolean,
zaokrąglanie i fazowanie topologicznych krawędzi CAD, transformacje, odbicie,
cofanie i ponawianie, projekty RCCADX, import/eksport STEP/BREP/STL/DXF.
STL jest importowany jako siatka podglądowa; do dokładnej edycji użyj STEP.

To pierwsza wersja desktopowa, a nie pełny zestaw funkcji programu HTML.
Nie ma jeszcze rysowania szkiców myszą, więzów parametrycznych, tekstu i SVG.
Stare projekty przenieś przez eksport STEP z programu HTML.

Paczka jest budowana na Windows i sprawdzana przez uruchomienie gotowego EXE.
Zawiera raport `selftest_windows.json`. Widok 3D wymaga OpenGL 2.1 lub nowszego.
Wydanie nie jest podpisane certyfikatem wydawcy.
