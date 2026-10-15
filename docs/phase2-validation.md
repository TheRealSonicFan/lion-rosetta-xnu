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


## Carbon GUI result: SIGABRT under postmortem analysis

The first controlled PPC Carbon GUI experiment in the companion runtime repository passed on Snow Leopard but aborted on Lion before the probe printed either GUI marker.

The same validated syscall-295 kernel was still running, the commpage and syscall-295 native preflights passed, and the guarded integrity hashes remained unchanged. Lion loaded the Carbon/ApplicationServices framework graph and then terminated with `EXC_CRASH (SIGABRT)`, status 134, generating `/cores/core.1311`.

The crash report places the x86 host PC at Rosetta's previously identified syscall-wrapper area `0xb815ac07`, but this is not evidence by itself of another missing XNU ABI. The current next step is read-only postmortem analysis of the preserved core using the runtime repository's `docs/carbon-gui-sigabrt-postmortem.md`.

Do not make another XNU compatibility change until that postmortem identifies a concrete kernel boundary.


## Carbon postmortem: guest-requested SIGABRT

The preserved non-debugged core from the first PPC Carbon GUI failure has now been analyzed in the companion runtime repository.

Runtime-decrypted Rosetta code shows that the direct caller supplies Unix syscall number `0x25` (decimal 37) to the host syscall wrapper. Both Snow Leopard and Lion define syscall 37 as `kill(pid, signum, posix)`.

The preserved arguments are PID 1311, signal 6 (SIGABRT), and posix flag 1. The syscall returns success (`EAX=0`, carry clear) before the process terminates.

Therefore this Carbon failure is not evidence of another missing Lion syscall ABI. Rosetta is faithfully delivering a guest-requested self-SIGABRT.

No XNU change should be made from this result. The next experiment remains user-space localization with the runtime repository's milestone-instrumented Carbon probe.


## Carbon milestone: GetCurrentProcess boundary

The companion runtime repository's milestone-instrumented Carbon GUI probe has now localized the Lion guest-side abort to the first `GetCurrentProcess` call.

The exact Snow Leopard control reaches every milestone through successful window/event-loop completion. On Lion, the same validated kernel/runtime stack reaches `main()` and `M01_BEFORE_GetCurrentProcess`, then the translated guest deliberately requests SIGABRT before `M02_AFTER_GetCurrentProcess`.

This does not identify another missing XNU syscall ABI. The current next experiment changes only launch context by using a registered application bundle through LaunchServices.

Do not make another XNU change from this result.


## LaunchServices Rosetta availability gate

The companion runtime repository's registered Carbon `.app` control exposed a user-space LaunchServices gate before PPC execution.

The exact application bundle launches successfully through LaunchServices on Snow Leopard. On Lion, `lsregister -f` succeeds but `open -n -W` returns LaunchServices error `-10665` before the PPC executable starts. That result code is `kLSNoRosettaEnvironmentErr`.

No milestone file or crash/core diagnostic is produced because the app never reaches `main()`.

This does not indicate another XNU compatibility failure. The currently validated kernel continues to pass commpage, syscall-295, direct Rosetta, normal PPC exec, and CoreFoundation controls. No new XNU change should be made from the LaunchServices result.

The next step is a read-only Snow Leopard/Lion LaunchServices Rosetta-environment audit in the companion runtime repository.


## LaunchServices audit: user-space PPC policy difference

The companion runtime repository's Snow Leopard/Lion LaunchServices environment audit confirms that the current PPC application-bundle failure remains above XNU.

Both systems expose the same Rosetta translator identity, RosettaVersion.plist, and PowerPC architecture handler. However, Snow Leopard LaunchServices contains explicit Rosetta/OAH support logic and a ppc7400 slice, while Lion LaunchServices lacks that Rosetta-specific machinery and records the same PPC application with an additional `unsupported-format` flag.

Snow Leopard also has Rosetta package receipts that are not installed on Lion, but the current evidence does not establish those receipts as the LaunchServices availability source.

No XNU change is indicated. The next step is a read-only static analysis of the LaunchServices/CarbonCore/CoreServices PPC gate in the runtime repository.


## LaunchServices static PPC gate: no new XNU boundary

The companion runtime repository's first-pass LaunchServices static audit confirms that the current `kLSNoRosettaEnvironmentErr (-10665)` failure remains a user-space LaunchServices decision.

Snow Leopard's i386 LaunchServices error path calls its explicit Rosetta requirement checker immediately before deciding whether to return `-10665`. Lion's i386 LaunchServices still contains the `-10665` value, but reaches it through structurally different internal architecture logic and no longer exposes the Snow Leopard Rosetta-specific checker.

The first static analyzer also had symbol-name/reporting limitations, so the exact Lion enclosing function/flag has not yet been proven. The runtime repository now contains a corrected read-only callsite audit.

No new XNU change is indicated. Do not broaden the syscall-295 or commpage patches for this LaunchServices result.


## LaunchServices callsite result: unsupported-format policy gate

The companion runtime repository's corrected LaunchServices callsite audit has now resolved the Lion `kLSNoRosettaEnvironmentErr (-10665)` launch decision.

Snow Leopard's `_LSLaunch` path calls its explicit `_LSAppMeetsRosettaRequirement` helper. Lion's `_LSLaunch` no longer has that helper; instead it calls `_LSBundleDataGetUnsupportedFormatFlag` and returns `-10665` from the persisted unsupported-format classification.

This confirms that the current PPC application-bundle rejection is a user-space LaunchServices registration/policy issue, not another missing XNU ABI.

No XNU change is indicated. The runtime repository is now tracing the registration-time provenance of the unsupported-format flag before any LaunchServices compatibility patch is designed.

## LaunchServices provenance: removed PPC fallback

The companion runtime repository has completed the unsupported-format provenance audit.

Lion's _LSBundleDataGetUnsupportedFormatFlag computes its unsupported-format result dynamically from bundle architecture bits and current CPU policy. Snow Leopard contains an Intel-host fallback that accepts the PPC architecture bit for Rosetta; Lion's x86_64-host path removed that fallback and therefore classifies the validated PPC-only application as unsupported.

This explains the later kLSNoRosettaEnvironmentErr launch rejection without identifying another kernel ABI problem.

No XNU change is indicated. The next experiment uses only a private i386 LaunchServices copy in the runtime repository; the installed system framework and current syscall-295 kernel remain unchanged.

## Private LaunchServices compatibility result: launch gate cleared

The companion runtime repository's private, process-local LaunchServices compatibility experiment has now cleared Lion's user-space PPC application launch gate.

A verified one-byte change was applied only to a private i386 LaunchServices copy. The installed system LaunchServices hash remained unchanged. An i386 `open` preflight proved that the private framework was loaded, after which the registered PPC application launched successfully through LaunchServices instead of returning `kLSNoRosettaEnvironmentErr (-10665)`.

The launched PPC application then reached `main()` and reproduced the previously independent Carbon Process Manager boundary: it self-SIGABRTed inside `GetCurrentProcess`.

Therefore the current unresolved GUI problem is no longer LaunchServices admission and does not expose another XNU ABI failure. The next runtime experiment tests alternate Process Manager PSN/PID APIs while leaving the validated kernel unchanged.

No additional XNU change is indicated by this result.


## Process Manager pseudo-PSN result

The companion runtime repository's alternate Process Manager experiment passed fully on Snow Leopard but failed on Lion inside its first guest Process Manager operation, `GetProcessPID({0,kCurrentProcess},...)`.

The Lion subject reached `main()` and its pre-call marker, then self-SIGABRTed before the function returned. The crash registers again match the already decoded Rosetta guest abort wrapper: PID 5106, signal 6, posix flag 1, host return EAX 0.

This is the same abort family previously observed for `GetCurrentProcess`. It does not expose a new XNU syscall failure.

Because `GetProcessForPID` was not reached, investigation remains in the runtime layer. The next experiment begins with `GetProcessForPID(getpid(), &psn)` and avoids both current-process lookup APIs.

No additional XNU change is indicated.


## Process Manager GetProcessForPID result: no new XNU boundary

The companion runtime repository's GetProcessForPID-first experiment has now closed the remaining Process Manager API-permutation question.

The exact PPC/ppc7400 subject passes on Snow Leopard 10.6.8: `GetProcessForPID(getpid(), &psn)` returns successfully and the probe completes foreground conversion, window creation, and its event loop. On Lion 10.7.5, the same subject reaches `M01_BEFORE_GetProcessForPID` and self-SIGABRTs before the function returns.

The crash again uses Rosetta's already decoded guest-requested abort wrapper: the subject PID is supplied with signal 6 and the posix flag, while the host syscall returns success. The native syscall-295 probe still reaches the compatibility front-end and returns EBADF, and the guarded runtime hashes remain unchanged.

Together with the earlier `GetCurrentProcess` and pseudo-PSN `GetProcessPID` results, this points to a shared user-space translated-PPC Process Manager registration/backend requirement rather than another missing kernel syscall ABI.

No additional XNU change is indicated. The authoritative next step is the runtime repository's read-only `docs/process-manager-hiservices-audit.md`, including Rosetta-cache/on-disk image provenance before any HIServices compatibility design.


## Process Manager HIServices audit: shared RegisterApplication path

The companion runtime repository's first Process Manager/HIServices differential audit is complete.

Both Snow Leopard and Lion contain the exact validated Rosetta cache/map, and the relevant HIServices/ApplicationServices/CarbonCore/AE paths are present in that cache. The Rosetta ApplicationServices shim and `Interposers.dylib` also match byte-for-byte in their i386 and ppc7400 slices.

Snow Leopard's PPC HIServices implementation shows that `GetCurrentProcess`, `GetProcessPID`, and `GetProcessForPID` all perform the same lazy `__RegisterApplication` initialization before their normal identity lookup work. HIServices contains explicit diagnostics for failure to obtain an application ASN from CoreServices/coreservicesd and exposes the `LSDoNotAbortIfNoASN`/`LSDONOTABORTIFNOASN` names.

Both systems have `coreservicesd`, WindowServer, and the `com.apple.pbs` launchd job, so the result does not point to a missing daemon or another XNU ABI.

No additional XNU change is indicated. The runtime repository now performs a narrower read-only `__RegisterApplication`/ASN callsite audit before testing any no-abort behavior or designing a user-space compatibility layer.


## RegisterApplication callsite audit: analyzer rerun required

The companion runtime repository's first `__RegisterApplication`/ASN callsite execution did not complete its intended disassembly step.

Both Snow Leopard and Lion reports successfully inventoried the relevant symbols, including `__RegisterApplication` and Process Manager/LaunchServices registration functions, but every analyzed slice ended with `selected_symbol_windows=0`. Review of the runtime analyzer identified an over-escaped symbol/instruction address parser in version 1.

This is a tooling/reporting defect, not a new kernel boundary and not evidence that the target code is absent.

The runtime repository now contains analyzer version 2, which validates nonzero code-window selection, adds x86_64 LaunchServices coverage for the native coreservicesd side, records Rosetta-cache membership for LaunchServices, and emits `RESULT: PASS` only when the intended static evidence was collected.

No XNU change is indicated. The next action remains a read-only runtime audit rerun; no PPC application is launched and no no-ASN behavior override should be tested yet.


## Corrected RegisterApplication audit: user-space protocol boundary

The companion runtime repository's corrected version-2 RegisterApplication/ASN callsite audit now passes on both Snow Leopard and Lion.

Snow Leopard PPC HIServices `__RegisterApplication` performs LaunchServices application check-in, ASN/PSN fallback and extraction, WindowServer/CPS registration, and then a fatal no-ASN check if the cached PSN remains unusable. The same static review also exposes an earlier independent LaunchServices abort when the CoreApplicationServices process-dispatch channel cannot be established.

The LaunchServices registration message family persists across Snow Leopard and Lion, but the corrected disassembly shows request/reply-layout and validator differences between the Snow Leopard PPC client and Lion native server-side paths. That is a concrete user-space compatibility question, not evidence for another missing kernel ABI.

No XNU change is indicated. The runtime repository now performs a read-only registration-protocol audit to identify the active native service architecture, map the exact no-ASN environment cstring, and compare the Snow Leopard PPC request against Snow Leopard/Lion server validation before any abort bypass or protocol adapter is attempted.


## Registration-protocol audit: exact no-ASN discriminator

The companion runtime repository has completed the LaunchServices registration-protocol audit on Snow Leopard and Lion.

The audit maps the Snow Leopard PPC HIServices abort-control `getenv()` operand to the exact uppercase literal `LSDONOTABORTIFNOASN`. The local control byte defaults to 1 and is replaced by `atoi()` of the environment value, so `LSDONOTABORTIFNOASN=0` suppresses only the later no-ASN abort branch.

The same audit shows that Snow Leopard PPC and Lion i386 `_LSDoRegisterApplication` use registration message ID `0x4652` with the same `0x44` send and `0x48` receive sizes. The x86_64 layout is wider, but the current evidence does not establish that a protocol adapter or daemon replacement is required.

An earlier LaunchServices `getProcessDispatchTable()` abort remains independently possible if the CoreApplicationServices process-dispatch channel cannot be established.

No XNU change is indicated. The next runtime step is a single process-local discriminator: the test bundle supplies `LSDONOTABORTIFNOASN=0`, calls `GetProcessForPID` once, logs status/PSN, and exits immediately. If the call still aborts, investigation moves to the earlier user-space dispatch channel; if it returns, the returned registration state becomes the next user-space boundary.


## No-ASN discriminator: failure is upstream of the HIServices no-ASN gate

The companion runtime repository has completed the guarded process-local no-ASN discriminator.

The exact PPC subject sees `LSDONOTABORTIFNOASN=0` on Snow Leopard and Lion. Snow Leopard returns successfully from `GetProcessForPID` with a nonzero PSN. Lion reaches the pre-call milestone and still self-SIGABRTs before `GetProcessForPID` returns.

The latest Lion crash again matches Rosetta's already decoded guest-requested self-abort wrapper, and the native syscall-295 preflight still reaches the compatibility front-end and returns EBADF. Protected kernel/runtime hashes remain unchanged.

This rules out the later HIServices no-ASN abort controlled by `LSDONOTABORTIFNOASN` as the observed fatal branch. The remaining investigation is user-space LaunchServices process-services initialization, where `getProcessDispatchTable()` can abort if `SetupCoreApplicationServicesCommunicationPort()` fails to establish a usable dispatch table.

No additional XNU change is indicated. The runtime repository now performs a read-only Snow Leopard/Lion process-dispatch audit covering session lookup, service/version negotiation, `_LSDoInitializeProcessesServices`, the InitializeProcessesServices server-wrapper family, port creation, and dispatch-table installation before any compatibility layer is designed.


## Process-dispatch audit: no LaunchServices wire mismatch identified

The companion runtime repository has completed the Snow Leopard/Lion Process Manager process-dispatch audit.

The Snow Leopard PPC and Lion i386 LaunchServices clients use the same InitializeProcessesServices message ID `0x4650`, request size `0x2c`, receive size `0x50`, and expected reply ID `0x46b4`. Their high-level setup paths both perform security-session discovery, acquire the `LaunchApplicationServices` system service at version `0x00010000`, invoke `_LSDoInitializeProcessesServices`, validate returned process-services state, create a CoreFoundation Mach port, and install the Process Manager dispatch table.

