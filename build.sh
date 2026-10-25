#!/usr/bin/env bash
# X00TD / AxionOS Android 16 / Linux 4.4 builder.
set -Eeuo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
cd "$ROOT"

KERNEL_REPO="${KERNEL_REPO:-https://github.com/Kyura-Ground/android_kernel_asus_sdm660}"
KERNEL_BRANCH="${KERNEL_BRANCH:-axion-23.2-4.4}"
DEFCONFIG="${DEFCONFIG:-X00TD_defconfig}"
CLANG_URL="${CLANG_URL:-https://android.googlesource.com/platform/prebuilts/clang/host/linux-x86/+archive/747f0cceb48f48bf7cf497a3e01af1389266904b/clang-r614150.tar.gz}"
GCC_64_REPO="${GCC_64_REPO:-https://github.com/LineageOS/android_prebuilts_gcc_linux-x86_aarch64_aarch64-linux-android-4.9}"
GCC_64_REF="${GCC_64_REF:-5e030eafe024784a73cdf47e6936ac0dbfc763dc}"
GCC_32_REPO="${GCC_32_REPO:-https://github.com/LineageOS/android_prebuilts_gcc_linux-x86_arm_arm-linux-androideabi-4.9}"
GCC_32_REF="${GCC_32_REF:-111258a10e017f067b27e6cfcea7619d753f3309}"
KSU_REPO="${KSU_REPO:-https://github.com/backslashxx/KernelSU}"
KSU_REF="${KSU_REF:-a7f37595dcf067791fc2c689047a651c19d6704c}"
ANYKERNEL_REPO="${ANYKERNEL_REPO:-https://github.com/Kyura-Ground/AnyKernel3}"
ANYKERNEL_BRANCH="${ANYKERNEL_BRANCH:-4.4}"
BUILD_KSU="${BUILD_KSU:-1}"
BUILD_NOMOUNT="${BUILD_NOMOUNT:-0}"
SIGN_ZIP="${SIGN_ZIP:-1}"
USE_CCACHE="${USE_CCACHE:-1}"
LOCALVERSION="${LOCALVERSION:--Singularity}"
KBUILD_BUILD_USER="${KBUILD_BUILD_USER:-Kyura}"
KBUILD_BUILD_HOST="${KBUILD_BUILD_HOST:-circleci}"
WORK_DIR="${WORK_DIR:-$ROOT}"
JOBS="${JOBS:-$(nproc)}"

if [[ -f "$ROOT/config.sh" ]]; then
    # shellcheck source=/dev/null
    source "$ROOT/config.sh"
fi

