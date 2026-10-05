# lion-rosetta-xnu

Experimental tooling to restore Rosetta 1's PowerPC-on-Intel execution path on Mac OS X 10.7 Lion.

## Current status

The project has confirmed four kernel-side compatibility requirements:

1. **PowerPC architecture-handler dispatch** — Lion defaults the handler to `/usr/libexec/oah/RosettaNonGrata`; Snow Leopard uses `/usr/libexec/oah/translate`.
2. **Translated 32-bit commpage ABI** — Snow Leopard maps and populates additional PPC-facing commpage data that Lion removes.
3. **PowerPC subject exec-path preservation** — Lion's exec refactor resets the saved exec path to the interpreter; Snow Leopard keeps the PPC subject path available to Rosetta while looking up `translate` separately.
4. **Legacy shared-region syscall 295** — Snow Leopard dyld calls `shared_region_map_np` to populate the PPC shared cache. Lion leaves the old API declarations and mapping machinery in place but routes syscall 295 to `nosys`.

The first three requirements are represented in the current phase-2 source patch. The fourth is confirmed by a non-debugged Rosetta core and now has a separate experiment-only implementation patch. It is intentionally not folded into phase 2 yet. See `docs/shared-region-map-np-compatibility-design.md`, `docs/xnu-syscall-295-experiment.md`, and `docs/phase2-validation.md`.

**Therefore the existing handler-only source/binary patch is phase 1, not a complete Rosetta restoration. Do not treat a successful `sysctl kern.exec.archhandler.powerpc` result as proof that PPC applications can run yet.**

## Architecture-handler difference

Snow Leopard 10.6.8 (`xnu-1504.15.3`) initializes:

```
/usr/libexec/oah/translate
```

Lion 10.7.5 (`xnu-1699.32.7`) initializes:

```
/usr/libexec/oah/RosettaNonGrata
```

The current source and binary patchers restore that handler path.

## Missing translated commpage support

Snow Leopard's 32-bit commpage reserves 19 pages beginning at `0xfffec000` and contains PPC-facing compatibility data used by Rosetta, including byte-swapped data at offset `+0x8000`, branch-assist entries, and generated signature data.

Lion reduces the 32-bit commpage to two pages beginning at `0xffff0000` and removes the translated population code and `commpage_sigs.c`.

The first Lion PPC execution test faulted inside `translate` with:

```
KERN_INVALID_ADDRESS at 0xffff8020
```

Snow Leopard computes that address as:

```
0xffff0000 + 0x20 + 0x8000
```

where `0x20` is the commpage CPU-capabilities slot and `0x8000` is the translated/signature offset.

See `docs/xnu-rosetta-audit.md` and `docs/crash-ffff8020.md` for the source comparison and test evidence.

## Lion universal-kernel handler patching

Stock Lion `/mach_kernel` may be a universal Mach-O containing both i386 and x86_64 slices. In that case two total `RosettaNonGrata` strings are expected: one in each x86 slice.

`tools/patch_lion_kernel.py` parses the fat Mach-O architecture table and requires exactly one unpatched handler in every recognized i386/x86_64 slice. It refuses unexplained handler strings outside those slices and does not blindly replace every occurrence.

`tools/verify_lion_kernel.py` reports each slice independently.

### Important limitation

This binary patch changes **only the architecture-handler path**. It does not restore the translated commpage ABI and is therefore insufficient by itself to execute Rosetta successfully on Lion.

It remains useful for reproducing and diagnosing the kernel dispatch path while the commpage restoration is developed.

## Scope

This repository contains only open-source/kernel-side tooling and documentation. It does **not** contain Rosetta, `translate`, Rosetta Shims, or any other closed-source Apple payload. Use the companion `lion-rosetta-runtime` tooling to collect those files from a Snow Leopard 10.6.8 installation you are entitled to use.

## Supported baseline

The source work targets Apple's `xnu-1699.32.7` Lion 10.7.5 release and compares it against Snow Leopard 10.6.8 `xnu-1504.15.3`.

The existing `patches/xnu-1699.32.7-rosetta.patch` remains the **handler-only phase-1 diagnostic patch**. The standalone phase-2 source patch is `patches/xnu-1699.32.7-rosetta-commpage.patch`; it includes the handler change plus the translated 32-bit commpage restoration. An earlier phase-2 revision compiled for both RELEASE_I386 and RELEASE_X86_64 but exposed an early-boot `nanotime trouble 1` panic caused by Lion's INT3 commpage initialization covering the newly enlarged allocation. The current source patch contains the allocator-bounds fix; it must be rebuilt and boot-tested.

## Phase-2 source patch workflow

Start from an unmodified Apple `xnu-1699.32.7` source tree. Do **not** apply the phase-1 patch first; phase 2 includes it.

```sh
cd /path/to/xnu-1699.32.7
patch --dry-run -p1 < /path/to/lion-rosetta-xnu/patches/xnu-1699.32.7-rosetta-commpage.patch
patch -p1 < /path/to/lion-rosetta-xnu/patches/xnu-1699.32.7-rosetta-commpage.patch
/usr/bin/python /path/to/lion-rosetta-xnu/tools/validate_rosetta_source.py .
```

Proceed to kernel compilation only after the validator passes. See `docs/translated-commpage.md` and `docs/phase2-validation.md`.

The syscall-295 experiment has passed on Lion 10.7.5, and the same kernel has now also passed a normal PowerPC exec control through the architecture handler. This validates the subject-path correction together with the translated commpage and syscall-295 compatibility work. `docs/xnu-syscall-295-experiment.md` and `docs/phase2-validation.md` record the results. No new XNU change is currently indicated; compatibility expansion continues in the companion runtime repository.

