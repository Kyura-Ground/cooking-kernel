#!/usr/bin/env python3
"""Exercise the real recipe with simulated block I/O; never access a device."""
from pathlib import Path
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
RECIPE = (ROOT / "configs/anykernel-5.4.sh").read_text()
CORE = '''
AKHOME=$PWD
SPLITIMG=$AKHOME/split_img
mkdir -p "$SPLITIMG"
abort() { echo "$*" >&2; exit 1; }
ui_print() { :; }
reset_ak() { :; }
split_boot() {
    printf 'split:%s\\n' "${BLOCK##*/}" >> "$EVENTS"
    cp "$BLOCK" "$SPLITIMG/kernel"
}
flash_boot() {
    printf 'flash:%s\\n' "${BLOCK##*/}" >> "$EVENTS"
    [ "$FLASH_FAIL" != "${BLOCK##*/}" ] || abort "simulated flash failure"
    printf 'Linux version 5.4.new kernel\\n' > "$AKHOME/boot-new.img"
    if [ "$CORRUPT" = "${BLOCK##*/}" ]; then
        printf bad > "$BLOCK"
    else
        cp "$AKHOME/boot-new.img" "$BLOCK"
    fi
}
'''

with tempfile.TemporaryDirectory(prefix="kernel54-installer-") as directory:
    root = Path(directory)

    def run(name, boot="5.4.259", recovery="5.4.259", missing=False,
            flash_fail="", corrupt=""):
        case = root / name
        (case / "tools").mkdir(parents=True)
        partitions = case / "partitions"
        partitions.mkdir()
        for part, version in (("boot", boot), ("recovery", recovery)):
            if part == "recovery" and missing:
                continue
            (partitions / part).write_text("Linux version " + version + " fixture\n")
        (case / "tools/ak3-core.sh").write_text(CORE)
        # Regular fixture files stand in for the two real block-device paths.
        recipe = RECIPE.replace("/dev/block/bootdevice/by-name", str(partitions))
        recipe = recipe.replace("[ -b ", "[ -f ")
        (case / "anykernel.sh").write_text(recipe)
        events = case / "events"
        result = subprocess.run(
            ["bash", "anykernel.sh"], cwd=case, capture_output=True, text=True,
            env=dict(os.environ, EVENTS=str(events), FLASH_FAIL=flash_fail, CORRUPT=corrupt),
        )
        history = events.read_text().splitlines() if events.exists() else []
        writes = [event for event in history if event.startswith("flash:")]
        if name == "success":
            assert result.returncode == 0, result.stderr
            assert history == ["split:boot", "split:recovery", "flash:recovery",
                               "split:boot", "flash:boot"]
            assert (partitions / "boot").read_bytes() == (partitions / "recovery").read_bytes()
        else:
            assert result.returncode != 0, name
            if missing or boot.startswith("4.") or recovery.startswith("4."):
                assert not writes, history
            else:
                assert writes == ["flash:recovery"], history
            if corrupt:
                assert "readback failed" in result.stderr
        print(name + ": PASS")

    run("success")
    run("missing-recovery", missing=True)
    run("refuse-4.4-boot", boot="4.4.302")
    run("refuse-4.4-recovery", recovery="4.4.302")
    run("flash-failure", flash_fail="recovery")
    run("readback-failure", corrupt="recovery")
