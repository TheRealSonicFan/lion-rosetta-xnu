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
