# Lion kernelcache note

Mac OS X 10.7 normally boots a unified prelinked kernel/kernelcache. Installing a modified `/mach_kernel` without rebuilding the system prelinked kernel may therefore have no effect on the next normal boot.

`tools/install_kernel.sh` backs up both `/mach_kernel` and the current Lion kernelcache (when present), installs the patched kernel, and calls:

```sh
/usr/sbin/kextcache -system-prelinked-kernel
```

If `kextcache` fails, the script restores `/mach_kernel` and aborts rather than encouraging a reboot with an inconsistent boot cache.
