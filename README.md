# 🌌 StoneSky Kernel Builder

<p align="center">
  <img src="https://img.shields.io/badge/Kernel-StoneSky-blueviolet?style=for-the-badge&logo=linux" alt="Kernel Name">
  <img src="https://img.shields.io/badge/Platform-Android-green?style=for-the-badge&logo=android" alt="Platform">
  <img src="https://img.shields.io/badge/Build-Optimized-orange?style=for-the-badge&logo=github-actions" alt="Build">
</p>

---

### 🚀 Overview
**StoneSky** is a high-performance, automated kernel building environment designed for efficiency and simplicity. This repository contains the core scripts and configurations required to compile the StoneSky kernel with modern toolchains and optimizations.

### ✨ Key Features
- 🛠️ **Modern Toolchains**: Powered by the latest AOSP Clang and GCC cross-compilers.
- ⚡ **Concurrent Setup**: Parallelized environment preparation for lightning-fast build starts.
- 🛡️ **KernelSU Integration**: Native support for KernelSU-Next integration.
- 📦 **Automated Packaging**: Seamless integration with AnyKernel3 for flashable ZIP generation.
- 🖋️ **Zip Signing**: Automatic signing of build artifacts for security and compatibility.
- 📢 **Instant Notifications**: Real-time build status updates via Telegram.

---

### 📥 Getting Started

#### 1. Requirements
- A Linux environment (Ubuntu 22.04+ recommended).
- Basic build dependencies (git, wget, curl, zip, java).

#### 2. Configuration
The builder is designed to be modular. Customize your build by editing `config.sh`:

```bash
# Example config.sh
KERNEL_REPO="https://github.com/user/stone-sky-tree"
KERNEL_BRANCH="main"
DEFCONFIG="vendor/device_defconfig"

# Build options
BUILD_KSU=1
LTO=1 # 0: Default, 1: Thin, 2: Full
```

#### 3. Execution
Simply run the build script:
```bash
bash build.sh
```

---

### 🛠️ Configuration Options

| Variable | Description | Default |
|----------|-------------|---------|
| `KERNEL_REPO` | Source repository for the kernel | (Asus SDM660) |
| `KERNEL_BRANCH` | Git branch to compile | `StoneSky` |
| `DEFCONFIG` | Device-specific configuration file | `vendor/asus/X00TD_defconfig` |
| `USE_LLVM` | Build using LLVM/Clang | `1` |
| `BUILD_KSU` | Enable KernelSU integration | `1` |
| `LTO` | Link Time Optimization level | `0` |

---

### 🤝 Acknowledgments
- **AnyKernel3** by [osm0sis](https://github.com/osm0sis)
- **KernelSU** by [tiann](https://github.com/tiann)
- **GCC Toolchains** by [mvaisakh](https://github.com/mvaisakh)

<p align="center">
  <i>Maintained with ❤️ for the Android Community</i>
</p>
