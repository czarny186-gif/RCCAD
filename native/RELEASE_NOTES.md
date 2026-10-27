## RCCAD Desktop 0.3 — obsługa w stylu RCCAD HTML

Natywna aplikacja Windows x64. Wygląd i gesty nawiązują do RCCAD HTML;
obliczenia bryłowe nadal wykonuje OpenCascade z wersji Desktop.

### Co zmieniono

- Oryginalne ikony HTML, jasny widok, pływające panele i kolorowa kostka widoków.
- Rysowanie myszą: prostokąt, prostokąt ze środka, okrąg, elipsa, wielokąt,
  fasolka, zamknięty profil łamany, odcinek i łuk przez trzy punkty.
- Szkic na XY/XZ/YZ, odsuniętej płaszczyźnie lub wskazanej płaskiej ścianie bryły.
- Siatka na płaszczyźnie szkicu, przyciąganie i podgląd wymiarów podczas rysowania.
- Wyciąganie zaznaczonego profilu: nowa bryła, połączenie, wycięcie i część wspólna.
  Podgląd narzędzia, symetria, wewnętrzne profile jako otwory i przeciągany uchwyt.
- Zaokrąglanie i fazowanie: wybór krawędzi, uchwyt rozmiaru i podgląd CAD na żądanie.
- Graficzny panel przesunięcia/obrotu, podgląd i uchwyt wybranej osi.
- Operacje na bryłach i lustro z paneli; menu kontekstowe pod prawym przyciskiem.
- Metadane płaszczyzny szkicu zapisują się w projekcie RCCADX. Starsze projekty Desktop nadal się otwierają.

### Uruchomienie

1. Pobierz **RCCAD-Desktop-Windows-x64.zip**.
2. Rozpakuj archiwum w całości.
3. Uruchom **RCCAD Desktop.exe** z folderu `RCCAD Desktop`.
4. Zachowaj obok EXE folder `_internal`.

### Szybki początek

**Szkic → wybierz płaszczyznę → wybierz figurę → kliknij punkty → Zakończ szkic
→ Wyciągnij → Zastosuj.**

Aby zrobić otwór: Szkic → Wybierz płaską ścianę → kliknij ścianę → narysuj okrąg
→ Zakończ szkic → Wyciągnij → Wytnij w bryle → podaj dodatnią głębokość → Zastosuj.
W trybie szkicu rolka przybliża, a przyciski Obrót i Przesuń widok zmieniają gest myszy.

To wersja rozwojowa. Nie przeniesiono jeszcze wszystkich narzędzi HTML, m.in.
tekstu/SVG i zaawansowanej edycji istniejących figur. Odcinek i łuk są otwartymi
krzywymi i nie można ich samodzielnie wyciągać w bryłę. Brak więzów parametrycznych.
STL jest siatką podglądową; do edycji użyj STEP. Stare projekty HTML przenieś przez STEP.

Nie zmieniono modułu istniejących obliczeń CAD `kernel.py`. Gesty szkicu są
zamieniane na dokładne krzywe i operacje OpenCascade, a nie operacje na trójkątach.
Podglądy są odrębne od dokumentu: dopiero Zastosuj zapisuje zmianę i historię cofania.

Paczka jest budowana na Windows i sprawdzana uruchomieniem gotowego EXE.
Zawiera raport `selftest_windows.json`. Wymaga OpenGL 2.1 lub nowszego.
