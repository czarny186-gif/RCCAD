## RCCAD Desktop 0.4 — projektowanie i grafika z RCCAD HTML

Natywny program Windows x64. Zachowuje dotychczasowy silnik OpenCascade.

### Zmiany

- Wszystkie grafiki interfejsu z HTML: 6 PNG, 15 SVG i 3 symbole; oryginalne stany ikon,
  pionowy pasek narzędzi, warianty figur, kostka widoków, gradient, siatka i materiał brył.
- Najazdy, pulsowanie aktywnego narzędzia, podświetlenia, bieżące podglądy,
  uchwyty, przejścia widoków i znikające komunikaty.
- Wybór płaszczyzny w 3D lub płaskiej ściany; rysowanie myszą i Tab/Enter przy wymiarach.
- Prostokąty w trzech wariantach, okręgi w czterech wariantach, elipsa,
  fasolka, wielokąt, łuk, punkty, linie i geometria konstrukcyjna.
- Tekst z czcionkami DejaVu, obrotem, wyrównaniem i prawdziwymi otworami liter.
- Edycja wymiarów dwuklikiem, zachowanie wspólnych końców i dokładne nożyczki.
- Obszary z przecinających się konturów i osobnych odcinków/łuków liczy OpenCascade.
- Wyciąganie wielu profili, jedna strona, symetria lub dwie niezależne strony;
  nowa bryła, połączenie, wycięcie i część wspólna.
- Automatyczny podgląd fazy/zaokrąglenia, kolorowe osie i pierścienie transformacji,
  odbicie względem wskazanej ściany z kopiowaniem, zastąpieniem lub połączeniem.
- Cofanie całej operacji i anulowanie podglądu bez zmiany projektu.

### Uruchomienie

Rozpakuj **całą paczkę ZIP** do nowego folderu i uruchom **RCCAD Desktop.exe**.
Zachowaj obok EXE katalog `_internal`. Nie trzeba instalować Pythona ani przeglądarki.

### Pierwsza bryła

Szkic → kliknij płaszczyznę → wybierz figurę → klikaj jej punkty.
Tab otwiera dokładne wymiary; Enter zatwierdza. Potem kliknij Wyciągnij,
wskaż obszar, ustaw odległość lub przeciągnij strzałkę i wybierz Zastosuj.
Shift + klik dodaje kolejne obszary.

Przy wycinaniu: Szkic → kliknij płaską ścianę → narysuj zamknięty profil →
Wyciągnij → Wytnij → dodatnia głębokość → Zastosuj.

Wydanie obejmuje projektowanie nowych brył, bez deklaracji pikselowej zgodności
wszystkich okien systemowych. Import SVG i stare projekty JSON nie są przeniesione;
modele przenieś przez STEP. STL nadal jest siatką podglądową.

Gotowy EXE jest uruchamiany na Windows przed publikacją. Raport testu znajduje
się w paczce jako `selftest_windows.json`. Widok wymaga sterownika OpenGL 2.1+.