Both systems also expose an active `coreservicesd` and the same `com.apple.CoreServices.coreservicesd` launchd Mach-service declaration. The static review did not reveal an obvious LaunchServices-level 32-bit wire-ABI incompatibility.

The remaining unresolved static layer is below LaunchServices: CarbonCore's `scCreateSystemServiceVersion` / reconnect transport and Security's `SessionGetInfo` implementation. The runtime repository now performs a read-only differential audit of those functions before any live instrumentation or compatibility code.

No additional XNU change is indicated.


## System-service transport audit: next boundary remains user space

The companion runtime repository has completed the Snow Leopard/Lion CarbonCore/Security transport audit.

CarbonCore's top-level `scCreateSystemServiceVersion` path remains semantically similar across Snow Leopard PPC and Lion i386 and still reaches `SCSession::findOrCreateService`. The material difference is in Security session lookup: Snow Leopard PPC `SessionGetInfo` uses the legacy SecurityServer client path, while Lion i386 uses `CommonCriteria::AuditInfo` and reads audit-session state locally.

Because translated PPC on Lion executes the restored Snow Leopard PPC Security image from the validated Rosetta shared cache, the legacy Security client path is being exercised in a Lion host environment.

The runtime repository now performs one guarded command-line PPC pre-dispatch preflight that tests only the two prerequisites before LaunchServices process-services initialization: `scCreateSystemServiceVersion("LaunchApplicationServices", 0x00010000, NULL)` followed by `SessionGetInfo(callerSecuritySession,...)`.

No additional XNU change is indicated.


## Pre-dispatch probe: null CoreServices service port on Lion

The companion runtime repository has completed the guarded PPC pre-dispatch primitive test.

The exact PPC executable succeeds on Snow Leopard, returning a nonzero `LaunchApplicationServices` service port and a valid Security session. On Lion, the same executable reaches `scCreateSystemServiceVersion("LaunchApplicationServices", 0x00010000, NULL)`; the call returns normally but supplies a zero port. `SessionGetInfo` is never reached.

The native syscall-295 safety probe still passes, no new crash/core is generated, and the protected kernel/runtime identities remain unchanged.

The immediate failure boundary is therefore CarbonCore/CoreServices system-service acquisition, not another kernel ABI and not the Security session call itself. The runtime repository is proceeding with a read-only `SCSession::findOrCreateService` / `SCClientSession` differential audit before any further live instrumentation.

No additional XNU change is indicated.


## CarbonCore client-internals audit: RPC contract is the remaining static gap

The companion runtime repository has completed the CarbonCore system-service client-internals audit.

Snow Leopard PPC and Lion i386 retain the same broad client architecture: CoreServices client check-in uses a bootstrap lookup followed by `ServerCheckin`, and service acquisition reaches `SCSession::findOrCreateService` and the client `FindService` RPC. Private `SCClientSession` object sizes/offsets differ between releases, but those framework-local layout changes do not establish an IPC incompatibility.

The remaining runtime boundary is still the zero `LaunchApplicationServices` port. Static analysis must now distinguish client check-in/session establishment from the subsequent `FindService` transaction.

The runtime repository therefore performs one final read-only RPC-contract audit covering the actual `ServerCheckin` and `FindService` stubs, check-in naming, Lion connection-state logic, message sizes/IDs, and output/status handling.

No additional XNU change is indicated.


## CoreServices RPC audit: no static wire mismatch established

The companion runtime repository has completed the CarbonCore system-service RPC protocol audit.

Snow Leopard PPC uses an older complex `ServerCheckin` request. A later re-read of Lion's shipped `__XServerCheckin` wrapper corrects the initial interpretation here: Lion rejects the complex form and accepts only its simple `0x18` request. The `FindService` request/reply IDs and message sizes still align directly between Snow Leopard PPC and Lion native CarbonCore.

The remaining zero-port boundary is therefore runtime state rather than a demonstrated wire-format mismatch: either the translated PPC CarbonCore fails to establish a usable coreservicesd client/check-in session, or check-in succeeds and the subsequent `LaunchApplicationServices` service lookup fails.

The runtime repository is proceeding with one guarded post-call state discriminator using the guest CarbonCore's existing exported check-in/status helpers. No direct RPC injection, framework patch, or kernel change is involved.

No additional XNU change is indicated.


## CoreServices stage discriminator: check-in session unavailable

The companion runtime repository has completed the guarded CoreServices system-service stage discriminator.

The exact PPC subject passes on Snow Leopard with a nonzero `LaunchApplicationServices` port and nonzero CarbonCore server-checkin port. On Lion, the same subject returns normally from service acquisition but reports both ports as zero, process options `0x00000002`, no crash/core diagnostic, and `RESULT: CHECKIN_SESSION_UNAVAILABLE`.

The native syscall-295 probe remains a clean EBADF/no-SIGSYS PASS, and all protected kernel/runtime identities remain unchanged.

This localizes the active failure before `FindService`: the guest PPC CarbonCore does not establish a usable coreservicesd client/check-in session.

The runtime repository is therefore testing only the first half of the remaining `bootstrap_look_up2 -> ServerCheckin` boundary. The next one-shot PPC probe performs the exact coreservicesd bootstrap lookup with the recovered target PID and 64-bit flags value, and deliberately does not call `ServerCheckin` in the same run.

No additional XNU change is indicated.


## Bootstrap lookup discriminator: Lion returns MIG_BAD_ARGUMENTS

The companion runtime repository has completed the guarded coreservicesd bootstrap-lookup discriminator.

The exact PPC subject succeeds on Snow Leopard with a nonzero bootstrap port, `kr=0`, and a nonzero `com.apple.CoreServices.coreservicesd` service port. On Lion, the same subject has a nonzero bootstrap port and the same clean environment/name/target/flags, but `bootstrap_look_up2` returns `-304` (`0xfffffed0`) and service port zero, with no crash or protected-file change.

Darwin MIG defines `-304` as `MIG_BAD_ARGUMENTS`.

Public Apple launchd source for the exact baselines shows a matching user-space protocol evolution: launchd-329.3.3 `vproc_mig_look_up2` places 64-bit flags immediately after target PID, whereas launchd-392.39 inserts an `instanceid : uuid_t` field before those flags. Lion's public `bootstrap_look_up2` API remains source-compatible by routing through `bootstrap_look_up3`.

The runtime repository is now performing a read-only shipped-binary audit of liblaunch/libSystem and launchd to confirm the exact request layouts before any process-local protocol adapter is attempted.

The syscall-295 safety probe remains healthy. No additional XNU change is indicated.


## Bootstrap protocol binary audit: request-layout mismatch confirmed

The companion runtime repository has completed the corrected Snow Leopard/Lion bootstrap protocol audit.

The shipped Snow Leopard PPC `vproc_mig_look_up2` request uses message ID `0x194`, send size `0xac`, receive size `0x6c`, and reply ID `0x1f8`. Its target PID is followed directly by the 64-bit flags field.

Lion's private MIG symbol name is stripped, but the corrected analyzer resolves the unique repeated non-stub `bootstrap_look_up3` callee in i386 liblaunch. The corresponding Lion request keeps the same message/reply IDs and receive size but sends `0xbc` bytes and inserts a 16-byte field between target PID and flags.

That exact `0x10` expansion matches Lion's `instanceid : uuid_t` addition and explains the translated Snow Leopard PPC client's live `MIG_BAD_ARGUMENTS` response from Lion launchd.

The runtime repository is proceeding with one process-local proof transaction that constructs the Lion-format request and stops before CoreServices `ServerCheckin`.

The syscall-295/XNU boundary remains closed. No additional XNU change is indicated.


## Bootstrap protocol adapter proof: corrected PPC lookup succeeds

The companion runtime repository has completed the guarded one-transaction bootstrap protocol adapter experiment.

The translated PPC subject constructed the Lion-format `look_up2` request with the binary-confirmed 16-byte instance UUID field and `0xbc` send size. Lion accepted the request, returned the expected complex reply, and supplied a nonzero coreservicesd service port. No crash occurred, protected identities remained unchanged, and the syscall-295 safety probe remained a clean EBADF/no-SIGSYS PASS.

This experimentally closes the launchd/bootstrap request-layout defect itself.

The runtime repository is now proceeding with a process-local integration discriminator: a private PPC dyld interposer adapts only CarbonCore's exact coreservicesd bootstrap lookup and then lets unmodified PPC CarbonCore continue into its existing `ServerCheckin -> FindService` path.

No direct CoreServices RPC is issued by the custom test code, no system binary is patched, and no additional XNU change is indicated.


## Bootstrap integration reaches ServerCheckin protocol boundary

The companion runtime repository has completed the guarded bootstrap integration experiment.

The validated process-local bootstrap adapter succeeds inside the real Snow Leopard PPC CarbonCore call path on Lion and returns a nonzero coreservicesd service port. CarbonCore nevertheless ends with a zero server-checkin port, zero requested service port, process options `0x00000002`, no crash/core, and `RESULT: BOOTSTRAP_COMPAT_SERVERCHECKIN_FAILURE`.

A re-read of the previously collected shipped stubs corrects an earlier runtime-side interpretation: Snow Leopard PPC `ServerCheckin` sends a complex `0x28` request with one port descriptor, while Lion native i386 sends a simple `0x18` request. Lion's i386 `__XServerCheckin` rejects complex requests before reaching `__scserver_ServerCheckin`.

The runtime repository is therefore proceeding with a standalone one-transaction proof of Lion's native simple ServerCheckin request from translated PPC, after the already-proven adapted bootstrap lookup.

The syscall-295 probe remains a clean EBADF/no-SIGSYS PASS. No additional XNU change is indicated.


## ServerCheckin protocol adapter proof: native Lion form succeeds

The companion runtime repository has completed the guarded standalone ServerCheckin protocol adapter experiment.

The Snow Leopard PPC control sent the recovered complex `0x28` ServerCheckin request and received a nonzero session port.

On Lion, the translated PPC subject first completed the already-proven UUID-expanded coreservicesd lookup. It then sent Lion's native simple `0x18` ServerCheckin request with request ID `0x2710` and receive size `0x3c`. Lion returned Mach success and the expected complex `0x34` reply with reply ID `0x2774`, descriptor count 1, disposition `0x11`, a nonzero session port, and options `0x03000000`.

No crash/core diagnostic was produced. The kernel and protected runtime hashes remained unchanged, and the native syscall-295 probe remained a clean EBADF/no-SIGSYS PASS.

This independently closes the second user-space protocol defect at the standalone transaction level.

The runtime repository is now proceeding with a single process-local integration discriminator that combines only the already-proven bootstrap UUID adaptation and the already-proven ServerCheckin request-shape adaptation, then returns control to unmodified PPC CarbonCore. The result will determine whether its existing `FindService("LaunchApplicationServices")` transaction succeeds without another adapter.

No additional XNU change is indicated.


## Dual CoreServices integration proof: CarbonCore service acquisition succeeds

The companion runtime repository has completed the corrected v3 dual CoreServices integration experiment.

On Lion, the translated PPC process used the process-local adapter for exactly the two independently proven request-shape differences:

- the UUID-expanded coreservicesd bootstrap lookup;
- the native simple `0x18` ServerCheckin request.

Both adaptations succeeded. The ServerCheckin reply contained a nonzero session port and options `0x03000000`. Unmodified Snow Leopard PPC CarbonCore then completed its existing `FindService("LaunchApplicationServices")` transaction and returned a nonzero service port; its exposed check-in port was also nonzero and process options were zero.

No crash/core diagnostic was produced. The kernel and protected runtime hashes remained unchanged. The native syscall-295 probe remained a clean EBADF/no-SIGSYS PASS.

This closes the CarbonCore system-service transport boundary and establishes that no additional FindService compatibility adapter is required.

The runtime repository is now proceeding with a pre-dispatch compatibility discriminator that keeps the proven CoreServices adapter active and calls the untouched Snow Leopard PPC `SessionGetInfo(callerSecuritySession,...)` path. That is the next unresolved primitive before LaunchServices `_LSDoInitializeProcessesServices`.

No additional XNU change is indicated.


## Pre-dispatch Security boundary: SessionGetInfo returns status 1

The companion runtime repository has completed the pre-dispatch compatibility discriminator under the proven v3 CoreServices adapter.

On Lion, translated PPC CarbonCore again completes its adapted bootstrap lookup and ServerCheckin sequence and returns a nonzero `LaunchApplicationServices` service port. The next untouched Snow Leopard PPC call, `SessionGetInfo(callerSecuritySession,...)`, returns normally with status `1`, session ID zero, and attributes zero. The exact Snow Leopard control returns status 0 with a nonzero session ID and nonzero attributes.

No crash/core diagnostic was produced. Protected runtime and kernel identities remained unchanged. The native syscall-295 probe remains a clean EBADF/no-SIGSYS PASS.

The active compatibility boundary is therefore user-space Security/session behavior, not XNU or CarbonCore.

The subsequent read-only Security/securityd shipped-binary audit proved that the restored Snow Leopard PPC `ucsp_client_getSessionInfo` request is `0x428` (1064), and that first use performs SecurityServer lookup/verification/setup before that request.

The follow-on Security-only discriminator localized the live Lion failure at `bootstrap_look_up("com.apple.SecurityServer")`, before any legacy Security ucsp request.

The companion runtime repository has now completed the standalone SecurityServer bootstrap proof. Snow Leopard's ordinary lookup returned a nonzero service port. On Lion, the translated PPC subject sent the binary-confirmed UUID-expanded `0xbc` lookup request (request ID `0x194`, target PID 0, zero instance UUID, flags 0) for `com.apple.SecurityServer`; Lion returned Mach success and the expected complex `0x28` reply with one descriptor and a nonzero service port.

This closes the Security first-use bootstrap failure as the same user-space launchd request-layout mismatch already proven for the earlier coreservicesd path.

The follow-on Security-only integration has now advanced through that corrected bootstrap lookup. Lion accepts `verifyPrivileged2 (0x441)` and `setup (0x3e8)`, then the untouched Snow Leopard PPC client sends `getSessionInfo (0x428)`. Mach transport succeeds but Lion returns a simple `0x24` MIG error reply. The PPC-visible raw error word `0xd1feffff` is byte-swapped by the shipped generated stub according to the reply NDR integer representation, yielding `0xfffffed1` = signed `-303` / `MIG_BAD_ID`. The retired legacy session RPC is therefore directly proven absent.

Lion's native `SessionGetInfo(callerSecuritySession,...)` instead uses the kernel-backed AuditInfo path through `getaudit_addr(..., 0x30)`. The runtime repository is now proceeding with a narrow AuditInfo oracle that validates the native field mapping and checks whether translated PPC can call `getaudit_addr` directly before any API compatibility shim is designed.

This remains entirely a user-space compatibility boundary; no additional XNU change is indicated.


## Security AuditInfo oracle: translated PPC can read Lion audit-session state

The companion runtime repository has completed the corrected Security AuditInfo oracle.

On Lion, native i386 `SessionGetInfo(callerSecuritySession,...)` returned status 0 and its session ID/attribute outputs exactly matched the typed 0x30-byte `auditinfo_addr` returned by `getaudit_addr`. The translated PPC subject also called `getaudit_addr` successfully and returned the same audit session ID. The first raw 32-bit word of the 64-bit `ai_flags` field differs across i386 and PPC because of endianness, so the next runtime experiment uses the typed 64-bit field rather than a hard-coded word.

