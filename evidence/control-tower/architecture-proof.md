# Control Tower architecture proof

```text
CONTROL_TOWER_READ_ONLY=IMPLEMENTED
N8N_REMAINS_CONTROL_PLANE=true
DIRECT_N8N_DB_ACCESS=false
CONTROL_TOWER_WRITE_ENDPOINTS=0
UPSTREAM_METHODS=GET_ONLY
LLM_CONTROLLER=false
PRIVATE_LAN_ONLY=true
```

The BFF is a same-origin Python stdlib service. Credentials are server-side
LoadCredential inputs; the UI receives operational metadata only.
