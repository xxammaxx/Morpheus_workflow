# Task t-003 — csvfields.parse_csv_line

## Kontext
Ein Mini-CSV-Parser für einen Datenimport. `parse_csv_line(line)` zerlegt eine
CSV-Zeile in Felder.

## Verhaltensvertrag (aus den Tests ersichtlich)
- Felder werden per Komma getrennt
- Felder in doppelten Anführungszeichen dürfen Kommas enthalten
- Verdoppelte Anführungszeichen ("" ) innerhalb eines Felds sind ein escaped Quote
- Führende/nachfolgende Leerzeichen AUßERHALB von Quotes werden entfernt
- Innerhalb von Quotes bleiben Leerzeichen erhalten
- Leere Felder bleiben erhalten

## Aufgabe
Finde die Ursache des Fehlers in `csvfields.py` und behebe sie.
Ändere NUR die Moduldatei, niemals die Testdatei.

## Verifikation
```
python3 -m pytest test_csvfields.py -q
```
