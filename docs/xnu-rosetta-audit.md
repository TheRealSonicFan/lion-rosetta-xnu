# XNU Rosetta audit: 10.6.8 vs 10.7

Compared Apple OSS tags:

- Snow Leopard 10.6.8: `xnu-1504.15.3`
- Lion 10.7.5: `xnu-1699.32.7`

## Confirmed retained in Lion

| Mechanism | Snow Leopard | Lion | Location |
|---|---|---|---|
| PowerPC image activator | yes | yes | `bsd/kern/kern_exec.c` (`exec_powerpc32_imgact`) |
| `IMGPF_POWERPC` | yes | yes | `bsd/sys/imgact.h` |
| `P_TRANSLATED` | yes | yes | `bsd/sys/proc.h` |
| PPC handler vnode identity (`fsid`/`fileid`) | yes | yes | `bsd/kern/kern_exec.c`, `bsd/kern/kern_sysctl.c` |
| `set_archhandler(... CPU_TYPE_POWERPC)` | yes | yes | `bsd/kern/kern_sysctl.c`, called by `bsd_init.c` |
| `vm_map_exec(... CPU_TYPE_POWERPC)` for translated images | yes | yes | `bsd/kern/kern_exec.c` |
| translated flag inheritance across fork | yes | yes | `bsd/kern/kern_fork.c` |
| `proc_is_classic()` checks translated flag | yes | yes | `bsd/kern/kern_proc.c` |
| Rosetta-sensitive page-zero logic/comment | yes | yes | `bsd/kern/mach_loader.c` |

## Architecture-handler difference

Snow Leopard initializes the PowerPC architecture handler to:

```c
.path = "/usr/libexec/oah/translate",
```

Lion initializes it to:

```c
.path = "/usr/libexec/oah/RosettaNonGrata",
```

Restoring this path is necessary, but the first Lion execution test proved that it is not sufficient.

## Translated commpage support removed in Lion

Snow Leopard's 32-bit commpage reserves and populates a much larger region specifically for translated processes.

In `xnu-1504.15.3/osfmk/i386/cpu_capabilities.h`:

```c
#define _COMM_PAGE32_AREA_LENGTH      ( 19 * 4096 )
#define _COMM_PAGE32_BASE_ADDRESS     ( 0xfffec000 )
#define _COMM_PAGE32_START_ADDRESS    ( 0xffff0000 )
#define _COMM_PAGE32_AREA_USED        ( 19 * 4096 )
#define _COMM_PAGE32_SIGS_OFFSET      0x8000
```

Snow Leopard's `commpage.c` explicitly describes the 32-bit commpage as having additional data for translated processes. It:

- writes byte-swapped PPC-view data at native commpage addresses plus `0x8000`;
- synthesizes PPC CPU-capability data;
- populates translated branch-assist descriptors; and
- populates `sigdata_descriptor` from `commpage_sigs.c`.

The PPC-view CPU-capability address is therefore:

```
0xffff0000 + 0x20 + 0x8000 = 0xffff8020
```

Lion removes the translated population code and removes `commpage_sigs.c` from the source tree/build. Its 32-bit commpage is reduced to:

```c
#define _COMM_PAGE32_AREA_LENGTH      ( 2 * 4096 )
#define _COMM_PAGE32_BASE_ADDRESS     ( 0xffff0000 )
#define _COMM_PAGE32_START_ADDRESS    ( _COMM_PAGE32_BASE_ADDRESS )
#define _COMM_PAGE32_AREA_USED        ( 2 * 4096 )
#define _COMM_PAGE32_SIGS_OFFSET      0x8000
```

The offset definition remains, but the address range at `+0x8000` is no longer mapped or populated.

## First Lion execution evidence

With the handler restored and the validated Snow Leopard 10.6.8 OAH payload installed, a known-good 32-bit PPC smoke test reaches `/usr/libexec/oah/translate` and then faults immediately.

The crash is:

```
EXC_BAD_ACCESS (SIGSEGV)
KERN_INVALID_ADDRESS at 0x00000000ffff8020
```

The VM report shows Lion mapped only:

```
0xffff0000-0xffff2000
```

for the shared commpage, exactly matching Lion's two-page definition. The faulting address is the Snow Leopard translated CPU-capabilities slot identified above.

The x86 thread backtrace is entirely inside `translate`, confirming that the architecture-handler redirection succeeded and that the failure occurs during translator startup before the PPC smoke test reaches `main()`.

## Revised conclusion

The architecture-handler path patch is **phase 1 only**.

A functional Lion Rosetta kernel also needs restoration of Snow Leopard's translated 32-bit commpage ABI while preserving Lion's native commpage ABI. A correct source-level implementation should restore, at minimum:

1. the extended 32-bit commpage mapping needed by Rosetta;
2. the translated/byte-swapped PPC view at `+0x8000`;
3. the PPC branch-assist data and signature data from the Snow Leopard commpage implementation; and
4. the Snow Leopard `commpage_sigs.c` build input or an equivalent generated representation in both the I386 and X86_64 build lists.

The implementation must not simply replace Lion's native commpage with Snow Leopard's version: Lion's native commpage format is newer. The intended approach is to retain Lion's native values and add back the translated-only compatibility region.

A standalone phase-2 source patch implementing this translated-commpage restoration is now provided as `patches/xnu-1699.32.7-rosetta-commpage.patch`. It has passed static/source validation against the exact Apple OSS inputs but still requires compilation and Lion boot testing. The handler-only binary kernel patch remains diagnostic rather than a complete Rosetta restoration.

## PowerPC exec-path regression in Lion

Lion's exec refactor changed PowerPC redirection in `exec_powerpc32_imgact()`. Snow Leopard copies the architecture-handler path to a dedicated interpreter-name buffer but leaves the saved executable path unchanged. Lion copies the handler to `ip_interp_buffer`, then calls `exec_reset_save_path()` and saves the interpreter as the new exec path. Lion's generic interpreter relookup subsequently uses `ip_strings`.

That behavior is suitable for `#!` scripts but removes the PPC subject exec path Rosetta expects. With the commpage restored, this manifests as `translate` starting successfully, printing its command-line usage, and exiting 1 without a crash or PPC execution.

The phase-2 patch now preserves `ip_strings` across the PowerPC redirect and performs the PowerPC interpreter lookup through `ip_interp_buffer`; ordinary shell interpreters retain Lion's original `ip_strings` lookup path.


## Direct translator control

On stock Snow Leopard 10.6.8, invoking `/usr/libexec/oah/translate` directly with the known-good PPC smoke-test path successfully executes the PPC program and exits 0. On the current Lion phase-2 system, the same command segfaults with status 139.

This proves that direct translator invocation is a useful cross-version control and that Lion still has at least one translator-visible incompatibility independent of the normal PowerPC exec-path handoff. The normal Lion PPC launch also still prints translator usage and exits 1; the subject-path hotfix remains plausible for that symptom but should not be treated as the only remaining issue.