The runtime repository is now proceeding with a one-tuple process-local `SessionGetInfo(callerSecuritySession,...)` adapter that reads `auditinfo_addr_t.ai_asid` and `ai_flags` directly and bypasses the retired SecurityServer `getSessionInfo=0x428` RPC entirely.

The validated syscall-295 gate remains a clean EBADF/no-SIGSYS PASS, protected identities were unchanged, and no new diagnostic was produced. This remains a user-space compatibility boundary; no additional XNU change is indicated.


## Security SessionGetInfo AuditInfo API adapter proof

The companion runtime repository has completed the standalone process-local `SessionGetInfo(callerSecuritySession,...)` compatibility proof.

On Lion, the translated PPC one-tuple interposer called `getaudit_addr` successfully, read the typed 0x30-byte `auditinfo_addr_t`, and returned `ai_asid=0x000186a3` with logical attribute bits `0x00002030`. The public PPC probe observed status 0 and exactly the same session ID and attributes. The raw PPC words confirm the expected big-endian view of the 64-bit `ai_flags` field: the high 32-bit half is at offset `0x28` and the low half is at `0x2c`.

No SecurityServer session RPC is needed for this `callerSecuritySession` API path. The runtime repository is now proceeding with a combined pre-dispatch integration using the already-proven CoreServices transport adapter plus this Security API adapter, while still stopping before LaunchServices process-services initialization and Process Manager identity calls.

The native syscall-295 gate remains a clean EBADF/no-SIGSYS PASS. This remains a user-space compatibility boundary; no additional XNU change is indicated.


## Combined pre-dispatch compatibility proof

The companion runtime repository has now completed the combined pre-dispatch integration with both proven user-space compatibility layers active in the same translated PPC process.

On Lion, the v3 CoreServices adapter completed the coreservicesd bootstrap and ServerCheckin adaptations and returned a nonzero `LaunchApplicationServices` service port. The AuditInfo-backed Security adapter then returned `SessionGetInfo(callerSecuritySession,...)=0` with a nonzero session ID and valid attributes. The original pre-dispatch subject reached `PREDISPATCH_PRIMITIVES_PASS` and exited normally. No crash/core diagnostic was produced and all protected identities remained unchanged.

The runtime repository is therefore advancing to the first LaunchServices process-services wire transaction: one exact Snow Leopard PPC `InitializeProcessesServices` request (ID `0x4650`, send `0x2c`, receive `0x50`, expected reply `0x46b4`) after the now-proven service/session prerequisites. That stage remains entirely user-space and stops before dispatch-table installation or Process Manager identity calls.

The native syscall-295 gate remains a clean EBADF/no-SIGSYS PASS. No additional XNU change is indicated.


## LaunchServices InitializeProcessesServices wire proof

The companion runtime repository has now completed the first LaunchServices process-services wire transaction after the proven CoreServices and Security compatibility prerequisites.

On Lion, the translated Snow Leopard PPC client sent the binary-proven InitializeProcessesServices request with ID `0x4650`, send size `0x2c`, receive size `0x50`, the current security session ID twice, and process-services version `0x00a1be40`. Mach transport succeeded. Lion coreservicesd returned the expected complex reply ID `0x46b4`, size `0x48`, two descriptors, a nonzero process port, `outVersion=0x00a1be40`, `outError=0`, and `outCount=0`. The Snow Leopard control produced the same successful reply shape and scalar values.

The runtime repository is therefore advancing to the real Snow Leopard PPC LaunchServices post-reply setup path. The next experiment calls the audited local `getProcessDispatchTable()` function directly, then verifies the established process-services port, while still stopping before any Process Manager identity API.

The native syscall-295 gate remains a clean EBADF/no-SIGSYS PASS. This remains a user-space compatibility investigation; no additional XNU change is indicated.


## LaunchServices process-dispatch setup proof

The companion runtime repository has now completed the corrected Snow Leopard PPC LaunchServices process-dispatch setup experiment.

On Lion, with the proven CoreServices bootstrap/ServerCheckin adapter and AuditInfo-backed Security `SessionGetInfo` adapter active, the real Snow Leopard PPC `getProcessDispatchTable()` setup path returned nonzero dispatch table `0xa0bbf59c`. A subsequent `getProcessesServerPort()` call returned nonzero port `0x00008f03`. No diagnostic was produced and all protected identities remained unchanged. The corrected Snow Leopard control passed the same local-function resolution/prologue checks and returned a nonzero dispatch table and server port.

This closes the earlier LaunchServices dispatch-table abort candidate. The runtime repository is now advancing to exactly one `GetProcessForPID(getpid(), &psn)` call after re-proving dispatch state in the same PPC process, with the historical `LSDONOTABORTIFNOASN` override explicitly left unset.

The native syscall-295 gate remains a clean EBADF/no-SIGSYS PASS. This remains a user-space compatibility boundary; no additional XNU change is indicated.


## Post-dispatch GetProcessForPID termination

The companion runtime repository has now reached `GetProcessForPID(getpid(), &psn)` only after re-proving a nonzero Snow Leopard PPC LaunchServices process-dispatch table and process-services port in the same Lion process. The CoreServices bootstrap/ServerCheckin adapter and AuditInfo-backed Security `SessionGetInfo` adapter both passed first.

The identity call did not return. The first runner recorded exit status `138` and listed a crash report plus `/cores/core.17940`. Its historical result label called every non-returning identity call an “abort,” but that classification did not inspect the actual signal, and this status differs from the already-proven status-`134` SIGABRT family. Protected hashes remained unchanged, and the native syscall-295 gate remains a clean EBADF/no-SIGSYS PASS.

The runtime repository is therefore performing a read-only preserved-core/crash postmortem before any no-ASN override or further compatibility change. No additional XNU change is indicated.


## Post-dispatch GetProcessForPID SIGBUS localization

The companion runtime repository has completed the preserved-core postmortem for the first `GetProcessForPID` call made after the translated PPC process had already established a nonzero LaunchServices dispatch table and process-services port.

The failure is not the historical guest-requested SIGABRT/no-ASN branch. The crash is `EXC_BAD_ACCESS (SIGBUS)` with `KERN_PROTECTION_FAILURE` at guest address `0x3c`. The PPC stack localizes the fault through `GetProcessForPID -> __RegisterApplication -> __LSApplicationCheckIn -> __CSCheckFix -> _GetBugsForOurBundleIDFromCoreservicesd`, then through CoreFoundation FSRef conversion and CarbonCore filesystem/session-universe helpers, ending at `__SCSessionUniverseByUIDAcquireAndLock`.

The PPC register state includes `r10=0xd0feffff`, which byte-swaps to signed `-304` / `MIG_BAD_ARGUMENTS`; this is being treated only as a static clue until the exact CarbonCore path proves it live.

The runtime repository is therefore advancing to a read-only Snow Leopard/Lion CarbonCore session-universe differential audit. The native syscall-295 gate remains validated, and no additional XNU change is indicated.


## CarbonCore session-universe InitConnection differential

The companion runtime repository has completed the Snow Leopard/Lion CarbonCore session-universe differential audit. Both reports pass, and the validated Rosetta cache/map identities are unchanged across the two systems.

The decisive user-space difference is in `__SCSessionUniverseByUIDAcquireAndLock`. Snow Leopard PPC calls `__scclient_SCSessionUniverseInitConnection_rpc` with five arguments, including an explicit PID: `port,pid,uid,0,&out`. Snow Leopard i386/x86_64 use the same five-argument family with architecture/layout values 2/3. Lion native CarbonCore instead uses `port,uid,2/3,&out`, with the explicit PID removed.

Snow PPC also continues after a nonzero InitConnection return without constructing a mapped universe, whereas Lion native code logs the RPC error and aborts. This is consistent with the preserved translated-PPC `-304/MIG_BAD_ARGUMENTS` register clue and subsequent SIGBUS at `0x3c`, but the runtime repository is first performing a read-only generated-stub protocol audit to prove the exact message ID/layout/size mismatch before writing any adapter.

The native syscall-295 gate remains validated. No additional XNU change is indicated.


## SCSessionUniverse InitConnection wire mismatch proof

The companion runtime repository has completed the Snow Leopard/Lion generated-stub audit for the CarbonCore `SCSessionUniverseInitConnection_rpc` boundary under the first post-dispatch `GetProcessForPID` failure.

The mismatch is now exact. Snow Leopard PPC sends request ID `0x2712`, size `0x2c`, with scalar payload `PID, UID, layout`. Lion retains request ID `0x2712` but its native client and generated dispatcher use size `0x28` with payload `UID, layout`; the explicit PID field is gone. Lion's dispatcher requires `msgh_size == 0x28` and emits `MIG_BAD_ARGUMENTS (-304)` on the legacy request-shape failure path. This directly explains the preserved translated-PPC `0xd0feffff` / byte-swapped `-304` result before the later null-universe SIGBUS.

The reply remains wire-compatible for this boundary: reply ID `0x2776`, success size `0x2c`, error size `0x24`. The runtime repository is advancing to a process-local request-only `mach_msg` adapter that drops the legacy PID and shifts UID/layout into Lion's `0x28` request, while leaving the reply unchanged. The adapter is first gated by a Snow Leopard passthrough control.

The native syscall-295 gate remains validated. This is a user-space CoreServices protocol boundary; no additional XNU change is indicated.


## SessionUniverse InitConnection adapter pass and next Process Manager boundary

The runtime repository has now completed the corrected v5 SessionUniverse InitConnection compatibility experiment.

On Snow Leopard, the v5 CoreServices interposer observed the exact legacy InitConnection transaction transparently and the control completed `GetProcessForPID` successfully.

On Lion, the existing user-space compatibility stack now proves:

```text
CoreServices bootstrap adaptation      PASS
CoreServices ServerCheckin adaptation  PASS
Security SessionGetInfo AuditInfo      PASS
SessionUniverse InitConnection v5      PASS
GetProcessForPID(getpid(), &psn)       PASS with nonzero PSN
```

The InitConnection adapter translated only request ID `0x2712` from Snow PPC's `0x2c [PID,UID,layout]` request to Lion's `0x28 [UID,layout]` request and received the compatible `0x2776 / 0x2c / RetCode=0` reply. The PPC identity call then returned normally. No new crash/core diagnostic was produced and all guarded runtime/kernel identities remained unchanged.

The native syscall-295 probe still returns EBADF without SIGSYS under the validated kernel. This confirms that the repaired boundary remains entirely user-space.

The runtime repository is advancing to a second documented Process Manager identity proof: `GetProcessPID` on the PSN returned by `GetProcessForPID`, requiring an exact PID round-trip and stopping before foreground conversion or GUI work.

No additional XNU code change is indicated.


## Process Manager identity round-trip pass

The runtime repository has now completed the post-identity `GetProcessPID` round-trip experiment successfully.

With the existing validated syscall-295 kernel and unchanged user-space compatibility stack, Lion now proves:

```text
CoreServices bootstrap adaptation       PASS
CoreServices ServerCheckin adaptation   PASS
Security SessionGetInfo AuditInfo       PASS
SessionUniverse InitConnection v5       PASS
GetProcessForPID(getpid(), &psn)        PASS
GetProcessPID(returned PSN, &pid)       PASS
returned pid == getpid()                YES
```

The accepted Lion run used the same v5 CoreServices interposer and v1 Security interposer as the preceding SessionInit proof. The PSN returned after registration was consumed by a second documented Process Manager identity API and mapped back to the exact subject PID. No new crash/core diagnostic was produced and protected hashes remained unchanged.

The native syscall-295 probe still reaches the compatibility front-end and returns EBADF without SIGSYS. No additional XNU behavior is implicated.

The runtime repository is advancing to the first foreground-conversion boundary: one `TransformProcessType(..., kProcessTransformToForegroundApplication)` call after re-proving both identity directions, with a mandatory Snow Leopard direct-execution control before Lion.

No additional XNU code change is indicated.


## TransformProcessType foreground-conversion pass

The runtime repository has now completed the first foreground-conversion experiment successfully.

With the validated syscall-295 kernel and unchanged user-space compatibility stack, Lion now proves:

```text
CoreServices bootstrap adaptation                         PASS
CoreServices ServerCheckin adaptation                     PASS
Security SessionGetInfo AuditInfo                         PASS
SessionUniverse InitConnection v5                         PASS
GetProcessForPID(getpid(), &psn)                          PASS
GetProcessPID(returned PSN, &pid)                         PASS
TransformProcessType(returned PSN, foreground)            PASS
```

The accepted Lion run returned status 0 from `TransformProcessType`, produced no new crash/core diagnostic, and left all guarded runtime/kernel identities unchanged. Snow Leopard also passed the same direct-execution foreground conversion, validating that test context.

The native syscall-295 probe still reaches the compatibility front-end and returns EBADF without SIGSYS. No additional XNU behavior is implicated.

The runtime repository is advancing to one `SetFrontProcess` call using the same PSN, still before window creation, front-process verification, or an event loop.

No additional XNU code change is indicated.


## SetFrontProcess returned-error boundary

The runtime repository has completed the first front-process selection experiment.

The Snow Leopard direct-execution control returned status 0 from:

```text
GetProcessForPID
GetProcessPID
TransformProcessType
SetFrontProcess
```

On Lion, the same validated compatibility stack again passed the repaired SessionInit transaction, both Process Manager identity directions, and `TransformProcessType`, but `SetFrontProcess` returned `-50` normally. The call did not crash or abort, no second exact SessionInit request occurred, no new crash/core diagnostic was produced, and all guarded runtime/kernel identities remained unchanged.

The native syscall-295 probe still reaches the compatibility front-end and returns EBADF without SIGSYS. No additional XNU behavior is implicated.

The runtime repository is advancing to a read-only differential audit of HIServices `SetFrontProcess`/`SetFrontProcessWithOptions` and its CoreGraphics/CGS/CPS/LaunchServices dependencies before any new compatibility behavior is considered.

No additional XNU code change is indicated.


## SetFrontProcess call-path audit localizes failure to CPS/CoreGraphics

The runtime repository has completed the first read-only SetFrontProcess call-path audit on Snow Leopard and Lion.

The audit confirms that:

```text
Snow PPC SetFrontProcessWithOptions -> _CPSSetFrontProcess
Lion i386 SetFrontProcessWithOptions -> _CPSSetFrontProcess
```

with the public pointer/options checks preceding that call. The actual experiment supplied a non-null PSN and options 0, so the Lion `-50` result is generated at or below the CoreGraphics/CPS boundary rather than by the initial HIServices argument validation.

The validated Rosetta cache/map is still identical across Snow Leopard and Lion and contains both HIServices and CoreGraphics. Thus the translated PPC guest continues to execute the restored Snow Leopard client code while talking to Lion host-side graphics/session services.

The first audit did not exact-target the late CoreGraphics CPS/CGS function windows, so the runtime repository is advancing to a second read-only audit that captures `_CPSSetFrontProcess`, `__CPSSetFrontProcessWithOptions`, `__CGSSetFrontProcess`, default-connection, and CPS registration helpers explicitly.

