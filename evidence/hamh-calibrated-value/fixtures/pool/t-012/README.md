# Task t-012 — dedup_refactor: gemeinsamen Kern einführen

## Kontext
Zwei Funktionen `format_short(value)` und `format_long(value)` enthalten
duplizierte Logik. Die Codebase soll eine zentrale Normalisierungsfunktion
`normalize(value)` bekommen, die BEIDE Funktionen verwenden.

## Verhaltensvertrag (aus den Tests ersichtlich)
- `normalize(value)` existiert und liefert einen String
- `format_short(value)` und `format_long(value)` liefern ihre dokumentierten
  Ergebnisse (Verhalten muss erhalten bleiben)
- `normalize` MUSS von beiden Format-Funktionen tatsächlich aufgerufen werden
  (der Test überwacht das)
- Der Aufruf von `normalize` erfolgt mit dem ROHEN Eingabewert (nicht mit
  einem bereits vorverarbeiteten Wert)

## Aufgabe
Diese Aufgabe ist ein REFACTOR: Es gibt keine klassischen "Bug-Zeilen".
Finde die Duplikation, entwirf `normalize`, stelle beide Funktionen darauf
um und stelle sicher, dass alle Tests grün sind.
Ändere NUR die Moduldatei, niemals die Testdatei.

## Verifikation
```
python3 -m pytest test_dedup_refactor.py -q
```
