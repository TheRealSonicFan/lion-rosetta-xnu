# Phase-2 boot panic: `nanotime trouble 1`

## Observed failure

The first boot of the phase-2 kernel reached early commpage initialization and panicked before the OS version was set:

```
panic: "nanotime trouble 1"
commpage_set_nanotime
rtc_nanotime_init_commpage
commpage_populate
vm_commpage_init
```

The kernel was the RELEASE_X86_64 phase-2 build.

## Root cause

Lion `xnu-1699.32.7` added an INT3 fill in `commpage_allocate()` that is not present in Snow Leopard `xnu-1504.15.3`:

```c
for (i = _COMM_PAGE_TEXT_START - _COMM_PAGE_START_ADDRESS; i < size; i++)
    commpage_ptr[i] = 0xCC;
```

With stock Lion's two-page 32-bit allocation, that initializes native text slots from offset `0x80` through the end of the two-page commpage and leaves the time-data structure at offset `0x50` untouched.

Phase 2 enlarged the 32-bit allocation to 19 pages and moved its allocation base from `0xffff0000` to `0xfffec000`. Leaving Lion's loop unchanged therefore filled almost the entire enlarged allocation with `0xCC`, starting at allocation offset `0x80`.

But the native time-data block at runtime `0xffff0050` now lies at allocation offset:

```
0xffff0050 - 0xfffec000 = 0x4050
```

That offset was inside the erroneous INT3 fill. Consequently `nt_generation` was initialized to `0xCCCCCCCC` instead of zero. The first `rtc_nanotime_init_commpage()` call enters `commpage_set_nanotime()`, whose initial generation counter is zero, so Lion correctly triggers:

```c
if (generation != p32->nt_generation)
    panic("nanotime trouble 1");
```

This failure occurs before Rosetta or user-space execution.

## Fix

The allocator is now passed the commpage `base_offset`. Lion's INT3 fill is bounded to the native commpage text interval only:

```c
text_start = _COMM_PAGE_TEXT_START - base_offset;
text_end = (_COMM_PAGE_END + 1) - base_offset;
for (i = text_start; i < text_end; i++)
    commpage_ptr[i] = 0xCC;
```

For the restored 32-bit allocation this means:

- allocation base: `0xfffec000`
- native text start: `0xffff0080` -> allocation offset `0x4080`
- native commpage end + 1: `0xffff2000` -> allocation offset `0x6000`

Thus the native data block at allocation offset `0x4050` remains zero-initialized, exactly as required before nanotime setup, while Lion's native text slots retain their INT3 initialization behavior.

For the 64-bit commpage, `base_offset` remains `0xffff0000`, so the bounds resolve to `0x80-0x2000`, exactly matching stock Lion behavior.

The extended Rosetta compatibility pages remain zero-filled until the explicit Rosetta population code writes translated data, branch assists, and signature data.

## Existing patched trees

Trees patched with the earlier phase-2 revision can apply:

```
patches/xnu-1699.32.7-rosetta-commpage-nanotime-hotfix.patch
```

Both I386 and X86_64 kernels must be rebuilt because the fix changes shared `commpage.c`.
