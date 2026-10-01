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

The attempted live GDB comparison did not reach Rosetta execution on either Lion or Snow Leopard. Under GDB, `translate` exited with code `055` on both systems before a breakpoint, crash, register state, or backtrace could be captured. The subsequent `ps` command matched the GDB command line (which contains the translate pathname), so both `vmmap` captures were maps of `gdb-i386-apple-darwin`, not of `translate`.

The supplied Snow Leopard `translate` Mach-O also marks its `__TEXT` segment with `SG_PROTECTED_VERSION_1`. XNU maps such a segment through the Apple protected pager. Therefore static bytes in the protected part of the file are not a reliable representation of the runtime instructions, and debugger-mediated execution is not a valid comparison path for this binary.

Future diagnosis of the Lion direct-launch crash should use non-ptrace evidence first: the native crash report, a postmortem core dump if the kernel permits one, and syscall/VM tracing (for example DTrace/dtruss) compared against the successful Snow Leopard direct launch.
