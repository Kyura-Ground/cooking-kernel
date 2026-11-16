#!/usr/bin/env python3
"""Check the live SDM660 binding and exercise the actual btpower parser in CI."""

from pathlib import Path
import json
import re
import subprocess
import sys
import tempfile

kernel = Path(sys.argv[1])
source = (kernel / 'drivers/bluetooth/btpower.c').read_text()
dts = (kernel / 'arch/arm64/boot/dts/vendor/qcom/sdm660.dtsi').read_text()
node = re.search(r'bluetooth: bt_wcn3990 \{(.*?)\n\s*};', dts, re.S).group(1)
compatible = re.search(r'compatible = "([^"]+)";', node).group(1)
assert compatible == 'qca,wcn3990'
assert re.search(r'\.compatible\s*=\s*"qca,wcn3990",\s*'
                 r'\.data\s*=\s*&bt_vreg_info_wcn3990_legacy', source), \
    'SDM660 Bluetooth power node has no driver match'
assert 'if (!bt_power_pdata || !probe_finished)' in source, \
    'ioctl can run before the Bluetooth power probe finishes'
assert source.index('if (!bt_power_pdata || !probe_finished)') < source.index('switch (cmd)')
assert 'probe_finished = true;' in source and 'probe_finished = false;' in source

rails = ['qca,bt-vdd-core', 'qca,bt-vdd-pa', 'qca,bt-vdd-ldo', 'qca,bt-chip-pwd']
expected = [(1800000, 1900000, 1), (1304000, 1370000, 1),
            (3312000, 3400000, 1), (3600000, 3600000, 0)]
properties = []
for name, raw in re.findall(r'([\w,-]+)\s*=\s*<([^>]+)>;', node):
    if name.endswith('-supply'):
        properties.append((name, [1]))
    elif name.endswith(('-voltage-level', '-current-level')):
        properties.append((name, [int(v) for v in raw.split()]))
for name, values in zip(rails, expected):
    props = dict(properties)
    assert props[name + '-voltage-level'] == list(values[:2])
    assert props.get(name + '-current-level', [0]) == [values[2]]
print('PASS: SDM660 WCN3990 driver match, supply properties and pre-probe ioctl guard')
if '--check-only' in sys.argv:
    sys.exit(0)


def function(name, signature='static int'):
    start = re.search(re.escape(signature + ' ' + name) + r'\([^;]*?\)\n\{',
                      source, re.S).start()
    end = source.index('\n}', start) + 2
    return source[start:end]


header = (kernel / 'include/linux/btpower.h').read_text().replace('#include <linux/types.h>', '')
# Use the real match table and regulator definitions, not a parallel test table.
tables = source[source.index('#define PWR_SRC_NOT_AVAILABLE'):source.index('static int bt_power_vreg_set(')]
prop_c = ',\n'.join('{%s, {%s}, %d}' % (
    json.dumps(name), ','.join(str(int.from_bytes(v.to_bytes(4, 'big'), 'little')) + 'U' for v in words),
    4 * len(words)) for name, words in properties)
