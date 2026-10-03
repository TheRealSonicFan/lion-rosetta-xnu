#!/usr/bin/python
from __future__ import print_function

import argparse
import os
import stat
import sys


OLD_SYSCALL = (
    "295\tAUE_NULL\tALL\t{ int nosys(void); } { old shared_region_map_np }"
)
NEW_SYSCALL = (
    "295\tAUE_NULL\tALL\t{ int shared_region_map_np(int fd, uint32_t count, "
    "const struct shared_file_mapping_np *mappings) NO_SYSCALL_STUB; }"
)

VM_INSERT_ANCHOR = "\nint\n_shared_region_slide(uint32_t slide,"

COMPAT_FUNCTION = """
/*
 * Compatibility entry point for Snow Leopard dyld/Rosetta.
 * Lion retained the mapping machinery but retired syscall 295.
 */
int
shared_region_map_np(
\tstruct proc\t\t\t\t*p,
\tstruct shared_region_map_np_args\t*uap,
\t__unused int\t\t\t\t*retvalp)
{
\tstruct shared_file_mapping_np\t*mappings;
\tstruct shared_file_mapping_np\tstack_mappings[8];
\tunsigned int\t\t\tmappings_count;
\tint\t\t\t\terror;

\tmappings_count = uap->count;
\tif (mappings_count > 8) {
\t\treturn EINVAL;
\t}

\tmappings = &stack_mappings[0];
\terror = shared_region_copyin_mappings(p, uap->mappings,
\t\t\t\t\t      mappings_count, mappings);
\tif (error) {
\t\treturn error;
\t}

\treturn _shared_region_map(p, uap->fd, mappings_count, mappings,
\t\t\t\t  NULL, NULL);
}

"""


def read_text(path):
    with open(path, "rb") as f:
        data = f.read()
    if sys.version_info[0] >= 3:
        return data.decode("utf-8")
    return data


def write_text_atomic(path, text):
    mode = stat.S_IMODE(os.stat(path).st_mode)
    temp = path + ".syscall295.tmp"
    data = text.encode("utf-8") if sys.version_info[0] >= 3 else text
    with open(temp, "wb") as f:
        f.write(data)
    os.chmod(temp, mode)
    os.rename(temp, path)


def classify_syscalls(text):
    old_count = text.count(OLD_SYSCALL)
    new_count = text.count(NEW_SYSCALL)
    if old_count == 1 and new_count == 0:
        return "unpatched"
    if old_count == 0 and new_count == 1:
        return "patched"
    return "invalid"


def classify_vm_unix(text):
    function_marker = "\nint\nshared_region_map_np(\n"
    marker_count = text.count(function_marker)
    exact_count = text.count(COMPAT_FUNCTION)
    anchor_count = text.count(VM_INSERT_ANCHOR)

    if marker_count == 0 and exact_count == 0 and anchor_count == 1:
        return "unpatched"
    if marker_count == 1 and exact_count == 1 and anchor_count == 1:
        return "patched"
    return "invalid"


def source_prerequisites(errors, vm_unix):
    if vm_unix.count("int\n_shared_region_map(") != 1:
        errors.append("expected exactly one Lion _shared_region_map() definition")
    if vm_unix.count("int\nshared_region_copyin_mappings(") != 1:
        errors.append("expected exactly one Lion shared_region_copyin_mappings() definition")
    if vm_unix.count(VM_INSERT_ANCHOR) != 1:
        errors.append("expected exactly one _shared_region_slide() insertion anchor")


def main():
    ap = argparse.ArgumentParser(
        description="Check or apply the Rosetta syscall-295 compatibility source edit."
    )
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true",
                       help="validate semantic anchors without modifying source")
    group.add_argument("--apply", action="store_true",
                       help="apply the semantic source edit atomically")
    ap.add_argument("xnu_root", nargs="?", default=".",
                    help="phase-2-patched xnu-1699.32.7 source root")
    args = ap.parse_args()

    root = os.path.abspath(args.xnu_root)
    syscalls_path = os.path.join(root, "bsd/kern/syscalls.master")
    vm_unix_path = os.path.join(root, "bsd/vm/vm_unix.c")

    for path in (syscalls_path, vm_unix_path):
        if not os.path.isfile(path):
            print("FAIL: missing:", path)
            return 2

    syscalls = read_text(syscalls_path)
    vm_unix = read_text(vm_unix_path)

    errors = []
    source_prerequisites(errors, vm_unix)

    syscalls_state = classify_syscalls(syscalls)
    vm_state = classify_vm_unix(vm_unix)

    if syscalls_state == "invalid":
        errors.append("syscalls.master is neither the expected Lion nor prepared syscall-295 state")
    if vm_state == "invalid":
        errors.append("vm_unix.c is neither the expected pre-experiment nor prepared compatibility state")
    if syscalls_state != vm_state:
        errors.append("source tree is partially applied: syscalls.master=%s vm_unix.c=%s" %
                      (syscalls_state, vm_state))

    print("syscalls.master state=%s" % syscalls_state)
    print("vm_unix.c state=%s" % vm_state)

    if errors:
        for error in errors:
            print("FAIL:", error)
        return 1

    if syscalls_state == "patched":
        print("PASS: syscall-295 compatibility source is already applied consistently")
        return 0

    print("PASS: semantic syscall-295 anchors are valid")
    if args.check:
        print("READY: no source file was modified")
        return 0

    new_syscalls = syscalls.replace(OLD_SYSCALL, NEW_SYSCALL, 1)
    new_vm_unix = vm_unix.replace(VM_INSERT_ANCHOR,
                                  "\n" + COMPAT_FUNCTION + "int\n_shared_region_slide(uint32_t slide,",
                                  1)

    if classify_syscalls(new_syscalls) != "patched":
        print("FAIL: internal syscalls.master transformation did not reach the expected state")
        return 2
    if classify_vm_unix(new_vm_unix) != "patched":
        print("FAIL: internal vm_unix.c transformation did not reach the expected state")
        return 2

    write_text_atomic(syscalls_path, new_syscalls)
    write_text_atomic(vm_unix_path, new_vm_unix)

    final_syscalls = classify_syscalls(read_text(syscalls_path))
    final_vm = classify_vm_unix(read_text(vm_unix_path))
    if final_syscalls != "patched" or final_vm != "patched":
        print("FAIL: post-write verification failed")
        return 2

    print("PASS: syscall 295 source edit applied atomically")
    print("PASS: only bsd/kern/syscalls.master and bsd/vm/vm_unix.c were modified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
