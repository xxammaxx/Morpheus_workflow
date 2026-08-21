# Task t-001 — stringutils.is_palindrome

## Kontext
Eine kleine String-Utility-Bibliothek. Die Funktion `is_palindrome(s)` soll
prüfen, ob ein String ein Palindrom ist.

## Verhaltensvertrag (aus den Tests ersichtlich)
- Groß-/Kleinschreibung wird ignoriert ("Racecar" ist ein Palindrom)
- Nur alphanumerische Zeichen zählen; Satzzeichen/Leerzeichen werden ignoriert
- Leere Zeichenfolgen und reine Satzzeichen-Strings gelten als Palindrom
- Unicode-Buchstaben (z. B. "Ä") müssen korrekt behandelt werden

## Aufgabe
Finde die Ursache des Fehlers in `stringutils.py` und behebe sie.
Ändere NUR die Moduldatei, niemals die Testdatei.

## Verifikation
```
python3 -m pytest test_stringutils.py -q
```
