# Task t-006 — deepmerge.merge

## Kontext
Ein Deep-Merge-Helper für verschachtelte Konfigurationen. `merge(base, override)`
liefert einen NEUEN Wert (base wird nicht verändert) und wendet override-Regeln
auf beliebige Tiefe an.

## Verhaltensvertrag (aus den Tests ersichtlich)
- Verschachtelte Dicts werden rekursiv gemerged (nicht ersetzt)
- Bei Konflikten gewinnt override
- Listen werden KONKATENIERT (override-Liste wird an base-Liste angehängt),
  nicht ersetzt (Projektkonvention!)
- Andere Typen (int, str, bool, None) werden durch override ersetzt
- `base` darf durch den Aufruf nicht mutiert werden
- Dicts und Listen in `base` dürfen nicht mutiert werden (keine Aliase)

## Aufgabe
Finde die Ursache(n) des Fehlers in `deepmerge.py` und behebe sie.
Ändere NUR die Moduldatei, niemals die Testdatei.

## Verifikation
```
python3 -m pytest test_deepmerge.py -q
```
