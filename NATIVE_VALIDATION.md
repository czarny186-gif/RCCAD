# RCCAD Desktop — weryfikacja wydań

- Kod aplikacji: `d26080aab98417e72da23367ca65d681f26357c7`.
- Proces Windows: https://github.com/czarny186-gif/RCCAD/actions/runs/40385478786
- Wydanie: https://github.com/czarny186-gif/RCCAD/releases/tag/desktop-v0.1.0-3
- Paczka: `RCCAD-Desktop-Windows-x64.zip`, 208142177 bajtów.
- SHA-256: `29589c27d5fa267ec7dcde139fc3ecd08a3f8822540a69e41acea9314ea2d3a7`.

## Wykonane sprawdzenia

32 testy silnika CAD, formatu projektu i działań natywnego interfejsu przeszły
na Linuksie oraz w procesie Windows. Na Linuksie dodatkowo uruchomiono rzeczywisty
widok OpenGL na Xvfb/Mesa: renderowanie, kliknięcie krawędzi w widoku i wykonanie
zaokrąglenia. Zrzut obejmował bryłę z otworem i zaokrąglonymi narożnikami.

Proces Windows zainstalował przypięte zależności, zbudował aplikację przez
PyInstaller i uruchomił gotowy `RCCAD Desktop.exe --self-test`.
Raport dołączony do paczki potwierdza platformę `Windows-2025Server-10.0.26100-SP0`
oraz powodzenie:

- zaokrąglenia 12 krawędzi i wspólnych narożników;
- otworu, odejmowania Boolean i wyciągnięcia szkicu;
- cofania/ponawiania, projektu RCCADX, STEP i STL;
- ładowania Qt, drzewa obiektów, właściwości oraz projekcji i promienia wyboru.

Po publikacji pobrano publiczny plik ZIP. Sprawdzono integralność całego archiwum,
obecność programu PE Windows x64 (`MZ`, `PE`, maszyna `0x8664`), katalogu bibliotek
`_internal` oraz pozytywnego raportu `selftest_windows.json`.

Windows 10/11 x64 jest platformą docelową. Proces budowania uruchamia aplikację
na Windows Server 2025 w trybie testowym bez rzeczywistego okna GPU; nie zastępuje
to testów sterownika graficznego na komputerze użytkownika. Wydanie 0.1 jest
wersją rozwojową, a nie pełną implementacją funkcji starszego programu HTML.


## Wersja 0.3 — interfejs w stylu HTML (27.10.2026)

Moduł `native/rccad/kernel.py` jest identyczny jak w poprzednim EXE 0.2.
Nowa warstwa interakcji tworzy dokładne krzywe CAD i przekazuje operacje do
OpenCascade. Nie przeniesiono silnika geometrii ani obliczeń na siatkach z HTML.
Przeniesiono oryginalne ikony, układ pływających paneli, kostkę widoków i gesty.

Weryfikacja przed wydaniem:

- 48/48 testów jednostkowych/integracyjnych: dokładne profile i wyciągnięcia,
  łączenie wyciągnięć i otwory z sześciu stron, szkic na obróconej ścianie,
  profile wewnętrzne, zapis płaszczyzn, mysz/Qt, anulowanie i cofanie.
- 8/8 prób w rzeczywistym oknie Qt/OpenGL na Xvfb/Mesa: rysowanie figur,
  szkic na ścianie, wycięcie i undo/redo, uchwyty wyciągnięcia, przesunięcia
  i rozmiaru krawędzi, zastosowanie fazy/zaokrąglenia, anulowanie podglądu.
- Rzeczywiste renderowanie bez błędów OpenGL. Przy wielu oknach testowych
  włączono współdzielenie kontekstów Qt, zgodnie z globalną pamięcią shaderów pyqtgraph.
- Zwykły i rozszerzony test gotowości aplikacji: poprawny wynik; test gotowego
  EXE pozostaje obowiązkowym etapem Windows workflow przed publikacją paczki.

Podglądy działają w wątku roboczym. Spóźnione wyniki są odrzucane według generacji
narzędzia i rewizji dokumentu. Dopiero Zastosuj tworzy transakcję geometrii;
zużyte profile są ukrywane w tej samej transakcji, z poprawnym undo/redo.

Przykładowe zrzuty: [szkic](native/docs/szkic.png), [krawędzie](native/docs/krawedzie.png).
Nie deklarujemy pełnej zgodności narzędzi z HTML: tekst/SVG, zaawansowana edycja
istniejących figur i więzy parametryczne nie zostały przeniesione.


## Wersja 0.4 — projektowanie i wszystkie grafiki HTML (27.10.2026)

Przeniesiono wszystkie 24 grafiki kontrolek: 6 PNG, 15 SVG i 3 symbole.
Manifest zasobów zawiera hashe i identyfikatory z oryginalnego HTML.
Dołączono trzy czcionki DejaVu z licencją. Gradient, siatka, płaszczyzny,
materiał, krawędzie i perspektywa odtwarzają stałe i zachowanie renderera HTML.
Moduł `native/rccad/kernel.py` nadal pozostaje bez zmian.

76 testów obejmuje narzędzia z HTML, dokładne krzywe i tekst o zadanej wysokości,
nożyczki, przecięcia i styczność, zamknięte obszary (także z przecinających się
odcinków), dwustronne wyciągnięcia, zachowanie wspólnych punktów przy edycji,
wybór obszaru przecięcia, atomowe cofanie, lustro względem ściany i zasoby SVG/PNG.

Dwie serie prób w wyświetlonym oknie OpenGL to 8 poprzednich scenariuszy
modelowania i 12 kontraktów interfejsu/animacji. Zapis GIF powstał z klatek
rzeczywiście działającego okna, bez makiety. Testy przechwytują nieobsłużone
wyjątki ze slotów Qt, aby błąd obsługi myszy nie mógł dać fałszywego sukcesu.

Natywny `BOPAlgo_Splitter`/`BOPAlgo_BuilderFace` rozpoznaje obszary przed
wyciągnięciem. Sam wybór, podgląd i anulowanie nie zapisują ich w dokumencie.
Zatwierdzenie regionów i bryły jest jedną transakcją. Wspólne punkty szkicu
zmieniają się razem; błędy pozostawiają poprzednią geometrię.

Rozszerzony self-test gotowego EXE sprawdza również dołączone fonty i otwory
liter, 24 grafiki, analityczne przycinanie i natywne obszary przecięcia.
Workflow Windows blokuje publikację, jeżeli którykolwiek test nie przejdzie.
Szczegółowy zakres i granice zgodności: [HTML_PARITY.md](native/HTML_PARITY.md).
