# X00TD Kernel Builder

[![CircleCI](https://circleci.com/gh/Kyura-Ground/cooking-kernel.svg?style=shield)](https://app.circleci.com/pipelines/github/Kyura-Ground/cooking-kernel)

An automated CI/CD pipeline built with CircleCI to compile the Android Linux Kernel for ASUS Max Pro M1 (X00TD - Snapdragon 660).

## Infrastructure Overview
- **Target Source**: [android_kernel_asus_sdm660-4.19](https://github.com/Kyura-Ground/android_kernel_asus_sdm660-4.19)
- **Branch**: `lineage-23.2`
- **Compiler**: [LLVM-stable 22.1.2](https://github.com/PurrrsLitterbox/LLVM-stable/releases) by PurrrsLitterbox
- **Packager**: [AnyKernel3](https://github.com/Kyura-Ground/AnyKernel3)

## Build Lifecycle
1. Pushing commits to this repository automatically triggers a build via **CircleCI**.
2. The script downloads the kernel source, pulls the LLVM toolchain, and compiles the kernel using Clang.
3. The compiled `Image.gz-dtb` is packaged into a TWRP-flashable zip using AnyKernel3.
4. The final ZIP is cached as a CircleCI **Artifact** and sent to Telegram *(if variables are set)*.

## How to use
1. **Fork** this repository to your GitHub account.
2. Go to **CircleCI** and connect the repository (using the *Fastest* option via `.circleci/config.yml`).
3. *(Optional)* To enable Telegram Notification Mirror, go to your **Project Settings > Environment Variables** and add:
   - `TG_BOT_TOKEN`
   - `TG_CHAT_ID`
4. Committing any changes to this repository will start the build automatically.
