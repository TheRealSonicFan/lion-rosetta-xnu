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
4. the Snow Leopard `commpage_sigs.c` build input or an equivalent generated representation.

The implementation must not simply replace Lion's native commpage with Snow Leopard's version: Lion's native commpage format is newer. The intended approach is to retain Lion's native values and add back the translated-only compatibility region.

Until that work is implemented and validated, the handler-only binary kernel patch should be treated as diagnostic rather than a complete Rosetta restoration.
