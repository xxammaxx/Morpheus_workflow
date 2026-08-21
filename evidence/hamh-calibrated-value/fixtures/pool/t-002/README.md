# Task t-002 — daterange.days_between

## Kontext
Ein kleines Datums-Hilfsmodul. `days_between(start, end)` liefert die Anzahl
der vollen Kalendertage zwischen zwei Datumsangaben (exklusiv des Endtages).

## Verhaltensvertrag (aus den Tests ersichtlich)
- Gleicher Tag: 0 Tage
- Aufeinanderfolgende Tage: 1 Tag
- Monats- und Jahresgrenzen (z. B. 31.12. -> 01.01.) müssen korrekt sein
- Schaltjahre (29.02.) müssen korrekt behandelt werden
- Parameter sind ISO-Strings "YYYY-MM-DD"; end liegt immer nach start

## Aufgabe
Finde die Ursache des Fehlers in `daterange.py` und behebe sie.
Ändere NUR die Moduldatei, niemals die Testdatei.

## Verifikation
```
python3 -m pytest test_daterange.py -q
```