export TZ="${TZ:-Asia/Jakarta}" ARCH=arm64 SUBARCH=arm64
export KBUILD_BUILD_USER KBUILD_BUILD_HOST
[[ $WORK_DIR == /* ]] || WORK_DIR="$ROOT/$WORK_DIR"
mkdir -p "$WORK_DIR"
WORK_DIR=$(cd "$WORK_DIR" && pwd)
KERNEL_DIR="$WORK_DIR/kernel-src"
OUT_DIR="$KERNEL_DIR/out"
TOOLCHAIN_DIR="$WORK_DIR/.toolchains"
LOG_DIR="$WORK_DIR/logs"
ARTIFACT_DIR="$WORK_DIR/out-zip"
mkdir -p "$LOG_DIR" "$ARTIFACT_DIR" "$TOOLCHAIN_DIR"
BUILD_LOG="$LOG_DIR/build_$(date +%Y%m%d_%H%M%S).log"
BUILD_START=$(date +%s)
exec > >(tee "$BUILD_LOG") 2>&1

info() { printf '[%s] %s\n' "$(date +%T)" "$*"; }
success() { info "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

finish() {
    local status=$?
    trap - EXIT
    if [[ -f "$OUT_DIR/.config" ]]; then
        cp "$OUT_DIR/.config" "$LOG_DIR/kernel.config"
    fi
    if (( status != 0 )); then
        printf 'Build failed (exit %s). Log: %s\n' "$status" "$BUILD_LOG" >&2
    fi
    exit "$status"
}
trap finish EXIT

# CircleCI booleans interpolate to true/false; environment overrides may use 1/0.
normalize_bool() {
    case "$2" in
        1|true) printf -v "$1" '%s' 1 ;;
        0|false) printf -v "$1" '%s' 0 ;;
        *) die "$1 must be 1/0 or true/false" ;;
    esac
}
normalize_bool BUILD_KSU "$BUILD_KSU"
normalize_bool SIGN_ZIP "$SIGN_ZIP"
normalize_bool USE_CCACHE "$USE_CCACHE"
[[ $JOBS =~ ^[1-9][0-9]*$ ]] || die "JOBS must be a positive integer"
[[ ${LTO:-0} == 0 ]] || die "This 4.4 builder does not enable LTO"
[[ $BUILD_NOMOUNT == 0 ]] || die "NoMount is not configured for this 4.4 tree"

for command in git make bc bison flex gcc g++ curl tar zip unzip sha256sum python3; do
    command -v "$command" >/dev/null || die "Missing dependency: $command (see README)"
done
if (( SIGN_ZIP )); then
    command -v java >/dev/null || die "SIGN_ZIP=1 requires java"
fi

# Cache only immutable toolchain revisions. Never stash/reset a user's worktree.
checkout_repo() {
    local repo=$1 ref=$2 dest=$3
    if [[ -e "$dest" ]]; then
        [[ -d "$dest/.git" ]] || die "$dest exists and is not a Git clone"
        # Compare the stored URL; get-url expands CircleCI's insteadOf rewrites.
        [[ $(git -C "$dest" config --get remote.origin.url) == "$repo" ]] ||
            die "Cached repository URL differs: $dest"
        [[ -z $(git -C "$dest" status --porcelain) ]] ||
            die "$dest has changes; move it aside before rebuilding"
        if [[ $ref =~ ^[0-9a-f]{40}$ ]] &&
            [[ $(git -C "$dest" rev-parse HEAD) == "$ref" ]]; then
            return
        fi
    else
        git init -q "$dest"
        git -C "$dest" remote add origin "$repo"
    fi
    git -C "$dest" fetch --depth=1 --no-tags origin "$ref"
    git -C "$dest" checkout --detach FETCH_HEAD
}

setup_clang() {
    local dest="$TOOLCHAIN_DIR/clang"
    if [[ -x "$dest/bin/clang" && -f "$dest/.source-url" ]] &&
        [[ $(cat "$dest/.source-url") == "$CLANG_URL" ]]; then
        return
    fi
    local staging
    staging=$(mktemp -d "$TOOLCHAIN_DIR/.clang-download.XXXXXX")
    curl --fail --location --retry 8 --retry-delay 15 --retry-max-time 600 \
        --connect-timeout 30 \
        "$CLANG_URL" -o "$staging/clang.tar.gz"
    mkdir "$staging/extracted"
    tar -xzf "$staging/clang.tar.gz" -C "$staging/extracted"
    [[ -x "$staging/extracted/bin/clang" ]] || die "Clang archive lacks bin/clang"
    printf '%s\n' "$CLANG_URL" > "$staging/extracted/.source-url"
    # dest is the builder-owned compiler cache, never the kernel checkout.
    if [[ -e "$dest" ]]; then
        mv "$dest" "$staging/previous"
    fi
    mv "$staging/extracted" "$dest"
    rm -rf -- "$staging"
}

info "Preparing Linux 4.4 source and toolchains"
info "Kernel source: $KERNEL_REPO ($KERNEL_BRANCH)"
checkout_repo "$KERNEL_REPO" "$KERNEL_BRANCH" "$KERNEL_DIR"
info "Kernel commit: $(git -C "$KERNEL_DIR" rev-parse HEAD)"
[[ -f "$KERNEL_DIR/arch/arm64/configs/$DEFCONFIG" ]] ||
    die "Missing arch/arm64/configs/$DEFCONFIG"
if ! grep -Eq '^VERSION[[:space:]]*=[[:space:]]*4$' "$KERNEL_DIR/Makefile" ||
    ! grep -Eq '^PATCHLEVEL[[:space:]]*=[[:space:]]*4$' "$KERNEL_DIR/Makefile"; then
    die "Expected a Linux 4.4 kernel; check KERNEL_REPO/KERNEL_BRANCH"
fi

setup_clang
checkout_repo "$GCC_64_REPO" "$GCC_64_REF" "$TOOLCHAIN_DIR/gcc-arm64"
checkout_repo "$GCC_32_REPO" "$GCC_32_REF" "$TOOLCHAIN_DIR/gcc-arm32"
export PATH="$TOOLCHAIN_DIR/clang/bin:$TOOLCHAIN_DIR/gcc-arm64/bin:$TOOLCHAIN_DIR/gcc-arm32/bin:$PATH"
for command in clang aarch64-linux-android-gcc aarch64-linux-android-ld \
    aarch64-linux-android-elfedit arm-linux-androideabi-gcc arm-linux-androideabi-ld; do
    command -v "$command" >/dev/null || die "Toolchain is incomplete: $command"
done

MAKE_ARGS=(
    -C "$KERNEL_DIR" O="$OUT_DIR" ARCH=arm64 SUBARCH=arm64
    CROSS_COMPILE=aarch64-linux-android-
    CROSS_COMPILE_ARM32=arm-linux-androideabi-
    CLANG_TRIPLE=aarch64-linux-gnu-
    CLANG_TRIPLE_ARM32=arm-linux-gnueabi-
    # The compat vDSO needs the full binutils prefix, not just the bin directory.
    "CLANG_PREFIX32=--prefix=$TOOLCHAIN_DIR/gcc-arm32/bin/arm-linux-androideabi-"
    LLVM_IAS=0 HOSTCC=gcc HOSTCXX=g++
)
if (( USE_CCACHE )); then
    command -v ccache >/dev/null || die "USE_CCACHE=1 requires ccache"
    export CCACHE_DIR="$WORK_DIR/.ccache"
    ccache --max-size "${CCACHE_MAXSIZE:-5G}"
    MAKE_ARGS+=("CC=ccache clang -fdebug-default-version=4")
else
    MAKE_ARGS+=("CC=clang -fdebug-default-version=4")
fi
# Keep GNU 4.9 binutils selected by CROSS_COMPILE; this builder uses LLVM_IAS=0.
# Modern Clang defaults to DWARF 5, which those assemblers cannot read. Keep the
# default on CC so the compat vDSO's separate flags also use DWARF 4 with -g.

if [[ -d "$ROOT/patches" ]]; then
    for patch in "$ROOT/patches/"*.patch; do
        [[ -f "$patch" ]] || continue
        info "Applying $(basename "$patch")"
        git -C "$KERNEL_DIR" apply --check "$patch"
        git -C "$KERNEL_DIR" apply "$patch"
    done
fi

if (( BUILD_KSU )); then
    info "Integrating KernelSU at $KSU_REF"
    checkout_repo "$KSU_REPO" "$KSU_REF" "$KERNEL_DIR/KernelSU"
    [[ -f "$KERNEL_DIR/KernelSU/kernel/Kconfig" ]] || die "KernelSU Kconfig missing"
    [[ ! -e "$KERNEL_DIR/drivers/kernelsu" && ! -L "$KERNEL_DIR/drivers/kernelsu" ]] ||
        die "Source already has drivers/kernelsu; use a fresh kernel-src"
    ln -s ../KernelSU/kernel "$KERNEL_DIR/drivers/kernelsu"
    # CONFIG_KSU is a Make variable; preserve it literally for Kbuild.
    # shellcheck disable=SC2016
    printf '\nobj-$(CONFIG_KSU) += kernelsu/\n' >> "$KERNEL_DIR/drivers/Makefile"
    printf '\nsource "drivers/kernelsu/Kconfig"\n' >> "$KERNEL_DIR/drivers/Kconfig"
fi

mkdir -p "$OUT_DIR"
make "${MAKE_ARGS[@]}" "$DEFCONFIG"
if (( BUILD_KSU )); then
    (
        cd "$KERNEL_DIR"
        scripts/kconfig/merge_config.sh -m -O "$OUT_DIR" \
            "$OUT_DIR/.config" "$ROOT/configs/ksu.config"
    )
fi
"$KERNEL_DIR/scripts/config" --file "$OUT_DIR/.config" \
    --set-str LOCALVERSION "$LOCALVERSION" --disable LOCALVERSION_AUTO
make "${MAKE_ARGS[@]}" olddefconfig
if (( BUILD_KSU )); then
    for option in KSU KSU_TAMPER_SYSCALL_TABLE; do
        grep -qx "CONFIG_$option=y" "$OUT_DIR/.config" ||
            die "CONFIG_$option did not survive olddefconfig; check KSU dependencies"
    done
    for option in KSU_DEBUG KSU_TOOLKIT KSU_EXTRAS; do
        if grep -qx "CONFIG_$option=y" "$OUT_DIR/.config"; then
            die "CONFIG_$option must remain disabled"
        fi
    done
fi

{
    printf 'Kernel repo: %s\nKernel ref: %s\nKernel commit: %s\n' \
        "$KERNEL_REPO" "$KERNEL_BRANCH" "$(git -C "$KERNEL_DIR" rev-parse HEAD)"
    printf 'KernelSU enabled: %s\n' "$BUILD_KSU"
    if (( BUILD_KSU )); then
        printf 'KernelSU commit: %s\n' "$(git -C "$KERNEL_DIR/KernelSU" rev-parse HEAD)"
    fi
    printf 'Clang archive: %s\n' "$CLANG_URL"
    printf 'GCC ARM64 commit: %s\nGCC ARM32 commit: %s\n' \
        "$(git -C "$TOOLCHAIN_DIR/gcc-arm64" rev-parse HEAD)" \
        "$(git -C "$TOOLCHAIN_DIR/gcc-arm32" rev-parse HEAD)"
    clang --version
    aarch64-linux-android-gcc --version
    arm-linux-androideabi-gcc --version
} > "$LOG_DIR/manifest.txt"

info "Building Image.gz-dtb with $JOBS jobs"
make -j"$JOBS" "${MAKE_ARGS[@]}" Image.gz-dtb
IMAGE="$OUT_DIR/arch/arm64/boot/Image.gz-dtb"
[[ -s "$IMAGE" ]] || die "Image.gz-dtb is missing or empty"

info "Packaging AnyKernel3 ($ANYKERNEL_BRANCH)"
checkout_repo "$ANYKERNEL_REPO" "$ANYKERNEL_BRANCH" "$WORK_DIR/anykernel"
[[ -f "$WORK_DIR/anykernel/anykernel.sh" ]] || die "AnyKernel3 anykernel.sh missing"
grep -q 'device.name[0-9]*=X00TD' "$WORK_DIR/anykernel/anykernel.sh" ||
    die "AnyKernel3 does not declare X00TD"
git -C "$WORK_DIR/anykernel" rev-parse HEAD > "$LOG_DIR/anykernel-commit.txt"
printf 'AnyKernel3 repo: %s\nAnyKernel3 ref: %s\nAnyKernel3 commit: %s\n' \
    "$ANYKERNEL_REPO" "$ANYKERNEL_BRANCH" \
    "$(git -C "$WORK_DIR/anykernel" rev-parse HEAD)" >> "$LOG_DIR/manifest.txt"
cp "$IMAGE" "$WORK_DIR/anykernel/Image.gz-dtb"

KERNEL_VER=$(make -s "${MAKE_ARGS[@]}" kernelversion)
KERNEL_SHA=$(git -C "$KERNEL_DIR" rev-parse --short=12 HEAD)
VARIANT=vanilla
(( BUILD_KSU == 0 )) || VARIANT=KSU
ZIP_NAME="$KERNEL_VER$LOCALVERSION-$VARIANT-$(date +%Y%m%d-%H%M%S)-$KERNEL_SHA.zip"
[[ $ZIP_NAME != */* ]] || die "LOCALVERSION must not contain '/'"
(
    cd "$WORK_DIR/anykernel"
    zip -q -r9 "$ARTIFACT_DIR/$ZIP_NAME" . \
        -x '.git/*' '.github/*' 'README.md' '*placeholder'
)
unzip -tq "$ARTIFACT_DIR/$ZIP_NAME"

