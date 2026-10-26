# RCCAD

Samodzielna aplikacja CAD w pliku `RCCAD.html`.
Nie wymaga npm ani kompilacji. Z katalogu repozytorium uruchom:

```sh
python -m http.server 8000 --bind 127.0.0.1
```

Następnie otwórz plik HTML przez uruchomiony serwer w przeglądarce.
Zapis projektów i eksport korzystają z okna wyboru pliku, jeśli przeglądarka
je udostępnia, albo ze standardowego pobierania pliku.

Testy w przygotowanym środowisku:

```sh
python tests/test_browser.py
python tests/test_edge_tools.py
python tests/test_corner_blends.py
```

Wymagania testów: Python, Chromium oraz biblioteki z `tests/requirements.txt`.
Zainstaluj je poleceniem `python -m pip install -r tests/requirements.txt`.
Testy narożników używają Pillow do sprawdzania pikseli zrzutów ekranu.
Ścieżkę do Chromium można podać w `CHROMIUM_PATH`. Testy nie wymagają
uruchomionego serwera ani dostępu do Internetu; raport JSON wypisują na stdout,
a niepowodzenie dowolnego scenariusza daje kod wyjścia 1.

Zakres sprawdzeń i poprawki: [TEST_REPORT.md](TEST_REPORT.md).
