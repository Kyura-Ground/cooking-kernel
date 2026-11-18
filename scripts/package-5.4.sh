#!/usr/bin/env bash
set -Eeuo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
ARTIFACT_DIR=$(cd -- "$1" && pwd)
LOG_DIR=$(cd -- "$2" && pwd)
TOOLS_DIR=$(cd -- "$3" && pwd)
KERNEL_SHA=$(cat "$LOG_DIR/source-revision.txt")
ANYKERNEL_SHA=$(cat "$TOOLS_DIR/anykernel-commit.txt")
[[ $KERNEL_SHA =~ ^[0-9a-f]{40}$ ]] || {
    printf 'Invalid kernel source revision\n' >&2
    exit 1
}
[[ $ANYKERNEL_SHA =~ ^[0-9a-f]{40}$ ]] || {
    printf 'Invalid installer source revision\n' >&2
    exit 1
}
cp "$LOG_DIR/source-revision.txt" "$LOG_DIR/toolchain.txt" "$ARTIFACT_DIR/"
ZIP_NAME="X00TD-5.4-${KERNEL_SHA:0:12}.zip"
ZIP_PATH="$ARTIFACT_DIR/$ZIP_NAME"
FILES=(Image.gz-dtb sdm636-qrd-X00TD.dtb .config System.map Module.symvers
       modules.tar.gz source-revision.txt toolchain.txt)
(
    cd "$ARTIFACT_DIR"
    test -s Image.gz-dtb
    test -s sdm636-qrd-X00TD.dtb
    for file in "${FILES[@]}"; do
        test -f "$file"
    done
    rm -f -- "$ZIP_NAME"
    zip -q -9 "$ZIP_NAME" "${FILES[@]}"
    unzip -tq "$ZIP_NAME"
    sha256sum "$ZIP_NAME" >> SHA256SUMS
)
printf 'Packaged %s\n' "$ZIP_NAME"

PACKAGE_TMP=$(mktemp -d)
trap 'rm -rf -- "$PACKAGE_TMP"' EXIT
cp "$TOOLS_DIR/anykernel-commit.txt" "$LOG_DIR/"
mkdir "$PACKAGE_TMP/installer"
cp -a "$TOOLS_DIR/anykernel/META-INF" "$TOOLS_DIR/anykernel/tools" \
    "$TOOLS_DIR/anykernel/LICENSE" "$PACKAGE_TMP/installer/"
sed "s/@KERNEL_SHA@/$KERNEL_SHA/g" "$ROOT/configs/anykernel-5.4.sh" \
    > "$PACKAGE_TMP/installer/anykernel.sh"
cp "$ARTIFACT_DIR/Image.gz-dtb" "$PACKAGE_TMP/installer/"
cp "$LOG_DIR/source-revision.txt" "$PACKAGE_TMP/installer/"
cp "$TOOLS_DIR/anykernel-commit.txt" "$PACKAGE_TMP/installer/anykernel-revision.txt"
(
    cd "$PACKAGE_TMP/installer"
    zip -q -r9 "$PACKAGE_TMP/installer-unsigned.zip" .
)
ZIP_NAME="X00TD-5.4-${KERNEL_SHA:0:12}-ak3-${ANYKERNEL_SHA:0:12}-recovery.zip"
ZIP_PATH="$ARTIFACT_DIR/$ZIP_NAME"
rm -f -- "$ZIP_PATH"
java -jar "$TOOLS_DIR/zipsigner.jar" "$PACKAGE_TMP/installer-unsigned.zip" "$ZIP_PATH"
unzip -tq "$ZIP_PATH"
sha256sum "$ZIP_PATH" >> "$ARTIFACT_DIR/SHA256SUMS"
printf 'Packaged recovery installer %s\n' "$ZIP_NAME"

send_telegram() {
    if [[ -z ${TG_BOT_TOKEN:-} || -z ${TG_CHAT_ID:-} ]]; then
        printf 'Telegram credentials not set, skipping upload.\n'
        return 0
    fi
    if (( $(stat -c %s "$ZIP_PATH") > 50000000 )); then
        printf 'ZIP exceeds Telegram bot upload limit; CircleCI artifacts are retained.\n'
        return 0
    fi

    local zip_sha
    zip_sha=$(sha256sum "$ZIP_PATH" | cut -d' ' -f1)
    local caption="X00TD Linux 5.4 recovery installer (boot + recovery)
Kernel commit: $KERNEL_SHA
Installer commit: $ANYKERNEL_SHA
SHA256: $zip_sha"
    local response="$PACKAGE_TMP/telegram-response.json"
    printf 'Uploading ZIP to Telegram\n'
    if curl --silent --fail --max-time 300 \
        --output "$response" \
        --form-string "chat_id=$TG_CHAT_ID" \
        --form "document=@$ZIP_PATH" \
        --form-string "caption=$caption" \
        "https://api.telegram.org/bot${TG_BOT_TOKEN}/sendDocument" 2>/dev/null &&
        python3 - "$response" <<'PY'
import json
import sys

try:
    with open(sys.argv[1]) as response:
        result = json.load(response)
except (OSError, ValueError):
    sys.exit(1)
sys.exit(0 if isinstance(result, dict) and result.get("ok") is True else 1)
PY
    then
        printf 'Telegram upload ok\n'
    else
        printf 'Telegram upload failed; CircleCI artifacts are retained.\n'
    fi
}

send_pixeldrain() {
    if [[ ! -f "$ZIP_PATH" ]]; then
        printf 'Pixeldrain upload skipped: ZIP not found at %s\n' "$ZIP_PATH"
        return 0
    fi

    if [[ -z ${PIXELDRAIN_API_KEY:-} ]]; then
        printf 'Pixeldrain API key not set, skipping fallback.\n'
        return 0
    fi

    printf 'Uploading to Pixeldrain\n'
    if curl -sS --max-time 300 -T "$ZIP_PATH" -u :"$PIXELDRAIN_API_KEY" https://pixeldrain.com/api/file/ 2>/dev/null; then
        printf '\n'
    else
        printf 'Pixeldrain upload failed; CircleCI artifacts are retained.\n'
    fi
}

send_telegram
send_pixeldrain
