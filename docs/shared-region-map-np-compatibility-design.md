# Syscall 295 shared-region compatibility design

## Status

The postmortem confirmation gate is closed. The preserved Lion core proves that the cache-bypass failure is a call to legacy syscall 295 with the Snow Leopard `shared_region_map_np` ABI, not an inferred or adjacent failure.

The design has now been translated into a separate experiment-only source edit. `patches/xnu-1699.32.7-rosetta-syscall295.patch` remains the human-readable review diff, while `tools/apply_syscall295_source.py` is the authoritative application mechanism used by the experiment. The semantic applicator was added after a reused, otherwise validated Lion source tree rejected the context-sensitive `vm_unix.c` diff hunk. The edit is intentionally layered on top of the existing phase-2 patch and has not been folded into `xnu-1699.32.7-rosetta-commpage.patch`. The authoritative execution procedure is `docs/xnu-syscall-295-experiment.md`.

## Evidence that fixes the ABI

The non-debugged Rosetta core records an i386 syscall wrapper executing `int $0x80` and stopping at the following carry-test instruction with `EAX=0x4e` and carry set. The caller supplies syscall number `0x127` (295).

The reconstructed arguments are:

- file descriptor: 4
- mapping count: 3
- mapping array: `0xb7fff7b0`

Those three `shared_file_mapping_np` entries describe the validated Rosetta shared cache exactly:

| address | size | file offset | max/init protection |
|---|---:|---:|---:|
| `0x90000000` | `0x0918a000` | `0x00000000` | 5 / 5 |
| `0xa0000000` | `0x00ea0000` | `0x0918a000` | 3 / 3 |
| `0x9918a000` | `0x02764000` | `0x0a02a000` | 1 / 1 |

The final file range ends at `0x0c78e000`, exactly 209,248,256 bytes, the validated Snow Leopard Rosetta cache size.

Therefore syscall 295 is definitively the immediate boundary.

## Source baseline

The design was reviewed against these exact Apple OSS inputs:

| File | Tag | Git blob |
|---|---|---|
| `bsd/vm/vm_unix.c` | `xnu-1504.15.3` | `369c913505e8fd1dd8b963fbdfbfa5a7be382f14` |
| `bsd/vm/vm_unix.c` | `xnu-1699.32.7` | `0190e70f73081b00b99d15b1e3cf600c18c2c991` |
| `bsd/kern/syscalls.master` | `xnu-1504.15.3` | `00fb84082e93ff6cdc6cc33a3be52d9b904ca150` |
| `bsd/kern/syscalls.master` | `xnu-1699.32.7` | `009dd377b5e7fe3682e592170ee97a1ae4f952ce` |
| `osfmk/mach/shared_region.h` | `xnu-1504.15.3` | `1e2143e1aee2916f84a83bdf18184980abce9449` |
| `osfmk/mach/shared_region.h` | `xnu-1699.32.7` | `29ced2a401993ab94f79af30a3d8299643aa4a69` |
| `osfmk/vm/vm_shared_region.c` | `xnu-1699.32.7` | `a5931c9980a18ac807be74484e97be31e7c047dc` |
| `osfmk/vm/vm_shared_region.h` | `xnu-1699.32.7` | `51742f0b0053e900c6ff8f5245979331bf49ae80` |

## Important source result

The required mapping machinery was not removed from Lion.

Snow Leopard syscall 295 is:

`shared_region_map_np(int fd, uint32_t count, const struct shared_file_mapping_np *mappings)`.

Lion changes only syscall-table entry 295 to `nosys`, annotated `old shared_region_map_np`.

At the same time, Lion still:

- declares `shared_region_map_np()` in `osfmk/mach/shared_region.h`;
- keeps the same `shared_file_mapping_np` field layout;
- keeps PowerPC shared-region constants and `CPU_TYPE_POWERPC` handling;
- contains `shared_region_copyin_mappings()`;
- contains `_shared_region_map()`, which performs the file/vnode/security checks and calls `vm_shared_region_map_file()`;
- contains `vm_shared_region_map_file()`, whose own comment still describes it as the mechanism used by `shared_region_map_np()`;
- supports a null slide-output pointer in `vm_shared_region_map_file()`.

Lion's newer syscall 438, `shared_region_map_and_slide_np`, already uses those helpers. This means the old ABI can be restored as a thin compatibility front-end to Lion's existing implementation rather than by importing Snow Leopard's full syscall body.

## Proposed implementation boundary

The prepared experiment implementation follows this smallest practical surface:

