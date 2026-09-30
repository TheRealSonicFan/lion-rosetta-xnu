# XNU Rosetta audit: 10.6.8 vs 10.7

Compared Apple OSS tags:

- Snow Leopard 10.6.8: `xnu-1504.15.3`
- Lion: `xnu-1699.32.7`

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

## Material initialization difference

Snow Leopard:

```c
struct exec_archhandler exec_archhandler_ppc = {
    .path = "/usr/libexec/oah/translate",
};
```

Lion:

```c
struct exec_archhandler exec_archhandler_ppc = {
    .path = "/usr/libexec/oah/RosettaNonGrata",
};
```

Snow Leopard also contains fallback code that switches to `RosettaNonGrata` only when `translate` is missing. Lion removes that fallback because `RosettaNonGrata` is already the default.

## Consequence

For the audited XNU release, no Snow Leopard kernel code transplant is required to reach the translator. The smallest open-source change is to restore the architecture-handler path. Whether a particular PowerPC program actually runs then depends on the proprietary OAH runtime and user-space/library compatibility.