The native syscall-295 compatibility probe remains unrelated to this returned user-space status. No additional XNU code change is indicated.


## SetFrontProcess CPS/CGS audit resolves pre-transport and latent wire boundaries

The runtime repository has completed the focused read-only CoreGraphics CPS/CGS audit.

The audit proves that restored Snow Leopard PPC `__CPSSetFrontProcessWithOptions` returns raw status `0x3eb` when its current CoreGraphics connection record is null, before issuing `__CGSSetFrontProcess`. Snow PPC HIServices maps that positive CPS status to public `paramErr (-50)`. Lion native CoreGraphics has the same no-connection guard.

The same audit also proves a later user-space protocol difference if transport is reached:

```text
Snow PPC __CGSSetFrontProcess: request 0x729e, reply 0x7302
Lion i386 __CGSSetFrontProcess: request 0x72a1, reply 0x7305
send/receive sizes on both: 0x30 / 0x2c
```

The runtime repository is therefore advancing to a process-local CPS connection-state discriminator that reads the audited PPC CoreGraphics connection slot and records the raw `CPSSetFrontProcess` result before any CGS request-ID adaptation is attempted.

The native syscall-295 compatibility path remains healthy and unrelated to this user-space graphics/session boundary. No additional XNU code change is indicated.


## CPS null-connection discriminator closes current SetFrontProcess pre-transport boundary

The runtime repository has completed the corrected CPS connection-state discriminator on Snow Leopard and Lion.

Snow Leopard establishes the restored PPC CoreGraphics default connection during Process Manager registration: the decoded connection slot begins at zero, becomes nonzero after `GetProcessForPID`, and raw `CPSSetFrontProcess` returns 0.

Lion shows the opposite live state. The same decoded Snow PPC CoreGraphics slot remains zero, HIServices reports that `_CGSDefaultConnection()` is NULL, and raw `CPSSetFrontProcess` returns `0x3eb` before the legacy `__CGSSetFrontProcess` request is reached. No new crash/core diagnostic was produced and all guarded identities remained unchanged.

The runtime investigation is therefore moving one layer earlier into a read-only Snow-PPC/Lion-native differential audit of `_CGSDefaultConnection -> _CGSNewConnection`, WindowServer service-port acquisition, bootstrap/vproc/XPC use, and connection-creation transport. The previously observed `0x729e -> 0x72a1` SetFrontProcess request-ID difference remains a later latent boundary.

The native syscall-295 probe still returns EBADF without SIGSYS. No additional XNU code change is indicated.


## CGS default-connection audit localizes server-port acquisition

The runtime repository has completed the read-only Snow Leopard/Lion CGS default-connection differential audit.

Both systems had a live WindowServer. Snow PPC and Lion native `__CGSDefaultConnection` retain the same high-level `_CGSNewConnection` creation path, and their visible `__CGSNewConnectionPort` client contracts agree at request/reply IDs `0x7469/0x74cd`, receive size `0x44`, Mach options `0x3`, request bits `0x80001513`, and aligned client-name-plus-`0x44` send sizing.

The concrete evolution is earlier in WindowServer server-port acquisition: Snow PPC `_CGSLookupServerPort` calls `_lookupServerPort(0,1)`, while Lion native x86_64 calls `_getSessionPort(1)` and falls back to `_CGSLookupServerRootPort(1)`; Lion additionally contains per-session WindowServer helpers, `bootstrap_look_up_per_user`, and XPC plumbing absent from the Snow PPC lookup path.

The runtime investigation is therefore moving to a second read-only helper audit to prove the exact Snow service-name/bootstrap tuple and Lion replacement semantics before any process-local compatibility adapter is considered.

The native syscall-295 probe remains healthy. No additional XNU code change is indicated.


## CGS server-port audit requires corrected exact-window pass

The first runtime CGS server-port acquisition reports passed their version-1 validation gates, but report review exposed an analyzer-selection ambiguity rather than a kernel issue. The relevant CoreGraphics slices contain duplicate local `_lookupServerPort` symbols; version 1 kept only the last same-name address for exact-window emission. It also did not emit the complete Snow PPC `_CGSLookupSessionPort` helper that sits in the candidate session/root lookup cluster. Consequently, the version-1 reports do not yet prove the exact active WindowServer port-acquisition contract and do not justify a user-space lookup adapter.

The runtime repository has corrected the analyzer to version 2. The next step is another read-only Snow Leopard/Lion pass that preserves all duplicate symbol addresses and captures the Snow `_CGSLookupSessionPort` and Lion `__CGSGetSessionPort` paths before any compatibility behavior is introduced.

The native syscall-295 probe remains healthy. No additional XNU code change is indicated.


## CGS server-port v2 audit resolves the user-space session-port contract

The corrected runtime version-2 CGS server-port audit has passed on Snow Leopard and Lion and resolves the duplicate-symbol ambiguity without identifying a new kernel defect.

Snow PPC CoreGraphics obtains its initial WindowServer session port from task special port 4 through ordinary `bootstrap_look_up("com.apple.windowserver.session")`, with the legacy active/root lookup as fallback. Lion native CoreGraphics instead routes `_CGSLookupSessionPort` through `_getSessionPort(1)`: it obtains the active root WindowServer service using the Lion `bootstrap_look_up2` contract with target PID 0 and privileged-server flag 8, then sends `__CGSGetSessionPort` request/reply `0x7151/0x71b5` and returns a one-descriptor send right. The subsequent DeathWatch request/reply remains `0x714c/0x71b0`.

The runtime repository is therefore advancing to a standalone PPC proof of that native Lion session-port acquisition sequence before any process-local CoreGraphics compatibility interposer is introduced. The existing `__CGSNewConnectionPort 0x7469/0x74cd` path remains downstream of the active failure.

The native syscall-295 probe remains healthy. No additional XNU code change is indicated.


## Standalone translated-PPC CGS session-port proof passed

The runtime repository has now completed the standalone Snow/Lion CGS session-port protocol proof without identifying any new kernel defect.

On Snow Leopard 10.6.8, the corrected version-3 PPC probe successfully resolved `com.apple.windowserver.session`, validated the returned send right, and completed the unchanged DeathWatch request/reply `0x714c/0x71b0` with the expected `0x11/0x00` port descriptor.

On Lion 10.7.5, translated PPC successfully used the native active WindowServer lookup contract (request `0x194`, target PID 0, zero UUID, flags 8), received a root-owned WindowServer service port, completed `GetSessionPort 0x7151/0x71b5`, validated the returned session send right, and completed the unchanged DeathWatch transaction. No new crash/core diagnostic was produced and protected hashes remained unchanged. The Lion runner ended `RESULT: CGS_SESSION_PORT_PROTOCOL_ADAPTER_PASS`.

The runtime repository is therefore moving to a narrowly scoped process-local integration experiment for only the legacy `bootstrap_look_up("com.apple.windowserver.session")` call. That experiment will perform one Process Manager registration request and read the already-audited CoreGraphics connection slot, stopping before foreground/CPS transport. The known `0x729e -> 0x72a1` SetFrontProcess request-ID difference remains a later boundary and is not being adapted yet.

The native syscall-295 probe still returns EBADF without SIGSYS. No additional XNU code change is indicated.


## CGS session-bootstrap integration advances past lookup but exits before identity return

The runtime repository has now tested the exact process-local compatibility bridge for Snow PPC `bootstrap_look_up("com.apple.windowserver.session")`.

On Lion 10.7.5, translated PPC successfully completed the native active WindowServer lookup, obtained a root-owned send right, completed `GetSessionPort 0x7151/0x71b5`, validated the returned session send right, and the integration interposer reported `ADAPTER_PASS`. The process then exited with status 1 before the post-`GetProcessForPID` marker. No new crash/core diagnostic was produced and protected hashes remained unchanged.

The earlier runner label `GETPROCESSFORPID_ABORT_OR_CRASH` was overbroad for this exact result; runtime `main` now distinguishes the clean status-1 early exit. The next runtime stage is a behavior-preserving trace of the immediate downstream CoreGraphics Mach transactions: DeathWatch `0x714c/0x71b0` and `__CGSNewConnectionPort 0x7469/0x74cd`. No request adaptation is being introduced at this stage.

The native syscall-295 probe remains healthy, returning EBADF without SIGSYS. No additional XNU code change is indicated.


## Passive CGS registration trace corrects DeathWatch path assumption

The first Snow Leopard passive registration trace completed successfully at the platform level: `__CGSNewConnectionPort` request `0x7469` received Mach success and reply `0x74cd`, `GetProcessForPID` returned 0, and the CoreGraphics connection record became nonzero. The runtime runner nevertheless reported failure because it incorrectly required a `0x714c/0x71b0` DeathWatch transaction.

The previously collected Snow PPC static audit resolves the discrepancy. The registration path is `_CGSNewConnection -> _CGSServerPort -> _lookupServerPort(0,0) -> __CGSNewConnectionPort`; the separate `_CGSLookupServerPort` helper is the path that wraps `_lookupServerPort(0,1)` with `__CGSSessionDeathWatchPort`. Runtime `main` now treats DeathWatch as optional evidence for this experiment and gates on the actual registration transaction `0x7469/0x74cd`.

The native syscall-295 result remains healthy. No additional XNU code change is indicated.


## CGS session bridge passes but registration stops before NewConnection

The corrected runtime passive trace now places the remaining translated-PPC CoreGraphics failure entirely in user space after the proven session-port adapter.

Snow Leopard registration reaches `__CGSNewConnectionPort` request `0x7469`, receives Mach success with reply `0x74cd`, returns successfully from `GetProcessForPID`, and publishes a nonzero CoreGraphics connection record. Lion translated PPC instead completes the native active-root lookup, `GetSessionPort 0x7151/0x71b5`, validates the returned send right, and reports session-bootstrap `ADAPTER_PASS`, but exits with status 1 before any `0x7469` request is observed. No new crash/core diagnostic is produced and protected hashes remain unchanged.

The runtime repository is therefore moving to a read-only differential audit of the internal CoreGraphics `_connectAndCheck` helper executed inside `_CGSServerPort` after the lookup and before selected-port publication. No new runtime request adaptation has been introduced, and the native syscall-295 probe remains healthy with EBADF/no-SIGSYS.

No additional XNU code change is indicated.


## Connect-and-check audit localizes first unresolved remote helper

The first read-only Snow/Lion `_connectAndCheck` differential passed and confirms that the translated-PPC failure remains entirely in user-space CoreGraphics after a valid Lion session port is returned. Both the Snow PPC and Lion native paths obtain their local CoreGraphics version and PID, then call private `__CGSGetCoreGraphicsServerVersion` before publishing the selected server port. A nonzero return from that helper prevents progress to `__CGSNewConnectionPort`.

Runtime analyzer version 1 did not emit the private server-version MIG client itself, so runtime `main` now advances the same read-only audit to version 2 and exact-targets that helper plus `_CGSGetCoreGraphicsVersion`. No PPC execution or new compatibility behavior is authorized until the resulting Snow/Lion wire contracts are compared.

No additional XNU code change is indicated.


## CGS server-version transport is the next user-space discriminator

The corrected runtime analyzer v2 shows that Snow PPC and Lion native CoreGraphics use the same visible private server-version MIG envelope before NewConnection: request `0x7148`, reply `0x71ac`, request bits `0x1513`, `mach_msg` options `0x3`, send size `0x24`, and receive size `0x48`. Both clients include NDR/endian-aware reply handling.

The important static difference is framework version provenance: Snow Leopard CoreGraphics is 545.0.0 and Lion CoreGraphics is 600.0.0. Snow PPC `_connectAndCheck` compares server-returned version values to its local values and can return `0x3f0`; Snow PPC `_CGSServerPort` handles `0x3f0` with `exit(1)`, matching the currently observed translated-PPC stop after the session-port adapter and before NewConnection.

Runtime `main` therefore advances to a passive `0x7148/0x71ac` trace-v2 with a Snow positive control and exactly one Lion run. No reply rewrite or defaults override has been introduced. Syscall 295 remains healthy, and no additional XNU code change is indicated.


## CGS server-version skew confirmed dynamically

The runtime passive trace now confirms the remaining pre-NewConnection failure mechanism without implicating XNU. Snow PPC and Lion translated PPC both send the same private CoreGraphics server-version request `0x7148` and receive the expected complex `0x71ac` reply. The Snow raw version field `0x21020000` decodes through the PPC MIG NDR path to 545, while the Lion reply field `0x58020000` decodes to 600. The second version field is zero in both, and the remaining reply structure is equivalent apart from expected Mach port names.

After the Lion 600/0 reply, restored Snow PPC CoreGraphics follows its existing version-mismatch path and exits with status 1 before `__CGSNewConnectionPort`; no crash/core diagnostic appears and protected hashes remain unchanged. The native syscall-295 probe still returns EBADF/no-SIGSYS PASS.

Runtime `main` therefore advances to a standalone byte-level 600/0-to-545/0 compatibility-policy proof before any integrated reply normalization. No additional XNU code change is indicated.


## Standalone CGS server-version normalization proof passed

The runtime standalone policy proof has now validated the exact compatibility transformation without involving the integrated CoreGraphics client. Snow PPC reproduced the `0x7148 -> 0x71ac` reply with decoded version 545/0. Lion translated PPC reproduced the same reply shape with decoded version 600/0, then an NDR-aware copied-buffer normalization changed only the version region to 545/0, changed exactly one byte, preserved descriptor/auxiliary/flags outputs, and changed no byte outside offsets `0x30..0x37`. The proof exited successfully with no new diagnostic and unchanged protected hashes.

Runtime `main` now advances to one registration-only integration using the existing CoreServices `mach_msg` interposer with an exact, predicate-gated live `0x71ac` normalization. Snow remains passthrough. The test asks only whether the restored client then reaches `__CGSNewConnectionPort 0x7469` and publishes a nonzero default connection. The known later `0x729e` foreground/CPS mismatch remains deliberately out of scope.

Syscall 295 remains healthy, and no additional XNU code change is indicated.


## Default CoreGraphics connection established; CPS registration remains the active user-space boundary

The runtime server-version compatibility integration has now passed its narrow connection objective. Lion translated PPC accepted the exact NDR-aware `600/0 -> 545/0` server-version normalization, reached `__CGSNewConnectionPort 0x7469`, received expected reply `0x74cd` with Mach success, returned successfully from `GetProcessForPID`, and published a nonzero CoreGraphics default-connection record. No new crash/core diagnostic appeared and protected hashes remained unchanged.

The same run still emitted `_RegisterApplication(), FAILED TO REGISTER PROCESS WITH CPS/CoreGraphics in WindowServer, err=-304` after the connection was established. The runtime boundary has therefore moved to CPS application registration. Runtime `main` now prepares a read-only differential of Snow PPC `__CPSRegisterWithServer -> __CGSCheckInApplication` versus Lion native `__CPSRegisterWithServer -> __CGSCreateApplication` before any new dynamic adapter is considered.

The syscall-295 probe remains a clean EBADF/no-SIGSYS PASS. No additional XNU code change is indicated.


## CPS application-registration protocol differential confirmed

The runtime read-only audit now proves that the active post-connection registration client contract changed between Snow Leopard and Lion. Snow Leopard i386/x86_64/PPC expose `__CGSCheckInApplication` and no `__CGSCreateApplication`; Lion i386/x86_64 expose `__CGSCreateApplication` and no legacy helper.

