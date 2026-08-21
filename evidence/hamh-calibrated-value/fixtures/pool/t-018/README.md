# Task t-018 — scheduler.next_due

## Kontext
Ein Task-Scheduler. `next_due(tasks, now)` liefert den nächsten fälligen Task.

## Verhaltensvertrag (aus den Tests ersichtlich)
- tasks: Liste von {"name", "due_at" (ISO-Zeitstring "YYYY-MM-DDTHH:MM:SSZ",
  UTC), "priority" (int, höher = wichtiger), "created_at" (ISO-String)}
- `next_due` liefert den Task mit der FRÜHESTEN due_at, der NICHT vor `now`
  liegt (due_at >= now); bei gleicher due_at gewinnt die HÖHERE Priorität;
  bei gleicher due_at UND gleicher Priorität gewinnt der FRÜHER erstellte
  (stabile Reihenfolge, README-Konvention)
- Gibt es keinen Task mit due_at >= now, liefert die Funktion None
- `now` ist ein ISO-String; Vergleiche sind exakte Zeitvergleiche (UTC)
- Es dürfen nur Tasks zurückgegeben werden, deren due_at NICHT in der
  Vergangenheit liegt (relative zu now)

## Aufgabe
Finde die Ursache(n) des Fehlers in `scheduler.py` und behebe sie.
Ändere NUR die Moduldatei, niemals die Testdatei.

## Verifikation
```
python3 -m pytest test_scheduler.py -q
```
