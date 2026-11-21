#!/usr/bin/env python3
"""Replay the real legacy bus error path and camera flash deferred probe."""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

kernel = Path(sys.argv[1]).resolve()


def function(path, name):
    source = (kernel / path).read_text()
    match = re.search(r'^(?:static )?(?:int(?:32_t)?|struct msm_bus_device_node_registration\s*\*)\s*'
                      + name + r'\([^;{}]*\)\n\{.*?\n\}', source, re.M | re.S)
    assert match, name
    return match.group()


bus_path = 'drivers/soc/qcom/msm_bus/'
bus = (kernel / bus_path / 'msm_bus_of_adhoc.c').read_text()
parser = function(bus_path + 'msm_bus_of_adhoc.c', 'msm_bus_of_to_pdata')
probe = function(bus_path + 'msm_bus_fabric_adhoc.c', 'msm_bus_device_probe')
probe = probe[:probe.index('\n\tfor (i = 0;')] + '\n\treturn 0;\nexit_device_probe:\n\treturn ret;\n}'
clock_checks = ''
for context in ['DUAL_CTX', 'ACTIVE_CTX']:
    body = re.search(r'\t\tif \(IS_ERR_OR_NULL\(node_device->clk\[' + context +
                     r'\]\.clk\)\) \{.*?\n\t\t\}', bus, re.S).group()
    clock_checks += f'static int check_{context}(struct msm_bus_node_device_type *node_device) {{\n' + body + '\nreturn 0;\n}\n'
ahb = (kernel / 'drivers/media/platform/msm/camera_v2/common/cam_hw_ops.c').read_text()
ahb_failure = re.search(r'\tif \(!data.ahb_client\) \{.*?\n\t\}', ahb, re.S).group()
ahb_failure = 'static int check_ahb(void) { int rc = 0;\n' + ahb_failure + '\nreturn 0;\nerr5:\nreturn rc;\n}\n'

prefix = r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define EPROBE_DEFER 517
#define GFP_KERNEL 0
#define DUAL_CTX 0
#define ACTIVE_CTX 1
#define IS_ERR(p) ((uintptr_t)(p) >= (uintptr_t)-4095)
#define IS_ERR_OR_NULL(p) (!(p) || IS_ERR(p))
#define ERR_PTR(e) ((void *)(intptr_t)(e))
#define PTR_ERR(p) ((int)(intptr_t)(p))
#define dev_err(...) ((void)0)
#define dev_dbg(...) ((void)0)
#define pr_err(...) ((void)0)
#define pr_info(...) ((void)0)
#define CDBG(...) ((void)0)
#define MSM_BUS_ERR(...) ((void)0)
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
struct device_node { int unused; };
struct device { struct device_node *of_node; void *platform_data; };
struct platform_device { struct device dev; void *driver_data; };
static int refs, node_error, allocations;
static void *owned[64];
static struct device_node child;
static void *kzalloc(size_t size, int flags) {
    (void)flags;
    for (int i = 0; i < 64; i++) if (!owned[i]) {
        allocations++; return owned[i] = calloc(1, size);
    }
    abort();
}
static void kfree(void *p) {
    if (!p) return;
    for (int i = 0; i < 64; i++) if (owned[i] == p) {
        allocations--; free(p); owned[i] = NULL; return;
    }
    abort();
}
static void *devm_kzalloc(struct device *d, size_t size, int flags) { (void)d; return kzalloc(size, flags); }
static void devm_kfree(struct device *d, void *p) { (void)d; kfree(p); }
static struct device_node *of_node_get(struct device_node *n) { refs++; return n; }
static void of_node_put(struct device_node *n) { assert(n == &child && refs > 0); refs--; }
static int of_get_child_count(struct device_node *n) { (void)n; return 1; }
#define for_each_child_of_node(parent, node) \
    for ((node) = of_node_get(&child); (node); of_node_put(node), (node) = NULL)