A direct Snow Leopard control (`/usr/libexec/oah/translate ppc-smoketest`) succeeds and exits 0, while the same direct invocation on the current Lion phase-2 system segfaults. Therefore the exec-path hotfix is currently **provisional**: do not rebuild solely for that hotfix until the Lion direct-launch crash has been analyzed. Earlier trees may additionally require the X86_64 and nanotime hotfixes. The standalone phase-2 patch contains the current experimental changes.

## Handler-only diagnostic workflow

To inspect a stock Lion kernel:

```sh
file /mach_kernel
/usr/bin/python tools/verify_lion_kernel.py /mach_kernel
```

To stage the handler-only patch:

```sh
/usr/bin/python tools/patch_lion_kernel.py /mach_kernel ./mach_kernel.rosetta
/usr/bin/python tools/verify_lion_kernel.py ./mach_kernel.rosetta
```

After booting that kernel:

```sh
sysctl kern.exec.archhandler.powerpc
```

A value of:

```
kern.exec.archhandler.powerpc: /usr/libexec/oah/translate
```

confirms dispatch restoration only. It does not confirm functional PPC execution until the translated commpage work is complete.

## Safety

Replacing a kernel or kernelcache can make a machine unbootable. Keep a known-good bootable volume or Recovery/installer environment available. The installer creates backups, but rollback still requires a bootable environment if the modified system fails to start.

## Upstream source references

- Apple OSS XNU Snow Leopard tag: `https://github.com/apple-oss-distributions/xnu/tree/xnu-1504.15.3`
- Apple OSS XNU Lion tag: `https://github.com/apple-oss-distributions/xnu/tree/xnu-1699.32.7`

## License

Original scripts and documentation in this repository are under the MIT License. Apple's XNU source remains governed by the Apple Public Source License and upstream notices. No Apple proprietary Rosetta binaries are included.


The current syscall-295 kernel has also passed the runtime project's normal PPC CoreFoundation command-line test. That result produced no new kernel boundary. The next controlled expansion is a Carbon GUI/window-event-loop test in the companion runtime repository; no additional XNU change is currently indicated.


The Carbon GUI preserved-core postmortem now shows that the translated guest explicitly issues syscall 37 `kill(self, SIGABRT, 1)`, and Lion returns success. This is a guest-requested self-SIGABRT, not another missing kernel ABI. No additional XNU change is indicated; localization continues in the companion runtime repository.


The runtime Carbon milestone experiment now reaches `main()` on Lion and aborts specifically inside the first `GetCurrentProcess` call, while the exact Snow Leopard control completes successfully. The next test changes only LaunchServices application-registration context. No additional XNU change is currently indicated.


The current PPC GUI application-bundle test is blocked before exec by Lion LaunchServices error `-10665` (`kLSNoRosettaEnvironmentErr`). The same bundle launches on Snow Leopard. This is a LaunchServices Rosetta-availability gate, not evidence for another kernel ABI change. Investigation continues read-only in the companion runtime repository.


The LaunchServices differential audit now shows that Lion classifies the same registered PPC application as `unsupported-format` and lacks Snow Leopard's explicit Rosetta/OAH LaunchServices logic. Rosetta receipts are also absent on Lion, but are not yet proven causal. This remains a user-space LaunchServices policy/implementation problem; no additional XNU change is indicated.


The first-pass LaunchServices static audit confirms that the current `-10665` PPC application rejection is produced in user-space LaunchServices, with Snow Leopard and Lion using structurally different decision paths. A corrected callsite audit is pending in the companion runtime repository. No additional XNU change is indicated by this result.


The corrected LaunchServices callsite audit now ties Lion's `-10665` PPC application rejection directly to LaunchServices' persisted `unsupported-format` classification. Snow Leopard uses a separate Rosetta requirement checker instead. This remains a user-space registration/policy problem; no additional XNU change is indicated.

The LaunchServices provenance audit now shows that Lion removed Snow Leopard's Intel-to-PPC fallback inside the user-space unsupported-format policy helper. The next controlled test patches only a private i386 LaunchServices copy; no additional XNU change is indicated.

The private LaunchServices compatibility experiment has now cleared Lion's PPC application admission gate without modifying the system framework. The launched PPC app then reproduces the independent `GetCurrentProcess` self-SIGABRT boundary. Investigation has moved back to user-space Process Manager compatibility; no additional XNU change is indicated.


The corrected runtime RegisterApplication/ASN callsite audit, registration-protocol audit, and guarded no-ASN discriminator are now complete. The exact PPC process sees `LSDONOTABORTIFNOASN=0`, yet Lion still self-SIGABRTs before `GetProcessForPID` returns while Snow Leopard returns a nonzero PSN. The later HIServices no-ASN abort is therefore not the observed fatal branch. The companion runtime repository has moved to a read-only LaunchServices process-dispatch/InitializeProcessesServices audit. Investigation remains in user space; no new XNU change is indicated.


The runtime Process Manager process-dispatch audit has now passed on Snow Leopard and Lion. The Snow Leopard PPC and Lion i386 InitializeProcessesServices clients retain the same message ID and 32-bit request/reply sizing, the high-level LaunchServices setup paths are structurally aligned, and both systems advertise the same coreservicesd launchd Mach service. No new kernel boundary or obvious LaunchServices wire mismatch was identified. The companion runtime repository is proceeding with a read-only CarbonCore system-service/Security-session transport audit; no additional XNU change is indicated.
