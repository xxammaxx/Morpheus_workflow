# Control Tower deployment proof

```text
CONTROL_TOWER_BIND=192.168.1.136
CONTROL_TOWER_PORT=8092
CONTROL_TOWER_NETWORK_BOUNDARY=PRIVATE_LAN_ONLY
CONTROL_TOWER_SERVICE=morpheus-control-tower.service
```

The service uses a dedicated non-login user and systemd hardening with
LoadCredential injection.

```text
CONTROL_TOWER_SERVICE_STATE=active
HEALTHZ=PASS
PORT_8090=OCCUPIED_BY_EXISTING_HAMH_RESOLVER
HARDENING=NoNewPrivileges,PrivateTmp,ProtectSystem=strict,ProtectHome,ProtectKernelTunables,ProtectKernelModules,ProtectControlGroups,LockPersonality,RestrictSUIDSGID
```