struct node_info { unsigned num_connections, num_blist; };
struct msm_bus_node_device_type {
    struct node_info *node_info;
    void *fabdev;
    struct device_node *of_node;
    struct {void *clk;} clk[2];
};
struct msm_bus_device_node_registration { unsigned num_devices; struct msm_bus_node_device_type *info; };
static int get_bus_node_device_data(struct device_node *n, struct platform_device *p,
                                   struct msm_bus_node_device_type *d) {
    (void)n; (void)p; static struct node_info info;
    d->node_info = &info; return node_error;
}
static struct { unsigned ahb_client; } data;
'''

flash_prefix = r'''
#define FLASH_DRIVER_GPIO 1
#define FLASH_DRIVER_PMIC 2
#define MSM_CAMERA_FLASH_RELEASE 0
#define MSM_CAMERA_PLATFORM_DEVICE 0
#define V4L2_SUBDEV_FL_HAS_DEVNODE 4
#define MSM_CAMERA_SUBDEV_FLASH 1
#define MSM_SD_CLOSE_2ND_CATEGORY 0x20000
struct video_device { const void *fops; };
struct v4l2_subdev { const void *internal_ops; unsigned flags; char name[32];
    struct { unsigned function; const char *name; } entity;
    struct video_device *devnode; };
struct msm_sd_subdev { struct v4l2_subdev sd; int close_seq; };
struct msm_camera_cci_client { void *cci_subdev; unsigned cci_i2c_master; };
struct msm_flash_ctrl_t {
    struct platform_device *pdev;
    int flash_driver_type, flash_state, flash_device_type, cci_i2c_master;
    const void *flash_mutex;
    struct {struct device *dev; void *gpio_conf;} power_info;
    struct {const void *i2c_func_tbl; struct msm_camera_cci_client *cci_client;} flash_i2c_client;
    struct msm_sd_subdev msm_sd;
};
static const int msm_flash_mutex, msm_sensor_cci_func_tbl, msm_flash_subdev_ops;
static const int msm_flash_internal_ops, msm_flash_v4l2_subdev_fops;
static int sd_error;
static struct msm_flash_ctrl_t *last_ctrl;
static int msm_flash_get_dt_data(struct device_node *n, struct msm_flash_ctrl_t *f) {
    last_ctrl = f;
    assert(n); f->flash_driver_type = FLASH_DRIVER_GPIO;
    f->power_info.gpio_conf = kzalloc(1, 0); return 0;
}
static void platform_set_drvdata(struct platform_device *p, void *data) { p->driver_data = data; }
static void *msm_cci_get_subdev(void) { static int cci; return &cci; }
static void v4l2_subdev_init(struct v4l2_subdev *s, const void *ops) { (void)s; (void)ops; }
static void v4l2_set_subdevdata(struct v4l2_subdev *s, void *d) { (void)s; (void)d; }
static int media_entity_pads_init(void *entity, int n, void *pads) { (void)entity; (void)n; (void)pads; return 0; }
static void media_entity_cleanup(void *entity) { (void)entity; }
static int msm_sd_register(struct msm_sd_subdev *s) {
    if (sd_error) return sd_error;
    static struct video_device v; s->sd.devnode = &v; return 0;
}
static void msm_cam_copy_v4l2_subdev_fops(const void *ops) { (void)ops; }
static int msm_torch_create_classdev(struct platform_device *p, struct msm_flash_ctrl_t *f) { (void)p; (void)f; return 0; }
#define msm_subtorch_create_classdev msm_torch_create_classdev
'''
main = r'''
int main(int argc, char **argv) {
    struct platform_device p = {.dev.of_node = &child};
    assert(argc == 2);
    if (!strcmp(argv[1], "bus")) {
        const int errors[] = {-EPROBE_DEFER, -ENOMEM, -EINVAL, -ENXIO};
        for (unsigned i = 0; i < ARRAY_SIZE(errors); i++) {
            node_error = errors[i];
            assert(msm_bus_device_probe(&p) == node_error);
            assert(!allocations && !refs);
        }
        node_error = 0;
        struct msm_bus_device_node_registration *pd = msm_bus_of_to_pdata(&p);
        assert(!IS_ERR_OR_NULL(pd) && !refs);
        devm_kfree(&p.dev, pd->info); devm_kfree(&p.dev, pd);
        struct msm_bus_node_device_type node = {0};
        node.clk[DUAL_CTX].clk = ERR_PTR(-EPROBE_DEFER);
        assert(check_DUAL_CTX(&node) == -EPROBE_DEFER);
        node.clk[DUAL_CTX].clk = &child;
        node.clk[ACTIVE_CTX].clk = ERR_PTR(-EPROBE_DEFER);
        assert(check_ACTIVE_CTX(&node) == -EPROBE_DEFER);
        node.clk[ACTIVE_CTX].clk = ERR_PTR(-EINVAL);
        assert(check_ACTIVE_CTX(&node) == -EINVAL);
        assert(check_ahb() == -EPROBE_DEFER);
        data.ahb_client = 1; assert(check_ahb() == 0);
        puts("PASS: actual bus parser/probe preserves deferred and hard errors; camera waits for votes");
    } else {
        const int errors[] = {-EPROBE_DEFER, -ENOMEM, -EINVAL};
        for (unsigned i = 0; i < ARRAY_SIZE(errors); i++) {
            sd_error = errors[i];
            assert(msm_flash_platform_probe(&p) == sd_error);
            assert(!allocations && !p.driver_data);
        }
        sd_error = 0;
        assert(msm_flash_platform_probe(&p) == 0 && allocations == 3);
        assert(!!p.driver_data == EXPECT_PUBLISHED);
        struct msm_flash_ctrl_t *f = last_ctrl;
        assert(f->msm_sd.sd.devnode->fops == &msm_flash_v4l2_subdev_fops);
        kfree(f->flash_i2c_client.cci_client); kfree(f->power_info.gpio_conf); kfree(f);
        assert(!allocations);
        puts("PASS: actual flash deferred/failed registration unwinds and retry succeeds");
    }
}
'''
with tempfile.TemporaryDirectory(prefix='probe-deferral-') as tmp:
    failures = []
    for flash in ['msm_flash.c', 'msm_subflash.c']:
        path, binary = Path(tmp) / flash, Path(tmp) / flash.removesuffix('.c')
        path.write_text(f'#define EXPECT_PUBLISHED {int(flash == "msm_flash.c")}\n' +
                        prefix + parser + probe + clock_checks + ahb_failure + flash_prefix +
                        function('drivers/media/platform/msm/camera_v2/sensor/flash/' + flash,
                                 flash.removesuffix('.c') + '_platform_probe').replace(
                                     'msm_subflash', 'msm_flash') + main)
        subprocess.run(['gcc', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                        '-Wno-unused-variable', '-Wno-unused-function', str(path), '-o', str(binary)], check=True)
        for case in (['bus', 'flash'] if flash == 'msm_flash.c' else ['flash']):
            result = subprocess.run([str(binary), case])
            if result.returncode: failures.append((flash, case, result.returncode))
    assert not failures, failures

unchecked = []
for path in (kernel / 'drivers/media/platform/msm/camera_v2').rglob('*.c'):
    source = path.read_text()
    if re.search(r'^\s*msm_sd_register\(', source, re.M):
        unchecked.append(str(path.relative_to(kernel)))
    for call in re.finditer(r'^\s*(\w+) = msm_sd_register\([^;]+;', source, re.M):
        assert re.match(r'\s*if \(' + call[1] + r'(?: (?:<|!=) 0)?\)', source[call.end():]), path
assert not unchecked, unchecked
assert 'int __must_check msm_sd_register(' in (
    kernel / 'drivers/media/platform/msm/camera_v2/msm_sd.h').read_text()
print('PASS: no camera caller discards subdevice registration failure')
