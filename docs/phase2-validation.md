# Phase-2 static validation record

The phase-2 patch was generated from these exact Apple OSS inputs:

| File | Tag | Git blob |
|---|---|---|
| `bsd/kern/bsd_init.c` | `xnu-1699.32.7` | `e60df12e0a66edc0c03248192dd35e438a3dc21b` |
| `osfmk/i386/cpu_capabilities.h` | `xnu-1699.32.7` | `eee6a8173eb72cffecb8e8e79ba9099b1411fcb4` |
| `osfmk/i386/commpage/commpage.c` | `xnu-1699.32.7` | `375abc7c1d95353f1f66f662d91c380ce9e7ca01` |
| `osfmk/conf/files.i386` | `xnu-1699.32.7` | `8c28645275d5d3e5e80f94da1ad9aa5293cff574` |
| `osfmk/conf/files.x86_64` | `xnu-1699.32.7` | `a147f68de773470cfff9f368028e9537f9d711c9` |
| `osfmk/i386/commpage/commpage_sigs.c` | `xnu-1504.15.3` | `0c100a2761ea07ab99c26b8a63bf3da4164b5cb5` |

Validated before publication:

- restored range is exactly `0xfffec000-0xfffff000`;
- the translated CPU-capability slot computes to `0xffff8020`;
- Lion native ABI remains version 12 and the translated view uses version 11;
- Lion's native CPU-family population remains present;
- `commpage.c` explicitly includes `<libkern/OSByteOrder.h>` for the restored byte-swap helpers;
- all 24 branch-assist descriptors are within the restored mapping;
- `sigdata_descriptor` is `0xffff3000` and within the mapping;
- `commpage_sigs.c` is included exactly once in both the I386 and X86_64 build lists;
- 32-bit population enables Rosetta compatibility and 64-bit population disables it;
- every generated unified-diff section was reapplied in memory to the exact upstream base and matched the intended patched content byte-for-byte.

The pre-boot-fix phase-2 revision compiled on Lion 10.7.5 with Xcode 4.2.1 for both RELEASE_I386 and RELEASE_X86_64, completing `DSYMUTIL`, `STRIP`, `CTFMERGE`, and `CTFINSERT`; both kernels contained `/usr/libexec/oah/translate`. That revision then exposed an early-boot `nanotime trouble 1` panic. The current source includes the commpage INT3-bounds correction and therefore requires a fresh dual-architecture compile before compilation/boot validation can be re-established for the current revision.

## Build feedback correction

The first I386 compilation completed and linked with `commpage_sigs.o`. The first X86_64 compilation exposed a packaging omission in the earlier phase-2 patch: `files.x86_64` did not include `commpage_sigs.c`, so the final link could not resolve `ba_descriptors` and `sigdata_descriptor`. The current phase-2 patch and validator cover both architecture build lists. A minimal hotfix patch is provided for trees already patched with the earlier revision.

## Successful dual-architecture build

After correcting the X86_64 build-list omission, the X86_64 build explicitly compiled both `commpage_sigs.o` and `commpage.o`, then completed `LD mach_kernel.sys`, `DSYMUTIL mach_kernel.sys`, `STRIP mach_kernel`, `CTFMERGE mach_kernel`, and `CTFINSERT mach_kernel`. The I386 build had already completed the same final pipeline successfully. This validates the phase-2 patch through source application, source validation, compilation, and link for both Lion kernel architectures. Boot and Rosetta execution remain the next validation stages.

## Early-boot nanotime correction

The first universal phase-2 kernel panicked during `rtc_nanotime_init_commpage()` with `nanotime trouble 1`. Root-cause analysis showed that Lion's stock `commpage_allocate()` fills commpage text with `0xCC` from allocation offset `0x80` through the end of the allocation. Enlarging the 32-bit allocation from two pages to 19 pages without changing that loop poisoned the native nanotime data, which moved to allocation offset `0x4050` when the allocation base became `0xfffec000`.

The current patch passes `base_offset` into `commpage_allocate()` and confines the INT3 fill to the native text interval. For the restored 32-bit allocation the fill is `0x4080-0x6000`; for the 64-bit commpage it remains stock Lion's `0x80-0x2000`. The extended Rosetta pages stay zero-filled until explicitly populated. See `docs/boot-panic-nanotime.md`.

## PowerPC subject-path correction

After the translated commpage probe passed, a PPC smoke-test exec no longer crashed but `translate` printed its own usage and exited 1. The process name in that usage was the original PPC target, but no subject program was supplied. Source comparison identified a Lion exec refactor: Lion's `exec_powerpc32_imgact()` calls `exec_reset_save_path()` and replaces the saved executable path with the interpreter path, whereas Snow Leopard keeps the PPC subject path saved and looks up the Rosetta interpreter through a separate buffer.

