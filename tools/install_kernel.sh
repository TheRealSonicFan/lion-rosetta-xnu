#!/bin/bash
set -e

usage() {
    echo "usage: sudo $0 /path/to/patched/mach_kernel" >&2
    exit 64
}

[ "$#" -eq 1 ] || usage
[ "$(id -u)" -eq 0 ] || { echo "error: run as root" >&2; exit 77; }

PRODUCT_VERSION="$(/usr/bin/sw_vers -productVersion 2>/dev/null || true)"
case "$PRODUCT_VERSION" in
    10.7|10.7.*) ;;
    *) echo "error: this installer is restricted to Mac OS X 10.7.x (found: $PRODUCT_VERSION)" >&2; exit 65 ;;
esac

SRC="$1"
[ -f "$SRC" ] || { echo "error: not a file: $SRC" >&2; exit 66; }
[ -f /mach_kernel ] || { echo "error: /mach_kernel not found" >&2; exit 66; }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
/usr/bin/python "$SCRIPT_DIR/verify_lion_kernel.py" "$SRC" || {
    echo "error: candidate kernel did not verify as patched" >&2
    exit 67
}

STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_ROOT="/var/backups/lion-rosetta/$STAMP"
KERNELCACHE="/System/Library/Caches/com.apple.kext.caches/Startup/kernelcache"

/bin/mkdir -p "$BACKUP_ROOT"
/bin/cp -p /mach_kernel "$BACKUP_ROOT/mach_kernel"
if [ -f "$KERNELCACHE" ]; then
    /bin/mkdir -p "$BACKUP_ROOT/System/Library/Caches/com.apple.kext.caches/Startup"
    /bin/cp -p "$KERNELCACHE" "$BACKUP_ROOT/System/Library/Caches/com.apple.kext.caches/Startup/kernelcache"
fi

/bin/cp -p "$SRC" /mach_kernel.rosetta.new
/usr/sbin/chown root:wheel /mach_kernel.rosetta.new
/bin/chmod 644 /mach_kernel.rosetta.new
/bin/mv -f /mach_kernel.rosetta.new /mach_kernel

if [ -x /usr/sbin/kextcache ]; then
    echo "Rebuilding system prelinked kernel/kernelcache..."
    if ! /usr/sbin/kextcache -system-prelinked-kernel; then
        echo "error: kextcache rebuild failed; restoring /mach_kernel from backup" >&2
        /bin/cp -p "$BACKUP_ROOT/mach_kernel" /mach_kernel
        echo "backup retained at: $BACKUP_ROOT" >&2
        exit 68
    fi
else
    echo "error: /usr/sbin/kextcache not found; restoring /mach_kernel" >&2
    /bin/cp -p "$BACKUP_ROOT/mach_kernel" /mach_kernel
    exit 69
fi

/bin/ln -sfn "$BACKUP_ROOT" /var/backups/lion-rosetta/latest

echo "Installed patched kernel."
echo "Backup: $BACKUP_ROOT"
echo "Before reboot, install/verify the companion Rosetta runtime."
echo "Rollback after booting another system if necessary: $SCRIPT_DIR/rollback_kernel.sh $BACKUP_ROOT"