fixture = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
#include <arpa/inet.h>
typedef uint32_t u32;
typedef uint32_t __be32;
typedef uintptr_t resource_size_t;
#define __iomem
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
#define IS_ERR(p) ((intptr_t)(p) < 0)
#define PTR_ERR(p) ((int)(intptr_t)(p))
#define pr_debug(...) ((void)0)
#define pr_info(...) ((void)0)
#define pr_warn(...) ((void)0)
#define pr_err(...) ((void)0)
#define MAX_PROP_SIZE 32
#define EPROBE_DEFER 517
struct device_node { const char *compatible; };
struct device { struct device_node *of_node; };
struct platform_device { struct device dev; };
struct regulator { int id; };
struct of_device_id { const char *compatible; const void *data; };
struct property { const char *name; __be32 values[4]; int len; };
'''
fixture += header + tables
fixture += '\nstatic struct property props[] = {\n' + prop_c + ',\n' + r'''
    {"qcom,bt-vdd-io-supply", {1}, 4},
    {"qcom,bt-vdd-io-config", {0}, 16}
};
'''
fixture += r'''
static struct regulator regs[4];
static struct bluetooth_power_platform_data pdata, *bt_power_pdata = &pdata;
static int bt_power_src_status[BT_POWER_SRC_SIZE];
static int gets, put_count, fail_get, current_error, order[8], count;
static bool probe_finished;
static struct property *of_find_property(struct device_node *np, const char *name, int *len) {
    assert(np);
    for (size_t i = 0; i < ARRAY_SIZE(props); i++) {
        if (!strcmp(props[i].name, name)) {
            if (len) *len = props[i].len;
            return &props[i];
        }
    }
    return NULL;
}
static const __be32 *of_get_property(struct device_node *np, const char *name, int *len) {
    struct property *p = of_find_property(np, name, len);
    return p ? p->values : NULL;
}
static struct device_node *of_parse_phandle(struct device_node *np, const char *name, int index) {
    assert(index == 0);
    return of_find_property(np, name, NULL) ? np : NULL;
}
static bool of_device_is_compatible(struct device_node *np, const char *name) {
    return !strcmp(np->compatible, name);
}
static const void *of_device_get_match_data(struct device *dev) {
    for (size_t i = 0; i < ARRAY_SIZE(bt_power_match_table) - 1; i++)
        if (of_device_is_compatible(dev->of_node, bt_power_match_table[i].compatible))
            return bt_power_match_table[i].data;
    return NULL;
}
static u32 be32_to_cpup(const __be32 *p) { return ntohl(*p); }
static int of_property_read_u32(struct device_node *np, const char *name, u32 *value) {
    if (current_error) return current_error;
    const __be32 *p = of_get_property(np, name, NULL);
    if (!p) return -EINVAL;
    *value = be32_to_cpup(p);
    return 0;
}
static struct regulator *regulator_get(struct device *dev, const char *name) {
    assert(dev && (strstr(name, "qca,bt-") || strstr(name, "qcom,bt-")));
    if (++gets == fail_get) return (void *)(intptr_t)-517;
    return &regs[gets - 1];
}
static void regulator_put(struct regulator *reg) { assert(reg); put_count++; }
static int regulator_get_voltage(struct regulator *reg) { assert(reg); return 1; }
static int bt_vreg_enable(struct bt_power_vreg_data *vreg) {
    order[count++] = vreg - bt_power_pdata->vreg_info;
    vreg->is_enabled = true;
    return 0;
}
static int bt_vreg_disable(struct bt_power_vreg_data *vreg) {
    order[count++] = vreg - bt_power_pdata->vreg_info;
    vreg->is_enabled = false;
    return 0;
}
static int bt_vreg_enable_retention(struct bt_power_vreg_data *vreg) {
    assert(!vreg->is_retention_supp);
    return 0;
}
'''
fixture += function('bt_power_vreg_put', 'static void') + '\n'
fixture += function('btpower_register_slimdev', 'int') + '\n'
fixture += '\n'.join(function(name) for name in (
    'bt_dt_parse_vreg_info', 'bt_power_vreg_get', 'bt_power_vreg_set'))
fixture += r'''
int main(void) {
    struct device_node node = {"qca,wcn3990"};
    struct platform_device pdev = {{&node}};
    assert(btpower_register_slimdev(NULL) == -EINVAL);
    bt_power_pdata = NULL;
    assert(btpower_register_slimdev(&pdev.dev) == -EPROBE_DEFER);
    bt_power_pdata = &pdata;
    assert(btpower_register_slimdev(&pdev.dev) == -EPROBE_DEFER);
    probe_finished = true;
    assert(btpower_register_slimdev(&pdev.dev) == 0 && pdata.slim_dev == &pdev.dev);
    const char *names[] = {"qca,bt-vdd-core", "qca,bt-vdd-pa", "qca,bt-vdd-ldo", "qca,bt-chip-pwd"};
    const u32 volts[][3] = {{1800000,1900000,1}, {1304000,1370000,1},
                           {3312000,3400000,1}, {3600000,3600000,0}};
    assert(bt_power_vreg_get(&pdev) == 0 && pdata.num_vregs == 4 && gets == 4);
    for (int i = 0; i < 4; i++) {
        struct bt_power_vreg_data *v = &pdata.vreg_info[i];
        assert(!strcmp(v->name, names[i]));
        assert(v->min_vol == volts[i][0] && v->max_vol == volts[i][1]);
        assert(v->load_curr == volts[i][2] && !v->is_retention_supp);
    }
    bt_power_vreg_put();
    assert(put_count == 4);
    bt_power_vreg_put();
    assert(put_count == 4);
    gets = put_count = 0;
    fail_get = 3;
    assert(bt_power_vreg_get(&pdev) == -517 && gets == 3 && put_count == 2);
    for (int i = 0; i < 4; i++) assert(!pdata.vreg_info[i].reg);
    gets = put_count = fail_get = 0;
    assert(bt_power_vreg_get(&pdev) == 0 && gets == 4);
    assert(bt_power_vreg_set(BT_POWER_ENABLE) == 0);
    assert(bt_power_vreg_set(BT_POWER_RETENTION) == 0);
    assert(bt_power_vreg_set(BT_POWER_DISABLE) == 0 && count == 8);
    for (int i = 0; i < 4; i++) assert(order[i] == i && order[i + 4] == 3 - i);
    bt_power_vreg_put();
    struct property *voltage = of_find_property(&node, "qca,bt-vdd-core-voltage-level", NULL);
    struct property *current = of_find_property(&node, "qca,bt-vdd-core-current-level", NULL);
    struct bt_power_vreg_data v = {.name = names[0]};
    gets = 0;
    for (int len = 0; len <= 12; len += 4) {
        if (len == 8) continue;
        voltage->len = len;
        assert(bt_dt_parse_vreg_info(&pdev.dev, &v) == -EINVAL && gets == 0);
    }
    voltage->len = 8; voltage->values[0] = htonl(2000000);
    assert(bt_dt_parse_vreg_info(&pdev.dev, &v) == -EINVAL && gets == 0);
    voltage->values[0] = 0;
    assert(bt_dt_parse_vreg_info(&pdev.dev, &v) == -EINVAL && gets == 0);
    voltage->values[0] = htonl(1800000);
    for (int len = 0; len <= 8; len += 8) {
        current->len = len;
        assert(bt_dt_parse_vreg_info(&pdev.dev, &v) == -EINVAL && gets == 0);
    }
    current->len = 4; current_error = -EIO;
    assert(bt_dt_parse_vreg_info(&pdev.dev, &v) == -EIO && gets == 0);
    current_error = 0;
    assert(bt_dt_parse_vreg_info(&pdev.dev, &v) == 0 && gets == 1);
    regulator_put(v.reg);
    node.compatible = "qcom,wcn3990";
    struct property *config = of_find_property(&node, "qcom,bt-vdd-io-config", NULL);
    const u32 modern[] = {1700000, 1900000, 10, 1};
    for (int i = 0; i < 4; i++) config->values[i] = htonl(modern[i]);
    v = (struct bt_power_vreg_data){.name = "qcom,bt-vdd-io"};
    gets = 0;
    assert(bt_dt_parse_vreg_info(&pdev.dev, &v) == 0 && gets == 1);
    assert(v.min_vol == modern[0] && v.max_vol == modern[1]);
    assert(v.load_curr == modern[2] && v.is_retention_supp);
    regulator_put(v.reg);
    puts("PASS: real WCN3990 parser, four rails, reverse shutdown, probe retry and malformed properties");
}
'''
with tempfile.TemporaryDirectory() as tmp:
    path = Path(tmp) / 'btpower.c'
    binary = Path(tmp) / 'btpower'
    path.write_text(fixture)
    subprocess.run(['gcc', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                    str(path), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
