# Task t-004 — configloader.load_config

## Kontext
Ein Konfigurations-Loader für eine App. Er liest eine INI-artige Textdatei
und liefert ein Dict: Sektionen -> Option -> Wert.

## Verhaltensvertrag (aus den Tests ersichtlich)
- Format: `[sektion]`-Header, darunter `option = wert`-Zeilen
- Zeilen, die mit `#` beginnen, sind Kommentare und werden ignoriert
- Leerzeilen werden ignoriert
- Werte werden getrimmt; Werte dürfen Leerzeichen enthalten
- Optionen ohne Sektion (vor dem ersten Header) werden ignoriert
- Eine Option, die doppelt vorkommt, überschreibt die vorherige (letzte gewinnt)
- Optionen ohne `=` werden ignoriert

## Aufgabe
Finde die Ursache(n) des Fehlers in `configloader.py` und behebe sie.
Ändere NUR die Moduldatei, niemals die Testdatei.

## Verifikation
```
python3 -m pytest test_configloader.py -q
```
