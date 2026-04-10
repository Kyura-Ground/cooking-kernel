#!/bin/bash
# Kernel builder for CircleCI — X00TD
set -eo pipefail

# ──────────────────────────────────────────
# Configuration (edit these for your device)
# ──────────────────────────────────────────
KERNEL_REPO="https://github.com/Kyura-Ground/android_kernel_asus_sdm660-4.19"
KERNEL_BRANCH="lineage-23.2"
CLANG_URL="https://github.com/PurrrsLitterbox/LLVM-stable/releases/download/llvmorg-22.1.2/clang.tar.zst"
DEFCONFIG="vendor/asus/X00TD_defconfig"
ANYKERNEL_REPO="https://github.com/Kyura-Ground/AnyKernel3"
ANYKERNEL_BRANCH="4.19"

# ──────────────────────────────────────────
# Environment
# ──────────────────────────────────────────
export ARCH=arm64
export SUBARCH=arm64
export KBUILD_BUILD_USER="circleci"
export KBUILD_BUILD_HOST="circleci"

WORKDIR=$(pwd)
JOBS=$(nproc --all)
BUILD_START=$(date +%s)

# ──────────────────────────────────────────
# Clone kernel source
# ──────────────────────────────────────────
echo "--- Cloning Kernel Source ---"
git clone --depth=1 -b "${KERNEL_BRANCH}" "${KERNEL_REPO}" kernel-src

# ──────────────────────────────────────────
# Fetch & extract Clang toolchain
# ──────────────────────────────────────────
echo "--- Downloading Clang Toolchain ---"
mkdir -p clang-toolchain
wget -qO- "${CLANG_URL}" | zstd -d | tar -xf - -C clang-toolchain
export PATH="${WORKDIR}/clang-toolchain/bin:${PATH}"

# ──────────────────────────────────────────
# Build
# ──────────────────────────────────────────
cd kernel-src

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
    echo "❌ Build failed in ${BUILD_TIME}! Image.gz-dtb not found."
    exit 1
fi

echo "✅ Build successful in ${BUILD_TIME}! Packaging..."

KERNEL_VER="$(make -s kernelversion)"
LOCALVER="$(cat localversion 2>/dev/null || true)"
ZIP_NAME="${KERNEL_VER}${LOCALVER}-$(date +'%Y%m%d-%H%M').zip"

git clone --depth=1 -b "${ANYKERNEL_BRANCH}" "${ANYKERNEL_REPO}" anykernel
cp "${IMAGE}" anykernel/

cd anykernel
zip -r9 "../${ZIP_NAME}" . -x '.git/*' 'README.md' '*placeholder'
cd ..

mkdir -p out-zip
mv "${ZIP_NAME}" out-zip/

echo "--- Signing ZIP with ZipSigner ---"
wget -qO zipsigner-3.0-dexed.jar "https://github.com/Magisk-Modules-Repo/zipsigner/raw/master/bin/zipsigner-3.0-dexed.jar"
java -jar zipsigner-3.0-dexed.jar "out-zip/${ZIP_NAME}" "out-zip/${ZIP_NAME%.zip}-signed.zip"
rm "out-zip/${ZIP_NAME}" zipsigner-3.0-dexed.jar
ZIP_NAME="${ZIP_NAME%.zip}-signed.zip"

echo "✅ ZIP: ${ZIP_NAME}"

# ──────────────────────────────────────────
# Telegram notification (optional)
# ──────────────────────────────────────────
if [ -n "${TG_BOT_TOKEN}" ] && [ -n "${TG_CHAT_ID}" ]; then
    echo "--- Uploading to Telegram ---"
    TG_MSG="✅ <b>Build Finished</b>
<b>Kernel:</b> Kyura-Kernel-X00TD
<b>Version:</b> ${ZIP_NAME}
<b>Branch:</b> ${KERNEL_BRANCH}
<b>Compiler:</b> LLVM 22.1.2
<b>Time:</b> ${BUILD_TIME}"

    curl -sf -X POST "https://api.telegram.org/bot${TG_BOT_TOKEN}/sendDocument" \
        -F chat_id="${TG_CHAT_ID}" \
        -F document=@"out-zip/${ZIP_NAME}" \
        -F parse_mode="HTML" \
        -F caption="${TG_MSG}"
else
    echo "ℹ️  Telegram vars not set, skipping upload."
fi

echo "✅ Done!"
