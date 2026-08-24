# Control Tower security proof

```text
VIEWER_AUTH=constant_time_X-Control-Tower-Token
VIEWER_TOKEN_STORAGE=sessionStorage_only
UPSTREAM_CREDENTIAL_STORAGE=systemd_LoadCredential
NO_SECRET_FIELDS_IN_JSON=PASS
NO_RAW_UPSTREAM_ERRORS=PASS
NO_CORS_WILDCARD=PASS
NO_REQUEST_PATH_SHELL_EXECUTION=PASS
```

The adapter runtime route is authenticated with the existing
`X-Harness-Token` validator and performs no refresh or provider call.