The current patch removes the PowerPC-only saved-path reset and makes the `-3` interpreter relookup use `ip_interp_buffer` when `IMGPF_POWERPC` is set, while retaining Lion's `ip_strings` behavior for ordinary `#!` interpreters. This restores the Snow Leopard separation between Rosetta's subject exec path and its interpreter lookup path.


## Direct `translate` invocation control

A manual launch such as:

```
/usr/libexec/oah/translate /path/to/ppc-program
```

is a valid positive control on Snow Leopard 10.6.8: with the known-good `ppc-smoketest`, the stock Snow Leopard translator prints the PPC smoke-test message and exits 0.

The same direct invocation on the current Lion phase-2 system exits by SIGSEGV (status 139). Therefore Lion still differs from Snow Leopard in at least one translator-visible runtime/kernel behavior even after the translated commpage has been restored. This direct-launch crash must be analyzed before another kernel rebuild.

The normal Lion PPC launch remains a separate symptom: the kernel redirects to `translate`, which prints its usage and exits 1 without a new crash report. The subject-exec-path source difference remains a plausible explanation for that normal-launch symptom, but the exec-path hotfix is provisional until the direct-launch crash is understood.


## GDB/vmmap capture caveat for protected translate

The attempted live GDB comparison did not reach Rosetta execution on either Lion or Snow Leopard. Under GDB, `translate` exited with code `055` on both systems before a breakpoint, crash, register state, or backtrace could be captured. This is consistent with Rosetta's imported `ptrace()` anti-debug path: Darwin's `PT_DENY_ATTACH` exits an already-traced process with `ENOTSUP` (45 decimal, octal `055`). The subsequent `ps` command matched the GDB command line (which contains the translate pathname), so both `vmmap` captures were maps of `gdb-i386-apple-darwin`, not of `translate`.

The supplied Snow Leopard `translate` Mach-O also marks its `__TEXT` segment with `SG_PROTECTED_VERSION_1`. XNU maps such a segment through the Apple protected pager. Therefore static bytes in the protected part of the file are not a reliable representation of the runtime instructions, and debugger-mediated execution is not a valid comparison path for this binary.

Future diagnosis of the Lion direct-launch crash should use non-ptrace evidence first: the native crash report, a postmortem core dump if the kernel permits one, and syscall/VM tracing (for example DTrace/dtruss) compared against the successful Snow Leopard direct launch.


## Postmortem direct-translate crash analysis

The non-debugged Lion direct invocation produced a usable core dump, and the runtime-decrypted translator text now explains the `0xc918a01c` fault.

The parser containing the fault is called with requested Mach CPU type `0x12` (PowerPC) and subtype `0x0a`. Its object in the core contains the pathname `/usr/lib/dyld`, a raw file mapping at `0xb0189000`, selected slice offset `0x1000`, and selected slice base `0xb018a000`.

The Snow Leopard 10.6.8 control now closes the architecture question directly: its `/usr/lib/dyld` contains x86_64, i386, and `ppc7400` slices. The Mac OS X 10.6 `mach/machine.h` definition assigns `CPU_SUBTYPE_POWERPC_7400` the value 10, exactly `0x0a`. Thus the dyld slice present on Snow Leopard is not merely PowerPC-compatible in the generic sense; it exactly matches the subtype requested by the Rosetta parser in the Lion core.

The selected slice is not PowerPC. Its header begins:

```
0xb018a000: 0xfeedfacf 0x01000007 0x00000003 0x00000007
0xb018a010: 0x0000000b 0x00000710 0x00000085 0x00000000
```

This is a little-endian 64-bit x86_64 `MH_DYLINKER` image. Lion's installed `/usr/lib/dyld` contains x86_64 and i386 slices but no PPC slice.

The decrypted parser recognizes the 32-bit Mach-O/fat magic values `MH_MAGIC`, `MH_CIGAM`, `FAT_MAGIC`, and `FAT_CIGAM`; the captured code contains no `MH_MAGIC_64` or `MH_CIGAM_64` test. Its fat-architecture scoring also permits the first nonmatching architecture to become the provisional candidate while the best score is `-1`. Thus when no requested PPC architecture exists, the first Lion dyld slice is selected instead of returning "no compatible architecture."

The exact crash sequence is then deterministic:

