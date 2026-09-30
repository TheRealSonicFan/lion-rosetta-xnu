#!/bin/bash
set -e

OUT="${1:-./mach_kernel.rosetta}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

[ -f /mach_kernel ] || { echo "error: /mach_kernel not found" >&2; exit 66; }
/usr/bin/python "$SCRIPT_DIR/patch_lion_kernel.py" /mach_kernel "$OUT"
/usr/bin/python "$SCRIPT_DIR/verify_lion_kernel.py" "$OUT"
echo "Staged only; no system file was modified."
