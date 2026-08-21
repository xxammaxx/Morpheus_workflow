# Task t-007 — luhn.validate_card

## Kontext
Ein Zahlungsmodul mit Luhn-Prüfsummen-Logik. `validate_card(number)` prüft
eine Kreditkartennummer (nur Ziffern), `compute_check_digit(partial)` liefert
die Prüfziffer für einen Nummernstamm.

## Verhaltensvertrag (aus den Tests ersichtlich)
- Luhn-Algorithmus: von RECHTS nach links, jede zweite Ziffer (beginnend mit
  der zweiten von rechts) wird verdoppelt; bei Verdopplung > 9 wird 9
  subtrahiert (bzw. Ziffernsumme); Summe muss durch 10 teilbar sein
- `compute_check_digit` liefert die Ziffer, die die Summe auf Vielfaches von 10
  bringt (Wert 0-9)
- `validate_card` akzeptiert nur Ziffernstrings; Nicht-Ziffern → False
- Die Prüfziffer ist im Nummernstamm NICHT enthalten (Test prüft Stamm+Ziffer)

## Aufgabe
Finde die Ursache(n) des Fehlers in `luhn.py` und behebe sie.
Ändere NUR die Moduldatei, niemals die Testdatei.

## Verifikation
```
python3 -m pytest test_luhn.py -q
```
