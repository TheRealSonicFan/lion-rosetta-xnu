# XNU syscall-295 experiment

## Objective

Restore exactly one retired Snow Leopard kernel ABI on Lion 10.7.5 for the next controlled Rosetta experiment:

`shared_region_map_np(int fd, uint32_t count, const struct shared_file_mapping_np *mappings)`

at Unix syscall number 295.

The preserved Rosetta core has already proved that this is the immediate cache-bypass failure boundary. This experiment tests the smallest compatibility restoration capable of routing that old three-argument request into Lion's existing shared-region mapping implementation.

This is an experimental kernel change. It is not a production installation design.

## Repository implementation prepared for this experiment

The repository now contains:

```text
patches/xnu-1699.32.7-rosetta-syscall295.patch
tools/validate_syscall295_source.py
tools/syscall295_probe.c
tools/build_syscall295_probe.sh
tools/run_syscall295_probe.sh
docs/shared-region-map-np-compatibility-design.md
docs/xnu-syscall-295-experiment.md
```

The patch changes only two Apple XNU source files:

```text
bsd/kern/syscalls.master
bsd/vm/vm_unix.c
```

It does not modify the lower shared-region VM implementation.

### What the patch does

1. Restores syscall-table entry 295 with the Snow Leopard three-argument `shared_region_map_np` ABI.
2. Adds a thin compatibility front-end in Lion `bsd/vm/vm_unix.c`.
3. Preserves the historical maximum of eight mapping records.
4. Uses Lion's existing `shared_region_copyin_mappings()` helper.
5. Routes the request through Lion's existing `_shared_region_map()` implementation.
6. Requests no slide operation.
7. Leaves Lion syscall 438 `shared_region_map_and_slide_np` unchanged.
8. Does not gate the compatibility entry on `P_TRANSLATED`, because the controlled direct-`translate` positive control must also be able to use it.

The design rationale and exact source baselines are recorded in `docs/shared-region-map-np-compatibility-design.md`.

## Safety rules

Do not deviate from these constraints during this experiment:

- Keep a known-good alternate boot or Recovery/installer environment available.
- Do not overwrite Lion's native `/usr/lib/dyld`.
- Do not copy Snow Leopard libraries into Lion's `/usr/lib`.
- Do not rebuild the Rosetta shared cache.
- Do not change `DYLD_SHARED_REGION`.
- Do not alter the private Snow Leopard dyld or Rosetta cache.
- Do not add any other XNU compatibility change to this build.
- Do not run Rosetta before the post-boot commpage and syscall-routing probes pass.
- Do not run the normal PPC exec path in this experiment.
- Stop after the guarded direct-translator test and preserve its evidence.
- Keep all proprietary Apple runtime material out of GitHub.

## Prerequisites

This procedure assumes the Lion machine still has the previously working kernel-build environment:

- Mac OS X 10.7.5;
- Xcode 4.2.1 / Lion-era Developer Tools;
- the previously installed DTrace 90 and bootstrap_cmds-78 prerequisites;
- the companion `lion-rosetta-runtime` checkout and its existing validated private payload;
- a known-good `lion-commpage-probe` from the earlier phase-2 validation, or the ability to reproduce it by following the runtime repository's `docs/LION_COMMPAGE_PROBE.md`.

Before changing source, verify the toolchain:

```sh
xcodebuild -version
xcode-select -print-path 2>/dev/null || true
which gcc
which g++
gcc -v
```

The expected Xcode baseline is 4.2.1 with Developer directory `/Developer`.

## Phase A — update the public tooling

On Lion:

```sh
cd /path/to/lion-rosetta-xnu
git pull --ff-only
git rev-parse HEAD

cd /path/to/lion-rosetta-runtime
git pull --ff-only
git rev-parse HEAD
```

Confirm the XNU checkout contains the files listed in “Repository implementation prepared for this experiment.”

## Phase B — prepare the XNU source tree

### Recommended path: start from a clean Apple xnu-1699.32.7 tree

Use a fresh, unmodified Apple `xnu-1699.32.7` tree when practical. The phase-2 patch already includes the architecture-handler, translated-commpage, nanotime-bounds, and PowerPC subject-path work.

Set convenient paths:

```sh
export ROSETTA_XNU=/path/to/lion-rosetta-xnu
cd /path/to/xnu-1699.32.7
```

Dry-run and apply the existing phase-2 patch:

```sh
patch --dry-run -p1 < "$ROSETTA_XNU/patches/xnu-1699.32.7-rosetta-commpage.patch"
patch -p1 < "$ROSETTA_XNU/patches/xnu-1699.32.7-rosetta-commpage.patch"
```

Validate the phase-2 source before adding syscall 295:

```sh
/usr/bin/python "$ROSETTA_XNU/tools/validate_rosetta_source.py" .
```

Require a complete PASS.

### Alternative: reuse the previously validated phase-2 source tree

If the exact source tree used for the already boot-tested phase-2 kernel is being reused, do not reapply the phase-2 patch. Instead run:

```sh
/usr/bin/python "$ROSETTA_XNU/tools/validate_rosetta_source.py" .
```

