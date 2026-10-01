#!/usr/bin/python
from __future__ import print_function
import argparse
import hashlib
import os
import re
import sys

EXPECTED_SIGS_GIT_BLOB = "0c100a2761ea07ab99c26b8a63bf3da4164b5cb5"

def read_bytes(path):
    with open(path, "rb") as f:
        return f.read()

def read_text(path):
    data = read_bytes(path)
    if sys.version_info[0] >= 3:
        return data.decode("utf-8")
    return data

def git_blob_sha1(data):
    if sys.version_info[0] >= 3 and not isinstance(data, bytes):
        data = data.encode("utf-8")
    header = ("blob %d\0" % len(data))
    if sys.version_info[0] >= 3:
        header = header.encode("ascii")
    h = hashlib.sha1()
    h.update(header)
    h.update(data)
    return h.hexdigest()

def require(errors, cond, message):
    if not cond:
        errors.append(message)

def main():
    ap = argparse.ArgumentParser(description="Validate the Lion Rosetta phase-2 XNU source patch.")
    ap.add_argument("xnu_root", nargs="?", default=".", help="patched xnu-1699.32.7 source root")
    args = ap.parse_args()
    root = os.path.abspath(args.xnu_root)
    rel = {
        "bsd": "bsd/kern/bsd_init.c",
        "cpu": "osfmk/i386/cpu_capabilities.h",
        "comm": "osfmk/i386/commpage/commpage.c",
        "sigs": "osfmk/i386/commpage/commpage_sigs.c",
        "conf_i386": "osfmk/conf/files.i386",
        "conf_x86_64": "osfmk/conf/files.x86_64",
    }
    errors = []
    data = {}
    for key, name in rel.items():
        path = os.path.join(root, name)
        if not os.path.isfile(path):
            errors.append("missing: %s" % name)
        else:
            data[key] = read_text(path)
    if errors:
        for e in errors:
            print("FAIL:", e)
        return 2

    bsd, cpu, comm, sigs = data["bsd"], data["cpu"], data["comm"], data["sigs"]
    conf_i386, conf_x86_64 = data["conf_i386"], data["conf_x86_64"]
    require(errors, '.path = "/usr/libexec/oah/translate",' in bsd, "PowerPC handler is not translate")
    require(errors, "_COMM_PAGE32_AREA_LENGTH\t( 19 * 4096 )" in cpu, "32-bit area length is not 19 pages")
    require(errors, "_COMM_PAGE32_BASE_ADDRESS\t( 0xfffec000 )" in cpu, "32-bit base is not 0xfffec000")
    require(errors, "_COMM_PAGE32_START_ADDRESS\t( 0xffff0000 )" in cpu, "native start is not 0xffff0000")
    require(errors, "_COMM_PAGE32_AREA_USED\t\t( 19 * 4096 )" in cpu, "populated area is not 19 pages")
    require(errors, "_COMM_PAGE32_SIGS_OFFSET\t0x8000" in cpu, "translated offset is not 0x8000")
    require(errors, "_COMM_PAGE_THIS_VERSION\t\t12" in cpu, "Lion native commpage version 12 not preserved")
    require(errors, "_COMM_PAGE_ROSETTA_VERSION\t11" in cpu, "Rosetta compatibility version is not 11")

    require(errors, "#include <libkern/OSByteOrder.h>" in comm, "explicit OSByteOrder include missing")
    require(errors, "commpage_stuff_rosetta_swap" in comm, "Rosetta byte-swap helper missing")
    require(errors, all(x in comm for x in ("OSWriteSwapInt16","OSWriteSwapInt32","OSWriteSwapInt64")), "byte-swap widths incomplete")
    require(errors, "rosetta_caps = 0x44" in comm, "PPC capability baseline missing")
    require(errors, "rosetta_caps |= 0x101" in comm, "Altivec/data-stream synthesis missing")
    require(errors, "commpage_stuff(_COMM_PAGE_CPUFAMILY, &cfamily, 4);" in comm, "Lion CPU-family field not preserved")
    require(errors, "for (rd = ba_descriptors; *rd != NULL; rd++)" in comm, "branch-assist population missing")
    require(errors, "commpage_stuff_routine(&sigdata_descriptor);" in comm, "signature population missing")
    require(errors, "TRUE,\t\t/* restore Rosetta translated commpage ABI */" in comm, "32-bit compatibility enable missing")
    require(errors, "FALSE,\t\t/* no Rosetta compatibility data in the 64-bit commpage */" in comm, "64-bit compatibility guard missing")
    require(errors, conf_i386.count("osfmk/i386/commpage/commpage_sigs.c\tstandard") == 1, "commpage_sigs.c i386 build entry count != 1")
    require(errors, conf_x86_64.count("osfmk/i386/commpage/commpage_sigs.c\tstandard") == 1, "commpage_sigs.c x86_64 build entry count != 1")

    blob = git_blob_sha1(read_bytes(os.path.join(root, rel["sigs"])))
    require(errors, blob == EXPECTED_SIGS_GIT_BLOB, "commpage_sigs.c differs from xnu-1504.15.3 blob %s" % blob)

    addrs = [int(x,16) for x in re.findall(r"\{\s*&badata\[\s*\d+\],\s*4,\s*(0x[0-9a-fA-F]+),", sigs)]
    require(errors, len(addrs) == 24, "expected 24 branch assists, found %d" % len(addrs))
    sm = re.search(r"commpage_descriptor sigdata_descriptor\s*=\s*\{\s*sigdata,\s*sizeof\(sigdata\),\s*(0x[0-9a-fA-F]+)", sigs, re.S)

    base, start, end = 0xfffec000, 0xffff0000, 0xfffec000 + 19 * 4096
    critical = start + 0x20 + 0x8000
    require(errors, end == 0xfffff000, "restored range end mismatch")
    require(errors, critical == 0xffff8020, "critical translated capability address mismatch")
    for a in addrs:
        require(errors, base <= a < end, "branch assist outside range: 0x%08x" % a)
    require(errors, sm is not None, "sigdata descriptor address not found")
    if sm:
        a = int(sm.group(1),16)
        require(errors, a == 0xffff3000, "sigdata address is 0x%08x" % a)
        require(errors, base <= a < end, "sigdata outside restored range")

    if errors:
        for e in errors: print("FAIL:", e)
        return 1
    print("PASS: PowerPC handler -> /usr/libexec/oah/translate")
    print("PASS: Lion native commpage ABI remains version 12")
    print("PASS: Rosetta compatibility ABI is version 11 at +0x8000")
    print("PASS: 32-bit commpage range 0xfffec000-0xfffff000")
    print("PASS: translated CPU capabilities resolve to 0xffff8020")
    print("PASS: 24 branch-assist descriptors are in range")
    print("PASS: sigdata_descriptor is at 0xffff3000")
    print("PASS: commpage_sigs.c exactly matches xnu-1504.15.3")
    print("PASS: Lion native CPU-family population remains present")
    print("PASS: Rosetta data is enabled only for the 32-bit commpage")
    print("PASS: commpage_sigs.c is built into both I386 and X86_64 kernels")
    return 0

if __name__ == "__main__":
    sys.exit(main())
