# Task t-021 — overbook.check_conflicts

## Kontext
Eine Belegungsprüfung für Ressourcenbuchungen (Konferenzräume).

## Verhaltensvertrag (aus den Tests ersichtlich)
- `check_conflicts(bookings)` liefert True, wenn zwei Buchungen kollidieren,
  sonst False
- Eine Buchung ist (resource, start_iso, end_iso) mit "YYYY-MM-DDTHH:MM:SSZ"
- Kollision: Zwei Buchungen DERSELBEN Ressource überlappen im Zeitraum
- Zwei Buchungen, die sich nur BERÜHREN (eine endet exakt, wenn die andere
  beginnt), kollidieren NICHT (halb-offene Intervalle [start, end))
- Buchungen können unsortiert sein; eine Buchung, die eine andere komplett
  umschließt, kollidiert
- Identische Buchungen derselben Ressource kollidieren
- Buchungen unterschiedlicher Ressourcen kollidieren nie
- Eine einzelne Buchung kollidiert nie; leere Liste: False

## Aufgabe
Finde die Ursache(n) des Fehlers in `overbook.py` und behebe sie.
Ändere NUR die Moduldatei, niemals die Testdatei.

## Verifikation
```
python3 -m pytest test_overbook.py -q
```
