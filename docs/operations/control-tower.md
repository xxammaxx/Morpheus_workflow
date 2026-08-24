# Morpheus Control Tower operations

URL: `http://192.168.1.136:8090/`

Service: `morpheus-control-tower.service`, dedicated user `morpheus-ct`.

```sh
systemctl status morpheus-control-tower
systemctl restart morpheus-control-tower
curl http://192.168.1.136:8090/healthz
journalctl -u morpheus-control-tower -n 100 --no-pager
```

Viewer token semantic path: `/var/lib/morpheus-control-tower/viewer-token`,
mode `0600`. Upstream credentials are injected through systemd LoadCredential
from the existing n8n API-key and Harness token paths; no values are stored in
the repository or browser.

Data sources are n8n Public API Data Tables `autodev_runs` and
`autodev_attempts`, n8n workflow/execution visibility, and authenticated
Adapter GET endpoints. The browser refreshes every five seconds while visible
and pauses when hidden. Upstream failures degrade each source independently;
missing data is never shown as healthy.

Rollback: stop the service and restore the previous `/opt/morpheus-control-tower`
build. Upgrade by deploying the reviewed tree, checking `/healthz`, and
restarting the service. No n8n restart is required.
