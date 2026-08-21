# Task t-017 — retrywrapper.execute_with_retry

## Kontext
Ein Retry-Wrapper für externe Aufrufe.

## Verhaltensvertrag (aus den Tests ersichtlich)
- `execute_with_retry(fn, max_retries, retry_on)`:
  - `fn` ist ein Callable, das einen Wert liefert oder eine Exception wirft
  - `retry_on` ist eine Liste von Exception-KLASSEN (z. B. [TimeoutError])
  - NUR Exceptions, die in `retry_on` sind (oder Unterklassen davon), werden
    wiederholt; ANDERE Exceptions propagieren SOFORT
  - max_retries = Anzahl der WIEDERHOLUNGEN (nicht der Gesamtversuche)
  - Nach Erschöpfung wird die LETZTE Exception propagiert (nicht die erste)
  - Ein Erfolg nach Retry liefert den Wert
  - Der Aufruf-Zähler muss exakt stimmen

## Aufgabe
Finde die Ursache(n) des Fehlers in `retrywrapper.py` und behebe sie.
Ändere NUR die Moduldatei, niemals die Testdatei.

## Verifikation
```
python3 -m pytest test_retrywrapper.py -q
```
