# Task t-016 — cart + pricing Cross-File-Vertrag

## Kontext
Ein Warenkorb-Modul (`cart.py`) und ein Preis-Modul (`pricing.py`). Der
Warenkorb nutzt die Preis-Logik für Rabatte.

## Verhaltensvertrag (aus den Tests ersichtlich)
- `pricing.discount_for(quantity)` liefert den Rabatt-FAKTOR (0.0 = kein
  Rabatt, 0.1 = 10 %) für eine Menge
- `cart.calculate_total(items)` liefert die Gesamtsumme; items sind
  (name, unit_price, quantity)-Tupel
- Der Rabatt wird auf JEDE Position angewendet (Faktor auf den
  Positionspreis), NICHT auf die Gesamtsumme
- Der Rabatt hängt von der MENGE ab, nicht vom Preis
- Zwischensummen werden pro Position auf 2 Dezimalen gerundet

## Aufgabe
Finde die Ursache(n) des Fehlers in `cart.py` und/oder `pricing.py` und
behebe sie. Der Fehler kann in der VERBINDUNG zwischen beiden Modulen
liegen (Argument-Reihenfolge, Rückgabetyp, Semantik).
Ändere NUR die Moduldateien, niemals die Testdatei.

## Verifikation
```
python3 -m pytest test_cart.py -q
```
