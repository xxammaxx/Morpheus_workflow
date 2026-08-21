# Task t-020 — legacy parser Refactor mit Seiteneffekt-Erhalt

## Kontext
Ein Legacy-Parser mit zwei Einstiegsfunktionen `parse_csv(text)` und
`parse_tsv(text)`. Beide teilen fast dieselbe Logik. Die Codebase soll die
Duplikation durch eine gemeinsame Hilfsfunktion `_parse_delimited(text, delim)`
entfernen. Zusätzlich gibt es eine VERSTECKTE Anforderung: Beide
Einstiegsfunktionen müssen weiterhin jede Zeile über die Funktion
`normalize_line(line)` laufen lassen (Seiteneffekt-Kette, die von anderen
Komponenten beobachtet wird).

## Verhaltensvertrag (aus den Tests ersichtlich)
- `parse_csv(text)` → Liste von Listen (Zeilen → Felder); Komma-getrennt;
  leere Zeilen werden übersprungen; Felder werden getrimmt
- `parse_tsv(text)` → wie oben, aber Tab-getrennt; zusätzlich werden leere
  FELDER als None repräsentiert (Konvention des TSV-Formats)
- `normalize_line(line)` existiert und normalisiert eine Zeile (trimmen +
  Kollaps von Mehrfach-Leerzeichen); der Aufruf erfolgt durch die Parser
- Der Test überwacht, dass `normalize_line` von BEIDEN Parsern für JEDE
  nicht-leere Zeile genau einmal aufgerufen wird (Spy)
- Verhalten der öffentlichen Funktionen bleibt exakt erhalten

## Aufgabe
Führe den Refactor durch: gemeinsame `_parse_delimited` einführen, beide
Parser darauf umstellen, die Seiteneffekt-Kette (`normalize_line`) erhalten.
Ändere NUR die Moduldatei, niemals die Testdatei.

## Verifikation
```
python3 -m pytest test_legacy_parser.py -q
```
