#!/bin/bash
# Kernel builder for CircleCI — X00TD
set -euo pipefail

# Set Timezone to WIB
export TZ="Asia/Jakarta"
echo "Build started at: $(date) (Timezone: $TZ)"

# ──────────────────────────────────────────
# Functions
# ──────────────────────────────────────────
info() { echo -e "\e[1;34m[$(date +%T)] --- $1 ---\e[0m"; }
success() { echo -e "\e[1;32m[$(date +%T)] ✅ $1\e[0m"; }
error() {
    echo -e "\e[1;31m[$(date +%T)] ❌ $1\e[0m"
    if [ -n "${TG_BOT_TOKEN:-}" ] && [ -n "${TG_CHAT_ID:-}" ]; then
        local tg_msg="❌ <b>Build Failed!</b>
<b>Error:</b> $1"
        if [ -n "${BUILD_LOG:-}" ] && [ -f "${BUILD_LOG}" ]; then
            curl -sS -m 300 -X POST "https://api.telegram.org/bot${TG_BOT_TOKEN}/sendDocument" \
                -F chat_id="${TG_CHAT_ID}" \
                -F document=@"${BUILD_LOG}" \
                -F parse_mode="HTML" \
                -F caption="${tg_msg}" >/dev/null 2>&1 || true
        else
            curl -sS -m 300 -X POST "https://api.telegram.org/bot${TG_BOT_TOKEN}/sendMessage" \
                -d chat_id="${TG_CHAT_ID}" \
                -d parse_mode="HTML" \
                -d text="${tg_msg}" >/dev/null 2>&1 || true
        fi
    fi
    exit 1
}

# ──────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────
# Defaults (fallback)
KERNEL_REPO="${KERNEL_REPO:-https://github.com/Kyura-Ground/android_kernel_asus_sdm660-4.19}"
KERNEL_BRANCH="${KERNEL_BRANCH:-StoneSky}"
DEFCONFIG="${DEFCONFIG:-vendor/asus/X00TD_defconfig}"
ANYKERNEL_REPO="${ANYKERNEL_REPO:-https://github.com/Kyura-Ground/AnyKernel3}"
ANYKERNEL_BRANCH="${ANYKERNEL_BRANCH:-4.19}"
BUILD_KSU="${BUILD_KSU:-1}" # Set to 1 to enable KernelSU, 0 to disable
KBUILD_BUILD_USER="${KBUILD_BUILD_USER:-Kyura}"
KBUILD_BUILD_HOST="${KBUILD_BUILD_HOST:-Labs}"

# Load custom config if exists (overrides defaults)
if [ -f "config.sh" ]; then
    info "Using custom config from config.sh"
    # shellcheck source=/dev/null
    source config.sh
fi

# Toolchain (Clang) URL
CLANG_URL="https://android.googlesource.com/platform/prebuilts/clang/host/linux-x86/+archive/f60b8b55282f002f594f452ce22dfd6cf1fd7e3c/clang-r596125.tar.gz"

# Build Options
USE_CCACHE="${USE_CCACHE:-1}"
USE_LLVM="${USE_LLVM:-1}"
USE_LLVM_IAS="${USE_LLVM_IAS:-1}"
LTO="${LTO:-0}" # 0: Default, 1: Thin, 2: Full (if supported)

# Toolchain (GCC Cross Compiler) logic
USE_GCC_CROSS="${USE_GCC_CROSS:-1}" # Set to 1 to use Clang x GCC 11.2.1
GCC_64_REPO="${GCC_64_REPO:-https://github.com/mvaisakh/gcc-arm64}"
GCC_64_BRANCH="${GCC_64_BRANCH:-gcc-new}"
GCC_32_REPO="${GCC_32_REPO:-https://github.com/mvaisakh/gcc-arm}"
GCC_32_BRANCH="${GCC_32_BRANCH:-gcc-new}"

# Export build environment
export ARCH=arm64
export SUBARCH=arm64
export KBUILD_BUILD_USER
export KBUILD_BUILD_HOST

