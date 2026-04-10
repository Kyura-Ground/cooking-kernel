# 🍳 cooking-kernel

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
2. **Edit `build.sh`** — set your kernel repo, branch, defconfig, and toolchain URL
3. **Connect** to [CircleCI](https://circleci.com) and follow the project
4. **Push** — the build triggers automatically

#### Optional: Telegram notifications

Add these in **CircleCI → Project Settings → Environment Variables**:

| Variable | Value |
|----------|-------|
| `TG_BOT_TOKEN` | Token from [@BotFather](https://t.me/BotFather) |
| `TG_CHAT_ID` | Your chat or channel ID |

## Configuration

Everything is at the top of [`build.sh`](build.sh):

```bash
KERNEL_REPO="https://github.com/user/kernel_tree"
KERNEL_BRANCH="main"
CLANG_URL="https://direct-link-to/clang.tar.zst"
DEFCONFIG="vendor/device_defconfig"
ANYKERNEL_REPO="https://github.com/user/AnyKernel3"
ANYKERNEL_BRANCH="master"
```

## Requirements

- A kernel source repo on GitHub
- An [AnyKernel3](https://github.com/osm0sis/AnyKernel3) fork configured for your device
- A direct-download URL to a Clang/LLVM toolchain (`.tar.zst`)

---

<p align="center"><sub>built with ☕ and sleep deprivation</sub></p>
