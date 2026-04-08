#!/bin/bash
# Script to build kernel in CircleCI

set -ex

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
make O=out clean
make O=out mrproper

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
    TG_MESSAGE+="<b>Compiler:</b> LLVM 22.1.2 (PurrrsLitterbox)%0A"

    curl -s -X POST "https://api.telegram.org/bot${TG_BOT_TOKEN}/sendDocument" \
        -F chat_id="${TG_CHAT_ID}" \
        -F document=@"${WORKDIR}/kernel-flashable.zip" \
        -F parse_mode="HTML" \
        -F caption="$(echo -e ${TG_MESSAGE})"
else
    echo "Telegram secret variables not set, skipping upload."
fi
