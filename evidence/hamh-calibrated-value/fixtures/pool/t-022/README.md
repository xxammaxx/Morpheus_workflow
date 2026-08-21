# Task t-022 — rangevalidator.validate_ranges

## Kontext
Ein Validator für Konfigurationsbereiche (z. B. Portbereiche, Altersbereiche).

## Verhaltensvertrag (aus den Tests ersichtlich)
- `validate_ranges(ranges, lo, hi)` validiert eine Liste von (start, end)-
  Bereichen gegen das erlaubte Fenster [lo, hi]
- Ein Bereich ist gültig, wenn er VOLLSTÄNDIG im Fenster liegt (inklusiv:
  start >= lo UND end <= hi)
- start muss <= end sein (einzelner Punkt erlaubt: start == end)
- Bereiche dürfen sich gegenseitig überlappen (kein Problem)
- Rückgabe: Liste der INVALIDEN Bereiche (unverändert als Tupel)
- Ein Bereich, der das Fenster nur berührt (end == hi oder start == lo),
  ist gültig
- Fehlerhafte Eingaben (start > end) sind invalide

## Aufgabe
Finde die Ursache(n) des Fehlers in `rangevalidator.py` und behebe sie.
Ändere NUR die Moduldatei, niemals die Testdatei.

## Verifikation
```
python3 -m pytest test_rangevalidator.py -q
```
