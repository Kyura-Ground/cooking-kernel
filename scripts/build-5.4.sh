#!/usr/bin/env bash
set -Eeuo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
KERNEL_DIR="$ROOT/kernel-src-54"
OUT_DIR="$KERNEL_DIR/out"
LOG_DIR="$ROOT/logs-54"
ARTIFACT_DIR="$ROOT/artifacts-54"
KERNEL_REVISION=${KERNEL_REVISION:-lineage-22.1}
export PATH="/usr/lib/llvm-14/bin:$PATH"
mkdir -p "$LOG_DIR" "$ARTIFACT_DIR"
exec > >(tee "$LOG_DIR/build.log") 2>&1

finish() {
    local result=$?
    trap - EXIT
    if [[ -f "$OUT_DIR/.config" ]]; then
        cp "$OUT_DIR/.config" "$LOG_DIR/kernel.config"
    fi
    ccache --show-stats || true
    exit "$result"
}
trap finish EXIT

git init -q "$KERNEL_DIR"
git -C "$KERNEL_DIR" remote add origin https://github.com/Kyura-Ground/android_kernel_asus_sdm660-5.4.git
git -C "$KERNEL_DIR" fetch --depth=1 --no-tags origin "$KERNEL_REVISION"
git -C "$KERNEL_DIR" checkout --detach FETCH_HEAD
git -C "$KERNEL_DIR" rev-parse HEAD | tee "$LOG_DIR/source-revision.txt"
clang-14 --version | tee "$LOG_DIR/toolchain.txt"
grep -Eq '^VERSION[[:space:]]*=[[:space:]]*5$' "$KERNEL_DIR/Makefile"
grep -Eq '^PATCHLEVEL[[:space:]]*=[[:space:]]*4$' "$KERNEL_DIR/Makefile"
ccache --max-size 3G

MAKE_ARGS=(
    -C "$KERNEL_DIR" O="$OUT_DIR" ARCH=arm64
    'CC=ccache clang-14' HOSTCC=gcc HOSTCXX=g++
    LD=ld.lld-14 AR=llvm-ar-14 NM=llvm-nm-14
    STRIP=llvm-strip-14 OBJCOPY=llvm-objcopy-14 OBJDUMP=llvm-objdump-14
    CROSS_COMPILE=aarch64-linux-gnu- CROSS_COMPILE_COMPAT=arm-linux-gnueabi-
    CC_COMPAT=arm-linux-gnueabi-gcc
    CLANG_TRIPLE=aarch64-linux-gnu- LLVM_IAS=1
)

make "${MAKE_ARGS[@]}" vendor/asus/X00TD_defconfig
for option in ARCH_SDM660 QCOM_BUS_SCALING MSMB_CAMERA MSM_CAMERA_SENSOR \
    MSM_CPP MSM_CCI MSM_CSIPHY MSM_CSID MSMB_JPEG SND_SOC_SDM660 \
    SND_SOC_INT_CODEC SND_SOC_QDSP6V2 QCOM_SOUNDWIRE SND_SOC_QCOM_WCD9335 \
    MSM_ADSP_LOADER QPNP_SMB2 QPNP_FG_GEN3 MMC_CRYPTO DRM_MSM; do
    grep -qx "CONFIG_$option=y" "$OUT_DIR/.config" || {
        printf 'Required X00TD driver was discarded by Kconfig: %s\n' "$option" >&2
        exit 1
    }
done
for option in SOUNDWIRE SND_SOC_WCD9335; do
    if grep -qx "CONFIG_$option=y" "$OUT_DIR/.config"; then
        printf 'Conflicting upstream/vendor provider selected: %s\n' "$option" >&2
        exit 1
    fi
done
# Android normally supplies this public development trust anchor to Kbuild.
cp "$ROOT/configs/verity.x509.pem" "$OUT_DIR/verity.x509.pem"
make "${MAKE_ARGS[@]}" -j"$(nproc)" Image.gz-dtb modules
test -s "$OUT_DIR/arch/arm64/boot/Image.gz-dtb"
test -s "$OUT_DIR/vmlinux"

cp "$OUT_DIR/arch/arm64/boot/Image.gz-dtb" "$ARTIFACT_DIR/"
cp "$OUT_DIR/arch/arm64/boot/dts/vendor/qcom/sdm636-qrd-X00TD.dtb" "$ARTIFACT_DIR/"
cp "$OUT_DIR/.config" "$OUT_DIR/System.map" "$OUT_DIR/Module.symvers" "$ARTIFACT_DIR/"
gzip -c "$OUT_DIR/vmlinux" > "$ARTIFACT_DIR/vmlinux.gz"
(
    cd "$OUT_DIR"
    find . -type f -name '*.ko' -print0 | tar --null -T - -czf "$ARTIFACT_DIR/modules.tar.gz"
)
(
    cd "$ARTIFACT_DIR"
    sha256sum Image.gz-dtb sdm636-qrd-X00TD.dtb vmlinux.gz modules.tar.gz > SHA256SUMS
)
