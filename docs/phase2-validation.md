# Phase-2 static validation record

The phase-2 patch was generated from these exact Apple OSS inputs:

| File | Tag | Git blob |
|---|---|---|
| `bsd/kern/bsd_init.c` | `xnu-1699.32.7` | `e60df12e0a66edc0c03248192dd35e438a3dc21b` |
| `osfmk/i386/cpu_capabilities.h` | `xnu-1699.32.7` | `eee6a8173eb72cffecb8e8e79ba9099b1411fcb4` |
| `osfmk/i386/commpage/commpage.c` | `xnu-1699.32.7` | `375abc7c1d95353f1f66f662d91c380ce9e7ca01` |
| `osfmk/conf/files.i386` | `xnu-1699.32.7` | `8c28645275d5d3e5e80f94da1ad9aa5293cff574` |
| `osfmk/i386/commpage/commpage_sigs.c` | `xnu-1504.15.3` | `0c100a2761ea07ab99c26b8a63bf3da4164b5cb5` |

Validated before publication:

- restored range is exactly `0xfffec000-0xfffff000`;
- the translated CPU-capability slot computes to `0xffff8020`;
- Lion native ABI remains version 12 and the translated view uses version 11;
- Lion's native CPU-family population remains present;
- all 24 branch-assist descriptors are within the restored mapping;
- `sigdata_descriptor` is `0xffff3000` and within the mapping;
- `commpage_sigs.c` is included exactly once in the i386 build list;
- 32-bit population enables Rosetta compatibility and 64-bit population disables it;
- every generated unified-diff section was reapplied in memory to the exact upstream base and matched the intended patched content byte-for-byte.

Compilation and boot/runtime validation are deliberately not claimed here; they require the historical Apple build environment and Lion test machine.
