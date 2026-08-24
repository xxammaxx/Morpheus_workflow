# Morpheus Leitstand – Betriebsdokumentation

URL: `http://192.168.1.136:8092/` (8090 ist durch den bestehenden Resolver belegt)

Technischer Dienst: `morpheus-control-tower.service`, Benutzer `morpheus-ct`.
Release: `1.1.2` (Core `v1.0.0`, Morpheus `v1.1.2`, Leitstand `v1.1.2`).

```sh
systemctl status morpheus-control-tower
systemctl restart morpheus-control-tower
curl http://192.168.1.136:8092/healthz
journalctl -u morpheus-control-tower -n 100 --no-pager
```

Viewer-Token-Pfad: `/var/lib/morpheus-control-tower/viewer-token`, Modus `0600`.
Die Upstream-Zugangsdaten werden über systemd `LoadCredential` aus den
bestehenden n8n- und Harness-Pfaden eingespeist; kein Zugangswert wird im
Repository oder im Browser gespeichert. Die sichtbare Oberfläche ist Deutsch.

Die Datenquellen sind die öffentlichen n8n-Data-Tables `autodev_runs` und
`autodev_attempts`, die n8n-Workflow-/Ausführungssicht und authentifizierte
Adapter-GET-Endpunkte. Der Browser aktualisiert alle fünf Sekunden, solange
der Tab sichtbar ist, und pausiert bei ausgeblendetem Tab. Die Darstellung
bleibt vollständig read-only; der Leitstand verwendet ausschließlich GET-
Aufrufe zu n8n und Adapter.

Aktive Zustände sind `ACCEPTED`, `BASELINING`, `RESEARCHING`, `PLANNING`,
`BUILDING`, `VERIFYING`, `REVIEWING`, `DECIDING`, `RUNNING` und `ACTIVE`.
Die 24-Stunden-Zähler verwenden UTC und bevorzugen `ended_at`, danach
`updated_at`; fehlende oder ungültige Zeitstempel werden nicht gezählt.
Ein aktiver Lauf wird standardmäßig nach `CONTROL_TOWER_STALE_RUN_SECONDS`
(1800 Sekunden) als veraltet gemeldet. Der kostenlose Anbieter-Pool ist erst
ab zwei geeigneten Anbietern gesund.

Rollback: Dienst stoppen und den vorherigen Build unter
`/opt/morpheus-control-tower` wiederherstellen. Für ein Upgrade den geprüften
Quellbaum ausrollen, `/healthz` prüfen und den Dienst neu starten. Ein n8n-
Neustart ist für reine Leitstand-Änderungen nicht erforderlich.
