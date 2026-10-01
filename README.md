# lion-rosetta-xnu

Experimental tooling to restore the PowerPC architecture handler used by Rosetta 1 on Intel Macs running Mac OS X 10.7 Lion.

## What Lion changed

Apple's public XNU sources show that Snow Leopard 10.6.8 (`xnu-1504.15.3`) initializes the PowerPC architecture handler to:

```
/usr/libexec/oah/translate
```

Lion (`xnu-1699.32.7`) retains the PowerPC image activator and translated-process plumbing but changes the default handler path to:

```
/usr/libexec/oah/RosettaNonGrata
```

This repository provides two equivalent ways to restore that path:

1. **Source patch** — apply `patches/xnu-1699.32.7-rosetta.patch` to Apple's XNU source before building.
2. **Binary patch** — use `tools/patch_lion_kernel.py` to replace the NUL-terminated handler string in each x86 kernel slice, padding the shorter `translate` path so the binary layout and slice sizes are unchanged.

## Lion universal-kernel handling

Stock Lion `/mach_kernel` may be a universal Mach-O containing both i386 and x86_64 slices. In that case two total `RosettaNonGrata` strings are expected: one in each x86 slice.

The patcher parses the fat Mach-O architecture table and requires **exactly one unpatched handler in every recognized i386/x86_64 slice**. It also refuses unexplained handler strings outside those slices. It never patches by blindly replacing every occurrence in the file.

The verifier reports each slice independently and considers a kernel safe only when all recognized x86 slices have the same expected state.

## Scope

This repository changes only the open-source/kernel side. It does **not** contain Rosetta, `translate`, Rosetta Shims, or any other closed-source Apple payload. Use the companion `lion-rosetta-runtime` tooling to collect those files from a Snow Leopard 10.6.8 installation you are entitled to use.

## Supported baseline

The source patch is written against Apple's `xnu-1699.32.7` tag. The binary patcher is structure- and signature-aware and is intended for Lion 10.7.x kernels. It aborts if the Mach-O structure or per-slice Rosetta signatures do not match the expected state.

## Quick start (binary patch path)

On Lion, first inspect the stock kernel:

```sh
file /mach_kernel
/usr/bin/python tools/verify_lion_kernel.py /mach_kernel
```

For a stock universal Lion kernel, the verifier should report i386 and x86_64 slices as `unpatched`.

Then stage a patched kernel without installing it:

```sh
/usr/bin/python tools/patch_lion_kernel.py /mach_kernel ./mach_kernel.rosetta
/usr/bin/python tools/verify_lion_kernel.py ./mach_kernel.rosetta
```

The verifier should report every recognized x86 slice as `patched`.

After you have installed the Snow Leopard Rosetta runtime with the companion repository, install the patched kernel:

```sh
sudo tools/install_kernel.sh ./mach_kernel.rosetta
```

The installer creates a timestamped backup directory under `/var/backups/lion-rosetta/`, backs up `/mach_kernel` and the current kernelcache when present, installs the patched kernel, and invokes Lion's `kextcache -system-prelinked-kernel`.

**Boot-critical warning:** replacing a kernel can make a machine unbootable. Have a known-good bootable volume or Recovery/installer environment available before installation. The rollback script is provided, but it cannot help if you have no way to boot the machine.

## Source patch path

Fetch Apple's XNU source at `xnu-1699.32.7`, then:

```sh
cd xnu-1699.32.7
patch -p1 < /path/to/lion-rosetta-xnu/patches/xnu-1699.32.7-rosetta.patch
```

Building historical XNU requires an era-appropriate Apple toolchain and dependencies; this repository deliberately does not pretend that a modern Xcode build is equivalent.

## Verification after boot

After runtime installation and booting the patched kernel:

```sh
sysctl kern.exec.archhandler.powerpc
```

The expected value is:

```
kern.exec.archhandler.powerpc: /usr/libexec/oah/translate
```

Then run the diagnostics from `lion-rosetta-runtime` before attempting a valuable PowerPC application.

## Upstream source references

- Apple OSS XNU Snow Leopard tag: `https://github.com/apple-oss-distributions/xnu/tree/xnu-1504.15.3`
- Apple OSS XNU Lion tag: `https://github.com/apple-oss-distributions/xnu/tree/xnu-1699.32.7`

See `docs/xnu-rosetta-audit.md` for the exact retained mechanisms checked in Lion.

## License

Original scripts and documentation in this repository are under the MIT License. Apple's XNU source remains governed by the Apple Public Source License and the notices in the upstream source. No Apple proprietary binaries are included.