1. The selected x86_64 slice begins at `0xb018a000`.
2. The parser advances by `0x1c`, the size of a 32-bit Mach-O header, to `0xb018a01c`.
3. A 64-bit Mach-O header is `0x20` bytes. Therefore `+0x1c` is its reserved field, not its first load command.
4. The parser's swap flag is set from the fat-container byte order. It byte-swaps the words it believes are `cmd` and `cmdsize`.
5. The real first 64-bit command, `LC_SEGMENT_64 == 0x19` at `+0x20`, is therefore changed in place to `0x19000000` and interpreted as `cmdsize`.
6. The load-command loop executes `edi += *(edi + 4)`, so:
   `0xb018a01c + 0x19000000 = 0xc918a01c`.
7. The next loop iteration dereferences that unmapped address and faults.

The supplied memory dump contains the resulting mutated word `0x19000000` at selected-slice offset `0x20`, and the core confirms `0xc918a000` is unmapped.

This resolves the previously unexplained `0x19000000` delta. It is not evidence of a missing Lion VM mapping. The direct-launch failure is a guest-runtime dependency problem: the Snow Leopard Rosetta translator expects a PowerPC-capable guest `/usr/lib/dyld`, while Lion's native dyld no longer provides a PPC slice. No further XNU VM/commpage change should be made to address this specific fault.

The next controlled experiment is to provide a Snow Leopard PPC dyld at a private alternate path and build a disposable PPC smoke executable whose `LC_LOAD_DYLINKER` names that private path. Lion's native `/usr/lib/dyld` must not be replaced. The proprietary dyld image and decrypted translator dumps remain private test artifacts and must not be committed to this repository.

## DTrace/dtruss limitation

The attempted `dtruss` controls are not behavior-preserving. The Snow Leopard trace reports that DTrace's inserted dyld library could not be loaded and emits repeated invalid-user-access errors; the expected PPC smoke-test stdout is absent. Lion likewise produces no subject stdout under `dtruss`. Therefore those syscall streams are not used as authoritative translator-behavior comparisons.

A separate non-DTrace `DYLD_PRINT_LIBRARIES=1` control on Snow Leopard is valid: it reaches the PPC subject, loads the OAH Interposers shim plus PPC libSystem/libmathCommon, and the smoke test runs. The equivalent Lion direct launch crashes before reaching that guest-library output stage.


## Postmortem core result: missing PPC image-header mapping

A Lion direct `translate ppc-smoketest` run was allowed to core-dump and then inspected postmortem, avoiding the live-debugger behavior change. The core reproduces the prior crash PC at `0xb81605d9` with `EDI=0xc918a01c`. The runtime-decrypted instruction at the fault is `mov (%edi), %edx`, followed by an in-place byte-swap sequence over successive 32-bit words.

The address shape is significant: `0xc918a01c = 0xc918a000 + 0x1c`, and `0x1c` is the size of a 32-bit Mach-O header, i.e. the first load-command offset. This strongly indicates that Rosetta is trying to byte-swap/parse the first load command of a PPC Mach-O image whose expected header base is `0xc918a000`, but that page is not mapped on Lion.

The same core has `EAX=0xb018a000`, another page-aligned address with the same low offset; its relationship to the missing `0xc918a000` mapping is not yet established and must be verified by postmortem memory inspection before changing XNU again.

The `dtruss` comparison is not treated as execution-path evidence. Both Lion and Snow Leopard traces are perturbed by DTrace/ptrace behavior and contain many invalid-user-access errors; they do not reach the PPC smoke-test load path. The successful Snow Leopard `DYLD_PRINT_LIBRARIES` control does show the PPC target, Rosetta Interposers shim, PPC libSystem, and libmathCommon loading before the smoke test succeeds.


## Postmortem root cause: 64-bit Mach-O handed to Rosetta's 32-bit parser

The postmortem core has now isolated the direct-launch crash mechanically. The live Rosetta routine at `0xb81605a4` initializes its load-command cursor as `image_base + 0x1c`, which is the 28-byte header size of a 32-bit Mach-O. At the crash, the relevant readable page at `0xb018a000` is instead an x86_64 64-bit Mach-O header: magic `MH_MAGIC_64` (`0xfeedfacf`), CPU type `0x01000007`, and file type `MH_DYLINKER` (7). Inspection of the dumped page also identifies it as `/usr/lib/dyld`.

Because a 64-bit Mach-O header is 0x20 bytes, Rosetta starts four bytes too early: `+0x1c` is the 64-bit header's reserved word, not the first load command. With byte-swapping enabled, Rosetta leaves that zero reserved word unchanged but byte-swaps the actual first command word at `+0x20`, changing `LC_SEGMENT_64 == 0x19` into the little-endian value `0x19000000`.

