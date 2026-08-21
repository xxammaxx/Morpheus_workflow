# Task t-005 — ratelimiter.TokenBucket

## Kontext
Ein Token-Bucket-Rate-Limiter für einen API-Client. Die Uhr wird als
Funktion injiziert (deterministische Tests).

## Verhaltensvertrag (aus den Tests ersichtlich)
- `consume(n)` gibt True zurück, wenn n Tokens verfügbar sind, sonst False
- Das Bucket füllt sich kontinuierlich mit `rate` Tokens pro Sekunde
- Das Bucket ist auf `capacity` begrenzt (überschüssige Tokens verfallen)
- Zu Beginn ist das Bucket VOLL (capacity)
- Zeit läuft nur vorwärts

## Aufgabe
Finde die Ursache(n) des Fehlers in `ratelimiter.py` und behebe sie.
Ändere NUR die Moduldatei, niemals die Testdatei.

## Verifikation
```
python3 -m pytest test_ratelimiter.py -q
```