Snow PPC uses `0x7372 -> 0x73d6`, request bits `0x1513`, Mach option `0x3`, receive size `0x2c`, and a variable request sized as aligned string plus `0x40`. Lion native uses `0x73c1 -> 0x7425` with the same reply-size family but a request extended to aligned string plus `0x4c`, adding a 12-byte tail.

Runtime `main` now advances to a passive exact registration transport trace while retaining the already-proven session-port and server-version compatibility layers. The trace will observe the unchanged Snow `0x7372` request and raw Lion reply corresponding to the surviving `_RegisterApplication ... err=-304` before any registration adapter is designed.

No additional XNU code change is indicated.


## CPS legacy registration reply directly returns -304

The runtime passive trace now resolves the surviving CPS registration diagnostic without ambiguity. Snow Leopard PPC sends legacy `0x7372`, receives `0x73d6` / `0x24` with result zero, and completes registration. Lion translated PPC sends the same legacy request and receives the same expected reply envelope with Mach success, but raw result `0xd0feffff`; under the reply NDR this decodes to `-304`, exactly matching the subsequent `_RegisterApplication` diagnostic. The restored default CoreGraphics connection remains nonzero and `GetProcessForPID` passes.

Runtime `main` now advances to a standalone copied-buffer proof of the narrow `0x7372 -> 0x73c1`, request-size `+0x0c`, Lion-tail, and `0x7425 -> 0x73d6` reply-ID compatibility policy. That proof performs no Mach IPC and does not alter server state.

The syscall-295 probe remains a clean EBADF/no-SIGSYS PASS. No additional XNU code change is indicated.


## CPS registration copied-buffer compatibility proof passed

The runtime standalone CPS registration policy proof has now validated the exact Snow-to-Lion request/reply conversion without Mach IPC. For the registration-only subject, Snow's `0x7372` / `0x84` request is copied to a private buffer, converted to Lion native `0x73c1` / `0x90`, and extended by the proven 12-byte tail. The common request region changes by exactly one byte, the original source buffer remains unchanged, and a successful native `0x7425` reply converts back to legacy-facing `0x73d6` by changing exactly two reply-ID bytes while preserving result zero and NDR semantics.

Runtime `main` now advances to one exact live registration integration using the existing two-tuple CoreServices `mach_msg` interposer and a private request/reply buffer. Snow remains passthrough. Lion adaptation is predicate-gated to the first exact traced registration-only request and does not synthesize success if the native reply is not `0x7425/0x24/result 0`.

The syscall-295 probe remains healthy, and no additional XNU code change is indicated.


## CPS registration accepted; postidentity revalidation next

The runtime live integration now confirms that Lion accepts the exact Snow-to-Lion CPS application-registration conversion. The translated process receives a successful native registration reply, the interposer returns the expected legacy-facing success reply, the previous registration error no longer appears, and GetProcessForPID remains successful with no new diagnostic and unchanged protected hashes.

Runtime main now advances to a narrow postidentity revalidation: rebuild only the subject under the same exact executable basename and re-prove GetProcessPID plus TransformProcessType with the accepted compatibility dylibs unchanged. The foreground activation transaction remains held until that gate passes.

The syscall-295 probe remains healthy, and no additional XNU code change is indicated.


## Postregistration identity gate passed; SetFront transport trace next

Runtime evidence now proves that the accepted CPS application-registration repair survives the next Process Manager checkpoints: GetProcessPID returns the exact current PID and TransformProcessType to foreground returns success. No second registration call or new diagnostic is observed, and protected hashes remain unchanged.

Runtime main now advances to one passive live SetFrontProcess transport trace with the full accepted registration stack active. The translated Snow PPC client is expected to expose its legacy 0x729e/0x7302 transaction; the stage does not rewrite it to Lion native 0x72a1/0x7305. The syscall-295 probe remains healthy, and no additional XNU code change is indicated.


## Live SetFrontProcess transport reached; ID-policy proof next

Runtime evidence now proves that the restored translated PPC process reaches the legacy Snow SetFrontProcess Mach transaction on Lion. Snow returns success for 0x729e/0x7302; Lion returns Mach success and a normal 0x7302 reply carrying -304, which propagates to public SetFrontProcess. The earlier connection and registration boundaries remain repaired.

Runtime main now advances to an exact copied-buffer protocol proof that changes only the private request ID from 0x729e to Lion-native 0x72a1, requires native 0x7305/result 0, and changes only the private reply ID back to 0x7302. No payload or server result normalization is permitted.

The syscall-295 probe remains healthy, and no additional XNU code change is indicated.


## SetFrontProcess protocol proof passed; integration build next

Runtime evidence now proves the exact SetFrontProcess compatibility policy. The translated PPC client presents the traced legacy 0x729e request after one accepted CPS registration transaction; the compatibility layer changes only the private request ID to Lion-native 0x72a1, receives native 0x7305/result 0, changes only the private reply ID back to 0x7302, and the public SetFrontProcess call returns success. Snow remains strict passthrough.

Runtime main now advances to a combined SetFront compatibility integration build using the same exact predicate and copied-buffer policy. No payload fields or nonzero native results are normalized.

The syscall-295 probe remains healthy, and no additional XNU code change is indicated.


## Integrated SetFrontProcess compatibility passed; GetFrontProcess verification next

Runtime evidence now proves the exact SetFrontProcess ID-only policy in the normal combined compatibility build. The translated PPC process preserves the repaired registration and identity path, reaches the exact SetFront predicate, receives native Lion success for 0x72a1/0x7305, returns the legacy-facing 0x7302 success reply, and public SetFrontProcess returns 0 with no new diagnostic or protected-state change.

Runtime main now advances to a narrow public GetFrontProcess validation using the same accepted compatibility dylibs unchanged. The new subject calls GetFrontProcess once after successful SetFrontProcess and requires the returned front PSN to match the already-proven process PSN exactly. GetCurrentProcess remains out of scope until this gate is reviewed.

The syscall-295 probe remains healthy, and no additional XNU code change is indicated.


## GetFrontProcess validation passed; historic GetCurrentProcess boundary next

Runtime evidence now proves that the restored foreground-selection state is externally visible through the public Process Manager query: after the accepted registration and SetFrontProcess compatibility path, GetFrontProcess returns success and the returned front PSN exactly matches the current translated PPC process PSN. No new diagnostic or protected-state change is observed.

Runtime main now advances to a narrow GetCurrentProcess validation under the same accepted compatibility stack. The new subject re-proves the complete registration/identity/foreground sequence, then calls GetCurrentProcess exactly once and requires its PSN to match the already-established process PSN. LSDONOTABORTIFNOASN remains unset; no abort suppression or GetCurrentProcess-specific adapter is introduced.

The syscall-295 probe remains healthy, and no additional XNU code change is indicated.


## Historic GetCurrentProcess boundary closed; CreateNewWindow next

Runtime evidence now proves that the original translated-PPC GetCurrentProcess self-abort is no longer present under the restored registration/foreground stack. After successful registration, PID identity, foreground conversion, SetFrontProcess, and GetFrontProcess, GetCurrentProcess returns success and exactly the same PSN already established for the process. No abort suppression, LSDONOTABORTIFNOASN override, or GetCurrentProcess-specific adapter is required.

Runtime main now advances to a narrow CreateNewWindow validation using the same accepted compatibility dylibs unchanged. The new subject creates one small document window, requires a nonzero WindowRef, disposes it immediately, and stops before show/select/visibility or event-loop work.

The syscall-295 probe remains healthy, and no additional XNU code change is indicated.


## CreateNewWindow now localizes to distributed-notifications bootstrap lookup

Runtime evidence now reaches CreateNewWindow after the complete restored registration/identity/foreground sequence, but the API does not return on Lion. Immediately after the pre-CreateNewWindow milestone, the translated Snow PPC client performs bootstrap_look_up2 for com.apple.distributed_notifications.2 with pid 0 and flags 8. Snow returns success and a live service port; Lion's unchanged legacy PPC lookup returns -304 and a null port. HIToolbox then reports framework-resource failure, damage code -4960 with TTheme instance 0, and aborts. Protected hashes remain unchanged.

Runtime main now advances to a standalone distributed-notifications bootstrap compatibility protocol proof that reuses the already-proven Lion launchd 0x194/0x1f8 lookup formatter for exactly that service tuple. No CreateNewWindow retry or window-server adaptation is authorized until the standalone lookup result is reviewed.

The syscall-295 probe remains healthy, and no additional XNU code change is indicated.

## CreateNewWindow distributed-notifications schema captured; runtime registration gate next

The runtime-side process-local bridge now reaches the exact legacy distributed-notifications `.2` path and the capture-only Lion broker has recorded all traffic observed before the current CreateNewWindow abort. The audit contains exactly three valid binary-property-list requests and all three are registrations: MCX management-status changes with object `com.apple.MCX` and behavior 1, CFPreferences external-domain changes with object `com.apple.CFPreferences` and behavior 1, and `AppleColorPreferencesChangedNotification` with Snow's serialized `kCFNotificationAnyObject` sentinel and behavior 4. The audit reports three captures, zero failures, unchanged protected hashes, and a passing syscall-295 compatibility probe.

This supersedes the earlier runtime boundary at the missing Lion `.2` bootstrap service: the lookup/ingress problem has been bridged in process, and the current unresolved work is user-space registration semantics. Runtime main therefore advances to a dedicated native i386 broker that accepts only the three reviewed simultaneous registrations and normalizes the any-object sentinel through Lion's public CoreFoundation API before one controlled CreateNewWindow retry.

No additional XNU code change, kernel rebuild, or reboot is indicated by this evidence.

## CreateNewWindow notification registration closed; HIToolbox resource lookup next

The runtime exact-registration experiment now proves that the three real legacy distributed-notification registrations are not the remaining CreateNewWindow blocker. Lion accepted all three reviewed registrations through the native public CoreFoundation bridge, reported zero broker rejects and zero callbacks, and still aborted before CreateNewWindow returned. The immediate diagnostic remained the same HIToolbox framework-resource URL failure followed by TTheme damage `-4960`.

Runtime evidence and the historical resource audits now point to a user-space HIToolbox theme-resource boundary. Snow PPC HIToolbox statically requests `Extras.rsrc` through `CFBundleCopyResourceURLForLocalization`; Snow's framework bundle contains that resource, while Lion's framework bundle does not. Runtime main advances only to a pass-through live-call trace to confirm that differential on the actual CreateNewWindow path before any resource compatibility mechanism is considered.

The syscall-295 probe remains healthy. No additional XNU code change, kernel rebuild, or reboot is indicated.

## Live HIToolbox Extras lookup confirmed; exact user-space resource fallback next

The runtime live trace has now confirmed that the remaining CreateNewWindow abort is not a kernel boundary. The same restored Snow PPC HIToolbox callsite requests `com.apple.HIToolbox` / `Extras` / `rsrc` on both systems. Snow resolves that request to its `Extras.rsrc` and completes CreateNewWindow; Lion returns NULL immediately before the HIToolbox framework-resource warning and TTheme `-4960` abort. The already-proven distributed-notification registrations still complete with zero rejects, and the syscall-295 compatibility probe remains healthy.

Runtime main now advances to an exact, process-local user-space resource fallback experiment using only the SHA-pinned Snow Leopard 10.6.8 `Extras.rsrc`, copied from the user's own Snow installation and never installed into Lion's system framework. The forced external-resource path must pass on Snow before a single Lion fallback run is attempted. Lion's `Extras2.rsrc` is not considered equivalent. No additional XNU code change, kernel rebuild, or reboot is indicated.

## Post-Extras notification request is the current runtime gate

The exact process-local Snow `Extras.rsrc` fallback has advanced the restored PPC CreateNewWindow path beyond the prior HIToolbox/TTheme abort. Lion now reaches the exact resource lookup twice with `original=NULL fallback=NONNULL`, then emits a fourth legacy distributed-notification request that the intentionally three-name native registration broker rejects with status 25 (`BROKER_REJECT_NAME`). Execution subsequently reaches `M21_AFTER_CreateNewWindow` and returns `-304`; a downstream `com.apple.dock.server` lookup also fails with `-304`.

Runtime work now pauses policy expansion and captures the exact fourth notification dictionary first. The new diagnostic broker keeps the already-reviewed first three registrations intact, records the fourth request's full binary plist/XML, and intentionally returns the same name rejection. The later dock-server boundary is not changed in this stage. Syscall-295 remains a safety gate only; no XNU code change, kernel rebuild, or reboot is indicated.

## Exact Extras fallback advances past TTheme; fourth notification request exposed

The exact Snow Leopard 10.6.8 `Extras.rsrc` fallback experiment confirms that the process-local resource compatibility path works on Lion. The staged resource hash remained the reviewed `a0866d6cf2d48fac7787e8cf9e90264071642c0d39aa809636e7d478016a9197`; the restored PPC HIToolbox exact `com.apple.HIToolbox` / `Extras` / `rsrc` lookup was reached twice; Lion's original CFBundle lookup returned NULL both times; and the process-local fallback returned NONNULL both times. The prior HIToolbox resource warning and TTheme `-4960` abort did not recur.

Execution then crossed a newly reachable fourth legacy distributed-notification request. The exact-registration broker had accepted the three previously reviewed registrations, but rejected request 4 with status 25, which is its deliberate unreviewed-name rejection. The subject subsequently reached `M21_AFTER_CreateNewWindow` and returned `CreateNewWindow=-304`; a later `com.apple.dock.server` passthrough lookup also returned `-304`. Protected hashes remained unchanged, and the syscall-295 routing probe remains healthy.

The next runtime gate is `lion-rosetta-runtime/docs/process-manager-createwindow-post-extras-distributed-notification-schema-audit.md`. That diagnostic preserves the accepted first three native registrations and exact Snow `Extras.rsrc` fallback, captures the full fourth request dictionary, and intentionally continues to reject it. Do not broaden the notification allowlist or alter the downstream dock-server/CGS path until that request has been reviewed. No XNU code change, rebuild, or reboot is indicated.

## Exact fourth notification schema reviewed

The post-Extras CreateNewWindow schema audit passed after the exact Snow `Extras.rsrc` fallback. The fourth newly reachable legacy request is an ordinary eight-key `register` for `AppleAquaColorVariantChanged`, with `object=kCFNotificationAnyObject`, legacy behavior 4, counter 1, and the same PPC client/session discipline as the previously reviewed registrations. Static Snow Leopard HIToolbox evidence also contains this notification name in the appearance-preference cluster.

The runtime next gate is `lion-rosetta-runtime/docs/process-manager-createwindow-post-extras-distributed-notification-registration-experiment.md`: accept only this exact fourth registration through the existing native public-CoreFoundation broker path and rerun CreateNewWindow once with the exact Snow theme-resource fallback unchanged. If all four registrations pass and the existing `com.apple.dock.server` bootstrap lookup still returns `-304`, that user-space/bootstrap boundary becomes the next diagnostic target.

No XNU code change, rebuild, or reboot is indicated.



## Exact four notification registrations established; Dock bootstrap is next