WORKDIR=$(pwd)
LOG_DIR="${WORKDIR}/logs"
mkdir -p "${LOG_DIR}"
BUILD_LOG="${LOG_DIR}/build_$(date +'%Y%m%d_%H%M').log"

JOBS=$(nproc --all)
BUILD_START=$(date +%s)

# CCache Setup
if [ "${USE_CCACHE}" -eq 1 ]; then
    USE_CCACHE=1
    export USE_CCACHE
    CCACHE_DIR="${WORKDIR}/.ccache"
    export CCACHE_DIR
    CCACHE_EXEC=$(which ccache || true)
    export CCACHE_EXEC
    if [ -z "${CCACHE_EXEC}" ]; then
        info "ccache not found, installing..."
        sudo apt-get update -y && sudo apt-get install -y ccache
        CCACHE_EXEC=$(which ccache)
        export CCACHE_EXEC
    fi
    info "Using ccache: ${CCACHE_EXEC}"
    "${CCACHE_EXEC}" -M 10G
fi

# ──────────────────────────────────────────
# Setup (Parallel)
# ──────────────────────────────────────────
info "Starting parallel setup tasks..."

# Task 1: Clone kernel source
setup_kernel() {
    if [ ! -d "kernel-src" ]; then
        info "Cloning Kernel Source"
        git clone --depth=1 -b "${KERNEL_BRANCH}" "${KERNEL_REPO}" kernel-src || return 1
    else
        info "Kernel source already exists, skipping clone"
    fi
}

# Task 2: Fetch & extract Clang toolchain
setup_clang() {
    mkdir -p clang-toolchain
    if [ -x "clang-toolchain/bin/clang" ]; then
        info "Using cached Clang toolchain"
    else
        info "Downloading Clang Toolchain"
        if [[ "${CLANG_URL}" == *.tar.zst ]]; then
            wget -qO- "${CLANG_URL}" | tar -I zstd -xf - -C clang-toolchain || return 1
        else
            wget -qO- "${CLANG_URL}" | tar -xzf - -C clang-toolchain || return 1
        fi
    fi
    [ -x "clang-toolchain/bin/clang" ] || return 1
}

# Task 3: Clone AnyKernel3
setup_anykernel() {
    if [ ! -d "anykernel" ]; then
        info "Cloning AnyKernel3"
        git clone --depth=1 -b "${ANYKERNEL_BRANCH}" "${ANYKERNEL_REPO}" anykernel || return 1
    fi
}

# Task 5: Fetch GCC 64-bit
setup_gcc_64() {
    if [ "${USE_GCC_CROSS}" -eq 1 ] && [ ! -d "gcc-arm64" ]; then
        info "Cloning GCC ARM64 (CROSS_COMPILE)"
        git clone --depth=1 -b "${GCC_64_BRANCH}" "${GCC_64_REPO}" gcc-arm64 || return 1
    fi
}

# Task 6: Fetch GCC 32-bit
setup_gcc_32() {
    if [ "${USE_GCC_CROSS}" -eq 1 ] && [ ! -d "gcc-arm32" ]; then
        info "Cloning GCC ARM32 (CROSS_COMPILE_ARM32)"
        git clone --depth=1 -b "${GCC_32_BRANCH}" "${GCC_32_REPO}" gcc-arm32 || return 1
    fi
}

# Task 4: Fetch ZipSigner
setup_zipsigner() {
    ZIPSIGNER_JAR="${WORKDIR}/zipsigner-3.0-dexed.jar"
    if [ ! -f "${ZIPSIGNER_JAR}" ]; then
        info "Downloading ZipSigner"
        wget -qO "${ZIPSIGNER_JAR}" "https://github.com/Magisk-Modules-Repo/zipsigner/raw/master/bin/zipsigner-3.0-dexed.jar" || return 1
    fi
}

# Run tasks in background
setup_kernel & PID_KERNEL=$!
setup_clang & PID_KERNEL_CLANG=$!
setup_gcc_64 & PID_GCC_64=$!
setup_gcc_32 & PID_GCC_32=$!
setup_anykernel & PID_ANYKERNEL=$!
setup_zipsigner & PID_ZIPSIGNER=$!

