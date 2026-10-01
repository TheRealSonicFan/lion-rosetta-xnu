# Notice

This repository contains original tooling plus patches against Apple's open-source XNU source tree.

- `patches/xnu-1699.32.7-rosetta.patch` changes the Lion PowerPC architecture-handler path.
- `patches/xnu-1699.32.7-rosetta-commpage.patch` additionally restores Rosetta-specific commpage support and includes the generated `osfmk/i386/commpage/commpage_sigs.c` data from Apple XNU `xnu-1504.15.3`.

Apple's XNU source is distributed under the Apple Public Source License (APSL) and the other notices contained in the upstream source tree. The imported `commpage_sigs.c` content remains Apple XNU source material under those upstream terms.

This repository does not redistribute Apple's proprietary Rosetta translator, Shims, dyld Rosetta cache, or any other closed-source Rosetta runtime payload.
