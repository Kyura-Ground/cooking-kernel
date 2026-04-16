#!/bin/bash
# Kernel builder for CircleCI — X00TD
set -eo pipefail

# ──────────────────────────────────────────
# Functions
# ──────────────────────────────────────────
info() { echo -e "\e[1;34m--- $1 ---\e[0m"; }
success() { echo -e "\e[1;32m✅ $1\e[0m"; }
error() { echo -e "\e[1;31m❌ $1\e[0m"; exit 1; }

# ──────────────────────────────────────────
# Configuration (Default)
# ──────────────────────────────────────────
# Load custom config if exists (e.g. for local overrides)
if [ -f "config.sh" ]; then
    info "Using custom config from config.sh"
    source config.sh
fi

# Defaults (fallback)
KERNEL_REPO="${KERNEL_REPO:-https://github.com/Kyura-Ground/android_kernel_asus_sdm660-4.19}"
KERNEL_BRANCH="${KERNEL_BRANCH:-XXKSU}"
CLANG_URL="${CLANG_URL:-https://android.googlesource.com/platform/prebuilts/clang/host/linux-x86/+archive/9b144befdfd93b90e02c663504fb9f4b95f9faf8/clang-r596125.tar.gz}"
DEFCONFIG="${DEFCONFIG:-vendor/asus/X00TD_defconfig}"
ANYKERNEL_REPO="${ANYKERNEL_REPO:-https://github.com/Kyura-Ground/AnyKernel3}"
ANYKERNEL_BRANCH="${ANYKERNEL_BRANCH:-4.19}"
BUILD_KSU="${BUILD_KSU:-1}" # Set to 1 to enable KernelSU, 0 to disable

# ──────────────────────────────────────────
# Environment
# ──────────────────────────────────────────
export ARCH=arm64
export SUBARCH=arm64
export KBUILD_BUILD_USER="${KBUILD_BUILD_USER:-Kyura}"
export KBUILD_BUILD_HOST="${KBUILD_BUILD_HOST:-Labs}"

WORKDIR=$(pwd)
JOBS=$(nproc --all)
BUILD_START=$(date +%s)

# ──────────────────────────────────────────
# Clone kernel source
# ──────────────────────────────────────────
if [ ! -d "kernel-src" ]; then
    info "Cloning Kernel Source"
    git clone --depth=1 -b "${KERNEL_BRANCH}" "${KERNEL_REPO}" kernel-src
else
    info "Kernel source already exists, skipping clone"
fi

# ──────────────────────────────────────────
# Fetch & extract Clang toolchain
# ──────────────────────────────────────────
mkdir -p clang-toolchain

if [ -x "clang-toolchain/bin/clang" ]; then
    info "Using cached Clang toolchain"
else
    info "Downloading Clang Toolchain"
    wget -qO- "${CLANG_URL}" | tar -xzf - -C clang-toolchain
fi

export PATH="${WORKDIR}/clang-toolchain/bin:${PATH}"

# ──────────────────────────────────────────
# Build
# ──────────────────────────────────────────
cd kernel-src

if [ "${BUILD_KSU}" -eq 1 ]; then
    info "Setting up KernelSU"
    curl -LSs "https://raw.githubusercontent.com/backslashxx/KernelSU/master/kernel/setup.sh" | bash -s master
    sed -i 's/.*/-K-Line-KSU/' localversion
else
    info "KernelSU disabled"
    sed -i 's/.*/-K-Line/' localversion
fi

echo "======================================"
echo "🚀 Starting X00TD Kernel Build..."
echo "======================================"

make O=out LLVM=1 LLVM_IAS=1 "${DEFCONFIG}"

make -j"${JOBS}" \
    O=out \
    LLVM=1 \
    LLVM_IAS=1

BUILD_END=$(date +%s)
ELAPSED=$((BUILD_END - BUILD_START))
BUILD_TIME="$((ELAPSED / 60))m $((ELAPSED % 60))s"

# ──────────────────────────────────────────
# Package with AnyKernel3
# ──────────────────────────────────────────
IMAGE="out/arch/arm64/boot/Image.gz-dtb"

if [ ! -f "${IMAGE}" ]; then
    error "Build failed in ${BUILD_TIME}! Image.gz-dtb not found."
fi

success "Build successful in ${BUILD_TIME}! Packaging..."

KERNEL_VER="$(make -s kernelversion)"
LOCALVER="$(cat localversion 2>/dev/null || true)"
COMMIT_MSG="$(git log -1 --pretty=format:"%s")"
ZIP_NAME="${KERNEL_VER}${LOCALVER}-$(date +'%Y%m%d-%H%M').zip"

if [ ! -d "anykernel" ]; then
    git clone --depth=1 -b "${ANYKERNEL_BRANCH}" "${ANYKERNEL_REPO}" anykernel
fi

cp "${IMAGE}" anykernel/
cd anykernel
zip -r9 "../${ZIP_NAME}" . -x '.git/*' 'README.md' '*placeholder'
cd ..

mkdir -p out-zip
mv "${ZIP_NAME}" out-zip/

info "Signing ZIP with ZipSigner"
wget -qO zipsigner-3.0-dexed.jar "https://github.com/Magisk-Modules-Repo/zipsigner/raw/master/bin/zipsigner-3.0-dexed.jar"
java -jar zipsigner-3.0-dexed.jar "out-zip/${ZIP_NAME}" "out-zip/${ZIP_NAME%.zip}-signed.zip"
rm "out-zip/${ZIP_NAME}" zipsigner-3.0-dexed.jar
ZIP_NAME="${ZIP_NAME%.zip}-signed.zip"

success "ZIP: ${ZIP_NAME}"

# ──────────────────────────────────────────
# Notification
# ──────────────────────────────────────────
if [ -n "${TG_BOT_TOKEN}" ] && [ -n "${TG_CHAT_ID}" ]; then
    info "Uploading to Telegram"
    TG_MSG="✅ <b>Build Finished</b>
<b>Kernel:</b> K-Line
<b>Version:</b> ${ZIP_NAME}
<b>Branch:</b> ${KERNEL_BRANCH}
<b>Compiler:</b> $(clang --version | head -n 1 | perl -pe 's/ \(.*//')
<b>Time:</b> ${BUILD_TIME}
<b>Last Commit:</b> ${COMMIT_MSG}"

    if ! curl -sS -m 300 -X POST "https://api.telegram.org/bot${TG_BOT_TOKEN}/sendDocument" \
        -F chat_id="${TG_CHAT_ID}" \
        -F document=@"out-zip/${ZIP_NAME}" \
        -F parse_mode="HTML" \
        -F caption="${TG_MSG}"; then
        
        info "Telegram upload failed! Uploading to Pixeldrain (Mirror) instead..."
        if [ -n "${PIXELDRAIN_API_KEY}" ]; then
            curl -sS -T "out-zip/${ZIP_NAME}" -u :"${PIXELDRAIN_API_KEY}" https://pixeldrain.com/api/file/
            echo ""
        else
            info "Pixeldrain API key not set, skipping fallback mirror upload."
        fi
    fi
else
    info "Telegram vars not set, skipping upload."
fi

success "Done!"
