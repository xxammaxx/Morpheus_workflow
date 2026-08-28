# Morpheus Leitstand – Betriebsdokumentation

URL: `http://192.168.1.136:8092/` (8090 ist durch den bestehenden Resolver belegt)

Technischer Dienst: `morpheus-control-tower.service`, Benutzer `morpheus-ct`.
Release: `1.2.0` (Core `v1.0.0`, Morpheus `v1.1.2`, Leitstand `v1.2.0`).

```sh
systemctl status morpheus-control-tower
systemctl restart morpheus-control-tower
curl http://192.168.1.136:8092/healthz
journalctl -u morpheus-control-tower -n 100 --no-pager
```

Viewer-Token-Pfad: `/var/lib/morpheus-control-tower/viewer-token`, Modus `0600`.
Für Bedienung und Administration werden zusätzlich `operator_token` und
`admin_token` als systemd-Credentials verwendet. Der interne n8n-Webhook wird
über `command_token` authentifiziert.
Die Upstream-Zugangsdaten werden über systemd `LoadCredential` aus den
bestehenden n8n- und Harness-Pfaden eingespeist; kein Zugangswert wird im
Repository oder im Browser gespeichert. Die sichtbare Oberfläche ist Deutsch.

Die Datenquellen sind die öffentlichen n8n-Data-Tables `autodev_runs`,
`autodev_attempts` und optional `autodev_projects`, `autodev_issues`,
`autodev_events`, die n8n-Workflow-/Ausführungssicht und authentifizierte
Adapter-GET-Endpunkte. Der Browser aktualisiert einmal pro Sekunde, solange
der Tab sichtbar ist. Reads sind Projektionen; mutierende Aktionen laufen
über `POST /api/v1/commands` und werden ausschließlich an den allow-list-
basierten n8n-Webhook weitergeleitet. Es gibt keinen lokalen Run-State- oder
Event-Store.

Die Hauptansichten sind Übersicht, Projekte, Läufe, Anbieter, Systemkarte,
Datenfluss, Debugging und Administration. Operatoren dürfen laufbezogene
Aktionen ausführen; globale Routing-, Credential-, Service- und Release-
Aktionen erfordern Admin. `Anzeige pausieren` im Debugging stoppt nur die
UI-Nachführung und niemals den Run.

## Runtime-Telemetrie

`GET /api/v1/telemetry/runtime` ist eine authentifizierte, read-only Projektion
des Contracts `autodev.runtime-telemetry.v1`. Die Übersicht nutzt dieselbe
Projektion und pollt sie im bestehenden 1-Sekunden-Lifecycle; der
Backend-Cache coalesced Samples für mindestens zwei Sekunden. Es gibt keine
persistente Metrics-Datenbank. Kurze Sparklines stammen aus einem begrenzten
In-Memory-Ring; längere Containerverläufe werden, falls verfügbar, aus
Proxmox-RRD gelesen.

Proxmox wird ausschließlich über `status/current` und optional `rrddata`
abgefragt. Der Gast wird aus kanonischen Run-Metadaten und der serverseitigen
`MORPHEUS_RUNTIME_GUESTS`-Allowlist aufgelöst. GPU-Werte kommen ausschließlich
aus einer festen `nvidia-smi --query-*`-Feldliste. LM Studio ist optional und
wird nur über `GET /api/v1/models` beziehungsweise die kompatible Model-API
beobachtet; es wird keine Testinferenz erzeugt. GPU-Auslastung allein gilt
nicht als LM-Studio-Inferenz. Fehlende oder nicht unterstützte Werte bleiben
`null` und werden als `Nicht verfügbar` dargestellt.

Die Credentials `proxmox_api_token_secret` und ein optionales
`lmstudio_api_token` bleiben serverseitig und werden nie in Response, Logs,
Payload-Inspector oder Browser gespeichert. Proxmox benötigt eine explizite
CA-Datei (`PROXMOX_CA_FILE`) oder eine gleichwertige strikte Zertifikatspolitik;
TLS-Prüfung wird nicht deaktiviert.

Für neue Arbeit stehen bestehendes Issue, Repository-Analyse, Blueprint und
Neues Projekt aus Blueprint zur Verfügung. Blueprint-Intent wird strukturiert
validiert; die kanonische n8n-Continuation muss ihn dauerhaft im Repository
(bevorzugt `docs/blueprint.md`) sichern und Issue-/Dependency-Refresh nach
jedem DONE ausführen. Ohne aktuelle kanonische Projekt-/Issue-Tabellen zeigt
die UI `DERIVED` beziehungsweise `IDLE` und erfindet keine Daten.

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
