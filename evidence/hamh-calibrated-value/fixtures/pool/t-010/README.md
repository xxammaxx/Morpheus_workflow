# Task t-010 — paginatestream.fetch_all

## Kontext
Ein API-Client-Fetcher mit Offset-Pagination. `fetch_all(fetch, page_size)`
sammelt ALLE Elemente einer paginierten API.

## Verhaltensvertrag (aus den Tests ersichtlich)
- `fetch(offset, limit)` liefert `(items, next_offset, has_more)`:
  - items: Liste der Elemente dieser Seite
  - next_offset: Offset für die nächste Seite (0-basiert, inklusiv des
    nächsten ersten Elements)
  - has_more: True, wenn weitere Seiten existieren
- `fetch_all` sammelt Elemente, bis has_more False ist
- Elemente dürfen NICHT dupliziert werden
- `fetch_all` muss terminieren (keine Endlosschleife), auch wenn die API
  inkonsistente Offsets liefert (Schutz: max. 1000 Seiten)
- Leere Seiten mit has_more=False beenden die Iteration
- Die Reihenfolge der Elemente bleibt erhalten (Seite für Seite)

## Aufgabe
Finde die Ursache(n) des Fehlers in `paginatestream.py` und behebe sie.
Ändere NUR die Moduldatei, niemals die Testdatei.

## Verifikation
```
python3 -m pytest test_paginatestream.py -q
```
