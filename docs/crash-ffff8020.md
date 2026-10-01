# Lion Rosetta first execution: fault at 0xffff8020

## Observed result

A PPC smoke-test executable that runs successfully under Rosetta on Snow Leopard 10.6.8 was executed on Lion 10.7.5 after:

- installing the validated Snow Leopard OAH runtime,
- restoring `kern.exec.archhandler.powerpc` to `/usr/libexec/oah/translate`, and
- rebooting the patched Lion kernel.

Lion launches the translator but the process terminates with SIGSEGV before the PPC test prints its message.

The crash report identifies:

```
Path: /usr/libexec/oah/translate
Exception Type: EXC_BAD_ACCESS (SIGSEGV)
Exception Codes: KERN_INVALID_ADDRESS at 0x00000000ffff8020
```

The crashed thread has a 32-bit x86 thread state and every visible frame is inside `translate`.

## Why 0xffff8020 matters

Snow Leopard defines:

```
_COMM_PAGE32_START_ADDRESS = 0xffff0000
_COMM_PAGE_CPU_CAPABILITIES = start + 0x20
_COMM_PAGE32_SIGS_OFFSET = 0x8000
```

Its translated commpage population writes a byte-swapped PPC-facing CPU-capabilities value at:

```
0xffff0000 + 0x20 + 0x8000 = 0xffff8020
```

That exactly matches the Lion fault address.

Snow Leopard reserves 19 pages for the 32-bit commpage beginning at `0xfffec000`. Lion reserves only two pages beginning at `0xffff0000`. The Lion crash report likewise shows only an 8 KB shared-memory mapping from `0xffff0000` to `0xffff2000`.

Therefore `translate` is dereferencing a Rosetta commpage ABI location that Lion no longer maps.

## Source-level removal

Snow Leopard `osfmk/i386/commpage/commpage.c` contains translated-process support including byte-swapped commpage data, PPC capability synthesis, `ba_descriptors`, and `sigdata_descriptor`.

Snow Leopard also contains:

```
osfmk/i386/commpage/commpage_sigs.c
```

and includes it in `osfmk/conf/files.i386`.

Lion removes this translated population logic and removes `commpage_sigs.c` from the source tree/build, while retaining the otherwise-unused `_COMM_PAGE32_SIGS_OFFSET 0x8000` definition.

## Implication

The first execution test demonstrates that restoring only `exec_archhandler_ppc.path` reaches Rosetta but is not sufficient to run it.

The next kernel revision must restore the translated 32-bit commpage ABI in addition to the architecture-handler path.
