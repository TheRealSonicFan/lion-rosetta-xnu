#!/bin/bash
set -e

[ "$(id -u)" -eq 0 ] || { echo "error: run as root" >&2; exit 77; }

BACKUP="${1:-/var/backups/lion-rosetta/latest}"
[ -e "$BACKUP" ] || { echo "error: backup not found: $BACKUP" >&2; exit 66; }
BACKUP="$(cd "$BACKUP" && pwd -P)"
[ -f "$BACKUP/mach_kernel" ] || { echo "error: mach_kernel missing from backup" >&2; exit 66; }

/bin/cp -p "$BACKUP/mach_kernel" /mach_kernel
/usr/sbin/chown root:wheel /mach_kernel
/bin/chmod 644 /mach_kernel

KC_BACKUP="$BACKUP/System/Library/Caches/com.apple.kext.caches/Startup/kernelcache"
KC="/System/Library/Caches/com.apple.kext.caches/Startup/kernelcache"
if [ -f "$KC_BACKUP" ]; then
    /bin/mkdir -p "$(dirname "$KC")"
    /bin/cp -p "$KC_BACKUP" "$KC"
else
    /usr/sbin/kextcache -system-prelinked-kernel
fi

echo "Kernel rollback restored from: $BACKUP"