# Wait for essential tasks before build
wait "${PID_KERNEL}" || error "Kernel source setup failed"
wait "${PID_KERNEL_CLANG}" || error "Clang toolchain setup failed"
if [ "${USE_GCC_CROSS}" -eq 1 ]; then
    wait "${PID_GCC_64}" || error "GCC 64-bit setup failed"
    wait "${PID_GCC_32}" || error "GCC 32-bit setup failed"
    export PATH="${WORKDIR}/gcc-arm64/bin:${WORKDIR}/gcc-arm32/bin:${PATH}"
fi

export PATH="${WORKDIR}/clang-toolchain/bin:${PATH}"

# ──────────────────────────────────────────
# Build Preparation
# ──────────────────────────────────────────
cd kernel-src || error "Kernel source directory not found"

# Patching mechanism
if [ -d "${WORKDIR}/patches" ]; then
    info "Applying patches"
    for patch in "${WORKDIR}/patches"/*.patch; do
        [ -f "$patch" ] || continue
        info "Applying: $(basename "$patch")"
        patch -p1 < "$patch" || error "Failed to apply $patch"
    done
fi

if [ "${BUILD_KSU}" -eq 1 ]; then
    info "Setting up KernelSU"
    curl -LSs "https://raw.githubusercontent.com/ReSukiSU/ReSukiSU/main/kernel/setup.sh" | bash || error "KernelSU setup failed"
    sed -i 's/^CONFIG_LOCALVERSION=.*/CONFIG_LOCALVERSION="-StoneSky-KSU"/' "arch/${ARCH}/configs/${DEFCONFIG}"
else
    info "KernelSU disabled"
    sed -i 's/^CONFIG_LOCALVERSION=.*/CONFIG_LOCALVERSION="-StoneSky"/' "arch/${ARCH}/configs/${DEFCONFIG}"
fi

# ──────────────────────────────────────────
# Build Process
# ──────────────────────────────────────────
info "🚀 Starting Kernel Build..."

# Compiler Selection
MAKE_ARGS=(
    O=out
    ARCH="${ARCH}"
    SUBARCH="${SUBARCH}"
)

if [ "${USE_GCC_CROSS}" -eq 1 ]; then
    info "Using Clang x GCC Cross Compile"
    MAKE_ARGS+=(
        CROSS_COMPILE="aarch64-elf-"
        CROSS_COMPILE_ARM32="arm-eabi-"
        LD="ld.lld"
        AR="llvm-ar"
        NM="llvm-nm"
        OBJCOPY="llvm-objcopy"
        OBJDUMP="llvm-objdump"
        STRIP="llvm-strip"
    )
    if [ "${USE_CCACHE}" -eq 1 ]; then
        MAKE_ARGS+=( CC="ccache clang" HOSTCC="ccache gcc" )
    else
        MAKE_ARGS+=( CC="clang" HOSTCC="gcc" )
    fi
else
    if [ "${USE_LLVM}" -eq 1 ]; then
        MAKE_ARGS+=(
            LLVM=1
        )
        if [ "${USE_LLVM_IAS}" -eq 1 ]; then
            MAKE_ARGS+=(
                LLVM_IAS=1
            )
        fi
    fi

    if [ "${USE_CCACHE}" -eq 1 ]; then
        MAKE_ARGS+=(
            CC="ccache clang"
            HOSTCC="ccache gcc"
        )
    fi
fi

# LTO Optimization
if [ "${LTO}" -eq 1 ]; then
    info "Enabling Thin LTO"
    scripts/config --file out/.config -e LTO_CLANG -e THINLTO
elif [ "${LTO}" -eq 2 ]; then
    info "Enabling Full LTO"
    scripts/config --file out/.config -e LTO_CLANG -d THINLTO
fi

info "Executing defconfig..."
make "${MAKE_ARGS[@]}" "${DEFCONFIG}" 2>&1 | tee -a "${BUILD_LOG}" || error "Defconfig step failed"

