# X00TD Linux 5.4 CI bringup

The `sdm660-5.4` branch builds `Kyura-Ground/android_kernel_asus_sdm660-5.4`
through `.circleci/config.yml` and `scripts/build-5.4.sh`. The 4.4 builder
remains on `lineage-23.2`; its `build.sh` is not invoked by this workflow.

Trigger this branch with `kernel-revision` set to the full kernel commit SHA.
The job records that SHA, uses Ubuntu 22.04 Clang/LLVM 14, and builds the
unmodified `vendor/asus/X00TD_defconfig` with LTO, Image.gz-dtb and modules.
Artifacts include the image, X00TD DTB, compressed vmlinux, configuration,
System.map, Module.symvers, module archive and SHA256 checksums. Logs and the
resolved configuration are retained on failures.

`configs/verity.x509.pem` is the public AOSP development certificate from:
https://android.googlesource.com/platform/build/+/android-10.0.0_r1/target/product/security/verity.x509.pem

SHA256: `ea9e433bb502a3ddef2c85460b499ab1bf8b2ff3f776b468199e5aa358932d9c`.
Only the public certificate is included. CI supplies it in the output directory
for the kernel's existing SYSTEM_TRUSTED_KEYS setting; signature checks remain
enabled. Production Android builds must supply their intended trust anchor.

After a successful build, `scripts/package-5.4.sh` creates the installable
`artifacts-54/X00TD-5.4-<kernel-commit>-recovery.zip` using the same AnyKernel3
repository and signing approach as `lineage-23.2`. Sideload this ZIP in recovery
to update the kernel in both recovery and boot. It preserves each image's
ramdisk and boot header, checks that both installed images already use Linux
5.4, and verifies each write by reading it back. No ROM reinstall or data wipe
is part of this installer. It is not a migration package for a 4.4 ROM/recovery.

The AnyKernel3 revision and ZipSigner are pinned and the signer download is
verified by SHA256 in `scripts/prepare-installer-5.4.sh`. Signing uses the
development test key bundled with ZipSigner, as on `lineage-23.2`; a recovery
trusting a different custom OTA key will ask whether to install anyway. This
does not change recovery's trusted keys or disable signature verification.
Private ROM signing keys are not uploaded to CI.

The original build archive `artifacts-54/X00TD-5.4-<kernel-commit>.zip` is also
retained with the kernel image, X00TD DTB,
configuration, symbols, modules, source revision and toolchain information.
The ZIP checksum is appended to `artifacts-54/SHA256SUMS`. `vmlinux.gz` stays
in the CircleCI artifacts outside the ZIP to keep the Telegram upload small.

Set the existing CircleCI project environment variables `TG_BOT_TOKEN` and
`TG_CHAT_ID`, as on `lineage-23.2`, to upload the **recovery installer ZIP** using Telegram
`sendDocument`. The caption includes the full kernel commit and ZIP SHA256.
Missing credentials skip the upload; an upload error leaves the build artifacts
available in CircleCI. Tokens and API responses are not printed to build logs.

The raw build archive is for inspection and is not flashable. The workflow
checks compilation, package structure, failure handling and installer control
flow. It does not establish successful ROM boot, touch input or other hardware
behavior. Tests do not compile a kernel or send real Telegram messages:

```sh
python3 tests/package-5.4.py
python3 tests/installer-5.4.py
```
