#!/bin/bash
set -u

PROBE="${1:-./syscall295-probe}"
LOG="${2:-./syscall295-probe.log}"

fail() {
    echo "error: $*" >&2
    exit 1
}

PRODUCT_VERSION="$(/usr/bin/sw_vers -productVersion 2>/dev/null || true)"
BUILD_VERSION="$(/usr/bin/sw_vers -buildVersion 2>/dev/null || true)"

[ "$PRODUCT_VERSION" = "10.7.5" ] || fail "requires Mac OS X 10.7.5 (found: $PRODUCT_VERSION)"
[ -x "$PROBE" ] || fail "missing or non-executable probe: $PROBE"

{
    echo "== Lion syscall-295 routing probe =="
    echo "product_version=$PRODUCT_VERSION"
    echo "build_version=$BUILD_VERSION"
    echo "kernel=$(/usr/bin/uname -a 2>/dev/null || /bin/uname -a 2>/dev/null || true)"
    echo "mach_kernel_sha256=$(/usr/bin/shasum -a 256 /mach_kernel 2>/dev/null | /usr/bin/awk '{print $1}')"
    /usr/bin/file "$PROBE"
    if [ -x /usr/bin/lipo ]; then
        /usr/bin/lipo -info "$PROBE" || true
    fi
    echo "probe_sha256=$(/usr/bin/shasum -a 256 "$PROBE" | /usr/bin/awk '{print $1}')"
    echo
    echo "== execution =="
} > "$LOG"

if [ -x /usr/bin/lipo ]; then
    if ! /usr/bin/lipo "$PROBE" -verify_arch i386 >/dev/null 2>&1 &&
       ! /usr/bin/lipo -verify_arch i386 "$PROBE" >/dev/null 2>&1; then
        echo "error: probe does not contain i386 architecture" | /usr/bin/tee -a "$LOG" >&2
        exit 70
    fi
else
    /usr/bin/file "$PROBE" | /usr/bin/grep -Eiq 'i386' || {
        echo "error: probe is not an i386 Mach-O executable" | /usr/bin/tee -a "$LOG" >&2
        exit 70
    }
fi

"$PROBE" 2>&1 | /usr/bin/tee -a "$LOG"
STATUS=${PIPESTATUS[0]}

echo "probe_exit_status=$STATUS" | /usr/bin/tee -a "$LOG"

if [ "$STATUS" -eq 0 ] &&
   /usr/bin/grep -Fq "RESULT: PASS - syscall 295 reached the compatibility front-end and returned EBADF" "$LOG"; then
    echo "RESULT: PASS" | /usr/bin/tee -a "$LOG"
    exit 0
fi

echo "RESULT: FAIL" | /usr/bin/tee -a "$LOG"
exit "$STATUS"
