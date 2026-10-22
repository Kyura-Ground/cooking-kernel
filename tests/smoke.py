#!/usr/bin/env python3
"""Offline builder integration checks. Compilation/toolchains are mocked.

Exercises real Git checkout, config merging, Bash fixups, ZIP packaging and
failure propagation. Does not build a kernel or validate hardware.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
KERNEL = ROOT.parent / "android_kernel_asus_sdm660"


def write(path, text, executable=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    if executable:
        path.chmod(0o755)


def git_repo(path, files, branch="main"):
    path.mkdir()
    for name, text, executable in files:
        write(path / name, text, executable)
    subprocess.run(["git", "init", "-q", "-b", branch, str(path)], check=True)
    subprocess.run(["git", "-C", str(path), "add", "."], check=True)
    subprocess.run(["git", "-C", str(path), "-c", "user.name=Fixture", "-c",
                    "user.email=fixture@example.invalid", "-c", "commit.gpgsign=false",
                    "commit", "-qm", "Fixture"], check=True)
    return subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()


with tempfile.TemporaryDirectory(prefix="cooking44-test-") as directory:
    tmp = Path(directory)
    builder = tmp / "builder"
    builder.mkdir()
    shutil.copy2(ROOT / "build.sh", builder / "build.sh")
    shutil.copytree(ROOT / "configs", builder / "configs")
    # Use the actual kernel helpers where available, otherwise fixture helpers
    # model only their CLI for running this test in the standalone builder repo.
    config_helper = '''#!/bin/bash
set -eu
file=$2
printf 'CONFIG_LOCALVERSION="%s"\n' "$5" >> "$file"
'''
    merge_helper = '''#!/bin/bash
set -eu
cat "$5" >> "$4"
'''
    if KERNEL.is_dir():
        config_helper = (KERNEL / "scripts/config").read_text()
        merge_helper = (KERNEL / "scripts/kconfig/merge_config.sh").read_text()
    kernel = tmp / "kernel"
    kernel_sha = git_repo(kernel, [
        ("Makefile", "VERSION = 4\nPATCHLEVEL = 4\nSUBLEVEL = 302\n", False),
        ("arch/arm64/configs/X00TD_defconfig", "CONFIG_LOCALVERSION=\"-lineageos\"\n", False),
        ("drivers/Kconfig", 'menu "Drivers"\nendmenu\n', False),
        ("drivers/Makefile", "# fixture\n", False),
        ("scripts/config", config_helper, True),
        ("scripts/kconfig/merge_config.sh", merge_helper, True),
    ], "lineage-20")
    ksu = tmp / "ksu"
    ksu_sha = git_repo(ksu, [("kernel/Kconfig", "config KSU\n    tristate\n", False)])
    ak = tmp / "ak"
    git_repo(ak, [("anykernel.sh", "device.name1=X00TD\n", False),
                  ("META-INF/com/google/android/update-binary", "fixture installer\n", True)], "4.4")
    tool_repos = []
    for name, prefix, commands in [
        ("gcc64", "aarch64-linux-android-", ["gcc", "ld", "elfedit"]),
        ("gcc32", "arm-linux-androideabi-", ["gcc", "ld"]),
    ]:
        path = tmp / name
        sha = git_repo(path, [("bin/"+prefix+c, "#!/bin/sh\necho fixture-toolchain\n", True)
                              for c in commands])
        tool_repos.append((path, sha))
    clang = tmp / "clang"
    write(clang / "bin/clang", "#!/bin/sh\necho fixture-clang-14\n", True)
    archive = tmp / "clang.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(clang / "bin", arcname="bin")
    mockbin = tmp / "mockbin"
    mockbin.mkdir()
    for command in ("bc", "bison", "flex", "gcc", "g++"):
        write(mockbin / command, "#!/bin/sh\nexit 0\n", True)
    write(mockbin / "java", '''#!/usr/bin/env python3
import pathlib,shutil,sys
assert sys.argv[1]=='-jar' and pathlib.Path(sys.argv[2]).is_file()
shutil.copy2(sys.argv[3],sys.argv[4])
''', True)
    write(mockbin / "make", '''#!/usr/bin/env python3
import json,os,pathlib,sys
a=sys.argv[1:];d=pathlib.Path(a[a.index('-C')+1]);o=pathlib.Path(next(x[2:] for x in a if x.startswith('O=')))
assert 'CROSS_COMPILE=aarch64-linux-android-' in a
assert 'CROSS_COMPILE_ARM32=arm-linux-androideabi-' in a
assert 'CLANG_TRIPLE=aarch64-linux-gnu-' in a and 'LLVM_IAS=0' in a
assert 'CC=clang' in a
with open(os.environ['CALL_LOG'],'a') as f:f.write(json.dumps(a)+'\\n')
o.mkdir(parents=True,exist_ok=True)
if 'X00TD_defconfig' in a:(o/'.config').write_text('CONFIG_LOCALVERSION="-lineageos"\\n')
elif 'olddefconfig' in a:
    if os.environ.get('DROP_KSU')=='1':
        (o/'.config').write_text((o/'.config').read_text().replace('CONFIG_KSU=y',''))
elif 'Image.gz-dtb' in a:
    if os.environ.get('FAIL_BUILD')=='1':sys.exit(23)
    image=o/'arch/arm64/boot/Image.gz-dtb';image.parent.mkdir(parents=True,exist_ok=True)
    image.write_bytes(b'' if os.environ.get('EMPTY_IMAGE')=='1' else b'fixture-image')
elif 'kernelversion' in a:print('4.4.302')
else:raise AssertionError(a)
''', True)
    # Use a minimal environment to ensure tests never invoke optional uploads.
    env = dict(PATH=str(mockbin)+os.pathsep+os.environ["PATH"], HOME=os.environ["HOME"],
               KERNEL_REPO=str(kernel), KERNEL_BRANCH="lineage-20", DEFCONFIG="X00TD_defconfig",
               GCC_64_REPO=str(tool_repos[0][0]), GCC_64_REF=tool_repos[0][1],
               GCC_32_REPO=str(tool_repos[1][0]), GCC_32_REF=tool_repos[1][1],
               CLANG_URL=archive.as_uri(), KSU_REPO=str(ksu), KSU_REF=ksu_sha,
               ANYKERNEL_REPO=str(ak), ANYKERNEL_BRANCH="4.4", SIGN_ZIP="0", USE_CCACHE="0", JOBS="2")

    def run(name, overrides, succeeds, expected_error=None):
        work = tmp / name
        if overrides.get("SIGN_ZIP") == "true":
            write(work / ".toolchains/zipsigner-3.0-dexed.jar", "fixture signer")
        e = dict(env, WORK_DIR=str(work), BUILD_KSU="true", CALL_LOG=str(tmp / (name+"-calls.jsonl")))
        e.update(overrides)
        result = subprocess.run(["bash", str(builder / "build.sh")], env=e, text=True, capture_output=True)
        if (result.returncode == 0) != succeeds:
            raise AssertionError(name+"\n"+result.stdout+result.stderr)
        if expected_error:
            assert expected_error in result.stdout+result.stderr, result.stdout+result.stderr
        if succeeds:
            zips = list((work / "out-zip").glob("*.zip"))
            assert len(zips) == 1
            if overrides.get("SIGN_ZIP") == "true":
                assert zips[0].name.endswith("-signed.zip")
            with zipfile.ZipFile(zips[0]) as z:
                assert z.read("Image.gz-dtb") == b"fixture-image"
                assert not any(n.startswith(".git/") for n in z.namelist())
            assert kernel_sha in (work / "out-zip/build-manifest.txt").read_text()
            config = (work / "out-zip/kernel.config").read_text()
            if overrides.get("BUILD_KSU") == "false":
                assert "CONFIG_KSU=y" not in config and not (work / "kernel-src/KernelSU").exists()
            else:
                assert "CONFIG_KSU=y" in config and "CONFIG_KSU_TAMPER_SYSCALL_TABLE=y" in config
                assert (work / "kernel-src/drivers/kernelsu").resolve() == work / "kernel-src/KernelSU/kernel"
        else:
            assert not list((work / "out-zip").glob("*.zip"))
            assert list((work / "logs").glob("build_*.log"))
        print(name+": PASS")

    run("ksu", {}, True)
    run("vanilla", {"BUILD_KSU": "false"}, True)
    run("signed-ksu", {"SIGN_ZIP": "true"}, True)
    run("compile-failure", {"FAIL_BUILD": "1"}, False)
    run("empty-image", {"EMPTY_IMAGE": "1"}, False, "Image.gz-dtb is missing or empty")
    run("missing-ksu-option", {"DROP_KSU": "1"}, False, "CONFIG_KSU did not survive")
    run("unsupported-lto", {"LTO": "1"}, False, "does not enable LTO")
    run("unsupported-nomount", {"BUILD_NOMOUNT": "1"}, False, "NoMount is not configured")