The exact-four post-Extras CreateNewWindow run completed the currently reviewed distributed-notification compatibility sequence. Lion's native public-CoreFoundation broker accepted all four exact registrations with zero rejects, while the exact Snow Leopard HIToolbox `Extras.rsrc` fallback remained effective. The next untouched Snow PPC call was ordinary `bootstrap_look_up("com.apple.dock.server")`; on Lion that call returned `MIG_BAD_ARGUMENTS (-304)` with a zero service port, and `CreateNewWindow` returned `-304` with a null window.

This is a user-space launchd/bootstrap boundary, not evidence for another syscall-295 or VM/kernel defect. Runtime `main` now provides `docs/process-manager-createwindow-dockserver-bootstrap-protocol-adapter-experiment.md`, a standalone proof that first confirms the legacy Dock lookup on Snow Leopard and then sends one already-established Lion-format `0xbc` lookup request on Lion with target PID 0, zero instance UUID, and flags 0. CreateNewWindow and the CGS compatibility interposer remain unchanged until that isolated lookup result is reviewed.

No XNU code change, rebuild, or reboot is indicated.


## Dock bootstrap protocol proof passes; runtime integration is next

The standalone `com.apple.dock.server` lookup discriminator has now passed. Snow Leopard resolved the exact service through ordinary PPC `bootstrap_look_up` with a nonzero port. Lion accepted the known UUID-expanded `0xbc` lookup request with target PID 0, zero instance UUID, and flags 0, returned the expected complex `0x1f8` reply, and supplied a valid send right. No crash/core diagnostic or protected-state change occurred, and the syscall-295 routing probe remained a clean EBADF/no-SIGSYS PASS.

This closes the Dock lookup itself as another user-space launchd/bootstrap request-layout mismatch. Runtime `main` now advances to `docs/process-manager-createwindow-dockserver-bootstrap-compat-integration-experiment.md`, which adds only this exact service-name adaptation to an opt-in v2 build of the existing CGS bootstrap interposer, gates it with a Snow Leopard full CreateNewWindow passthrough control, and then performs one Lion CreateNewWindow run with the already accepted four-registration notification broker and exact Snow `Extras.rsrc` fallback unchanged.

No XNU code change, rebuild, or reboot is indicated.

## Dock bootstrap integration accepted; CGS NewWindow remains user-space boundary

The runtime Dock-aware CreateNewWindow integration now confirms that the exact `com.apple.dock.server` launchd-layout adaptation works inside the restored translated-PPC stack: Lion returns the expected service send right and the runtime interposer reports adapter PASS. The previously accepted four distributed-notification registrations and exact Snow HIToolbox resource fallback remain intact.

The next failure occurs after the Dock lookup: CoreGraphics reports `MIG: server type check failure: CGSNewWindowWithOpaqueShape: Cannot create window`, and public `CreateNewWindow` returns `-304` with no WindowRef. Runtime work therefore advances to the static read-only `docs/process-manager-createwindow-cgs-newwindow-protocol-audit.md` in `lion-rosetta-runtime` to compare Snow PPC and Lion i386 CoreGraphics client contracts before any transport adapter is considered.

The syscall-295 probe remains a clean EBADF/no-SIGSYS PASS with the established kernel identity. This evidence does not indicate an XNU defect; no kernel code change, rebuild, or reboot is part of the next stage.

## CGS NewWindow protocol differential remains a user-space boundary

The runtime static NewWindow audit now passes on Snow Leopard PPC and Lion i386. The generated `__CGSCreateWindowInline` clients retain the same visible message construction, variable send-size formula, Mach options, receive size, reply-size handling, and NDR-aware decoding, but the MIG routine IDs changed from Snow `0x7394/0x73f8` to Lion `0x739a/0x73fe`.

Runtime work therefore advances to a passive exact transport trace of the unchanged Snow PPC `0x7394` request on Snow and then Lion under the already accepted compatibility stack. No NewWindow ID conversion is integrated at this stage.

The syscall-295 compatibility path remains an established safety gate only. This evidence does not indicate an XNU defect; no kernel code change, rebuild, or reboot is part of the next experiment.


## Live CGS NewWindow trace confirms the boundary remains user-space

The runtime passive trace has now dynamically reproduced the exact Snow PPC inline NewWindow request on both systems. Snow and Lion translated PPC both send legacy request ID 0x7394 with bits 0x1513, explicit send/receive sizes 0x68/0x40, and matching visible request words. Snow receives the expected 0x73f8 / 0x38 success reply and creates a window. Lion also completes mach_msg successfully and receives the expected legacy 0x73f8 reply ID, but in the accepted 0x24 error form with raw result 0xd0feffff; the returned NDR decodes that scalar to -304, matching public CreateNewWindow=-304.

This is not a syscall-295, VM, Rosetta execution, or Mach transport failure. Together with the static Lion-native 0x739a/0x73fe contract, it isolates another generated-MIG user-space compatibility boundary. Runtime main advances to docs/process-manager-createwindow-cgs-newwindow-compat-protocol-adapter-experiment.md in lion-rosetta-runtime, a standalone no-Mach-IPC copied-buffer proof of the narrow request/reply ID conversion before any live adapter is integrated.

No XNU code change, rebuild, or reboot is indicated.


## CGS NewWindow copied-buffer policy proof passes; live runtime integration is next

The runtime standalone NewWindow compatibility proof has now passed. For the exact 0x68/0x40 transaction, the private request copy changes only generated-MIG request ID 0x7394 -> 0x739a with one changed byte, zero request-body changes, and zero source-buffer changes. Both accepted native reply forms map only 0x73fe -> 0x73f8 with one changed byte and zero reply-body changes; the modeled 0x24 error remains decoded -304 and is not normalized. Snow control, the syscall-295 EBADF/no-SIGSYS gate, diagnostics, and protected hashes all pass.

Runtime main therefore advances to docs/process-manager-createwindow-cgs-newwindow-compat-integration-experiment.md in lion-rosetta-runtime. That stage performs exactly one live native-ID NewWindow request inside the already accepted user-space compatibility stack and explicitly preserves any nonzero native server result.

This remains a user-space CoreGraphics/MIG compatibility boundary. No XNU code change, rebuild, or reboot is indicated.


## Native NewWindow success reached; post-NewWindow runtime CGS boundary

The latest runtime integration proves that the exact copied-buffer NewWindow ID conversion reaches a native Lion success reply in the restored translated-PPC stack. The adapter changes only request ID `0x7394 -> 0x739a`, receives native `0x73fe` with reply size `0x38` and result 0, changes only the reply ID back to `0x73f8`, and the legacy-facing client accepts that success shape.

The public `CreateNewWindow` call still does not return because additional CoreGraphics work immediately after the successful NewWindow transaction now exposes failures in `CGSSetWindowToReleaseBackingOnOrderOut`, `CGSSetWindowOpacity`, `CGSGetDisplayBounds`, and `CGSShapeWindow`. Protected hashes remain unchanged and the syscall-295 probe still reaches the compatibility front-end and returns EBADF without SIGSYS.

Runtime main therefore moves to a static Snow-PPC versus Lion-i386 audit of those four post-NewWindow CoreGraphics helper contracts before any further live adapter work. This evidence continues to point to runtime/user-space CoreGraphics/MIG compatibility rather than XNU. No kernel source change, rebuild, or reboot is indicated.


## Post-NewWindow CGS static differential passed; release-backing trace next

The runtime static audit now compares the four CoreGraphics helpers exposed immediately after the successful NewWindow compatibility transaction. The first live helper, `CGSSetWindowToReleaseBackingOnOrderOut`, differs only in generated-MIG IDs between Snow PPC and Lion i386: `0x724b/0x72af` versus `0x724c/0x72b0`, with the same `0x1513` bits, `0x3` Mach option, `0x28/0x2c` send/receive sizes, and `0x24` reply geometry. Later ShapeWindow helpers also show ID movement, but they are not yet being changed.

Runtime main therefore advances to a passive, exact release-backing transport trace under the already accepted NewWindow adapter. No release-backing translation is integrated in this stage. Syscall 295 remains a safety gate only, and the evidence continues to point to user-space CoreGraphics/MIG compatibility rather than XNU. No kernel source change, rebuild, or reboot is indicated.


## Release-backing legacy MIG error reproduced; copied-buffer proof next

The runtime passive trace now reproduces the first post-NewWindow CoreGraphics boundary exactly. Snow PPC sends release-backing request `0x724b` and receives `0x72af / 0x24 / result 0`; Lion translated PPC sends the same legacy ID and envelope, receives Mach success plus `0x72af / 0x24`, but the returned raw result `0xd0feffff` decodes to `-304`. The already accepted NewWindow adapter returns native success before this point, syscall 295 still reaches the compatibility front-end and returns EBADF without SIGSYS, and protected system hashes remain unchanged.

Static Lion i386 identifies native release-backing request/reply IDs `0x724c/0x72b0` with the same visible message geometry. Runtime main therefore advances to a standalone no-Mach-IPC copied-buffer proof of only `0x724b -> 0x724c` and `0x72b0 -> 0x72af`. This continues to localize the defect to user-space CoreGraphics/generated-MIG compatibility. No XNU source change, rebuild, or reboot is indicated.


## Release-backing copied-buffer policy passed; live user-space integration next

The runtime standalone policy proof now validates the exact release-backing generated-MIG ID translation with no Mach IPC: `0x724b -> 0x724c` changes exactly one request byte with zero request-body/source changes, and `0x72b0 -> 0x72af` changes exactly one reply byte with zero reply-body changes. Both success result 0 and a modeled nonzero `-304` result are preserved unchanged. The Snow control, Lion syscall-295 safety probe, protected-hash checks, and no-new-diagnostic gate all pass.

Runtime main therefore advances to one exact live release-backing compatibility integration while retaining the already accepted NewWindow adapter. This remains a user-space CoreGraphics/generated-MIG compatibility experiment. Syscall 295 remains healthy and only serves as a safety gate. No XNU source change, rebuild, or reboot is indicated.


## Release-backing live success moves boundary to opacity

The runtime live release-backing compatibility integration now reaches a native Lion success reply. The exact copied request changes only generated-MIG ID `0x724b -> 0x724c`; Lion returns `0x72b0 / 0x24 / result 0`; the copied legacy-facing reply changes only `0x72b0 -> 0x72af`; and the release-backing adapter reports PASS. The legacy-facing transport accepts the reply.

The translated PPC subject still does not return from `CreateNewWindow`. The first subsequent diagnostic is now `CGSSetWindowOpacity` receive-too-large, followed later by display-bounds and ShapeWindow diagnostics. Runtime main therefore advances to a static Snow-PPC/Lion-i386 audit of the opacity wrapper's `__CGSCreateWindowAlphaPlane` and `__CGSTerminateWindowAlphaPlane` generated-MIG clients before any further live transport change.

The syscall-295 probe remains healthy (`EBADF`, no SIGSYS), protected hashes remain unchanged, and no evidence points to a new kernel defect. No XNU source change, rebuild, or reboot is indicated.


## Opacity alpha-plane static differential passed; passive trace next

The runtime focused opacity audit now passes on Snow Leopard PPC and Lion i386. Beneath `CGSSetWindowOpacity`, create-alpha shifts from Snow `0x724f/0x72b3` to Lion `0x7250/0x72b4`, while terminate-alpha shifts from Snow `0x7250/0x72b4` to Lion `0x7251/0x72b5`. Both retain the same visible generated-MIG geometry: bits `0x1513`, option `0x3`, send/receive `0x24/0x2c`, accepted reply `0x24`, and equivalent NDR/result handling.

The Snow terminate IDs collide numerically with Lion create IDs, so no opacity adapter is authorized from static evidence alone. Runtime main advances to a passive create/terminate alpha-plane transport trace that keeps the accepted NewWindow and release-backing adapters unchanged and rewrites no opacity traffic.

This remains a user-space CoreGraphics/generated-MIG boundary. Syscall 295 remains a safety gate rather than the defect under investigation. No XNU source change, rebuild, or reboot is indicated.


## Opacity create-alpha live trace isolates user-space MIG receive boundary

The Snow and Lion passive opacity alpha-plane runs both selected the create-alpha helper. Snow's legacy `0x724f -> 0x72b3 / 0x24` transaction returned result 0 and completed CreateNewWindow through M24. Lion reached the same legacy `0x724f` request after native-success NewWindow and release-backing compatibility transactions, then returned `0x10004004/MACH_RCV_TOO_LARGE`. The static Lion-native create-alpha pair remains `0x7250/0x72b4`.

Runtime `main` therefore advances only to a standalone copied-buffer proof of the create-alpha ID mapping `0x724f -> 0x7250` and `0x72b4 -> 0x72b3`; that proof sends no Mach IPC and must preserve every non-ID byte and result value. Syscall 295 continues to pass the established EBADF/no-SIGSYS gate, and protected hashes remained unchanged in the trace run.

This remains a user-space CoreGraphics/generated-MIG compatibility boundary. No XNU source change, rebuild, or reboot is indicated.


## Opacity create-alpha copied-buffer proof passed; live user-space integration next

The standalone create-alpha compatibility proof now passes with no Mach IPC. It proves the exact copied-buffer mapping `0x724f -> 0x7250` for the request and `0x72b4 -> 0x72b3` for the reply, with exactly one changed byte in each message, zero body/source changes, and preservation of both result 0 and a modeled nonzero result.

Runtime `main` advances only to one exact live create-alpha integration while keeping the accepted NewWindow and release-backing adapters unchanged. The PPC `0x2c` receive size remains untouched; terminate-alpha, display-bounds, and ShapeWindow remain out of scope until that live result is reviewed.

Syscall 295 continues to pass the EBADF/no-SIGSYS safety gate. This remains a user-space CoreGraphics/generated-MIG compatibility boundary, so no XNU source change, rebuild, or reboot is indicated.


## CreateNewWindow construction gate passed; next boundary remains user-space window use

The restored-stack Lion run now completes the exact opacity create-alpha ID conversion with native Mach success and result 0, after the already accepted NewWindow and release-backing conversions. Public `CreateNewWindow` returns 0 with a nonzero WindowRef, immediate disposal completes, the PPC process exits 0, no new crash/core diagnostic is created, and protected hashes remain unchanged.

The same run still logs several CoreGraphics diagnostics during window construction, including display-bounds, ShapeWindow, backing-map/lock, and display-color-space errors. Because these no longer prevent the public API from succeeding, they are not evidence for an additional kernel or syscall defect and are not authorized compatibility targets in isolation.

Runtime validation therefore moves one application operation forward to `SetWindowTitleWithCFString` under the unchanged accepted compatibility stack. Syscall 295 remains EBADF/no-SIGSYS. No XNU source change, rebuild, or reboot is indicated.


## Post-CreateNewWindow title boundary is FontServer bootstrap

The first restored-stack operation after successful CreateNewWindow construction is now localized. Snow Leopard resolves the ordinary PPC `bootstrap_look_up("com.apple.FontServer")` during `SetWindowTitleWithCFString` with `kr=0` and a nonzero port, after which the title API returns 0. Lion reaches the same title boundary but the untouched legacy lookup returns `-304/MIG_BAD_ARGUMENTS` with a zero port before a later fifth distributed-notification request is rejected by the intentionally exact-four broker. Repeated FontServer lookups then fail and CoreText reports invalid font-server IPC destinations.

