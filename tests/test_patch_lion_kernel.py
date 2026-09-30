#!/usr/bin/python
from __future__ import print_function

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATCHER = os.path.join(ROOT, "tools", "patch_lion_kernel.py")
OLD = b"/usr/libexec/oah/RosettaNonGrata\x00"
NEW = b"/usr/libexec/oah/translate\x00"


class PatcherTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.d)

    def run_patcher(self, data):
        src = os.path.join(self.d, "in")
        dst = os.path.join(self.d, "out")
        with open(src, "wb") as f:
            f.write(data)
        p = subprocess.Popen([sys.executable, PATCHER, src, dst], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = p.communicate()
        return p.returncode, dst, out, err

    def test_exactly_one_signature(self):
        original = b"AAA" + OLD + b"BBB"
        rc, dst, _, _ = self.run_patcher(original)
        self.assertEqual(rc, 0)
        with open(dst, "rb") as f:
            patched = f.read()
        self.assertEqual(len(patched), len(original))
        self.assertNotIn(OLD, patched)
        self.assertIn(NEW, patched)

    def test_missing_signature_refused(self):
        rc, dst, _, _ = self.run_patcher(b"no signature")
        self.assertEqual(rc, 2)
        self.assertFalse(os.path.exists(dst))

    def test_ambiguous_signature_refused(self):
        rc, dst, _, _ = self.run_patcher(OLD + OLD)
        self.assertEqual(rc, 2)
        self.assertFalse(os.path.exists(dst))


if __name__ == "__main__":
    unittest.main()
