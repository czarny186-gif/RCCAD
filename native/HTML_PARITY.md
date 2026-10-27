# RCCAD Desktop 0.4 — projektowanie nowych brył według RCCAD HTML

Odniesienie: główny `RCCAD.html` z tego repozytorium. Interfejs jest natywny Qt/OpenGL.
Moduł `rccad/kernel.py` i wersje silnika CAD pozostają bez zmian.
Nie osadzamy strony ani silnika geometrii JavaScript.

## Grafiki i wygląd

Wszystkie osadzone zasoby graficzne przeniesiono przez
`scripts/extract_html_graphics.py`: 6 PNG, 15 ikon SVG i 3 symbole tekstowe.
Plik `rccad/assets/html/catalog.json` zachowuje nazwy kontrolek, ich teksty,
atrybuty, hash źródła HTML i hashe obrazów. Oryginalne SVG są zachowane obok
wersji z właściwościami odziedziczonymi w HTML z CSS.

- Główne przyciski 52 × 52; SVG pliku 34 px, obraz szkicu/wyciągnięcia 38 px,
  lustro 36 px; oryginalne kolory oraz odwrócenie obrazów w stanie aktywnym.
- Pionowy pasek narzędzi, rozwijane warianty prostokąta i okręgu.
- Kostka widoków: krążki 36 px, oryginalne kolory, przełączanie przeciwnej strony osi.
- Płaszczyzny ±23 mm i ich podświetlenie; gradient `#f9fbfe` → `#e4edf7`.
- Pole szkicu ±120 mm, rozszerzane zatwierdzoną geometrią; siatka o zmiennym
  zagęszczeniu, linie główne `#b3c7da`, pomocnicze `#d9e4ee` i obramowanie.
- Szary materiał RGB 138/138/144, czarne krawędzie i czerwony wybór krawędzi.
  Oświetlenie związane z kamerą i 24 stopnie jasności jak w rendererze HTML.
- Układ opcji wyciągnięcia po lewej i osobny pasek odległości/zatwierdzania.
- Czcionki tekstu DejaVu Sans, Sans Bold i Serif są dołączone do programu,
  wraz z licencją; nie wymagają instalowania na komputerze użytkownika.

## Przebieg projektowania

| HTML | Desktop 0.4 |
|---|---|
| Kliknięcie płaszczyzny / płaskiej ściany | Rzut promienia i aktywacja płaszczyzny szkicu |
| Prostokąt: narożniki, środek, trzy punkty | Te same punkty wejściowe; rzeczywiste krawędzie CAD |
| Okrąg: promień, średnica, 3 punkty, styczny do dwóch prostych | Te same gesty; dokładne krzywe OpenCascade |
| Elipsa, fasolka, wielokąt, łuk | Te same punkty; łuk: początek, koniec, punkt na łuku |
| Punkt i linia konstrukcyjna | Punkty odniesienia i kreskowana geometria pomocnicza, pomijana przy wyciąganiu |
| Tekst, obrót, krój i wyrównanie | Profile liter z rzeczywistymi otworami; orientacja czytelna w widoku |
| Tab / Enter podczas rysowania | Pola wymiarów przy kursorze i zatwierdzenie figury |
| Dwuklik wymiaru / narzędzie wymiaru | Edycja rekordu szkicu, zachowanie identyfikatora i wspólnych końców |
| Przyciąganie | Końce, środki, ćwiartki i przecięcia odcinków/okręgów |
| Nożyczki | Usunięcie fragmentu pomiędzy dokładnymi przecięciami krzywych |
| Kliknięcie zamkniętego obszaru | Obszary utworzone przez kontury, odcinki i łuki; także obszary przecięcia |
| Shift + klik profili | Wielokrotny wybór obszarów do jednej transakcji CAD |
| Wyciągnięcie: nowa / połącz / wytnij / część wspólna | Te same opcje przez silnik bryłowy Desktop |
| Jedna strona / symetria / dwie niezależne strony | Te same odległości i zakresy; dodatnie cięcie do wnętrza |
| Przeciąganie strzałki | Aktualizacja odległości i podglądu bez zapisu dokumentu |
| Zaokrąglenie i faza | Wybór krawędzi, uchwyt i automatyczny podgląd CAD |
| Przesunięcie i obrót | Pasek XYZ, trzy kolorowe osie i pierścienie obrotu; także dla szkiców |
| Odbicie | Obiekt → wskazana płaska ściana; kopia, zastąpienie lub połączenie z oryginałem |
| Boolean | Baza i narzędzia, z opcją zachowania narzędzi |
| Nawigacja | Lewy obrót poza szkicem, prawy / Shift + lewy przesunięcie, rolka zoom |
| Esc | Anulowanie pola / figury, potem zamknięcie narzędzia |

## Animacje i prezentacja zmian

Natywne animacje Qt odtwarzają najazd ikon (150/170 ms), aktywne pulsowanie
narzędzia (1800 ms), stany przycisków i komunikaty znikające ze zmianą
przezroczystości i przesunięciem (200 ms). Są również przejścia kamery i paneli,
podświetlenie wskazywanej geometrii, bieżący podgląd, uchwyty z oznaczeniami osi
oraz potwierdzenie zmiany kolorem. Film GIF pochodzi z rzeczywiście uruchomionej aplikacji.

Podgląd nie mutuje dokumentu. Spóźnione wyniki obliczeń są odrzucane.
Rozpoznawanie obszarów używa `BOPAlgo_Splitter` i `BOPAlgo_BuilderFace`.
Anulowanie rozpoznanych obszarów nie zapisuje zmian; ich materializacja i
wyciągnięcie tworzą jedną transakcję z poprawnym cofnięciem.

## Granice tej zgodności

Zakres dotyczy narzędzi projektowania nowych brył. Nie jest deklaracją
pikselowej identyczności każdego okna systemowego Windows i przeglądarki.
Nie przeniesiono importera plików SVG ani projektów JSON ze starego programu.
Formaty wymiany i projekty pozostają natywne dla Desktop: STEP/BREP/STL/DXF/RCCADX.
Nie dodano historii parametrycznych cech przebudowującej wcześniej wyciągniętą bryłę.
Dokładna geometria, tolerancje i wynik operacji pochodzą z OpenCascade,
więc nie odtwarzamy błędów ani artefaktów silnika siatkowego HTML.