The next runtime step is a standalone Lion-format launchd lookup discriminator for exactly `com.apple.FontServer`; no window-title rerun, notification-policy broadening, or FontServer RPC is authorized until that result is reviewed. Syscall 295 remains EBADF/no-SIGSYS and protected kernel/runtime identities remain unchanged. No XNU source change, rebuild, or reboot is indicated.


## FontServer standalone launchd lookup passes; live title integration next

The standalone translated-PPC `com.apple.FontServer` discriminator now succeeds with the exact Lion launchd request schema: request ID `0x194`, send size `0xbc`, PID 0, zero UUID, flags 0, followed by complex reply ID `0x1f8`, descriptor count 1, and a valid send right. Snow Leopard's ordinary legacy lookup also succeeds with a nonzero port. No new diagnostic or protected-state change occurred, and syscall 295 remains EBADF/no-SIGSYS.

Runtime validation therefore moves to one exact user-space FontServer lookup integration inside the existing `bootstrap_look_up` interposer, preserving all accepted CreateNewWindow compatibility and the exact-four notification broker unchanged. The fifth notification remains deliberately unaccepted until the FontServer live integration establishes whether it is truly the next boundary. No XNU source change, rebuild, or reboot is indicated.


## FontServer integration passed; fifth notification is next user-space boundary

The exact `com.apple.FontServer` launchd lookup compatibility path now passes live inside the restored-stack `SetWindowTitleWithCFString` run. The adapter returns a valid FontServer send right, after which legacy distributed-notification request index 5 appears with message ID 4, Mach size 356, and payload length 321. The unchanged exact-four broker rejects that request with status 25; the title call then does not return. Protected hashes remain unchanged and syscall 295 remains EBADF/no-SIGSYS.

The next runtime stage is therefore a read-only schema audit of exactly that fifth notification request: accept the four already reviewed registrations, capture the fifth binary plist and XML form, deliberately return status 25, and stop. This is a user-space notification-policy boundary, not evidence of a new syscall/kernel defect. No XNU source change, rebuild, or reboot is indicated.


## Fifth title-path notification schema audited; exact registration integration next

The post-FontServer fifth distributed-notification schema audit passed. The request is an exact legacy `register` dictionary for `com_apple_CoreText_FontManagerChangedNotification`, `kCFNotificationAnyObject`, behavior 1, counter 1, the established client/session scope, and a positive unique registration entry. The audit broker accepted the first four reviewed registrations, captured exactly one fifth request, intentionally returned status 25, and reported zero audit failures or unexpected rejects. Protected runtime/kernel identities remained unchanged and syscall 295 remained EBADF/no-SIGSYS.

Runtime validation therefore advances to an exact-five user-space notification broker and one unchanged `SetWindowTitleWithCFString` integration run. Any sixth unreviewed registration remains rejected and must be audited independently. This is still a distributed-notification user-space policy boundary, not evidence of an XNU defect. No XNU source change, rebuild, or reboot is indicated.


## Exact fifth notification accepted; FontServer RPC transport is next boundary

The reviewed fifth distributed-notification registration now succeeds under the exact-five user-space broker. The broker finishes with five accepted registrations, zero rejects, and exact state. The accepted `com.apple.FontServer` bootstrap adapter also still returns a valid send right.

The window-title call nevertheless does not return. CoreText immediately reports repeated `CopyFontForName` and `CopyPropertiesForFontsMatchingRequest` MIG errors `FFFFFED0` from FontServer. No sixth notification rejection is involved. Runtime validation therefore advances to a passive Snow-versus-Lion `mach_msg` trace targeted only at the exact FontServer service port, so the first failing request ID, send/receive sizes, message body, and reply can be established before any RPC translation is considered.

This remains a user-space service-protocol boundary. Syscall 295 remains EBADF/no-SIGSYS and protected identities are unchanged. No XNU source change, rebuild, or reboot is indicated.


## FontServer first RPC is a user-space protocol boundary

The passive Snow/Lion FontServer transport trace now identifies the first post-bootstrap divergence. Snow PPC sends request `0x32c8` with authoritative send/receive sizes `0x18/0x3c`, receives a complex `0x34` reply `0x332c`, and completes `SetWindowTitleWithCFString`. Lion translated PPC sends the same first request with successful Mach transport but receives a simple `0x24` reply `0x332c` whose raw status bytes are `65 fd ff ff`; later `0x32d9/0x32db` requests receive raw `d0 fe ff ff`, which CoreText reports as `FFFFFED0`.

The next stage is a read-only shipped-binary audit of the FontServer first-RPC method and Lion-native equivalent/precondition. Syscall 295 remains EBADF/no-SIGSYS and the protected kernel/Rosetta identities remain unchanged. This is a user-space FontServer protocol issue; no XNU source change, rebuild, or reboot is indicated.


## FontServer native rendezvous client changed on Lion

The completed first-RPC shipped-binary audit proves that Snow Leopard PPC FontRegistry uses `_XTSendRendezvous` for the `0x32c8` rendezvous transaction, while Lion's required native i386 FontRegistry no longer contains that request constant and instead exposes `_XTSendRendezvous2`; Lion's registry rendezvous path calls the new routine. The `fontd` executable delegates the server implementation to `libATSServer.dylib`, so the remaining work is to decode the new client request and actual server dispatch path.

Runtime validation therefore remains in a read-only user-space protocol-audit phase. The next focused audit exact-targets old/new rendezvous client functions and `libATSServer`; it will establish the Lion request/reply contract and the meaning of the `-667` reply before any adaptation is considered. This does not implicate XNU. No XNU source change, rebuild, or reboot is indicated.


## FontServer Rendezvous2 static contract decoded; still user-space only

The completed runtime v2 audit decodes Lion's native i386 FontRegistry rendezvous client as `_XTSendRendezvous2`, request `0x32e7`, bits `0x1513`, send/receive `0x18/0x40`, reply `0x334b`, and complex success size `0x38`. Its caller requires returned protocol version `5` and nonzero rendezvous payload state. Snow PPC remains on legacy `_XTSendRendezvous` request `0x32c8` with complex `0x332c/0x34` success.

The corrected Lion `libATSServer.dylib` audit has no true protocol-range instruction immediates, so the native server dispatch and semantic meaning of the translated legacy `-667` response remain unresolved statically. Runtime validation therefore advances to one native-i386 Lion FontServer Rendezvous2 transport capture only. This remains a user-space framework/service-protocol boundary; no XNU source change, rebuild, or reboot is indicated.


## Native Lion FontServer Rendezvous2 dynamically confirmed

The runtime one-shot native-i386 Lion trace now closes the remaining FontServer rendezvous server-contract gap. Lion sent request `0x32e7` with bits `0x1513` and send/receive `0x18/0x40`; `mach_msg` returned success with complex reply `0x334b / 0x38`, descriptor count 1, protocol version `5`, and explicit payload size `0x1000`. This matches the static `_XTSendRendezvous2` decode.

Runtime validation therefore advances only to a standalone no-IPC copied-buffer compatibility proof for the legacy Snow `0x32c8/0x332c/0x34` contract versus Lion `0x32e7/0x334b/0x38`. This remains a user-space framework/service-protocol boundary. No XNU source change, rebuild, or reboot is indicated.


## FontServer rendezvous copied-buffer policy proof passed

The runtime standalone PPC no-IPC proof has now validated the first FontServer rendezvous conversion policy. It changes only legacy request ID `0x32c8 -> 0x32e7` while widening the receive argument `0x3c -> 0x40`; native Lion complex success `0x334b/0x38`, protocol version 5, is converted to legacy `0x332c/0x34` by preserving the descriptor/NDR bytes, removing the version word, and relocating the explicit-size word. The modeled simple-error path preserves its nonzero result. Snow control and syscall-295 safety gates passed, no diagnostics appeared, and protected hashes remained unchanged.

Runtime validation therefore advances to one narrowly gated user-space live rendezvous integration run with later FontServer RPCs left trace-only and unadapted. This remains outside XNU; no kernel source change, rebuild, or reboot is indicated.


## FontServer rendezvous live integration passed

The runtime live translated-PPC title test now proves the first FontServer rendezvous compatibility rule end to end: legacy request `0x32c8` was converted to native `0x32e7`, Lion returned the expected complex `0x334b/0x38` protocol-version-5 reply, and runtime code reconstructed the legacy `0x332c/0x34` reply with descriptor/NDR and explicit size preserved. The adapter fired exactly once, `SetWindowTitleWithCFString` returned success, disposal completed, no new diagnostics appeared, and protected hashes remained unchanged. No later FontServer RPC was needed for the title operation.

Runtime validation now advances only to an isolated `ShowWindow` call with all accepted compatibility paths unchanged. This remains a user-space Carbon/WindowServer discriminator; no XNU source change, rebuild, or reboot is indicated.


## ShowWindow reaches a user-space sixth-notification boundary

The isolated ShowWindow subject passes on Snow Leopard but, on Lion, reaches `S00_BEFORE_ShowWindow` and then encounters a sixth legacy distributed-notification request (`id=4`, size 320, payload 287) that the current exact-five broker rejects with status 20. `S01_AFTER_ShowWindow` is not reached. The accepted FontServer rendezvous rule still passes exactly once, protected hashes remain unchanged, and syscall 295 remains healthy.

Runtime now advances to a capture/decode audit of that sixth payload while preserving the status-20 rejection. This is a user-space notification/Carbon boundary; no XNU source change, rebuild, or reboot is indicated.


## Sixth ShowWindow request is a user-space registration identity case

The post-ShowWindow schema audit passed and decoded request 6 as another `AppleAquaColorVariantChanged` registration with the already reviewed AnyObject/behavior-4 filter, `counter=2`, and a distinct positive entry. The distributed-notifications ABI already treats `entry/counter` as per-registration callback identity, so runtime now advances to a narrowly sequence-gated exact-six native broker and one unchanged ShowWindow rerun.

No kernel behavior is implicated by this result. Syscall 295 remains healthy and protected hashes are unchanged; no XNU source change, rebuild, or reboot is indicated.


## Exact-six ShowWindow registration accepted; CGS transport remains user-space boundary

The exact-six distributed-notification integration now accepts all six reviewed registrations with zero rejects and no seventh request. The PPC ShowWindow call still reaches its pre-call marker without reaching its post-call marker, exits 139, and produces crash/core diagnostics; the raw user-space log repeats a `CGSAddTrackingArea` MIG server type-check failure in the ShowWindow interval.

Runtime therefore advances to a behavior-preserving application-CGS Mach transport trace on the existing restored stack. Syscall 295 remains healthy and protected hashes remain unchanged. No XNU source change, kernel rebuild, or reboot is indicated by this result.


## ShowWindow passive trace localizes user-space CGSAddTrackingArea mismatch

The completed passive application-CGS trace is behavior-preserving on Snow Leopard and confirms a user-space generated-MIG boundary on Lion. The unchanged PPC client sends legacy `0x7388 -> 0x73ec` with the same `0x1513`, `0x60 / 0x2c` envelope on both systems. Snow returns result 0; Lion returns `-304 / MIG_BAD_ARGUMENTS` and immediately logs `MIG: server type check failure: CGSAddTrackingArea`. Syscall 295 remains healthy and the protected kernel/runtime hashes are unchanged.

Runtime now advances to a static Snow-PPC-versus-Lion-i386 `CGSAddTrackingArea` CoreGraphics protocol audit. No XNU source change, kernel rebuild, or reboot is indicated.


## ShowWindow CGSAddTrackingArea static differential remains user-space

The completed Snow PPC / Lion i386 CoreGraphics audit identifies the live ShowWindow tracking-area request as `__CGSAddTrackingAreaInline`. Snow uses `0x7388 / 0x73ec`; Lion uses `0x738e / 0x73f2`. The visible generated-MIG geometry is otherwise aligned: bits `0x1513`, option `0x3`, receive size `0x2c`, reply size `0x24`, and send size `0x3c + 4*count`. The previously captured count-9 request therefore maps exactly to the observed `0x60` send size.

Runtime now advances to one guarded user-space inline-ID compatibility integration. The neighboring ShowWindow CGS failures and color-profile/window-context diagnostics remain unmodified. Syscall 295 and protected kernel state remain outside this user-space protocol mismatch, so no XNU source change, kernel rebuild, or reboot is indicated.


## ShowWindow tracking-area adapter passes; next boundary remains user-space

The exact user-space `CGSAddTrackingAreaInline` adapter now succeeds live on Lion: the observed count-9 PPC request is converted `0x7388 -> 0x738e`, Lion returns native `0x73f2 / result 0`, and the adapter returns PPC-facing `0x73ec / result 0` without changing the payload. Snow passthrough remains successful and syscall 295 still returns the expected EBADF path.

`ShowWindow` nevertheless remains open with `S01` absent and exit 139. Two later application-CGS replies still return `-304` (`0x72e7 / 0x734b` and `0x72f2 / 0x7356`) while the color-profile/window-context diagnostic cluster persists. Runtime therefore advances only to a read-only Snow-PPC/Lion-i386 CoreGraphics protocol audit of those transactions. No XNU source change, kernel rebuild, or reboot is indicated.


## ShowWindow post-tracking static audit remains a user-space boundary

The Snow PPC and Lion i386 CoreGraphics audits identify the first remaining post-`S00` failure as `__CGSOrderFrontConditionally`: Snow uses request/reply `0x72e7 / 0x734b`, Lion uses `0x72ea / 0x734e`, and the generated-MIG envelope/payload geometry otherwise matches. The later `__CGSSetFrontWindow` request is independently the same class of release skew, Snow `0x72f2 / 0x7356` versus Lion `0x72f5 / 0x7359`, but it remains held.

Runtime advances only to one exact user-space `CGSOrderFrontConditionally` compatibility experiment after a Snow passthrough control and the existing syscall-295 health gate. No XNU source change, kernel rebuild, or reboot is indicated.


## ShowWindow SetFrontWindow remains a user-space protocol boundary

The exact OrderFrontConditionally compatibility conversion passed on Lion, and the existing AddTrackingArea conversion remained successful. The next deterministic nonzero-window failure is `__CGSSetFrontWindow`: Snow PPC uses request/reply `0x72f2 / 0x7356`, Lion i386 uses `0x72f5 / 0x7359`, with otherwise equivalent generated-MIG geometry. The unchanged Snow ID returns `-304` on Lion before ShowWindow returns.

Runtime therefore advances to one exact user-space SetFrontWindow ID-conversion experiment after the existing Snow passthrough control and syscall-295 health gate. The later zero-window disposal call remains held. No XNU source change, kernel rebuild, or reboot is indicated.


## ShowWindow color-profile/window-context remains a user-space boundary

The exact user-space SetFrontWindow compatibility conversion is now live-proven on Lion and returns native success. OrderFrontConditionally and AddTrackingArea also remain successful. ShowWindow still does not return, but there is no newly observed application-CGS request/reply mismatch after SetFrontWindow.

The remaining first-order evidence is CoreGraphics color-profile/window-context initialization failure followed by null-context rendering errors. Runtime therefore advances only to a static Snow-versus-Lion CoreGraphics audit of `CGSColorProfileCreateWithColorProfileID`, `_CGSWindowColorProfile`, `CGWindowContextCreate`, and their client/port dependencies. No XNU source change, kernel rebuild, or reboot is indicated.


## ShowWindow ColorProfileClient remains a user-space protocol boundary

