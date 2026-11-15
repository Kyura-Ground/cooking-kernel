#!/usr/bin/env python3
"""Exercise real ZIP packaging and mocked Telegram; never build a kernel."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SHA = "0123456789abcdef0123456789abcdef01234567"
ANYKERNEL_SHA = "fafee4a00ff19ce41f1e62b9549eafe980402ba7"
PAYLOAD = {
    "Image.gz-dtb": b"kernel fixture",
    "sdm636-qrd-X00TD.dtb": b"dtb fixture",
    ".config": b"CONFIG_ARCH_SDM660=y\n",
    "System.map": b"symbol fixture",
    "Module.symvers": b"module symbol fixture",
    "modules.tar.gz": b"module archive fixture",
}

with tempfile.TemporaryDirectory(prefix="kernel54-package-") as directory:
    tmp = Path(directory)
    mockbin = tmp / "bin"
    mockbin.mkdir()
    curl = mockbin / "curl"
    curl.write_text('''#!/usr/bin/env python3
import json, os, pathlib, sys
args = sys.argv[1:]
assert args[-1] == 'https://api.telegram.org/bottest-only-token/sendDocument'
forms = [args[i+1] for i, arg in enumerate(args) if arg == '--form-string']
assert 'chat_id=@test_channel' in forms
document = args[args.index('--form')+1]
assert document.startswith('document=@') and pathlib.Path(document[10:]).is_file()
pathlib.Path(os.environ['CURL_CALL']).write_text(json.dumps(args))
mode = os.environ['CURL_MODE']
if mode == 'transport':
    print('do not leak test-only-token', file=sys.stderr)
    sys.exit(22)
body = '{invalid' if mode == 'invalid' else json.dumps({'ok': mode == 'ok'})
pathlib.Path(args[args.index('--output')+1]).write_text(body)
''')
    curl.chmod(0o755)
    java = mockbin / "java"
    java.write_text('''#!/usr/bin/env python3
import os, pathlib, shutil, sys
assert sys.argv[1] == '-jar'
assert pathlib.Path(sys.argv[2]).read_bytes() == b'signer fixture'
if os.environ.get('SIGNER_FAIL'):
    sys.exit(1)
shutil.copyfile(sys.argv[3], sys.argv[4])
''')
    java.chmod(0o755)
    tools = tmp / "installer tools"
    for filename in ("META-INF/com/google/android/update-binary", "tools/ak3-core.sh",
                     "tools/magiskboot", "tools/busybox", "LICENSE"):
        path = tools / "anykernel" / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("AnyKernel fixture: " + filename)
    (tools / "zipsigner.jar").write_bytes(b"signer fixture")

    def run(name, mode=None, missing_image=False, bad_revision=False, stale_zip=False,
            signer_failure=False, bad_installer_revision=False):
        case = tmp / name
        artifacts, logs = case / "artifacts with spaces", case / "logs"
        artifacts.mkdir(parents=True)
        logs.mkdir()
        for filename, data in PAYLOAD.items():
            (artifacts / filename).write_bytes(data)
        (artifacts / "vmlinux.gz").write_bytes(b"large symbols stay in CircleCI")
        (artifacts / "SHA256SUMS").write_text(
            hashlib.sha256(PAYLOAD["Image.gz-dtb"]).hexdigest() + "  Image.gz-dtb\n")
        (logs / "source-revision.txt").write_text("bad/ref" if bad_revision else SHA + "\n")
        (logs / "toolchain.txt").write_text("clang fixture\n")
        if missing_image:
            (artifacts / "Image.gz-dtb").unlink()
        archive = artifacts / f"X00TD-5.4-{SHA[:12]}.zip"
        installer = artifacts / f"X00TD-5.4-{SHA[:12]}-ak3-{ANYKERNEL_SHA[:12]}-recovery.zip"
        (tools / "anykernel-commit.txt").write_text(
            "bad/ref" if bad_installer_revision else ANYKERNEL_SHA + "\n")
        if stale_zip:
            with zipfile.ZipFile(archive, "w") as zipped:
                zipped.writestr("stale.txt", "must not survive")
        call = case / "curl.json"
        env = dict(PATH=str(mockbin) + os.pathsep + os.environ["PATH"],
                   HOME=str(tmp), CURL_CALL=str(call), CURL_MODE=mode or "ok")
        if mode:
            env.update(TG_BOT_TOKEN="test-only-token", TG_CHAT_ID="@test_channel")
        if signer_failure:
            env["SIGNER_FAIL"] = "1"
        result = subprocess.run(
            ["bash", str(ROOT / "scripts/package-5.4.sh"), str(artifacts), str(logs), str(tools)],
            env=env, capture_output=True, text=True)
        output = result.stdout + result.stderr
        assert "test-only-token" not in output, output
        assert (result.returncode == 0) == (not missing_image and not bad_revision
                                         and not signer_failure and not bad_installer_revision), output
        if missing_image or bad_revision or bad_installer_revision:
            assert not archive.exists() and not call.exists()
        elif signer_failure:
            assert archive.exists() and not installer.exists() and not call.exists()
        else:
            with zipfile.ZipFile(archive) as zipped:
                assert set(zipped.namelist()) == set(PAYLOAD) | {
                    "source-revision.txt", "toolchain.txt"}
                for filename, data in PAYLOAD.items():
                    assert zipped.read(filename) == data
                assert zipped.read("source-revision.txt").decode().strip() == SHA
                assert zipped.testzip() is None
            with zipfile.ZipFile(installer) as zipped:
                for filename in ("META-INF/com/google/android/update-binary",
                                 "tools/ak3-core.sh", "tools/magiskboot", "tools/busybox"):
                    assert filename in zipped.namelist()
                assert zipped.read("Image.gz-dtb") == PAYLOAD["Image.gz-dtb"]
                assert zipped.read("source-revision.txt").decode().strip() == SHA
                recipe = zipped.read("anykernel.sh").decode()
                assert zipped.read("anykernel-revision.txt").decode().strip() == ANYKERNEL_SHA
                assert SHA in recipe and "@KERNEL_SHA@" not in recipe
                assert "/by-name/boot" in recipe and "/by-name/recovery" in recipe
                assert "vmlinux.gz" not in zipped.namelist()
                assert not any(name.endswith(".ko") for name in zipped.namelist())
                assert zipped.testzip() is None
            subprocess.run(["sha256sum", "-c", "SHA256SUMS"], cwd=artifacts,
                           check=True, capture_output=True)
            assert (artifacts / "vmlinux.gz").is_file()
            assert call.exists() == bool(mode)
            if mode:
                args = json.loads(call.read_text())
                caption = next(arg for arg in args if arg.startswith("caption="))
                assert SHA in caption
                assert ANYKERNEL_SHA in caption
                assert hashlib.sha256(installer.read_bytes()).hexdigest() in caption
                assert any(str(installer) in arg for arg in args)
                assert ("Telegram upload ok" in output) == (mode == "ok"), output
                if mode != "ok":
                    assert "Telegram upload failed" in output, output
            else:
                assert "credentials not set" in output
        print(name + ": PASS")

    run("credentials-missing")
    run("telegram-ok", "ok")
    run("telegram-api-error", "error")
    run("telegram-invalid-json", "invalid")
    run("telegram-transport-error", "transport")
    run("missing-kernel", missing_image=True)
    run("invalid-revision", bad_revision=True)
    run("replace-stale-zip", stale_zip=True)
    run("signer-failure", "ok", signer_failure=True)
    run("invalid-installer-revision", bad_installer_revision=True)
