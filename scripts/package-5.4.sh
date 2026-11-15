#!/usr/bin/env bash
set -Eeuo pipefail

ARTIFACT_DIR=$(cd -- "$1" && pwd)
LOG_DIR=$(cd -- "$2" && pwd)
KERNEL_SHA=$(cat "$LOG_DIR/source-revision.txt")
[[ $KERNEL_SHA =~ ^[0-9a-f]{40}$ ]] || {
    printf 'Invalid kernel source revision\n' >&2
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

if [[ -z ${TG_BOT_TOKEN:-} || -z ${TG_CHAT_ID:-} ]]; then
    printf 'Telegram credentials not set, skipping upload.\n'
    exit 0
fi
if (( $(stat -c %s "$ZIP_PATH") > 50000000 )); then
    printf 'ZIP exceeds Telegram bot upload limit; CircleCI artifacts are retained.\n'
    exit 0
fi

ZIP_SHA=$(sha256sum "$ZIP_PATH" | cut -d' ' -f1)
CAPTION="X00TD Linux 5.4 build
Kernel commit: $KERNEL_SHA
SHA256: $ZIP_SHA"
RESPONSE=$(mktemp)
trap 'rm -f -- "$RESPONSE"' EXIT
printf 'Uploading ZIP to Telegram\n'
if curl --silent --fail --max-time 300 \
    --output "$RESPONSE" \
    --form-string "chat_id=$TG_CHAT_ID" \
    --form "document=@$ZIP_PATH" \
    --form-string "caption=$CAPTION" \
    "https://api.telegram.org/bot${TG_BOT_TOKEN}/sendDocument" 2>/dev/null &&
    python3 - "$RESPONSE" <<'PY'
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
