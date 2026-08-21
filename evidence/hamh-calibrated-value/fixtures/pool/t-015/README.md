# Task t-015 — session.SessionManager

## Kontext
Ein Verbindungs-Manager mit Sequenz-Vertrag für einen Datenbank-Client.

## Verhaltensvertrag (aus den Tests ersichtlich)
- `connect()` öffnet eine Session; `request(payload)` sendet innerhalb einer
  Session; `close()` beendet die Session
- `request` OHNE aktive Session wirft `SessionError` (kein stiller Erfolg)
- `close` OHNE aktive Session wirft KEINEN Fehler (idempotent, gibt False zurück)
- `connect` bei bereits aktiver Session wirft `SessionError` (kein Doppel-Connect)
- Nach `close` ist eine neue `connect` möglich; alte Session-Daten (pending
  requests) dürfen NICHT in die neue Session übergehen
- `request` liefert die Anzahl bisheriger Requests in DIESER Session (1-basiert)

## Aufgabe
Finde die Ursache(n) des Fehlers in `session.py` und behebe sie.
Ändere NUR die Moduldatei, niemals die Testdatei.

## Verifikation
```
python3 -m pytest test_session.py -q
```