if (( SIGN_ZIP )); then
    ZIPSIGNER_JAR="$TOOLCHAIN_DIR/zipsigner-3.0-dexed.jar"
    if [[ ! -s "$ZIPSIGNER_JAR" ]]; then
        curl --fail --location --retry 3 \
            https://github.com/Magisk-Modules-Repo/zipsigner/raw/master/bin/zipsigner-3.0-dexed.jar \
            -o "$ZIPSIGNER_JAR.tmp"
        mv "$ZIPSIGNER_JAR.tmp" "$ZIPSIGNER_JAR"
    fi
    java -jar "$ZIPSIGNER_JAR" "$ARTIFACT_DIR/$ZIP_NAME" \
        "$ARTIFACT_DIR/${ZIP_NAME%.zip}-signed.zip"
    rm "$ARTIFACT_DIR/$ZIP_NAME"
    ZIP_NAME="${ZIP_NAME%.zip}-signed.zip"
    unzip -tq "$ARTIFACT_DIR/$ZIP_NAME"
fi

cp "$IMAGE" "$ARTIFACT_DIR/Image.gz-dtb"
cp "$OUT_DIR/.config" "$ARTIFACT_DIR/kernel.config"
for artifact in System.map Module.symvers; do
    [[ ! -f "$OUT_DIR/$artifact" ]] || cp "$OUT_DIR/$artifact" "$ARTIFACT_DIR/"
