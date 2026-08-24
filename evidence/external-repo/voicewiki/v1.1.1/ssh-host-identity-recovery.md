# SSH host identity recovery

- Resolved host: `pve` → `192.168.1.136`
- Network-presented ED25519 fingerprint: `SHA256:Ckn3kCc3ajtRuujNUphfm7AL4g82R+bkLV4uSzfY7Vw`
- Authoritative source: strict existing IP connection, verified directly on PVE with `/etc/ssh/ssh_host_ed25519_key.pub`
- Identity comparison: PASS
- `known_hosts`: backed up locally and repaired only for `pve` and `192.168.1.136`
- Strict IP connection and secondary PVE identity checks: PASS

The `pve` alias remains unusable for passwordless login because its user-auth method is rejected; deployment used the cryptographically verified IP endpoint.
