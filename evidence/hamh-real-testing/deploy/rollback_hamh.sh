#!/usr/bin/env bash
# HAMH additive deployment rollback — operator-executed, reversible.
# Stops the resolver service, removes the deployed layer and restores the
# pre-deployment state (which was: no HAMH layer on the host).
set -euo pipefail

SERVICE=hamh-resolver.service
DEPLOY=/opt/dev-fabric/hamh

echo "== HAMH rollback"
if systemctl is-active --quiet "$SERVICE"; then
  systemctl stop "$SERVICE"
  echo "stopped $SERVICE"
fi
if systemctl is-enabled --quiet "$SERVICE" 2>/dev/null; then
  systemctl disable "$SERVICE"
  echo "disabled $SERVICE"
fi
rm -f /etc/systemd/system/$SERVICE
systemctl daemon-reload
if [ -d "$DEPLOY" ]; then
  rm -rf "$DEPLOY"
  echo "removed $DEPLOY"
fi
echo "== verify"
systemctl is-active "$SERVICE" 2>/dev/null || echo "service not active (expected)"
[ -d "$DEPLOY" ] && echo "DEPLOY STILL EXISTS" || echo "deploy dir removed (expected)"
ss -tlnp 2>/dev/null | grep 8090 && echo "PORT 8090 STILL LISTENING" || echo "port 8090 free (expected)"
echo "== ROLLBACK_OK"
