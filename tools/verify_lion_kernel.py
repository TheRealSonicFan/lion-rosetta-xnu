#!/usr/bin/python
from __future__ import print_function

import argparse
import hashlib
import sys

OLD = b"/usr/libexec/oah/RosettaNonGrata\x00"
NEW = b"/usr/libexec/oah/translate\x00"


def main():
    p = argparse.ArgumentParser(description="Inspect Rosetta architecture-handler signatures in a Lion mach_kernel.")
    p.add_argument("kernel")
    args = p.parse_args()

    with open(args.kernel, "rb") as f:
        data = f.read()

    old_count = data.count(OLD)
    new_count = data.count(NEW)
    digest = hashlib.sha256(data).hexdigest()

    print("sha256: %s" % digest)
    print("size: %d" % len(data))
    print("RosettaNonGrata signatures: %d" % old_count)
    print("translate signatures: %d" % new_count)

    if old_count == 1 and new_count == 0:
        print("state: unpatched Lion-style handler")
        return 1
    if old_count == 0 and new_count >= 1:
        print("state: Rosetta translate handler present")
        return 0

    print("state: ambiguous; do not install this kernel")
    return 2


if __name__ == "__main__":
    sys.exit(main())
