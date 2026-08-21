# Task t-014 — eventpipeline.process_events

## Kontext
Ein Event-Verarbeitungssystem. Events kommen mit `event_id` und `seq` an
(Out-of-order möglich). Die Verarbeitung ist idempotent und fehlerisoliert.

## Verhaltensvertrag (aus den Tests ersichtlich)
- `process_events(events, handle)` verarbeitet Events; `handle(event)` liefert
  None bei Erfolg oder eine Exception/Fehlermeldung bei Fehler
- JEDES Event mit eindeutiger `event_id` wird GENAU EINMAL an `handle`
  übergeben — auch wenn es doppelt in der Eingabe vorkommt (Idempotenz)
- Die Reihenfolge der Verarbeitung folgt `seq` (aufsteigend), NICHT der
  Eingabereihenfolge (Events können unsortiert ankommen)
- Fehler bei einem Event stoppen die Verarbeitung der ÜBRIGEN Events NICHT
  (Fehler-Isolation); fehlerhafte Events werden in der Rückgabe gemeldet
- Rückgabe: dict {"processed": int, "failed": [event_id, ...]}
- Leere Eingabe: processed 0, failed []

## Aufgabe
Finde die Ursache(n) des Fehlers in `eventpipeline.py` und behebe sie.
Ändere NUR die Moduldatei, niemals die Testdatei.

## Verifikation
```
python3 -m pytest test_eventpipeline.py -q
```
