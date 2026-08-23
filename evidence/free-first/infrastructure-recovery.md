# Infrastructure recovery evidence

Run date: 2026-08-23. Source repository: `xxammaxx/Morpheus_workflow`.

## Root filesystem

- `ROOT_FS_SOURCE=/dev/mapper/pve-root`
- `ROOT_FS_TYPE=ext4`
- `ROOT_TOTAL_BYTES=72845778944`
- Before recovery: `ROOT_USED_PERCENT=100`, `ROOT_FREE_BYTES=0`.
- After bounded recovery: `ROOT_USED_PERCENT=90`, `ROOT_FREE_BYTES=7007862784`.
- After deployment: `ROOT_FREE_BYTES=6927085568` (6.45 GiB by `df -B1`).
- `ROOT_BYTES_RECLAIMED=10738274304` by the `df` used-byte delta.
- Inodes remained healthy at 8% used.

Initial top-level consumers were `/var` (57.6 GB), `/var/lib/vz` (36.9 GB),
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

No active adapter state, token, API token, PVE configuration, VM/CT disk, NAS
data, Git worktree, provider credential, or Paperless data was removed.

`ROLLBACK_PRESERVED=true`; the pre-deployment rollback artifact was created and
SHA256-verified before deployment.

## Gate

`ROOT_RECOVERY_GATE=PASS` because free space exceeded 5 GiB and `df` reported
90% used (the configured limit is `<=90%`).
