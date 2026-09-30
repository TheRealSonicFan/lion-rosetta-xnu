#!/usr/bin/python
from __future__ import print_function

import argparse
import hashlib
import os
import sys

OLD = b"/usr/libexec/oah/RosettaNonGrata\x00"
NEW_PATH = b"/usr/libexec/oah/translate\x00"
NEW = NEW_PATH + (b"\x00" * (len(OLD) - len(NEW_PATH)))


def sha256_bytes(data):
    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(
        description="Patch a Mac OS X Lion mach_kernel to select Rosetta translate instead of RosettaNonGrata."
    )
    parser.add_argument("input", help="input Lion mach_kernel")
    parser.add_argument("output", help="output patched kernel (must not be the input path)")
    args = parser.parse_args()

    in_path = os.path.abspath(args.input)
    out_path = os.path.abspath(args.output)
    if in_path == out_path:
        parser.error("refusing to overwrite the input kernel")

    with open(in_path, "rb") as f:
        data = f.read()

    count = data.count(OLD)
    if count != 1:
        print("error: expected exactly one RosettaNonGrata signature, found %d" % count, file=sys.stderr)
        return 2

    if len(NEW) != len(OLD):
        print("internal error: replacement length mismatch", file=sys.stderr)
        return 3

    patched = data.replace(OLD, NEW, 1)
    if len(patched) != len(data):
        print("internal error: kernel size changed", file=sys.stderr)
        return 4
    if patched.count(OLD) != 0:
        print("internal error: old signature remains", file=sys.stderr)
        return 5
    if patched.count(NEW_PATH) < 1:
        print("internal error: new signature missing", file=sys.stderr)
        return 6

    out_dir = os.path.dirname(out_path) or "."
    if not os.path.isdir(out_dir):
        print("error: output directory does not exist: %s" % out_dir, file=sys.stderr)
        return 7

    with open(out_path, "wb") as f:
        f.write(patched)

    try:
        st = os.stat(in_path)
        os.chmod(out_path, st.st_mode & 0o7777)
    except Exception:
        pass

    print("input_sha256  %s" % sha256_bytes(data))
    print("output_sha256 %s" % sha256_bytes(patched))
    print("input_size     %d" % len(data))
    print("output_size    %d" % len(patched))
    print("patched        %s" % out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
