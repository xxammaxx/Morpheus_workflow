# Control Tower deployment proof

```text
CONTROL_TOWER_BIND=192.168.1.136
CONTROL_TOWER_PORT=8090
CONTROL_TOWER_NETWORK_BOUNDARY=PRIVATE_LAN_ONLY
CONTROL_TOWER_SERVICE=morpheus-control-tower.service
```

The service uses a dedicated non-login user and systemd hardening with
LoadCredential injection. Final active-state and health output is recorded at
deployment completion.