The same routine advances the cursor with `edi += *(edi + 4)`. Starting at `0xb018a01c`, the corrupted pseudo-`cmdsize` is therefore `0x19000000`, yielding exactly:

```
0xb018a01c + 0x19000000 = 0xc918a01c
```

The next iteration executes `mov (%edi), %edx` at `0xb81605d9` and faults because `0xc918a01c` is unmapped. Separate postmortem probes confirm both `0xc918a000` and `0xc918a01c` are inaccessible.

This explains the direct Lion crash without invoking the translated commpage. The next validation target is why Snow Leopard Rosetta receives a 32-bit/PPC-compatible dyld image while Lion presents an x86_64 dyld slice. In particular, compare `/usr/lib/dyld` architectures on 10.6.8 and 10.7.5 and confirm the pathname stored in the crashing parser frame before designing a runtime workaround.


## Lion private-dyld follow-up: parser boundary passed

The controlled private-dyld experiment has now moved the Lion direct-launch failure beyond the former `0xc918a01c` parser crash. The exact Snow Leopard 10.6.8 dyld was staged privately as `/usr/oah/dyld`, and the disposable PPC smoke executable's `LC_LOAD_DYLINKER` was changed only to that private path. Lion's native `/usr/lib/dyld` remained byte-for-byte unchanged.

With the private PPC dyld selected, Rosetta reaches normal guest dynamic-library resolution. The new failure is:

```
dyld: shared cached file was build against a different libSystem.dylib, ignoring cache
dyld: Library not loaded: /usr/lib/libgcc_s.1.dylib
  Reason: no suitable image found.
```

Lion's on-disk `/usr/lib/libgcc_s.1.dylib` contains x86_64/i386 but no PPC slice. The direct process terminates with status 133 / SIGTRAP after dyld emits that fatal loader diagnostic. This is not recurrence of the earlier SIGSEGV and does not justify another XNU VM/commpage change.

The current next experiment remains entirely in the runtime layer. The first cache-bypass preflight verified the exact validated Snow Leopard Rosetta cache/map hashes and also established that this map does not list `/usr/lib/libgcc_s.1.dylib`. That is a cache-content fact, not evidence of corruption. The initial runtime runner incorrectly treated membership of that path as an identity requirement and stopped before launching `translate`.

The corrected runtime experiment uses `DYLD_SHARED_CACHE_DONT_VALIDATE=1` for the direct translator process while treating cache-map membership as diagnostic. Its immediate question is whether the guest dyld's stale-libSystem cache rejection disappears. If it does and the next loader failure remains uncached `libgcc_s.1.dylib`, the next boundary is a private runtime-library dependency, not XNU. Do not replace Lion's `/usr/lib` files, do not rebuild the Rosetta cache, and do not set `DYLD_SHARED_REGION=private` for this validation step. The companion `lion-rosetta-runtime` repository contains the guarded procedure.


## Cache-bypass result: retired `shared_region_map_np` ABI

The Lion private-dyld experiment with process-local `DYLD_SHARED_CACHE_DONT_VALIDATE=1` moved execution beyond the stale Rosetta-cache validation failure. Guest dyld reported the PPC subject as loaded and no longer printed the prior “ignoring cache” message. The process then terminated with status 140; its non-debugged crash report records `EXC_CRASH (SIGSYS)`, `EIP=0xb815ac07` inside `translate`, and `EAX=0x0000004e`.

Source comparison identifies a specific Snow Leopard-to-Lion syscall ABI removal:

- Apple dyld 132.13 calls `syscall(295, fd, count, mappings)` from its `_shared_region_map_np()` helper.
- XNU 1504.15.3 syscall 295 is `shared_region_map_np(int fd, uint32_t count, const struct shared_file_mapping_np *mappings)`.
- XNU 1699.32.7 syscall 295 is `nosys`, annotated `old shared_region_map_np`; Lion provides the newer syscall 438 `shared_region_map_and_slide_np`.
- XNU `nosys()` sends `SIGSYS` and returns `ENOSYS`.
- Darwin `ENOSYS` is decimal 78 (`0x4e`), exactly matching the crash `EAX`.

This is strong evidence that restoring the old shared-region syscall ABI is the next XNU compatibility problem exposed by the runtime work. It is distinct from the earlier translated-commpage and PowerPC subject-path fixes.

The preserved non-debugged `/cores/core.1090` has now confirmed the boundary. Runtime-decrypted code executes `int $0x80` at `0xb815ac05`; the crash EIP is the following `setb %cl`, with `EAX=0x4e` and carry set. The caller explicitly supplies syscall number `0x127` (295), and the wrapper frame reconstructs `fd=4`, `mappingCount=3`, and a mapping-array pointer. Those three `shared_file_mapping_np` records span the validated Rosetta shared cache exactly, ending at file size 209,248,256 bytes. This closes the postmortem confirmation gate. The next XNU work should be design-first: prefer a minimal compatibility wrapper using Lion's existing shared-region mapping helpers rather than importing the entire Snow Leopard implementation.


