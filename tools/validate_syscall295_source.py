#!/usr/bin/python
from __future__ import print_function

import argparse
import os
import re
import sys


SYSCALL_295 = (
    "295\tAUE_NULL\tALL\t{ int shared_region_map_np(int fd, uint32_t count, "
    "const struct shared_file_mapping_np *mappings) NO_SYSCALL_STUB; }"
)

SYSCALL_438 = (
    "438\tAUE_NULL\tALL\t{ int shared_region_map_and_slide_np(int fd, "
    "uint32_t count, const struct shared_file_mapping_np *mappings, "
    "uint32_t slide, uint64_t* slide_start, uint32_t slide_size) "
    "NO_SYSCALL_STUB; }"
)


def read_text(path):
    with open(path, "rb") as f:
        data = f.read()
    if sys.version_info[0] >= 3:
        return data.decode("utf-8")
    return data


def require(errors, cond, message):
    if not cond:
        errors.append(message)


def function_body(text, name, next_name):
    start = text.find("\n%s(" % name)
    if start < 0:
        start = text.find("\n%s\n" % name)
    if start < 0:
        return ""
    end = text.find("\n%s(" % next_name, start + 1)
    if end < 0:
        end = text.find("\n%s\n" % next_name, start + 1)
    if end < 0:
        end = len(text)
    return text[start:end]


def main():
    ap = argparse.ArgumentParser(
        description="Validate the Lion Rosetta syscall-295 compatibility experiment source."
    )
    ap.add_argument(
        "xnu_root", nargs="?", default=".",
        help="patched xnu-1699.32.7 source root"
    )
    args = ap.parse_args()
    root = os.path.abspath(args.xnu_root)

    paths = {
        "syscalls": "bsd/kern/syscalls.master",
        "vm_unix": "bsd/vm/vm_unix.c",
        "shared_h": "osfmk/mach/shared_region.h",
        "vm_shared": "osfmk/vm/vm_shared_region.c",
    }

    errors = []
    data = {}
    for key, rel in paths.items():
        path = os.path.join(root, rel)
        if not os.path.isfile(path):
            errors.append("missing: %s" % rel)
        else:
            data[key] = read_text(path)

    if errors:
        for error in errors:
            print("FAIL:", error)
        return 2

    syscalls = data["syscalls"]
    vm_unix = data["vm_unix"]
    shared_h = data["shared_h"]
    vm_shared = data["vm_shared"]

    require(errors, SYSCALL_295 in syscalls,
            "syscall 295 does not expose the restored shared_region_map_np ABI")
    require(errors,
            "295\tAUE_NULL\tALL\t{ int nosys(void); } { old shared_region_map_np }" not in syscalls,
            "syscall 295 still routes to nosys")
    require(errors, syscalls.count("295\tAUE_NULL\tALL\t") == 1,
            "syscall 295 entry count is not exactly one")
    require(errors, SYSCALL_438 in syscalls,
            "Lion syscall 438 shared_region_map_and_slide_np changed unexpectedly")

    match = re.search(
        r"\nint\nshared_region_map_np\(.*?\n\}\n\nint\n_shared_region_slide\(",
        vm_unix, re.S
    )
    require(errors, match is not None,
            "shared_region_map_np compatibility front-end was not found in vm_unix.c")
    body = match.group(0) if match else ""

    require(errors, "stack_mappings[8]" in body,
            "compatibility front-end does not preserve the eight-mapping limit")
    require(errors, "mappings_count > 8" in body,
            "compatibility front-end does not reject mapping counts above eight")
    require(errors, "mappings_count == 0" in body and "return 0;" in body,
            "compatibility front-end does not preserve zero-mapping success")
    require(errors, "shared_region_copyin_mappings(p, uap->mappings" in body,
            "compatibility front-end does not reuse Lion shared_region_copyin_mappings")
    require(errors, "_shared_region_map(p, uap->fd, mappings_count, mappings," in body,
            "compatibility front-end does not reuse Lion _shared_region_map")
    require(errors, "NULL, NULL" in body,
            "compatibility front-end unexpectedly requests sliding")
    require(errors, "P_TRANSLATED" not in body,
            "compatibility front-end is incorrectly gated on P_TRANSLATED")
    require(errors, "fp_lookup(" not in body and "vnode_getattr(" not in body,
            "compatibility front-end duplicates Lion's lower mapping implementation")

    layout = (
        "struct shared_file_mapping_np {\n"
        "\tmach_vm_address_t\tsfm_address;\n"
        "\tmach_vm_size_t\t\tsfm_size;\n"
        "\tmach_vm_offset_t\tsfm_file_offset;\n"
        "\tvm_prot_t\t\tsfm_max_prot;\n"
        "\tvm_prot_t\t\tsfm_init_prot;\n"
        "};"
    )
    require(errors, layout in shared_h,
            "shared_file_mapping_np layout differs from the expected Lion/Snow Leopard ABI")
    require(errors, "int\tshared_region_map_np(int fd," in shared_h,
            "shared_region_map_np declaration is missing from shared_region.h")
    require(errors, "VM_PROT_SLIDE  0x20" in shared_h,
            "Lion VM_PROT_SLIDE definition is missing")

    require(errors, "int\n_shared_region_map(" in vm_unix,
            "Lion _shared_region_map helper is missing")
    require(errors, "int\nshared_region_copyin_mappings(" in vm_unix,
            "Lion shared_region_copyin_mappings helper is missing")
    require(errors, "vm_shared_region_map_file(shared_region," in vm_unix,
            "Lion _shared_region_map no longer routes into vm_shared_region_map_file")
    require(errors, "mapping_to_slide != NULL" in vm_shared,
            "vm_shared_region_map_file no longer tolerates a NULL slide-output pointer")

    if errors:
        for error in errors:
            print("FAIL:", error)
        return 1

    print("PASS: syscall 295 restores the Snow Leopard shared_region_map_np ABI")
    print("PASS: syscall 295 no longer routes to nosys")
    print("PASS: compatibility front-end preserves the 8-mapping limit")
    print("PASS: compatibility front-end reuses Lion mapping helpers")
    print("PASS: compatibility front-end does not request shared-cache sliding")
    print("PASS: compatibility front-end is not gated on P_TRANSLATED")
    print("PASS: Lion syscall 438 remains unchanged")
    print("PASS: shared_file_mapping_np layout remains compatible")
    print("PASS: Lion lower shared-region mapping machinery remains in use")
    return 0


if __name__ == "__main__":
    sys.exit(main())
