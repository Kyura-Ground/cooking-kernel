#!/usr/bin/env python3
"""Catch qcacld vendor tables rejected by cfg80211 before wiphy registration."""
from pathlib import Path
import re
import sys

kernel = Path(sys.argv[1])
hdd = kernel / 'drivers/staging/qcacld-3.0/core/hdd'
missing = []
entries = 0
handlers = set()
feature_definitions = ''
paths = list(hdd.rglob('*')) + list((kernel / 'drivers/staging/qcacld-3.0/os_if').rglob('*'))
paths += [kernel / 'drivers/staging/qca-wifi-host-cmn/os_if/linux/scan/inc/wlan_cfg80211_scan.h']
for path in sorted(paths):
    if path.suffix not in {'.c', '.h'}:
        continue
    text = re.sub(r'/\*.*?\*/', '', path.read_text(), flags=re.S)
    text = text.replace('\\\n', '\n')
    feature_definitions += text + '\n'
    commands = list(re.finditer(r'\{[^{}]*\.(?:doit|dumpit)\s*=[^{}]*\}', text))
    assert len(commands) == len(re.findall(r'\.(?:doit|dumpit)\s*=', text)), \
        f'unparsed vendor command in {path}'
    for command in commands:
        body = command.group()
        assert '.info.vendor_id' in body and '.info.subcmd' in body, str(path)
        entries += 1
        handler = re.search(r'\.(?:doit|dumpit)\s*=\s*(\w+)', body).group(1)
        assert handler not in {'NULL', '0'}, f'unimplemented command {path}'
        handlers.add(handler)
        if 'vendor_command_policy(' in body:
            assert re.search(r'\.(?:doit|dumpit)\s*=\s*\w+\s*,', body), handler
        if not re.search(r'\.policy\s*=\s*(?!NULL\b|0\b)\w+|'
                         r'vendor_command_policy\(\s*(?!NULL\b|0\b)\w+', body):
            missing.append(handler)
assert entries, 'no qcacld vendor commands checked'
assert not missing, f'{len(missing)}/{entries} vendor commands have no policy: {missing[:5]}'
print(f'PASS: all {entries} qcacld vendor command definitions have cfg80211 policy metadata')

main = (hdd / 'src/wlan_hdd_cfg80211.c').read_text()
start = main.index('const struct wiphy_vendor_command hdd_wiphy_vendor_commands[]')
table = main[start:main.index('\n};', start)]
for macro in re.findall(r'^\s*([A-Z][A-Z_0-9]*COMMANDS)\s*$', table, re.M):
    assert re.search(r'^#define\s+' + macro + r'\b', feature_definitions, re.M), macro
assert 'COMMON_VENDOR_COMMANDS' not in table, 'unimplemented legacy command placeholders advertised'
assert 'wlan_hdd_vendor_abort_scan' in handlers, 'abort-scan registration was lost'
assert 'wlan_hdd_cfg80211_set_roam_events' in handlers, 'roam event registration was lost'
print('PASS: feature macro dependencies and legacy abort-scan/roam commands retained')
