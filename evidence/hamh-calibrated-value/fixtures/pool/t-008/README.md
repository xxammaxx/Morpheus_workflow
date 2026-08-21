# Task t-008 — timetable.find_free_slot

## Kontext
Ein Terminplaner. `find_free_slot(busy, duration_min, start, end)` findet den
ersten freien Zeitraum eines Tages.

## Verhaltensvertrag (aus den Tests ersichtlich)
- ALLE Zeiten sind UTC (Projektkonvention); DST darf keine Rolle spielen
- `busy` ist eine Liste von (start_iso, end_iso)-Blöcken, ISO-Strings "YYYY-MM-DDTHH:MM:SSZ"
- `duration_min`: benötigte Minuten
- `start`/`end`: Suchfenster (ISO-Strings); der Slot muss vollständig im Fenster liegen
- Rückgabe: ISO-String des Slot-Beginns, oder None wenn kein Slot existiert
- Freie Slots beginnen direkt nach einem busy-Block (keine künstlichen Lücken)
- Busy-Blöcke können überlappen und unsortiert sein
- Der Slot darf busy-Blöcke NICHT berühren (weder Start- noch Endpunkt kollidieren)

## Aufgabe
Finde die Ursache(n) des Fehlers in `timetable.py` und behebe sie.
Ändere NUR die Moduldatei, niemals die Testdatei.

## Verifikation
```
python3 -m pytest test_timetable.py -q
```