Proceed only if it passes before the syscall-295 patch is applied.

## Phase C — apply only the syscall-295 compatibility patch

From the XNU source root:

```sh
patch --dry-run -p1 < "$ROSETTA_XNU/patches/xnu-1699.32.7-rosetta-syscall295.patch"
```

The dry run must complete with no failed or offset/reversed hunks.

Then apply it:

```sh
patch -p1 < "$ROSETTA_XNU/patches/xnu-1699.32.7-rosetta-syscall295.patch"
```

Run both validators:

```sh
/usr/bin/python "$ROSETTA_XNU/tools/validate_rosetta_source.py" .
/usr/bin/python "$ROSETTA_XNU/tools/validate_syscall295_source.py" .
```

Both must report PASS.

Do not edit `syscalls.master`, `vm_unix.c`, or any generated syscall file manually after validation.

## Phase D — build the native i386 syscall-routing probe

Build the probe before changing the boot kernel, but do not execute it yet.

From a convenient working directory on Lion:

```sh
/bin/bash "$ROSETTA_XNU/tools/build_syscall295_probe.sh" ./syscall295-probe
```

The output must be an i386 Mach-O executable targeting Lion. The builder uses `-mmacosx-version-min=10.7`.

Preserve its hash:

```sh
/usr/bin/shasum -a 256 ./syscall295-probe | tee ./syscall295-probe.sha256
```

Do not run the probe against the currently booted pre-experiment kernel.

## Phase E — rebuild both Lion kernel architectures

From the patched `xnu-1699.32.7` source root:

```sh
export CC=/usr/bin/gcc
export CXX=/usr/bin/g++

make clean
rm -rf BUILD/obj/RELEASE_I386
rm -rf BUILD/obj/RELEASE_X86_64
```

Build i386 first:

```sh
make ARCH_CONFIGS="I386" KERNEL_CONFIGS="RELEASE"   2>&1 | tee XNU32Compile-syscall295.log
```

Require a successful final link/post-link sequence and an output at:

```text
BUILD/obj/RELEASE_I386/mach_kernel
```

Then build x86_64:

```sh
make ARCH_CONFIGS="X86_64" KERNEL_CONFIGS="RELEASE"   2>&1 | tee XNU64Compile-syscall295.log
```

Require an output at:

```text
BUILD/obj/RELEASE_X86_64/mach_kernel
```

Inspect both products:

```sh
file BUILD/obj/RELEASE_I386/mach_kernel
file BUILD/obj/RELEASE_X86_64/mach_kernel

strings -a BUILD/obj/RELEASE_I386/mach_kernel | grep '/usr/libexec/oah/'
strings -a BUILD/obj/RELEASE_X86_64/mach_kernel | grep '/usr/libexec/oah/'
```

Each slice must still contain the `/usr/libexec/oah/translate` handler.

If the unstripped `mach_kernel.sys` products are present, also confirm the new function was linked:

```sh
/usr/bin/nm BUILD/obj/RELEASE_I386/mach_kernel.sys | grep '_shared_region_map_np$'
/usr/bin/nm BUILD/obj/RELEASE_X86_64/mach_kernel.sys | grep '_shared_region_map_np$'
```

A missing `mach_kernel.sys` file is not by itself a failure if the build cleaned it after producing the final kernel, but if it exists the symbol check must succeed.

Preserve the build logs before continuing.

## Phase F — construct and validate the universal kernel

Create the universal candidate:

```sh
/usr/bin/lipo -create   BUILD/obj/RELEASE_I386/mach_kernel   BUILD/obj/RELEASE_X86_64/mach_kernel   -output ./mach_kernel.rosetta-syscall295
```

Inspect it:

```sh
file ./mach_kernel.rosetta-syscall295
/usr/bin/lipo -info ./mach_kernel.rosetta-syscall295
/usr/bin/shasum -a 256 ./mach_kernel.rosetta-syscall295   | tee ./mach_kernel.rosetta-syscall295.sha256
```

It must contain exactly the intended i386 and x86_64 kernel slices.

Verify the two lipo slices survived byte-for-byte:

```sh
/usr/bin/lipo ./mach_kernel.rosetta-syscall295   -thin i386 -output /tmp/mach_kernel.syscall295.i386
/usr/bin/lipo ./mach_kernel.rosetta-syscall295   -thin x86_64 -output /tmp/mach_kernel.syscall295.x86_64

cmp BUILD/obj/RELEASE_I386/mach_kernel /tmp/mach_kernel.syscall295.i386
echo "i386 cmp status=$?"

cmp BUILD/obj/RELEASE_X86_64/mach_kernel /tmp/mach_kernel.syscall295.x86_64
echo "x86_64 cmp status=$?"
```

Both comparison statuses must be 0.

Run the existing kernel verifier:

```sh
/usr/bin/python "$ROSETTA_XNU/tools/verify_lion_kernel.py"   ./mach_kernel.rosetta-syscall295
```

The verifier confirms the Rosetta handler in both slices. The syscall-295 source validators, not this binary verifier, are the authoritative check for the compatibility source change.

