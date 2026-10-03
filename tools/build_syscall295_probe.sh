#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SRC="$SCRIPT_DIR/syscall295_probe.c"
OUT="${1:-./syscall295-probe}"

[ -f "$SRC" ] || {
    echo "error: missing source: $SRC" >&2
    exit 66
}

resolve_compiler() {
    candidate="$1"
    [ -n "$candidate" ] || return 1
    if [ -x "$candidate" ]; then
        echo "$candidate"
        return 0
    fi
    command -v "$candidate" 2>/dev/null || return 1
}

is_i386_macho() {
    file="$1"
    if [ -x /usr/bin/lipo ]; then
        /usr/bin/lipo "$file" -verify_arch i386 >/dev/null 2>&1 && return 0
        /usr/bin/lipo -verify_arch i386 "$file" >/dev/null 2>&1 && return 0
    fi
    /usr/bin/file "$file" 2>/dev/null | /usr/bin/grep -Eiq 'i386'
}

try_compiler() {
    candidate="$1"
    compiler="$(resolve_compiler "$candidate" || true)"
    [ -n "$compiler" ] || return 1

    echo "Probing compiler: $compiler" >&2
    /bin/rm -f "$OUT"
    if "$compiler" -arch i386 -mmacosx-version-min=10.7 -Wall -Wextra         "$SRC" -o "$OUT"; then
        if [ -f "$OUT" ] && is_i386_macho "$OUT"; then
            CC_SELECTED="$compiler"
            return 0
        fi
    fi

    /bin/rm -f "$OUT"
    return 1
}

CC_SELECTED=""

if [ -n "${CC:-}" ]; then
    try_compiler "$CC" || true
fi

if [ -z "$CC_SELECTED" ]; then
    for candidate in         /usr/bin/gcc         /Developer/usr/bin/gcc         /Developer/usr/bin/llvm-gcc-4.2         /usr/bin/cc; do
        if try_compiler "$candidate"; then
            break
        fi
    done
fi

[ -n "$CC_SELECTED" ] || {
    echo "error: no installed compiler could build an i386 Lion-compatible probe" >&2
    echo "Install the Lion-era Developer Tools or set CC explicitly." >&2
    exit 69
}

/bin/chmod +x "$OUT"

echo "Using compiler: $CC_SELECTED"
/usr/bin/file "$OUT"
if [ -x /usr/bin/lipo ]; then
    /usr/bin/lipo -info "$OUT" || true
fi
/usr/bin/shasum -a 256 "$OUT" 2>/dev/null || true

is_i386_macho "$OUT" || {
    echo "error: output is not an i386 Mach-O executable" >&2
    exit 70
}

echo "Created: $OUT"
