# Task t-013 — consistent_cache.TtlCache

## Kontext
Ein Cache mit Time-to-Live und Kapazitätsgrenze für einen Datenservice.

## Verhaltensvertrag (aus den Tests ersichtlich)
- `TtlCache(capacity, ttl_seconds, now)` — `now` ist eine injizierte Uhr
  (deterministische Tests); `get(key)` und `set(key, value)` als API
- `set` speichert value unter key mit Ablaufzeit now+ttl
- `get` liefert value, wenn vorhanden und nicht abgelaufen; sonst None
  (abgelaufene Einträge werden beim Zugriff entfernt)
- Bei Überschreitung der Kapazität wird der EINTRAG mit dem ÄLTESTEN
  Ablaufzeitpunkt entfernt (der zuerst abläuft)
- `get` verlängert die Lebensdauer NICHT (kein TTL-Refresh bei Reads)
- Der zurückgegebene Wert ist eine Kopie: Mutation des Rückgabewerts darf
  den Cache-Inhalt nicht verändern
- Nach Ablaufzeit liefert `get` None und der Eintrag ist weg (Größe sinkt)

## Aufgabe
Finde die Ursache(n) des Fehlers in `consistent_cache.py` und behebe sie.
Ändere NUR die Moduldatei, niemals die Testdatei.

## Verifikation
```
python3 -m pytest test_consistent_cache.py -q
```