The static Snow/Lion CoreGraphics differential now attributes the persistent color-profile initialization failure to the generated `__CGSColorProfileClient` RPC family. Snow PPC uses request/reply `0x74d4 / 0x7538`; Lion i386 uses `0x74d6 / 0x753a`, with otherwise equivalent request bits, descriptor/body geometry, send/receive sizes, and reply layout.

Runtime advances only to a target-specific passive live trace of the legacy ColorProfileClient transaction before any ID rewrite is authorized. No XNU source change, kernel rebuild, or reboot is indicated by this boundary.


## ColorProfileClient live trace confirms ID-only user-space boundary

The completed Snow/Lion live trace now confirms the static ColorProfileClient differential. Snow PPC sends `0x74d4` and receives `0x7538 / 0x28` with result zero and a nonzero client ID. On Lion, the unchanged PPC client sends the same exact `0x74d4` request four times; Mach transport succeeds each time, but the server returns `0x7538 / 0x24` with raw `0xd0feffff` (legacy-visible `-304`) and no client ID. The first two failures are at the start of the S00 ShowWindow interval before OrderFrontConditionally/AddTrackingArea/SetFrontWindow, and two retries occur after those accepted adapters. No Lion-native `0x74d6` request is emitted by the PPC client. The failures are immediately followed by the observed CoreGraphics color-profile initialization and window-context diagnostics, while the accepted upstream ShowWindow adapters and exact-six distributed-notifications broker remain successful and protected hashes remain unchanged.

Runtime therefore advances to one exact user-space ColorProfileClient compatibility conversion, gated to the first Lion S00 request after NewWindow/release/create-alpha but before the three ordering/tracking adapters: request ID `0x74d4 -> 0x74d6`, native reply ID `0x753a -> 0x7538`, with the request descriptor/body/PID and reply result/client-ID bytes preserved. This new evidence does not indicate an XNU source change, kernel rebuild, or reboot.


## ColorProfileClient integration passes; profile resolution remains user-space

The rebuilt Snow Leopard ColorProfileClient v2 passthrough control passed, and the Lion syscall-295 probe remains healthy on the accepted kernel. In the single Lion integration, the exact first legacy ColorProfileClient request was converted `0x74d4 -> 0x74d6`; the native server returned `0x753a / 0x28` with result zero and a nonzero client ID; the adapter returned `0x7538 / 0x28` to the PPC client while preserving the reply body. There was no later ColorProfileClient retry.

The first-order failure has therefore moved downstream from client initialization to `CGSColorProfileCreateWithColorProfileID: Cannot resolve color profile id(1)`. The accepted ShowWindow ordering/tracking adapters and exact-six notification broker remain successful, protected hashes are unchanged, and the process still stops before `S01_AFTER_ShowWindow`. Runtime advances to a read-only Snow-PPC/Lion-i386 CoreGraphics audit of `__CGSResolveColorProfile` and its server-side resolve/release family. This evidence still indicates a user-space compatibility boundary; no XNU source change, kernel rebuild, or reboot is indicated.


## ResolveColorProfile static differential remains user-space

The Snow PPC / Lion i386 CoreGraphics resolver audit passes and isolates another generated-MIG release skew immediately downstream of the accepted ColorProfileClient adapter. Snow `__CGSResolveColorProfile` uses request/reply `0x74d7 / 0x753b`; Lion uses `0x74d9 / 0x753d`. The request bits, one-port-descriptor shape, `0x38 / 0x3c` send/receive sizes, and `0x34 / 0x24` success/error reply geometry remain aligned. The corresponding server-side resolve path still performs the same live-relevant client/task/profile lookup sequence.

Runtime therefore advances only to a behavior-preserving passive live ResolveColorProfile discriminator with the accepted ColorProfileClient adapter unchanged. The new static evidence does not indicate an XNU source change, kernel rebuild, or reboot.


## ResolveColorProfile live trace proves user-space generated-MIG boundary

The completed passive ResolveColorProfile experiment leaves the accepted syscall-295 path unchanged: the Lion probe still reaches the compatibility front-end and returns `EBADF` without `SIGSYS`.

The Snow control proves the legacy resolver is healthy: the profile-ID-1 `0x74d7` request receives `0x753b / 0x34` with result zero and the full ShowWindow control passes. In the single Lion run, the accepted ColorProfileClient adapter succeeds first and returns a nonzero client ID; the following resolver uses that same semantic client ID with profile ID 1. Each exact legacy `0x74d7` resolver request completes Mach transport but receives the legacy-facing `0x753b / 0x24` error envelope with raw `0xd0feffff` (-304). This live result matches the static `0x74d7 / 0x753b` versus `0x74d9 / 0x753d` generated-MIG differential.

Runtime therefore advances to a narrowly gated user-space ID-only ResolveColorProfile compatibility experiment: private-copy request ID `0x74d7 -> 0x74d9`, native reply ID `0x753d -> 0x753b`, preserving descriptor, NDR, client ID, profile ID, result, and output bytes. No XNU source change, kernel rebuild, or reboot is indicated. `CGSReleaseColorProfile`, profile synthesis, downstream graphics workarounds, and the held ShapeWindow boundary remain outside this authorization.


## ResolveColorProfile compatibility passes; next boundary remains user-space backing

The accepted Lion syscall-295 probe remains unchanged and passes on the same kernel SHA with `EBADF` and no `SIGSYS`.

The single Lion ResolveColorProfile compatibility run also succeeds at the user-space generated-MIG boundary. The exact provenance-gated legacy `0x74d7` profile-ID-1 request is changed only to Lion `0x74d9`; the native server returns `0x753d / 0x34` with result zero; the PPC-facing reply changes only back to `0x753b`. The prior color-profile resolution and window-context creation diagnostic cascade disappears.

The next repeated failure is still in user-space/CoreGraphics handling: an observed `0x7263 / 0x72c7` transaction completes Mach transport and returns a result-zero `0x34` reply, followed immediately on Lion by `_CGSBindWindowBacking: cannot map backing data shmem` and `_CGSLockWindow: Unable to lock window`. Snow uses the same observed IDs and geometry without that failure. Runtime therefore advances to a read-only Snow-PPC/Lion-i386 backing-lock protocol/ABI audit before any live mapping adaptation is considered.

No XNU source change, kernel rebuild, or reboot is indicated by this result.


## WindowBackingInfo collision remains a user-space compatibility boundary

The Snow-PPC/Lion-i386 CoreGraphics backing-lock audit isolates the next ShowWindow failure without changing the accepted kernel path. Snow `__CGSGetWindowBackingInfo` uses `0x7263 / 0x72c7`; Lion's same helper uses `0x7264 / 0x72c8` with the same live-relevant request/reply geometry. Lion routine `0x7263 / 0x72c7` is instead `__CGSGetWindowInfo`.

This explains the observed Lion behavior: the translated PPC `0x7263` request is accepted as the wrong semantic routine and can return a result-zero reply whose outputs are then misinterpreted as backing shared-memory information. Runtime therefore advances to a one-call, ID-only user-space compatibility experiment that converts only `0x7263 -> 0x7264` and `0x72c8 -> 0x72c7`, preserving all request/reply body bytes.

No XNU source change, kernel rebuild, or reboot is indicated by this result.


## WindowBackingInfo compatibility passes; seventh notification remains user-space

The Snow WindowBackingInfo passthrough control completes ShowWindow and the single Lion compatibility run proves the one-call user-space ID correction. The exact legacy request `0x7263` is converted to Lion `0x7264`; Lion returns native `0x72c8 / 0x34 / result 0`; the PPC-facing reply is restored to `0x72c7`. Only the request/reply ID byte changes; the window ID, result, and both backing-info output pairs are preserved. The prior backing-data shared-memory mapping and `_CGSLockWindow` failure cascade disappears.

The accepted syscall-295 preflight remains unchanged: the expected kernel image routes syscall 295 to the compatibility front-end and returns EBADF without SIGSYS. No new kernel evidence appears.

The next boundary is later and wholly user-space: distributed-notification request index 7, bits `0x1111`, message ID 4, message size 356, payload 322, rejected by the exact-six broker with status 25 / unknown name. Runtime advances to a capture/decode-only seventh-request schema audit with the same rejection preserved.

No XNU source change, kernel rebuild, or reboot is indicated.


## Seventh notification schema is a user-space registration boundary

The capture-only seventh distributed-notification audit completes with the accepted kernel and ShowWindow compatibility stack unchanged. The seventh legacy request is an ordinary `register` dictionary for `com.apple.ColorSync.DisplayProfileNotification`, `kCFNotificationAnyObject`, legacy behavior 4, counter 1, a positive per-run entry, and the established session. The audit deliberately preserves the broker's status-25 rejection while capturing the exact binary plist.

The WindowBackingInfo, ColorProfileClient, and ResolveColorProfile adapters remain successful and the prior backing-data shared-memory mapping failure remains absent. The syscall-295 probe still returns EBADF without SIGSYS on the accepted kernel hash.

Runtime therefore advances only to an exact-seven user-space notification-registration experiment. No XNU source change, kernel rebuild, or reboot is indicated.


## Exact-seven notification boundary closes; crash remains user-space

The exact-seven distributed-notification registration run accepts the reviewed `com.apple.ColorSync.DisplayProfileNotification` request, finishes `register=7 callback=0 rejects=0 exact=YES` with broker PASS, and observes no eighth request. The accepted WindowBackingInfo, ColorProfileClient, and ResolveColorProfile compatibility paths remain successful and the former backing-data shared-memory mapping failure stays cleared.

`ShowWindow` still terminates before its after-return marker with exit status 139. The first visible diagnostics after the seventh registration are CoreUI `Invalid ArtFile Path!` messages, and the run preserved a crash report plus `/cores/core.89664`.

Runtime therefore advances to a read-only crash/core postmortem. This remains a user-space/Rosetta-framework boundary: no XNU source change, kernel rebuild, or reboot is indicated.


## Exact-seven crash localizes above XNU in CoreUI

The preserved exact-seven ShowWindow crash has been analyzed in postmortem mode without another PPC execution. The failure is `EXC_BAD_ACCESS (SIGSEGV)` at `0x787221c4`, and the PPC stack localizes it to libc formatting called by CoreUI's `ShowArtFilePathToStdErr`, reached through `CUIElement::LoadFromArtFile`, the CoreUI renderer, and HIToolbox titlebar-button drawing.

The translated Rosetta host instruction faults while loading through the same invalid address. The accepted WindowBackingInfo, ColorProfileClient, ResolveColorProfile, and exact-seven notification paths remain upstream successes; no eighth notification request was observed. RawCamera is absent from the crash stack.

Runtime therefore advances to a read-only Snow/Lion CoreUI/HIToolbox theme-path differential. The boundary remains user-space/framework/Rosetta-side. No XNU source change, kernel rebuild, or reboot is indicated.


## CoreUI crash is a Rosetta cache versus Lion resource contract mismatch

The Snow/Lion CoreUI static differential keeps the boundary above XNU. The Rosetta shared cache and map are byte-for-byte identical on Snow Leopard and Lion, and the preserved Lion crash addresses map exactly to the Snow PPC CoreUI and HIToolbox symbol offsets at fixed image bases. Lion's Rosetta process is therefore executing Snow-era PPC framework code from the unchanged cache while reading Lion-era CoreUI resources from disk.

The on-disk resource generation changed materially between releases: Lion adds `ArtFile200.bin`, changes `ArtFile.bin` and `SArtFile.bin`, and its native CoreUI introduces an `ArtFileInfo*`-aware diagnostic/setup contract absent from Snow PPC CoreUI. Runtime advances to a targeted read-only ArtFile code/resource audit before any compatibility experiment.

No XNU source change, kernel rebuild, or reboot is indicated.


## ArtFile discriminator remains entirely above XNU

The targeted Snow/Lion CoreUI ArtFile audit keeps the current boundary in user space. The old Snow-PPC CoreUI diagnostic helper decodes component IDs through global archive tables, while Lion's native CoreUI uses an `ArtFileInfo*`-aware path with separate ArtFile10/ArtFile20 setup and bounds checks. The exact dotted `west...scrollbars` diagnostics are synthesized from component names rather than stored as literal strings in the audited archives.

Runtime therefore advances to a read-only preserved-core decode of the old PPC CoreUI ArtFile globals and the active `CUIElement::Load` path buffer. No new PPC execution is required, and no XNU source change, kernel rebuild, or reboot is indicated.

## CoreUI shared-art source remains above XNU

The runtime caller-resolution audit now resolves the first divergent non-button CoreUI constructor site `0x0002ad34` to Snow-PPC `CUISharedArtReader::CreateImageFromBytes(long,long)`. That routine obtains its input through `CUISharedArtReader::GetImageHeader(long)` and decodes byte-swapped serialized width, height, provider-length, and provider-data-offset fields before invoking `CGImageCreate`. The observed Snow five-by-11x11 stream versus Lion's 256x256 and 2x62 stream is therefore a user-space CoreUI shared-art source/header divergence, while image construction remains non-NULL.

Runtime advances to a static shared-art source audit that resolves the unique reader caller, `GetImageHeader` implementation, and release-local CoreUI resource identities. No additional syscall/VM evidence, XNU source change, kernel rebuild, or reboot is indicated.

## SArtFile frame-record differential remains above XNU

The runtime shared-art source audit now resolves the divergent non-button image path to Snow-PPC `CUISharedArtReader::CreateImage(float)` / `GetImageHeader(long)`. The legacy reader subtracts `0x4e20` from each shared image ID and follows a release-local offset table; the seven frame-image IDs therefore target SArtFile indices 105, 106, and 109-113. Snow and Lion both expose version-2 `SArtFile.bin` resources but with different entry counts, sizes, and hashes.

Runtime advances only to a read-only static decode of those exact SArtFile records. No additional syscall, VM, or kernel evidence appears, so no XNU source change, kernel rebuild, or reboot is indicated.

## Shared-art selection trace remains above XNU

The runtime SArtFile frame-record audit now proves that the remaining non-button frame-image divergence is explained by release-local CoreUI resource metadata: Snow's exact-seven frame records are all type 2 / count 1, while Lion changes the corresponding records' type/count and geometry; Lion `0x4e8f` slot 1 is exactly the previously observed 256x256 raw image and `0x4e8e` / `0x4e8d` are the 2x62 candidates.

Runtime advances only to a guarded user-space trace that correlates exact frame IDs with the raw and ImageIO selection paths. No new syscall, VM, or kernel evidence appears, so no XNU source change, kernel rebuild, or reboot is indicated.

## Corrected SArtFile audit remains above XNU

The completed runtime live trace did not reveal a kernel boundary. Instead it corrected two user-space diagnostics: Snow-PPC `CUISharedArtReader::Setup()` proves the SArtFile offset table begins at mapped-base `+0x08`, superseding the v1 static analyzer's `0x04` base, and the final ImageIO call site cannot recover the legacy image ID from saved `r30` because `CreateImage(long,float)` has already reused that register.

Both Snow and Lion compatibility runners passed; Lion's live raw calls were `0x4e8e -> 256x256` and `0x4e8d -> 2x62`, with non-NULL results. Runtime now returns to a corrected static SArtFile v2 audit and re-summarization of preserved logs. No XNU source change, rebuild, or reboot is indicated.

