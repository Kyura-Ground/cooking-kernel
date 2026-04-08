#!/bin/bash
# Script to build kernel in CircleCI

set -e

BUILD_START=$(date +"%s")

# Variables
KERNEL_REPO="https://github.com/Kyura-Ground/android_kernel_asus_sdm660-4.19"
KERNEL_BRANCH="lineage-23.2"
CLANG_URL="https://github.com/PurrrsLitterbox/LLVM-stable/releases/download/llvmorg-22.1.2/clang.tar.zst"

WORKDIR=$(pwd)

echo "--- Cloning Kernel ---"
git clone --depth=1 -b ${KERNEL_BRANCH} ${KERNEL_REPO} kernel-src

echo "--- Downloading and Extracting Clang Toolchain ---"
mkdir -p clang-toolchain
wget -qO clang.tar.zst "${CLANG_URL}"
tar -I zstd -xf clang.tar.zst -C clang-toolchain
rm clang.tar.zst

export PATH="${WORKDIR}/clang-toolchain/bin:${PATH}"

cd kernel-src

echo "--- Setup Environment ---"
export ARCH=arm64
export SUBARCH=arm64
export KBUILD_BUILD_USER="circleci"
export KBUILD_BUILD_HOST="circleci"

DEFCONFIG="vendor/asus/X00TD_defconfig"

echo "--- Clean Build Directory ---"
rm -rf out/

# Build ZIP filename with version + timestamp
KERNEL_VER="$(sed -n 's/^VERSION[[:space:]]*=[[:space:]]*//p' Makefile).$(sed -n 's/^PATCHLEVEL[[:space:]]*=[[:space:]]*//p' Makefile).$(sed -n 's/^SUBLEVEL[[:space:]]*=[[:space:]]*//p' Makefile)"
LOCALVER="$(cat localversion 2>/dev/null)"
ZIP_NAME="${KERNEL_VER}${LOCALVER}-$(date +'%Y%m%d-%H%M').zip"

echo "======================================"
echo "🚀 Starting X00TD Kernel Build..."
echo "======================================"

echo "--- Make Defconfig ---"
make O=out CC=clang LLVM=1 LLVM_IAS=1 $DEFCONFIG

echo "--- Compiling Kernel ---"
make -j$(nproc --all) \
    O=out \
    CC=clang \
    LD=ld.lld \
    AR=llvm-ar \
    NM=llvm-nm \
    OBJCOPY=llvm-objcopy \
    OBJDUMP=llvm-objdump \
    READELF=llvm-readelf \
    STRIP=llvm-strip \
    LLVM=1 \
    LLVM_IAS=1

BUILD_END=$(date +"%s")
BUILD_TIME="$(($(($BUILD_END - $BUILD_START)) / 60))m $(($((BUILD_END - BUILD_START)) % 60))s"

if [ -f "out/arch/arm64/boot/Image.gz-dtb" ]; then
    echo "✅ Build successful in $BUILD_TIME! Packing ZIP..."
    
    echo "--- Setting up AnyKernel3 ---"
    ANYKERNEL_REPO="https://github.com/Kyura-Ground/AnyKernel3"
    ANYKERNEL_BRANCH="4.19"
    
    git clone --depth=1 -b ${ANYKERNEL_BRANCH} ${ANYKERNEL_REPO} anykernel
    cp out/arch/arm64/boot/Image.gz-dtb anykernel/
    
    cd anykernel
    rm -f *.zip
    zip -r9 "../$ZIP_NAME" * -x .git README.md *placeholder
    cd ..
    
    # Store it in a predictable folder for CircleCI Artifacts
    mkdir -p out-zip
    mv "$ZIP_NAME" out-zip/
    
    echo "✅ ZIP created: $ZIP_NAME"
    echo "======================================"
else
    echo "❌ Build failed in $BUILD_TIME! Image.gz-dtb not found!"
    exit 1
fi

if [ -n "$TG_BOT_TOKEN" ] && [ -n "$TG_CHAT_ID" ]; then
    echo "--- Uploading to Telegram ---"
    
    # Custom Message
    TG_MESSAGE="✅ <b>Build Finished Successfully</b>
<b>Kernel:</b> Kyura-Kernel-X00TD
<b>Version:</b> ${ZIP_NAME}
<b>Branch:</b> ${KERNEL_BRANCH}
<b>Compiler:</b> LLVM 22.1.2 (PurrrsLitterbox)
<b>Time:</b> ${BUILD_TIME}"

    curl -s -X POST "https://api.telegram.org/bot${TG_BOT_TOKEN}/sendDocument" \
        -F chat_id="${TG_CHAT_ID}" \
        -F document=@"out-zip/${ZIP_NAME}" \
        -F parse_mode="HTML" \
        -F caption="${TG_MESSAGE}"
else
    echo "Telegram secret variables not set, skipping upload."
fi

echo "🧹 Cleanup..."
rm -rf out/
echo "✅ Done!"
