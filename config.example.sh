#!/usr/bin/env bash
# shellcheck disable=SC2034
# Copy to config.sh for local overrides; config.sh is intentionally ignored.
KERNEL_REPO="https://github.com/Kyura-Ground/android_kernel_asus_sdm660-4.4"
KERNEL_BRANCH="lineage-23.2"
DEFCONFIG="X00TD_defconfig"
BUILD_KSU=1
SIGN_ZIP=1
USE_CCACHE=1
# Leave empty to keep the name from the kernel defconfig.
LOCALVERSION=""
# LOCALVERSION="-Custom"
# JOBS=4
# WORK_DIR=/absolute/path/to/fresh-build-directory
# KSU_REF is pinned in build.sh; override it to intentionally update KernelSU.
