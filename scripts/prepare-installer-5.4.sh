#!/usr/bin/env bash
set -Eeuo pipefail

TOOLS_DIR=$1
ANYKERNEL_SHA=fafee4a00ff19ce41f1e62b9549eafe980402ba7
SIGNER_SHA=0239ba28e54b7b4c920a236785b5fcff271c73ed
SIGNER_HASH=efc382651dadd4b47ed3e669a5fb17e1a5cacab2b65c0736c65246f442a4c19f
mkdir -p "$TOOLS_DIR"
git init -q "$TOOLS_DIR/anykernel"
git -C "$TOOLS_DIR/anykernel" remote add origin https://github.com/Kyura-Ground/AnyKernel3.git
git -C "$TOOLS_DIR/anykernel" fetch --depth=1 origin "$ANYKERNEL_SHA"
git -C "$TOOLS_DIR/anykernel" checkout -q --detach FETCH_HEAD
[[ $(git -C "$TOOLS_DIR/anykernel" rev-parse HEAD) == "$ANYKERNEL_SHA" ]]
python3 "$TOOLS_DIR/anykernel/tests/mount.py"
printf '%s\n' "$ANYKERNEL_SHA" > "$TOOLS_DIR/anykernel-commit.txt"
curl --fail --silent --show-error --location --retry 3 \
    "https://raw.githubusercontent.com/Magisk-Modules-Repo/zipsigner/$SIGNER_SHA/bin/zipsigner-3.0-dexed.jar" \
    --output "$TOOLS_DIR/zipsigner.jar"
printf '%s  %s\n' "$SIGNER_HASH" "$TOOLS_DIR/zipsigner.jar" | sha256sum -c -
