# Infrastructure recovery evidence

Run date: 2026-08-23. Source repository: `xxammaxx/Morpheus_workflow`.

## Root filesystem

- `ROOT_FS_SOURCE=/dev/mapper/pve-root`
- `ROOT_FS_TYPE=ext4`
- `ROOT_TOTAL_BYTES=72845778944`
- Before recovery: `ROOT_USED_PERCENT=100`, `ROOT_FREE_BYTES=0`.
- After initial bounded recovery: `ROOT_USED_PERCENT=90`, `ROOT_FREE_BYTES=7007862784`.
- Immediate post-deployment measurement: `ROOT_FREE_BYTES=6927085568` (6.45 GiB).
- A second read-only consumer refresh identified `/var/backups/n8n` at 15.9 GB:
  a 144-entry, 10-minute SQLite backup ring.
- After backup-ring cleanup and retention correction: `ROOT_USED_PERCENT=72`,
  `ROOT_FREE_BYTES=19922583552` (18.55 GiB).
- `ROOT_BYTES_RECLAIMED=23652995072` by the total initial-to-final `df`
  used-byte delta.
- Inodes remained healthy at 8% used.

Initial top-level consumers were `/var` (57.6 GB), `/var/backups/n8n` (15.9 GB),
`/var/lib/vz` (36.9 GB),
`/var/lib/vz/template/iso` (16.8 GB), `/var/lib/vz/images/108` (12.7 GB),
`/var/lib/vz/dump` (6.9 GB), `/var/lib/lxc/200` (4.3 GB), and `/root/.vscode-server`
(3.6 GB). VM/CT data, `/etc/pve`, NAS mounts, Paperless data, and unknown
directories were not deleted.

Journal usage was 121.0 MB and was not vacuumed. Deleted-open inspection found
only zero-sized temporary/runtime objects; no large reclaimable deleted-open file
was terminated or truncated.

## Bounded cleanup

Removed classes, after ownership and redundancy checks:

- two verified, redundant local Proxmox backup archives from 2024; newer matching
  backup generations were present on NAS and no active job targeted `local`;
- nine obsolete or partial Proxmox template/download-cache files;
- four inactive, older versioned VS Code Server cache directories, with no running
  VS Code Server process; the newest version was retained.
- 132 older n8n SQLite backup-ring files after the latest two and the retained
  current ring were integrity-checked; the backup script retention was corrected
  from 144 to 12 entries and its pre-change copy was preserved privately.

No active adapter state, token, API token, PVE configuration, VM/CT disk, NAS
data, Git worktree, provider credential, or Paperless data was removed.

`ROLLBACK_PRESERVED=true`; the pre-deployment rollback artifact was created and
SHA256-verified before deployment.

## Gate

`ROOT_RECOVERY_GATE=PASS` because the final free space is 18.55 GiB and `df`
reports 72% used (the configured limit is `<=90%`).
