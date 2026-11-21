#!/usr/bin/env python3
"""Compile real Venus early init and published-core probe failure paths."""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

kernel = Path(sys.argv[1]).resolve()
vidc = kernel / 'drivers/media/platform/msm/vidc_3x'
source = (vidc / 'venus_hfi.c').read_text()
v4l2 = (vidc / 'msm_v4l2_vidc.c').read_text()


def function(text, name):
    return re.search(r'^static (?:int|void) ' + name + r'\([^;{}]*\)\n\{.*?\n\}',
                     text, re.M | re.S).group()


probe = function(v4l2, 'msm_vidc_probe_vidc_device')
probe = ('static int run_probe(struct platform_device *pdev) {\n'
         'int rc = 0; struct msm_vidc_core *core = &core_storage;\n' +
         probe[probe.index('\t/* finish setting up the \'core\' */'):])
fixture = r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#define EPROBE_DEFER 517
#define EBADHANDLE 521
#define dprintk(...) ((void)0)
#define IS_ERR(p) ((uintptr_t)(p) >= (uintptr_t)-4095)
#define IS_ERR_OR_NULL(p) (!(p) || IS_ERR(p))
#define PTR_ERR(p) ((int)(intptr_t)(p))
#define ERR_PTR(e) ((void *)(intptr_t)(e))
struct device { int kobj; void *drvdata; };
struct platform_device { struct device dev; };
struct msm_vidc_platform_resources { struct platform_device *pdev; int pf_ver_tbl, pf_cap_tbl; };
struct venus_hfi_device { int lock; bool power_enabled; struct msm_vidc_platform_resources *res; };
static int regulator_error, clock_error, enable_regulator_error, enable_clock_error;
static int regulators, clocks, enabled_regs, enabled_clocks, enable_calls;
static void mutex_lock(int *m) { assert(*m == 1); }
static void mutex_unlock(int *m) { assert(*m == 1); }
static int __init_regulators(struct venus_hfi_device *d) {
    (void)d; assert(!regulators); if (!regulator_error) regulators = 1; return regulator_error;
}
static void __deinit_regulators(struct venus_hfi_device *d) { (void)d; assert(regulators && !enabled_regs); regulators = 0; }
static int __init_clocks(struct venus_hfi_device *d) {
    (void)d; assert(regulators && !clocks); if (!clock_error) clocks = 1; return clock_error;
}
static void __deinit_clocks(struct venus_hfi_device *d) { (void)d; assert(clocks && !enabled_clocks); clocks = 0; }
static int __enable_regulators(struct venus_hfi_device *d) {
    (void)d; assert(regulators && clocks); enable_calls++;
    if (!enable_regulator_error) enabled_regs = 1; return enable_regulator_error;
}
static int __disable_regulators(struct venus_hfi_device *d) { (void)d; assert(enabled_regs); enabled_regs = 0; return 0; }
static int __prepare_enable_clks(struct venus_hfi_device *d) {
    (void)d; assert(enabled_regs && clocks);
    if (!enable_clock_error) enabled_clocks = 1; return enable_clock_error;
}
static int __scale_clocks(struct venus_hfi_device *d, int rate, void *data, int size) {
    (void)d; (void)rate; (void)data; (void)size; return 0;
}
static void __venus_early_power_off(struct venus_hfi_device *d) {
    assert(d->power_enabled && enabled_regs && enabled_clocks);
    enabled_regs = enabled_clocks = 0; d->power_enabled = false;
}
''' + '\n'.join(function(source, n) for n in ['__early_init_resources',
    '__early_deinit_resources', '__venus_early_power_on', 'venus_hfi_core_early_init',
    'venus_hfi_core_early_release']) + r'''
