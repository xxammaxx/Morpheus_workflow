# Task t-009 — packetparse.parse_packet

## Kontext
Ein Parser für ein binäres Netzwerkpaketformat. Pakete kommen als `bytes`.

## Paketformat (Doku)
```
[magic 2B, BIG-endian, 0xA5A5]
[version 1B]
[flags 1B]
[payload_len 2B, BIG-endian]   <- Länge NUR des Payloads
[payload payload_len B]
[checksum 1B]                  <- (Summe aller Bytes VOR dem Checksum) & 0xFF
```

## Verhaltensvertrag (aus den Tests ersichtlich)
- `parse_packet(data)` liefert dict: version, flags, payload (bytes), checksum_ok (bool)
- magic muss 0xA5A5 sein, sonst ValueError
- payload_len bestimmt die Payload-Länge EXAKT
- checksum_ok ist True genau dann, wenn die Prüfsumme stimmt
- Ungültige Längen (Daten zu kurz) → ValueError

## Aufgabe
Finde die Ursache(n) des Fehlers in `packetparse.py` und behebe sie.
Ändere NUR die Moduldatei, niemals die Testdatei.

## Verifikation
```
python3 -m pytest test_packetparse.py -q
```
