# 🍳 cooking-kernel

[![CircleCI](https://dl.circleci.com/status-badge/img/gh/<USER>/<REPO>/tree/main.svg?style=svg)](https://dl.circleci.com/status-badge/redirect/gh/<USER>/<REPO>/tree/main)

> Minimal, out-of-tree kernel builder powered by CircleCI.  
> Clone. Configure. Push. Get a flashable ZIP.

---

## How it works

```
push → CircleCI spins up → clones your kernel → fetches clang → compiles → packs AnyKernel3 ZIP → done
```

No workflow files inside your kernel tree. Everything lives here.

## Setup

1. **Fork** this repo
2. **Configure** — Set your variables in `config.sh` (see below).
3. **Connect** to [CircleCI](https://circleci.com) and follow the project
4. **Push** — the build triggers automatically

#### Optional: Telegram notifications

Add these in **CircleCI → Project Settings → Environment Variables**:

| Variable | Value |
|----------|-------|
| `TG_BOT_TOKEN` | Token from [@BotFather](https://t.me/BotFather) |
| `TG_CHAT_ID` | Your chat or channel ID |
| `PIXELDRAIN_API_KEY` | (Optional) For fallback mirror upload |

## Configuration

The builder uses a modular configuration system. You can define your variables directly in `config.sh`. If `config.sh` doesn't exist, it will use the defaults in `build.sh`.

Example `config.sh`:

```bash
# Repo & Branch
KERNEL_REPO="https://github.com/user/kernel_tree"
KERNEL_BRANCH="main"
DEFCONFIG="vendor/device_defconfig"

# Toolchain
CLANG_URL="https://example.com/clang.tar.gz"

# Build options
BUILD_KSU=1
KBUILD_BUILD_USER="MyName"
KBUILD_BUILD_HOST="MyHost"

# AnyKernel3
ANYKERNEL_REPO="https://github.com/user/AnyKernel3"
ANYKERNEL_BRANCH="main"
```

## Features

- **Parallel Setup**: Setup tasks (kernel clone, toolchain, etc.) run concurrently to maximize build speed.
- **CCache Support**: Leverages `ccache` to significantly speed up subsequent builds by caching compilation results.
- **Advanced Build Options**:
  - **LLVM/Clang**: Build with LLVM and Integrated Assembler (`LLVM_IAS=1`) by default.
  - **LTO Support**: Easily enable Thin or Full Link Time Optimization for better performance.
  - **KernelSU support**: Seamlessly integrate KernelSU-Next.
- **Patching Support**: Automatically apply any `.patch` files from the `patches/` directory.
- **CI Quality Checks**: Automated ShellCheck validation on every push.
- **Zip Signing**: Automatically signs the flashable ZIP using ZipSigner.
- **Notifications**: Telegram alerts with direct ZIP upload and Pixeldrain mirror fallback.

## Setup

1. **Fork** this repo.
2. **Configure**: Rename `config.sh.sample` to `config.sh` and set your variables.
3. **Connect** to [CircleCI](https://circleci.com).
4. **Push**: The build triggers automatically.

#### Optional: Telegram notifications

Add these in **CircleCI → Project Settings → Environment Variables**:

| Variable | Value |
|----------|-------|
| `TG_BOT_TOKEN` | Token from [@BotFather](https://t.me/BotFather) |
| `TG_CHAT_ID` | Your chat or channel ID |
| `PIXELDRAIN_API_KEY` | (Optional) For fallback mirror upload |

## Configuration

The builder uses a modular configuration system. You can define your variables in `config.sh`.

Available options:

| Variable | Description | Default |
|----------|-------------|---------|
| `KERNEL_REPO` | URL of your kernel repository | (X00TD Lineage) |
| `KERNEL_BRANCH` | Branch to build | `lineage-23.2` |
| `DEFCONFIG` | Device defconfig path | `vendor/asus/X00TD_defconfig` |
| `CLANG_URL` | Direct link to Clang toolchain | (AOSP Clang 19) |
| `USE_CCACHE` | Enable ccache (1: Yes, 0: No) | `1` |
| `USE_LLVM` | Use LLVM for building (1: Yes, 0: No) | `1` |
| `LTO` | Link Time Optimization (0: No, 1: Thin, 2: Full) | `0` |
| `BUILD_KSU` | Enable KernelSU integration (1: Yes, 0: No) | `0` |