#define CONFIG_DEBUG_FS 1
#define MSM_VIDC_CORES_MAX 1
#define MSM_VIDC_ENCODER 1
#define MSM_VIDC_DECODER 0
struct hfi_device { void *hfi_device_data; };
struct video_device { struct device dev; };
struct msm_vidc_core {
    int list, hfi_type, id, v4l2_dev;
    struct msm_vidc_platform_resources resources;
    struct hfi_device *device;
    void *debugfs_root;
    struct {struct video_device vdev;} vdev[2];
};
static struct msm_vidc_core core_storage;
static struct {int lock, num_cores, cores, platform_version, capability_version; void *debugfs_root;} driver_storage;
static typeof(driver_storage) *vidc_driver = &driver_storage;
static struct venus_hfi_device venus;
static struct hfi_device hfi = {.hfi_device_data = &venus};
static int handle_cmd_response, dev_attr_link_name, msm_vidc_core_attr_group;
static int parsed, freed, hfi_released, debugfs_nodes, hfi_error, populate_error;
static void list_add_tail(int *entry, int *head) { assert(!*entry && !*head); *entry = *head = 1; }
static void list_del(int *entry) { assert(*entry && vidc_driver->cores); *entry = vidc_driver->cores = 0; }
static struct hfi_device *vidc_hfi_initialize(int type, int id,
        struct msm_vidc_platform_resources *res, void *callback) {
    (void)type; (void)id; (void)res; (void)callback;
    return hfi_error ? ERR_PTR(hfi_error) : &hfi;
}
static void vidc_hfi_deinitialize(int type, struct hfi_device *d) {
    (void)type; assert(d == &hfi && !vidc_driver->cores && !vidc_driver->num_cores);
    assert(!regulators && !clocks && !venus.power_enabled); hfi_released++;
}
static void *msm_vidc_debugfs_init_core(struct msm_vidc_core *c, void *parent) {
    (void)c; (void)parent; debugfs_nodes++; return (void *)1;
}
static void debugfs_remove_recursive(void *root) { assert(root && debugfs_nodes); debugfs_nodes--; }
static int msm_vidc_read_efuse_version(struct platform_device *p, int table, const char *name) {
    (void)p; (void)table; (void)name; return 0;
}
#define call_hfi_op(object, op, data) venus_hfi_##op(data)
static int msm_vidc_dt_match[1];
static int of_platform_populate(void *node, void *match, void *lookup, struct device *dev) {
    (void)node; (void)match; (void)lookup; (void)dev; return populate_error;
}
static void device_remove_file(struct device *d, void *attr) { (void)d; (void)attr; }
static void video_unregister_device(struct video_device *v) { (void)v; }
static void v4l2_device_unregister(int *v) { (void)v; }
static void sysfs_remove_group(int *k, void *group) { (void)k; (void)group; }
static void msm_vidc_free_platform_resources(struct msm_vidc_platform_resources *res) { (void)res; assert(parsed); parsed = 0; }
static void dev_set_drvdata(struct device *d, void *data) { d->drvdata = data; }
static void kfree(void *c) { assert(c == &core_storage && !parsed && !vidc_driver->cores && !debugfs_nodes); freed++; }
''' + probe.replace('pdev->dev.of_node', 'NULL') + r'''
static void reset(struct platform_device *p) {
    assert(!regulators && !clocks && !enabled_regs && !enabled_clocks && !venus.power_enabled);
    regulator_error = clock_error = enable_regulator_error = enable_clock_error = 0;
    enable_calls = freed = hfi_released = debugfs_nodes = hfi_error = populate_error = 0;
    core_storage = (struct msm_vidc_core){.resources.pdev = p};
    driver_storage = (typeof(driver_storage)){.lock = 1};
    venus = (struct venus_hfi_device){.lock = 1, .res = &core_storage.resources};
    p->dev.drvdata = &core_storage; parsed = 1;
}
int main(void) {
    struct platform_device p = {0};
    reset(&p); regulator_error = -EPROBE_DEFER;
    assert(run_probe(&p) == -EPROBE_DEFER && !enable_calls);
    assert(!p.dev.drvdata && freed == 1 && hfi_released == 1 && !vidc_driver->num_cores);
    for (int failure = 0; failure < 5; failure++) {
        reset(&p);
        if (failure == 0) regulator_error = -ENOMEM;
        if (failure == 1) clock_error = -EPROBE_DEFER;
        if (failure == 2) enable_regulator_error = -EIO;
        if (failure == 3) enable_clock_error = -EIO;
        if (failure == 4) populate_error = -EINVAL;
        int expected = failure == 0 ? -ENOMEM : failure == 1 ? -EPROBE_DEFER : failure == 4 ? -EINVAL : -EIO;
        assert(run_probe(&p) == expected && !p.dev.drvdata && freed == 1);
        assert(!vidc_driver->num_cores && !vidc_driver->cores && !debugfs_nodes);
    }
    reset(&p); hfi_error = -EPROBE_DEFER;
    assert(run_probe(&p) == -EPROBE_DEFER && !vidc_driver->num_cores && !enable_calls);
    reset(&p);
    assert(run_probe(&p) == 0 && vidc_driver->num_cores == 1 && vidc_driver->cores);
    assert(!regulators && !clocks && !venus.power_enabled && !freed);
    puts("PASS: actual Venus regulator/clock deferral, power failure cleanup, core rollback and retry");
}
'''
with tempfile.TemporaryDirectory(prefix='venus-early-init-') as tmp:
    path, binary = Path(tmp) / 'venus.c', Path(tmp) / 'venus'
    path.write_text(fixture)
    subprocess.run(['gcc', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                    '-Wno-unused-parameter', '-Wno-unused-label', '-Wno-unused-function',
                    '-Wno-misleading-indentation',
                    str(path), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)

delete = re.search(r'void venus_hfi_delete_device\(.*?\n\}', source, re.S).group()
assert 'devm_iounmap(' in delete and not re.search(r'\biounmap\(', delete)
assert 'devm_ioremap' in source
assert re.search(r'Failed to create attributes[^;]*;\s*goto err_free_resources;', v4l2)
print('PASS: managed mapping is unmapped once and parsed resources unwind on probe failure')
