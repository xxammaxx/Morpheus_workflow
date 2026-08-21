# Task t-019 — account transfer invariants

## Kontext
Ein Kontomodul mit Buchungslogik. Es gelten zwei Invarianten (Projektregel):
- Invariante 1: Ein Konto kann NIE unter 0 fallen
- Invariante 2: Die Summe aller Kontostände ist über alle Operationen
  KONSTANT (Geld wird nur verschoben, nie erzeugt/vernichtet) —
  ausgenommen `deposit`, das Geld hinzufügt

## Verhaltensvertrag (aus den Tests ersichtlich)
- `Account(balance)` erzeugt ein Konto; `balance()` liefert den Stand
- `deposit(amount)` erhöht; `withdraw(amount)` verringert (bei unzureichendem
  Stand: ValueError, Stand unverändert)
- `transfer(from, to, amount)` verschiebt Geld: from verliert, to gewinnt;
  bei unzureichendem from-Stand: ValueError, BEIDE Konten unverändert
- Invariante 2 gilt nach JEDER erfolgreichen transfer-Operation
- `ledger()` liefert die Liste aller Buchungen ("deposit"/"withdraw"/"transfer")
  mit Beträgen (positive Werte); die Summe der transfer-Beträge muss
  konsistent mit den Kontoständen sein (jede transfer-Buchung bewegt den
  Betrag von from zu to)

## Aufgabe
Finde die Ursache(n) des Fehlers in `account.py` und behebe sie.
Ändere NUR die Moduldatei, niemals die Testdatei.

## Verifikation
```
python3 -m pytest test_account.py -q
```
