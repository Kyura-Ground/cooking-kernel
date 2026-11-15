# shellcheck shell=bash
# AnyKernel3 recipe for the X00TD 5.4 bringup.
# AnyKernel3 by osm0sis; X00TD template by ikwfahmi.
# Variables below are consumed by the sourced AnyKernel core.
# shellcheck disable=SC2034

# AnyKernel reads this metadata block directly from the file.
# shellcheck disable=SC2289
properties() { '
kernel.string=X00TD Linux 5.4 @KERNEL_SHA@
do.devicecheck=1
do.modules=0
do.systemless=0
do.cleanup=1
do.cleanuponabort=0
device.name1=X00TD
device.name2=ASUS_X00TD
device.name3=WW_X00TD
device.name4=X00T
device.name5=WW_X00T
supported.versions=17
supported.patchlevels=
supported.vendorpatchlevels=
'; }

BLOCK=/dev/block/bootdevice/by-name/boot
IS_SLOT_DEVICE=0
RAMDISK_COMPRESSION=auto
PATCH_VBMETA_FLAG=0

# shellcheck source=/dev/null
. tools/ak3-core.sh

# Both target partitions must exist before either is written.
[ -b /dev/block/bootdevice/by-name/boot ] || abort "Missing boot partition"
[ -b /dev/block/bootdevice/by-name/recovery ] || abort "Missing recovery partition"

require_54() {
    grep -aq 'Linux version 5\.4\.' "$SPLITIMG/kernel" ||
        abort "Install the X00TD 5.4 ROM and recovery first; refusing a kernel-only migration"
}

verify_flash() {
    local expected actual
    sync
    expected=$(sha256sum "$AKHOME/boot-new.img")
    actual=$(head -c "$(wc -c < "$AKHOME/boot-new.img")" "$BLOCK" | sha256sum)
    [ "${expected%% *}" = "${actual%% *}" ] || abort "Image readback failed: $BLOCK"
}

# split_boot/flash_boot preserve each partition's ramdisk and boot header.
split_boot
require_54
BLOCK=/dev/block/bootdevice/by-name/recovery
reset_ak
split_boot
require_54

ui_print "Updating recovery kernel..."
flash_boot
verify_flash

BLOCK=/dev/block/bootdevice/by-name/boot
reset_ak
split_boot
ui_print "Updating boot kernel..."
flash_boot
verify_flash
ui_print "Boot and recovery updated. Reboot to test the new kernel."
