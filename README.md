# Universal Android Kernel Builder (CircleCI)

An automated, plug-and-play CI/CD pipeline built with CircleCI to fetch, compile, and package Android/Linux kernels entirely from scratch.

## Features
- **Standalone CI**: Build your kernel out-of-tree without needing to add workflow files directly to your kernel source repository.
- **Modern Toolchains**: Supports fetching and extracting custom LLVM/Clang toolchains from direct URLs (compatible with `.tar.gz` and `.tar.zst` compressions).
- **Automated Packaging**: Wraps the compiled `Image.gz-dtb` (or other targets) directly into a recovery-flashable ZIP file using [AnyKernel3](https://github.com/osm0sis/AnyKernel3).
- **Telegram Delivery**: Automatically sends the build status, compilation time, and the final ZIP file directly to your designated Telegram chat or channel.

## Configuration
All necessary environments can be adjusted at the top section of `build.sh`. Edit these variables to match your specific hardware target and toolchain:

```bash
# Target Kernel
KERNEL_REPO="https://github.com/YourName/your_kernel_tree"
KERNEL_BRANCH="branch-name"

# Target Defconfig & Arch
export ARCH=arm64
export SUBARCH=arm64
DEFCONFIG="vendor/your_device_defconfig"

# Compiler Toolchain
CLANG_URL="[direct_url_to_clang.tar.zst]"

# AnyKernel3 Packager
ANYKERNEL_REPO="https://github.com/YourName/AnyKernel3"
ANYKERNEL_BRANCH="master"
```
*(Also ensure to adjust your `make` arguments inside `build.sh` if you are cross-compiling with GCC/Proton-Clang instead of pure LLVM).*

## How to Deploy
1. **Fork** this repository to your GitHub account.
2. Go to **CircleCI Dashboard** and connect the repository. Follow the prompts to use the existing `.circleci/config.yml`.
3. *(Optional but Highly Recommended)* To enable the Telegram Bot uploader, go to your CircleCI **Project Settings > Environment Variables** and add:
   - `TG_BOT_TOKEN` : Your Telegram Bot Token from @BotFather.
   - `TG_CHAT_ID`  : The Chat/Channel ID.
4. Any new commits to this repository's main branch will automatically trigger the compilation runner.
