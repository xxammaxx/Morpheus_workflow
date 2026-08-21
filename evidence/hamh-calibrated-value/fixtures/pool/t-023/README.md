# Task t-023 — indexmap.window_items

## Kontext
Ein Helfer für Listen-Fenster (z. B. für eine Karussell-/Pager-Ansicht).

## Verhaltensvertrag (aus den Tests ersichtlich)
- `window_items(items, start, end)` liefert die Elemente im Index-Bereich
  [start, end) (start inklusiv, end EXKLUSIV)
- `start` darf negativ sein → zählt vom Listenende (Python-Semantik: -1 ist
  das letzte Element); der Bereich wird normalisiert (start >= 0)
- `end` darf über die Listenlänge hinausgehen → wird auf len(items) begrenzt
- `start` größer als `end` oder größer als die Listenlänge → leere Liste
- `end` == start → leere Liste
- Die Funktion muss mit leeren Listen und mit allen Grenzen robust sein

## Aufgabe
Finde die Ursache(n) des Fehlers in `indexmap.py` und behebe sie.
Ändere NUR die Moduldatei, niemals die Testdatei.

## Verifikation
```
python3 -m pytest test_indexmap.py -q
```