## Shared-region compatibility design review

The source-design pass is complete and is recorded in `docs/shared-region-map-np-compatibility-design.md`.

The important result is that Lion already retains the machinery needed by Rosetta. Its `bsd/vm/vm_unix.c` contains `shared_region_copyin_mappings()` and `_shared_region_map()`, used by syscall 438, and its `vm_shared_region_map_file()` accepts a null slide-output pointer. The `shared_file_mapping_np` layout is unchanged from Snow Leopard, and Lion still declares `shared_region_map_np()` in `osfmk/mach/shared_region.h`.

Therefore the implementation phase should restore syscall-table entry 295 and add only a thin three-argument compatibility front-end that reuses Lion's helpers. It should not import the Snow Leopard syscall body, alter syscall 438, or modify the lower shared-region VM implementation unless compilation/static validation demonstrates a concrete need.

The implementation is now prepared as a separate experiment-only patch and validation/probe set. It remains outside the standalone phase-2 patch so this compatibility change can be tested independently. Follow `docs/xnu-syscall-295-experiment.md`; do not fold the result into phase 2 until the experiment is reviewed.


## Syscall-295 experiment result: PASS

The isolated syscall-295 compatibility experiment has now passed through build, boot, native regression gates, and the guarded direct Rosetta control.

Observed validated kernel:

- universal `mach_kernel.rosetta-syscall295` SHA-256: `fe68467b60b3bd7edfab61b2d6c8af7f988de5206c4b7b624151dc9f1a1061d3`;
- booted Lion 10.7.5 build `11G63`;
- PowerPC handler remained `/usr/libexec/oah/translate`.

Both RELEASE_I386 and RELEASE_X86_64 builds regenerated the syscall artifacts from `bsd/kern/syscalls.master` and completed the final `LD mach_kernel.sys`, `DSYMUTIL`, `STRIP`, `CTFMERGE`, and `CTFINSERT` pipeline.

After reboot:

- the existing translated-commpage probe still reported `RESULT: PASS`;
- the native i386 syscall-295 routing probe returned `EBADF` with no `SIGSYS` and exited 0;
- the guarded direct Rosetta private-dyld/cache-bypass test loaded the PPC subject, Rosetta Interposers, PPC libSystem, and libmathCommon, printed the PPC smoke-test message, and exited 0;
- no new crash/core diagnostic was produced by that direct control;
- Lion's native `/usr/lib/dyld` and the private `/usr/oah/dyld` hashes remained unchanged.

This confirms the old syscall-295 ABI restoration is sufficient for the previously observed shared-region `SIGSYS/ENOSYS` boundary and does not regress the translated commpage.

The next untested layer is normal PowerPC exec activation on the same kernel/runtime stack. The authoritative next procedure is in the companion runtime repository at `docs/lion-normal-ppc-exec-experiment.md`. Do not broaden the kernel patch or add guest libraries before that normal-exec result is reviewed.


## Normal PowerPC exec result: PASS

The same syscall-295 experiment kernel has now passed a normal PowerPC `execve` control, not only the manual direct-`translate` control.

With the validated private PPC dyld and process-local Rosetta cache-validation bypass retained, the kernel recognized the PPC subject, dispatched through `/usr/libexec/oah/translate`, preserved the subject path, loaded the expected Rosetta guest runtime, printed the PPC smoke-test marker, and exited 0. No new crash/core diagnostic was produced.

This confirms the PowerPC subject-path correction in the running kernel together with the translated commpage and syscall-295 restoration.

No further XNU change is indicated by this result. The next work moves back to runtime compatibility expansion, beginning with a controlled PPC CoreFoundation command-line probe in the companion runtime repository.


## PPC CoreFoundation result: PASS

The syscall-295 experiment kernel has now also passed a normal 32-bit PowerPC CoreFoundation command-line test under Rosetta.

The exact Snow Leopard-positive-control executable loaded CoreFoundation and its dependent PPC runtime libraries, successfully exercised CFString and CFArray operations, printed the expected marker, exited 0, and produced no new crash/core diagnostic.

The kernel, private dyld, Lion native dyld, and Rosetta cache hashes remained unchanged.

No new XNU compatibility change is indicated by this result. The next work remains in user-space compatibility expansion: the companion runtime repository now contains the first controlled Carbon GUI/window-event-loop experiment.
