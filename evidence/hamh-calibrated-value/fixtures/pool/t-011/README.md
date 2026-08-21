# Task t-011 — ordersummary.summarize

## Kontext
Ein Bestell-Modul. `summarize(items)` berechnet die Bestellsumme mit
Mengenrabatten, Rundung und Steuer.

## Verhaltensvertrag (aus den Tests ersichtlich)
- items: Liste von (name, unit_price, quantity)
- Mengenrabatt (pro Position): ab 10 Stück 5 %, ab 50 Stück 10 %
- Steuer: 19 % auf den RABATTIERTEN Positionspreis (netto), wird pro Position
  berechnet und gerundet (kaufmännisch, 2 Dezimalen), dann summiert
- Zwischensumme: Summe der rabattierten Nettopreise (gerundet auf 2 Dez.)
- Rückgabe: dict {subtotal, tax, total}
- total = subtotal + tax; beide Komponenten auf 2 Dezimalen
- Rundung: kaufmännisch (halbe Werte werden aufgerundet)

## Aufgabe
Finde die Ursache(n) des Fehlers in `ordersummary.py` und behebe sie.
Ändere NUR die Moduldatei, niemals die Testdatei.

## Verifikation
```
python3 -m pytest test_ordersummary.py -q
```
