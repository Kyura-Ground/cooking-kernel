#!/usr/bin/env python3
"""Exercise Qualcomm SoundWire init failures and its real Kbuild selection."""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

kernel = Path(sys.argv[1]).resolve()
audio = kernel / 'techpack/audio'
source = (audio / 'soc/soundwire.c').read_text()
init = re.search(r'static int __init soundwire_init\(void\)\n\{.*?\n\}',
                 source, re.S).group()
fixture = r'''
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#define __init
struct bus_type { int unused; } soundwire_type;
struct device { int unused; } soundwire_dev;
static int bus_error, device_error, registered, devices, unregistered;
static int bus_register(struct bus_type *bus) {
    assert(bus == &soundwire_type && !registered);
    if (!bus_error) registered = 1;
    return bus_error;
}
static int device_register(struct device *dev) {
    assert(dev == &soundwire_dev && registered);
    devices++;
    return device_error;
}
static void bus_unregister(struct bus_type *bus) {
    assert(bus == &soundwire_type && registered);
    registered = 0;
    unregistered++;
}
''' + init + r'''
int main(void) {
    bus_error = -EEXIST;
    assert(soundwire_init() == -EEXIST);
    assert(!registered && !devices && !unregistered);
    bus_error = 0;
    device_error = -EIO;
    assert(soundwire_init() == -EIO);
    assert(!registered && devices == 1 && unregistered == 1);
    device_error = 0;
    assert(soundwire_init() == 0);
    assert(registered && devices == 2 && unregistered == 1);
    puts("PASS: SoundWire bus failure, device failure unwind, and successful init");
}
'''
with tempfile.TemporaryDirectory(prefix='soundwire-legacy-') as tmp:
    path = Path(tmp) / 'soundwire.c'
    binary = Path(tmp) / 'soundwire'
    path.write_text(fixture)
    subprocess.run(['gcc', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                    str(path), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)

kbuild = f'''
srctree := {kernel}
include {audio}/soc/Kbuild
include {kernel}/drivers/soundwire/Makefile
.PHONY: check
check:
\t@echo vendor_objects=$(SWR_OBJS)
\t@echo vendor_y=$(filter swr_dlkm.o,$(obj-y))
\t@echo vendor_m=$(filter swr_dlkm.o,$(obj-m))
\t@echo upstream_y=$(filter soundwire-bus.o,$(obj-y))
'''
for vendor, upstream in [('y', ''), ('m', ''), ('', 'y')]:
    result = subprocess.run(
        ['make', '-s', '-f', '-', 'check', f'CONFIG_QCOM_SOUNDWIRE={vendor}',
         f'CONFIG_SOUNDWIRE={upstream}'], input=kbuild, text=True,
        capture_output=True, check=True,
    )
    values = dict(line.split('=', 1) for line in result.stdout.splitlines())
    assert ('soundwire.o' in values['vendor_objects'].split()) == bool(vendor), values
    assert bool(values['vendor_y']) == (vendor == 'y'), values
    assert bool(values['vendor_m']) == (vendor == 'm'), values
    assert bool(values['upstream_y']) == (upstream == 'y'), values
assert re.search(r'^config QCOM_SOUNDWIRE$', (audio / 'Kconfig').read_text(), re.M)
for path in (audio / 'config').glob('*'):
    if path.is_file():
        assert not re.search(r'\bCONFIG_SOUNDWIRE\b', path.read_text()), path
print('PASS: independent upstream/Qualcomm Kbuild selection and external module configs')