done
cp "$LOG_DIR/manifest.txt" "$ARTIFACT_DIR/build-manifest.txt"
(
    cd "$ARTIFACT_DIR"
    sha256sum "$ZIP_NAME" Image.gz-dtb kernel.config > SHA256SUMS
)
BUILD_END=$(date +%s)
ELAPSED=$((BUILD_END - BUILD_START))
success "Built $ZIP_NAME in $((ELAPSED / 60))m $((ELAPSED % 60))s"
# Existing optional upload helpers use paths relative to WORK_DIR.
cd "$WORK_DIR"

send_telegram() {
    local zip_path="out-zip/${ZIP_NAME}"
    if [ ! -f "${zip_path}" ]; then
        info "Telegram upload skipped: ZIP not found at ${zip_path}"
        return 0
    fi

    if [ -z "${TG_BOT_TOKEN:-}" ] || [ -z "${TG_CHAT_ID:-}" ]; then
        info "Telegram credentials not set, skipping upload."
    else
        info "Uploading to Telegram"
        local md5
        md5=$(md5sum "${zip_path}" | cut -d' ' -f1)

        local h=$((ELAPSED / 3600))
        local m=$(((ELAPSED % 3600) / 60))
        local s=$((ELAPSED % 60))

        local compiler_ver
        compiler_ver=$(clang --version | perl -pe 's/\(http.*?\)//gs' | sed 's/[[:space:]]*$//' | head -n 1)

        local ksu_status="Disabled"
        if [ "${BUILD_KSU}" -eq 1 ]; then
            ksu_status="Enabled"
        fi

        local nomount_status="Disabled"
        if [ "${BUILD_NOMOUNT}" -eq 1 ]; then
            nomount_status="Enabled"
        fi

        local msg="build succeeded in ${h}h ${m}m ${s}s
Device: <code>X00TD</code>
Branch: <code>${KERNEL_BRANCH}</code>
KernelSU: <code>${ksu_status}</code>
NoMount: <code>${nomount_status}</code>
md5: <code>${md5}</code>
Compiler: ${compiler_ver}"

        local tg_resp
        tg_resp=$(curl -sS -m 300 -X POST "https://api.telegram.org/bot${TG_BOT_TOKEN}/sendDocument" \
            -F chat_id="${TG_CHAT_ID}" \
            -F document=@"${zip_path}" \
            -F parse_mode="HTML" \
            -F caption="${msg}" 2>&1 || true)

        if echo "${tg_resp}" | grep -q '"ok":true'; then
            info "Telegram upload ok"
        else
            info "Telegram upload failed. Response: ${tg_resp:-<empty>}"
        fi
    fi
}

send_pixeldrain() {
    local zip_path="out-zip/${ZIP_NAME}"
    if [ ! -f "${zip_path}" ]; then
        info "Pixeldrain upload skipped: ZIP not found at ${zip_path}"
        return 0
    fi

    [ -z "${PIXELDRAIN_API_KEY:-}" ] && { info "Pixeldrain API key not set, skipping fallback."; return 0; }
    
    info "Uploading to Pixeldrain"
    curl -sS -T "${zip_path}" -u :"${PIXELDRAIN_API_KEY:-}" https://pixeldrain.com/api/file/
    echo ""
}


# Upload only when the existing opt-in credentials are configured.
send_telegram || info "Telegram upload failed; CircleCI artifacts are retained"
send_pixeldrain || info "Pixeldrain upload failed; CircleCI artifacts are retained"
success "Done!"