1. Restore syscall-table entry 295 in `bsd/kern/syscalls.master` with the original three-argument Snow Leopard prototype and `NO_SYSCALL_STUB`.
2. Add a `shared_region_map_np` compatibility front-end in Lion `bsd/vm/vm_unix.c`.
3. Reuse Lion's `shared_region_copyin_mappings()` and `_shared_region_map()`.
4. Pass no slide request and no slide-output object. The validated Rosetta mappings use only ordinary protections 1, 3, and 5 and contain no `VM_PROT_SLIDE` bit.
5. Preserve the historical maximum of eight mapping records and the old ABI's invalid-count behavior. Do not short-circuit a zero mapping count before Lion's existing file-descriptor validation; Snow Leopard validated the fd before reaching its zero-count success path.
6. Keep Lion's own vnode, MAC, content-protection, root-volume, ownership, shared-region, and `VSHARED_DYLD` checks. Do not replace them with the older Snow Leopard checks.
7. Leave syscall 438 and Lion's sliding implementation unchanged.
8. Do not change `osfmk/vm/vm_shared_region.c` or `osfmk/mach/shared_region.h` unless static validation exposes a concrete need.

The compatibility entry should not be gated on `P_TRANSLATED`. The controlled direct-`translate` path is a required positive control and does not necessarily have the normal PPC exec activation state. The restored operation remains constrained by Lion's existing `_shared_region_map()` checks.

## Generated syscall interface

`bsd/kern/syscalls.master` is the authoritative syscall description. XNU's `bsd/kern/makesyscalls.sh` generates the syscall table, names, headers, prototypes, and audit glue from it.

The compatibility patch should modify the master definition rather than hand-maintaining generated syscall artifacts. The build must be checked to ensure the generated syscall-295 argument structure and dispatch entry match the restored three-argument ABI.

## Validation required before installation

The prepared `tools/validate_syscall295_source.py` checks the following before compilation:

- syscall 295 is no longer `nosys`;
- syscall 295 has exactly the Snow Leopard three-argument prototype;
- the compatibility front-end exists exactly once;
- the front-end reuses Lion's mapping helpers rather than duplicating the Snow Leopard body;
- syscall 438 remains unchanged;
- `shared_file_mapping_np` layout is not changed;
- no private Apple runtime material is introduced into the repository.

Both RELEASE_I386 and RELEASE_X86_64 kernels must compile because the project installs a universal Lion kernel.

## Safer post-boot preflight

Before Rosetta is rerun, use the prepared native i386 diagnostic in `tools/syscall295_probe.c`, built by `tools/build_syscall295_probe.sh` and executed through `tools/run_syscall295_probe.sh`. It invokes syscall 295 with an intentionally invalid file descriptor and one readable dummy mapping record.

The expected result is an ordinary `EBADF` syscall error, not `SIGSYS`. This proves that syscall 295 reaches the compatibility front-end without mapping a shared cache or launching Rosetta.

This probe is only a routing check. It does not replace the existing commpage regression test.

## First Rosetta test after the compatibility kernel

After installation and reboot:

1. Verify the running kernel identity and `kern.exec.archhandler.powerpc`.
2. Re-run the existing native i386 commpage probe and require `RESULT: PASS`.
3. Run the new syscall-295 routing probe and require the expected non-SIGSYS error.
4. Re-run the guarded direct private-dyld/cache-bypass experiment with the exact previously validated executable, dyld, cache, and cache-map hashes.
5. Preserve the exact stdout/stderr, exit status, and any new crash/core files before changing anything else.

The expected immediate success criterion is that the former syscall-295 `SIGSYS/ENOSYS` boundary disappears.

Do not predict the next runtime result. If the direct translator then stops on uncached `libgcc_s.1.dylib` or another dependency, that becomes the next measured boundary. Do not preemptively copy Snow Leopard libraries.

Only after the direct translator reaches the PPC smoke-test message and exits 0 should normal PPC exec be tested on the kernel that also contains the subject-path correction.

## Non-goals of the compatibility patch

The next patch must not:

- replace Lion's native `/usr/lib/dyld`;
- modify the private Snow Leopard dyld or Rosetta cache;
- restore obsolete shared-region code wholesale;
- alter syscall 438;
- add a general Snow Leopard library overlay;
- change the translated commpage implementation;
- alter the PowerPC subject-path fix;
- claim production readiness.

The goal is one compatibility ABI: route the confirmed Snow Leopard syscall-295 request into Lion's existing shared-region mapping machinery with the smallest auditable change.
