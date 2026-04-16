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
2. **Configure** — Set your variables in `build.sh` or create a `config.sh` file to override them.
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

The builder loads configuration from `build.sh`. You can also create a `config.sh` for local overrides.

Example `config.sh`:

```bash
KERNEL_REPO="https://github.com/user/kernel_tree"
KERNEL_BRANCH="main"
DEFCONFIG="vendor/device_defconfig"
BUILD_KSU=1
```

## Features

- **Modular Config**: Keep your settings separate from the build logic.
- **Clang Caching**: CircleCI caches the toolchain to speed up subsequent builds.
- **KernelSU Support**: Easily toggle KernelSU integration.
- **Zip Signing**: Automatically signs the flashable ZIP using ZipSigner.
- **Notifications**: Telegram alerts with direct ZIP upload and Pixeldrain mirror fallback.

## Requirements

- A kernel source repo on GitHub
- An [AnyKernel3](https://github.com/osm0sis/AnyKernel3) fork configured for your device
- A direct-download URL to a Clang/LLVM toolchain

---

<p align="center"><sub>built with ☕ and sleep deprivation</sub></p>

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
