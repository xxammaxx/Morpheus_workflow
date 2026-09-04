# Builder fixture workspace recovery

## Creation-order recovery — 2026-09-02

Provider-free PVE/CT8001 reproduction: a disposable host-root-owned `0700`
workspace caused the first `pct exec` filesystem traversal to fail with
`EACCES`. CT8001 is unprivileged and container root maps to host
`100000:100000`, confirmed by `/etc/subuid` and `/etc/subgid`.

The corrected sequence is host mkdir, mapped owner, restrictive mode, host
stat verification, mapped traverse/read/write preflight, then `pct exec git
init`, followed by fixture materialization, hashing, and builder/bwrap use.
The mapping is resolved from deployment override, CT idmap, or host sub-id
allocation, with the documented CT8001 default as final fallback. No `0777`
or privileged LXC mode is used. Regression tests prove ordering and fail-closed
preflight behavior.
