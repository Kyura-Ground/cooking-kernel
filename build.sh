#!/bin/bash
# Script to build kernel in CircleCI

set -ex

# Variables
KERNEL_REPO="https://github.com/Kyura-Ground/android_kernel_asus_sdm660-4.19"
KERNEL_BRANCH="lineage-23.2"
CLANG_URL="https://android.googlesource.com/platform/prebuilts/clang/host/linux-x86/+archive/9b144befdfd93b90e02c663504fb9f4b95f9faf8/clang-r596125.tar.gz"

WORKDIR=$(pwd)

echo "--- Cloning Kernel ---"
git clone --depth=1 -b ${KERNEL_BRANCH} ${KERNEL_REPO} kernel-src

echo "--- Downloading Clang Toolchain (Sparse Checkout) ---"
mkdir -p clang-toolchain
cd clang-toolchain
git init
git remote add origin https://android.googlesource.com/platform/prebuilts/clang/host/linux-x86
git config core.sparseCheckout true
echo "clang-r596125/*" >> .git/info/sparse-checkout
git fetch --depth=1 origin 9b144befdfd93b90e02c663504fb9f4b95f9faf8
git checkout 9b144befdfd93b90e02c663504fb9f4b95f9faf8
cd ..

export PATH="${WORKDIR}/clang-toolchain/clang-r596125/bin:${PATH}"

cd kernel-src

echo "--- Setup Environment ---"
export ARCH=arm64
export SUBARCH=arm64
export KBUILD_BUILD_USER="circleci"
export KBUILD_BUILD_HOST="circleci"

DEFCONFIG="vendor/asus/X00TD_defconfig"

echo "--- Clean Build Directory ---"
make O=out clean
make O=out mrproper

echo "--- Make Defconfig ---"
make O=out $DEFCONFIG

echo "--- Compiling Kernel ---"
make -j$(nproc --all) \
    O=out \
    ARCH=arm64 \
    CC=clang \
    LD=ld.lld \
    AR=llvm-ar \
    NM=llvm-nm \
    OBJCOPY=llvm-objcopy \
    OBJDUMP=llvm-objdump \
    STRIP=llvm-strip \
    CROSS_COMPILE=aarch64-linux-gnu- \
    CROSS_COMPILE_ARM32=arm-linux-gnueabi-

echo "--- Setting up AnyKernel3 ---"
ANYKERNEL_REPO="https://github.com/Kyura-Ground/AnyKernel3"
ANYKERNEL_BRANCH="4.19"

git clone --depth=1 -b ${ANYKERNEL_BRANCH} ${ANYKERNEL_REPO} anykernel
cp out/arch/arm64/boot/Image.gz-dtb anykernel/
cd anykernel
zip -r9 ../kernel-flashable.zip *
cd ..

echo "Build and Packaging Completed!"

if [ -n "$TG_BOT_TOKEN" ] && [ -n "$TG_CHAT_ID" ]; then
    echo "--- Uploading to Telegram ---"
    ZIP_NAME="kernel-flashable.zip"
    
    # Custom Message
    TG_MESSAGE="✅ <b>Build Finished Successfully</b>%0A"
    TG_MESSAGE+="<b>Kernel:</b> Kyura-Kernel-X00TD%0A"
    TG_MESSAGE+="<b>Branch:</b> ${KERNEL_BRANCH}%0A"
    TG_MESSAGE+="<b>Compiler:</b> AOSP Clang%0A"

    curl -s -X POST "https://api.telegram.org/bot${TG_BOT_TOKEN}/sendDocument" \
        -F chat_id="${TG_CHAT_ID}" \
        -F document=@"${WORKDIR}/kernel-flashable.zip" \
        -F parse_mode="HTML" \
        -F caption="$(echo -e ${TG_MESSAGE})"
else
    echo "Telegram secret variables not set, skipping upload."
fi
