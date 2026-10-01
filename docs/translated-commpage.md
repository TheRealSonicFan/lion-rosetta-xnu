# Translated commpage restoration design

## Target

This patch targets Apple XNU `xnu-1699.32.7` (Mac OS X 10.7.5) and restores the kernel-side commpage ABI required by the Snow Leopard 10.6.8 Rosetta 1 translator.

It is additive: Lion's native i386/x86_64 commpage behavior remains the baseline, while the Snow Leopard PPC-facing compatibility view is restored only for the 32-bit commpage.

## Why this is required

The first real PPC execution test on Lion entered `/usr/libexec/oah/translate` and then faulted at `0xffff8020`.

Snow Leopard's native 32-bit commpage starts at `0xffff0000`, the CPU-capability word is at offset `0x20`, and translated data is at `+0x8000`. Thus the Rosetta CPU-capability slot is `0xffff8020`.

## Patch structure

`patches/xnu-1699.32.7-rosetta-commpage.patch` is standalone and applies to an unmodified `xnu-1699.32.7` tree. Do not apply phase 1 first; phase 2 already contains the handler change.

It modifies `bsd/kern/bsd_init.c`, `osfmk/i386/cpu_capabilities.h`, `osfmk/i386/commpage/commpage.c`, `osfmk/conf/files.i386`, and `osfmk/conf/files.x86_64`, and adds `osfmk/i386/commpage/commpage_sigs.c`.

The added file is byte-for-byte identical to Apple XNU `xnu-1504.15.3` Git blob `0c100a2761ea07ab99c26b8a63bf3da4164b5cb5`.

## Native Lion ABI preservation

The patch does not replace Lion's commpage implementation with Snow Leopard's. Lion retains native commpage version 12, native CPU capabilities, the native CPU-family field, Lion's CPU-count fields, and the 64-bit commpage path.

The PPC-facing compatibility view separately publishes Snow Leopard commpage version 11.

This is necessary because Snow Leopard used native offsets `0x40` and `0x48` for floating constants while Lion uses `0x40` for `hw.cpufamily`. Phase 2 leaves `0xffff0040` as Lion's CPU-family field and writes the Snow Leopard constants only to their PPC-facing `+0x8000` locations.

## Restored mapping

The restored 32-bit mapping is `0xfffec000-0xfffff000` (19 pages), with the ordinary native commpage still starting at `0xffff0000`. The final 4 KB page of the 32-bit address space remains unused.

Lion's existing `vm_shared_region.c` already derives commpage creation and task mapping from these macros, so no separate VM source edit is needed.

## Restored compatibility contents

For the 32-bit commpage only, phase 2 restores the byte-swapped PPC version, synthetic PPC capability mask, PPC cache-line size, PPC-facing floating constants, all 24 Snow Leopard branch-assist descriptors, and the translated routine-signature table.

The 64-bit commpage explicitly skips these additions.

## Source validation

After applying the patch:

```sh
/usr/bin/python /path/to/lion-rosetta-xnu/tools/validate_rosetta_source.py /path/to/xnu-1699.32.7
```

This checks patch structure and ABI invariants. It does not substitute for compiling or boot-testing the kernel.

## Architecture build lists

Both `osfmk/conf/files.i386` and `osfmk/conf/files.x86_64` must include `osfmk/i386/commpage/commpage_sigs.c`. Both kernel architectures compile `commpage.c` and therefore both need definitions for `ba_descriptors` and `sigdata_descriptor`, even though the compatibility data is populated only into the shared 32-bit commpage.

## Lion INT3 initialization

Lion added an INT3 fill to `commpage_allocate()` that Snow Leopard did not have. Once the 32-bit allocation is enlarged for Rosetta, that fill must not span the entire allocation: doing so overwrites native commpage data and causes an early `nanotime trouble 1` panic. The phase-2 allocator now receives `base_offset` and initializes only the native text interval (`_COMM_PAGE_TEXT_START` through `_COMM_PAGE_END`). Extended compatibility pages remain zero-filled until Rosetta-specific population occurs. See `docs/boot-panic-nanotime.md`.
