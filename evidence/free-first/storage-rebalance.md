# Proxmox storage rebalance evidence

Run date: 2026-08-23. This records storage metadata only; no private host dump,
credential, disk content, or guest filesystem content is included.

## Measurements

| Storage | Before | After |
|---|---:|---:|
| `local-lvm` data | 94.41% | 62.68% |
| `local-lvm` metadata | 4.65% | 3.52% |
| `sata-local` data | 25.98% | 30.53% |
| `sata-local` metadata | 19.02% | 20.41% |

The PVE thin pools remained active and the cluster remained quorate. No
block-device-level thinpool manipulation was used.

## Guest inventory and move

Builder CTs 8000–8011 were individually identified from Proxmox configuration.
All were stopped and already owned by `sata-local`; canonical builder 8001 was
left untouched.

One safe move was performed:

- Guest: CT 122 (`paperless-ngx`), stopped and `onboot=0`.
- Source: `local-lvm:vm-122-disk-0`, configured size 50 GiB, 100% allocated.
- Target: `sata-local:vm-122-disk-0`, content type `rootdir` supported.
- Safety: current config digest checked; a NAS backup generation existed; a
  private configuration copy was retained; no task was in flight.
- Method: native Proxmox `pct move-volume 122 rootfs sata-local --delete 1`
  with the current config digest.
- Transfer: 21,694,115,741 bytes of regular file data; virtual volume size
  53,687,091,200 bytes.
- Result: guest remained stopped, configuration points to `sata-local`, and the
  source LV is absent after successful native move completion.

`VOLUMES_MOVED=1`; `VOLUMES_DELETED=0` means no guest or independent data volume
was destroyed. The source LV removal was the successful completion step of the
documented move, not a destroy operation.

No active n8n, Paperless, WireGuard, gateway, or canonical builder guest was
moved. No `pct destroy`, `qm destroy`, `lvremove`, or storage configuration
change was performed.

## Classification

`LOCAL_LVM_REBALANCE=PASS_SAFE_NATIVE_MOVE`

The remaining `local-lvm` pressure is materially reduced and below the stated
90% target. `sata-local` retains substantial free capacity.