## Phase G — install with the existing rollback discipline

Do not manually copy the candidate to `/mach_kernel`.

Install through the repository tool:

```sh
sudo "$ROSETTA_XNU/tools/install_kernel.sh"   ./mach_kernel.rosetta-syscall295
```

Record the backup directory printed by the installer.

If `kextcache` returns a nonzero status, do not reboot. Preserve the complete installer output; the installer should restore the prior kernel.

If installation completes cleanly, reboot Lion normally.

If Lion fails to boot, use the known-good alternate boot/Recovery environment and the printed backup path with:

```sh
sudo /path/to/lion-rosetta-xnu/tools/rollback_kernel.sh   /var/backups/lion-rosetta/YYYYMMDD-HHMMSS
```

## Phase H — post-boot identity checks

After a successful reboot, do not run Rosetta yet.

Record:

```sh
/usr/bin/uname -a
/usr/sbin/sysctl kern.exec.archhandler.powerpc
/usr/bin/shasum -a 256 /mach_kernel
cat /path/to/xnu-1699.32.7/mach_kernel.rosetta-syscall295.sha256
```

The installed `/mach_kernel` hash must equal the candidate hash recorded before installation.

The architecture handler must still report:

```text
kern.exec.archhandler.powerpc: /usr/libexec/oah/translate
```

If either identity check fails, stop.

## Phase I — repeat the native commpage regression probe

Use the same validated i386 commpage probe from the earlier phase-2 test.

From the runtime checkout:

```sh
cd /path/to/lion-rosetta-runtime
./scripts/run-lion-commpage-probe.sh ./lion-commpage-probe
```

Require:

```text
RESULT: PASS
```

This confirms the syscall change did not regress the already restored translated commpage ABI.

If the probe is no longer available, stop and reproduce it exactly according to `lion-rosetta-runtime/docs/LION_COMMPAGE_PROBE.md` before continuing.

## Phase J — run the syscall-295 routing probe

Only after the commpage probe passes, run the previously built i386 syscall probe:

```sh
/bin/bash "$ROSETTA_XNU/tools/run_syscall295_probe.sh"   ./syscall295-probe   ./syscall295-probe.log
```

The required success output is:

```text
RESULT: PASS - syscall 295 reached the compatibility front-end and returned EBADF
RESULT: PASS
```

The probe intentionally supplies an invalid file descriptor. A successful compatibility front-end therefore returns the ordinary `EBADF` error without mapping a shared cache.

Any `SIGSYS`, `ENOSYS`, unexpected errno, crash, or nonzero runner status is a stop condition. Do not run Rosetta in that case.

Preserve:

```text
syscall295-probe
syscall295-probe.sha256
syscall295-probe.log
```

## Phase K — rerun only the guarded direct Rosetta control

Only if both native probes pass, move to the runtime checkout:

```sh
cd /path/to/lion-rosetta-runtime
git pull --ff-only
```

Confirm the same private experiment inputs from the earlier run are still present. Do not replace or recollect them.

Run only:

```sh
ROSETTA_CACHE_BYPASS_VALIDATION=1   ./scripts/run-lion-private-dyld-experiment.sh
```

This is intentionally the same guarded direct-translator experiment that previously reached syscall 295.

Do not add other `DYLD_*` variables.

## Phase L — stop and preserve evidence

Stop after the guarded direct-translator experiment regardless of whether it passes or fails.

Preserve at minimum:

```text
XNU32Compile-syscall295.log
XNU64Compile-syscall295.log
mach_kernel.rosetta-syscall295.sha256
syscall295-probe.sha256
syscall295-probe.log
payload/lion-private-dyld-cache-bypass-experiment.log
payload/lion-private-dyld-cache-bypass-direct.raw.log
```

Also preserve every new crash report or core file explicitly listed by the runtime runner.

The immediate experimental question is only:

> Did the previously confirmed syscall-295 SIGSYS/ENOSYS boundary disappear?

Do not infer or repair any later failure before reviewing the resulting evidence.

If the direct translator reaches the PPC smoke-test message and exits 0, preserve that result and stop. Do not run normal PPC exec yet.

If the next failure is an uncached library such as `/usr/lib/libgcc_s.1.dylib`, preserve the exact dyld output; do not copy Snow Leopard libraries into Lion's system paths.

## What to return for review

Return the following logs first:

```text
XNU32Compile-syscall295.log
XNU64Compile-syscall295.log
syscall295-probe.log
lion-private-dyld-cache-bypass-experiment.log
lion-private-dyld-cache-bypass-direct.raw.log
```

Also return any newly generated crash report named by the guarded runtime runner.

Do not upload the full Rosetta core unless a later analysis specifically requests another postmortem extraction.

## Success criteria for this experiment

The experiment has three ordered gates:

1. Existing commpage probe: PASS.
2. Native syscall-295 routing probe: PASS with `EBADF` and no `SIGSYS`.
3. Guarded direct Rosetta experiment: no recurrence of the syscall-295 `SIGSYS/ENOSYS` boundary.

Only the evidence from gate 3 determines the next Rosetta compatibility step.