info "Starting compilation..."
make -j"${JOBS}" "${MAKE_ARGS[@]}" 2>&1 | tee -a "${BUILD_LOG}" || error "Compilation failed"

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
LOCALVER="$(grep -oP '(?<=CONFIG_LOCALVERSION=").*(?=")' "arch/${ARCH}/configs/${DEFCONFIG}" 2>/dev/null || true)"
COMMIT_MSG="$(git log -1 --pretty=format:"%s")"
COMMIT_HASH="$(git rev-parse --short HEAD)"
ZIP_NAME="${KERNEL_VER}${LOCALVER}-$(date +'%Y%m%d-%H%M').zip"

# Wait for AnyKernel3 (started in background)
wait "${PID_ANYKERNEL}" || error "AnyKernel3 setup failed"

if [ ! -d "../anykernel" ]; then
    error "AnyKernel3 directory not found"
fi

cp "${IMAGE}" "../anykernel/"
cd "../anykernel" || error "AnyKernel3 directory not accessible"
zip -r9 "../${ZIP_NAME}" . -x '.git/*' 'README.md' '*placeholder' || error "Failed to create ZIP"
cd ..

mkdir -p out-zip
mv "${ZIP_NAME}" out-zip/

# ──────────────────────────────────────────
# ZipSigner
# ──────────────────────────────────────────
# Wait for ZipSigner (started in background)
wait "${PID_ZIPSIGNER}" || error "ZipSigner download failed"

info "Signing ZIP with ZipSigner"
ZIPSIGNER_JAR="${WORKDIR}/zipsigner-3.0-dexed.jar"
if [ ! -f "${ZIPSIGNER_JAR}" ]; then
    error "ZipSigner JAR not found at ${ZIPSIGNER_JAR}"
fi

java -jar "${ZIPSIGNER_JAR}" "out-zip/${ZIP_NAME}" "out-zip/${ZIP_NAME%.zip}-signed.zip" || error "Signing failed"
rm -f "out-zip/${ZIP_NAME}"
ZIP_NAME="${ZIP_NAME%.zip}-signed.zip"

success "ZIP: ${ZIP_NAME}"

# ──────────────────────────────────────────
# Notifications
# ──────────────────────────────────────────
send_telegram() {
    [ -z "${TG_BOT_TOKEN}" ] || [ -z "${TG_CHAT_ID}" ] && return 0
    
    info "Uploading to Telegram"
    local compiler_ver
    compiler_ver=$(clang --version | head -n 1 | perl -pe 's/ \(.*//')
    
    local msg="✅ <b>Build Finished</b>
<b>Kernel:</b> StoneSky
<b>Version:</b> ${ZIP_NAME}
<b>Branch:</b> ${KERNEL_BRANCH}
<b>Compiler:</b> ${compiler_ver}
<b>Time:</b> ${BUILD_TIME}
<b>Last Commit:</b> <a href=\"${KERNEL_REPO}/commit/${COMMIT_HASH}\">${COMMIT_HASH}</a>: ${COMMIT_MSG}"

    if ! curl -sS -m 300 -X POST "https://api.telegram.org/bot${TG_BOT_TOKEN}/sendDocument" \
        -F chat_id="${TG_CHAT_ID}" \
        -F document=@"out-zip/${ZIP_NAME}" \
        -F parse_mode="HTML" \
        -F caption="${msg}"; then
        
        info "Telegram upload failed! Attempting Pixeldrain fallback..."
        send_pixeldrain
    fi
}

send_pixeldrain() {
    [ -z "${PIXELDRAIN_API_KEY}" ] && { info "Pixeldrain API key not set, skipping fallback."; return 0; }
    
    info "Uploading to Pixeldrain"
    curl -sS -T "out-zip/${ZIP_NAME}" -u :"${PIXELDRAIN_API_KEY}" https://pixeldrain.com/api/file/
    echo ""
}

# ──────────────────────────────────────────
# Finalize
# ──────────────────────────────────────────
send_telegram
success "Done!"
