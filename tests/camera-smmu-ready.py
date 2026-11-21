#!/usr/bin/env python3
"""Replay JPEG init against actual partially populated camera SMMU lookup."""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

kernel = Path(sys.argv[1]).resolve()
camera = kernel / 'drivers/media/platform/msm/camera_v2'
smmu = (camera / 'common/cam_smmu_api.c').read_text()
jpeg = (camera / 'jpeg_10/msm_jpeg_sync.c').read_text()


def function(source, name):
    return re.search(r'^(?:static )?int ' + name + r'\([^;{}]*\)\n\{.*?\n\}',
                     source, re.M | re.S).group()


fixture = r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define EPROBE_DEFER 517
#define HANDLE_INIT (-1)
#define IS_ERR(p) ((uintptr_t)(p) >= (uintptr_t)-4095)
#define IS_ERR_OR_NULL(p) (!(p) || IS_ERR(p))
#define PTR_ERR(p) ((int)(intptr_t)(p))
#define ERR_PTR(e) ((void *)(intptr_t)(e))
#define pr_err(...) ((void)0)
#define CDBG(...) ((void)0)
#define JPEG_DBG(...) ((void)0)
#define JPEG_PR_ERR(...) ((void)0)
#define JPEG_DEV_CNT 4
#define JPEG_DEC_ID 2
#define SCRATCH_ALLOC_END 0x10000000
#define SCRATCH_ALLOC_START 0x20000
#define VA_SPACE_END 0x80000000
#define SZ_128K 0x20000
#define SZ_128M 0x8000000
struct device { int unused; };
struct platform_device { int id; };
struct iommu_domain { int unused; };
struct scratch_mapping { int unused; };
struct cam_context_bank_info {
    const char *name;
    struct device *dev;
    struct iommu_domain *domain;
    int lock, handle, ref_cnt, cb_count, scratch_buf_support;
    unsigned long va_start, va_len;
    struct scratch_mapping scratch_map;
};
static struct { struct cam_context_bank_info *cb_info; unsigned cb_num, cb_init_count; } iommu_cb_set;
static struct iommu_domain *domain_result;
static int scratch_error, scratch_calls, setup_error, callbacks, destroyed;
static void mutex_init(int *m) { *m = 1; }
static void mutex_destroy(int *m) { assert(*m == 1); *m = 0; }
static void mutex_lock(int *m) { assert(*m == 1); }
static void mutex_unlock(int *m) { assert(*m == 1); }
static void cam_smmu_print_table(void) { assert(iommu_cb_set.cb_info); }
static int cam_smmu_create_iommu_handle(int i) { return 100 + i; }
static int cam_smmu_check_handle_unique(int h) { (void)h; return 0; }
static struct iommu_domain *iommu_get_domain_for_dev(struct device *d) { assert(d); return domain_result; }
static const char *dev_name(struct device *d) { (void)d; return "cb"; }
static int cam_smmu_init_scratch_map(struct scratch_mapping *m, unsigned long a,
                                   unsigned long size, int order) {
    (void)m; (void)a; (void)size; (void)order; scratch_calls++; return scratch_error;
}
''' + function(smmu, 'cam_smmu_setup_cb') + '\n' + function(
    smmu, 'cam_smmu_create_add_handle_in_table') + '\n' + function(
    smmu, 'cam_smmu_get_handle') + r'''
struct msm_jpeg_device {
    struct platform_device *pdev;
    int lock, idx, decode_flag, iommu_hdl;
    int evt_q, output_rtn_q, output_buf_q, input_rtn_q, input_buf_q;
};
static void msm_jpeg_q_init(const char *name, int *q) { (void)name; *q = 1; }
static void msm_jpeg_iommu_fault_handler(void) {}
static void cam_smmu_reg_client_page_fault_handler(int h, void (*fn)(void), void *reset, void *token) {
    (void)reset; assert(h >= 100 && token);
    if (fn) { assert(!callbacks); callbacks++; }
    else { assert(callbacks == 1); callbacks--; }
}
static int cam_smmu_destroy_handle(int h) {
    assert(h >= 100 && h < 100 + (int)iommu_cb_set.cb_num && !callbacks);
    struct cam_context_bank_info *cb = &iommu_cb_set.cb_info[h - 100];
    assert(cb->handle == h && cb->ref_cnt == 1);
    cb->handle = HANDLE_INIT; cb->ref_cnt = 0; destroyed++; return 0;
}
static int msm_jpeg_platform_setup(struct msm_jpeg_device *d) { assert(d); return setup_error; }
''' + function(jpeg, '__msm_jpeg_init') + r'''
#define BUF_MGR_NUM_BUF_Q 2
#define spin_lock_init(p) (*(p) = 1)
struct msm_isp_buf_mgr {
    int lock, open_count, attach_ref_cnt, num_buf_q, iommu_hdl;
    int pagefault_debug_disable, frameId_mismatch_recovery;
    struct {int bufq_lock;} bufq[BUF_MGR_NUM_BUF_Q];
};
''' + function((camera / 'isp/msm_buf_mgr.c').read_text(), 'msm_isp_init_isp_buf_mgr') + r'''
int main(void) {
    int h = 123;
    struct device device;
    struct iommu_domain domain;
    struct platform_device p = {.id = 0};
    struct msm_jpeg_device jpeg = {.pdev = &p};
    struct cam_context_bank_info table[2] = {
        {.handle = HANDLE_INIT, .lock = 1}, {.handle = HANDLE_INIT, .lock = 1}
    };
    iommu_cb_set.cb_info = table; iommu_cb_set.cb_num = 2;
    assert(__msm_jpeg_init(&jpeg) == -EPROBE_DEFER && !jpeg.lock);
    assert(!callbacks && !destroyed);
    struct msm_isp_buf_mgr mgr = {.lock = 1};
    assert(msm_isp_init_isp_buf_mgr(&mgr, "vfe") == -EPROBE_DEFER && !mgr.open_count);
    assert(cam_smmu_get_handle(NULL, &h) == -EFAULT);
    assert(cam_smmu_get_handle("jpeg_enc0", NULL) == -EFAULT);
    assert(cam_smmu_create_add_handle_in_table(NULL, &h) == -EINVAL);
    iommu_cb_set.cb_info = NULL;
    assert(cam_smmu_get_handle("jpeg_enc0", &h) == -EPROBE_DEFER);
    iommu_cb_set.cb_info = table;
    table[0].name = "vfe"; table[0].dev = &device; table[0].domain = &domain;
    iommu_cb_set.cb_init_count = 1;
    table[1].name = "jpeg_enc0";
    assert(cam_smmu_get_handle("jpeg_enc0", &h) == -EPROBE_DEFER);
    table[1].dev = &device; table[1].domain = &domain;
    assert(cam_smmu_get_handle("jpeg_enc0", &h) == -EPROBE_DEFER);
    iommu_cb_set.cb_init_count = 2;
    assert(cam_smmu_get_handle("unknown", &h) == -EINVAL);
    setup_error = -EPROBE_DEFER;
    assert(__msm_jpeg_init(&jpeg) == -EPROBE_DEFER);
    assert(!callbacks && destroyed == 1 && table[1].handle == HANDLE_INIT);
    setup_error = -EIO;
    assert(__msm_jpeg_init(&jpeg) == -EIO && destroyed == 2 && !callbacks);
    setup_error = 0;
    assert(__msm_jpeg_init(&jpeg) == 0 && callbacks == 1 && jpeg.lock);
    cam_smmu_reg_client_page_fault_handler(jpeg.iommu_hdl, NULL, NULL, &jpeg);
    assert(cam_smmu_destroy_handle(jpeg.iommu_hdl) == 0);
    assert(msm_isp_init_isp_buf_mgr(&mgr, "vfe") == 0 && mgr.open_count == 1 && mgr.iommu_hdl == 100);
    assert(msm_isp_init_isp_buf_mgr(&mgr, "vfe") == 0 && mgr.open_count == 2);
    assert(cam_smmu_get_handle("vfe", &h) == -EINVAL && table[0].ref_cnt == 2);
    puts("PASS: actual JPEG/SMMU partial table, deferred/hard errors, handle cleanup and retry");
    struct cam_context_bank_info cb = {.scratch_buf_support = 1};
    assert(cam_smmu_setup_cb(&cb, &device) == -EPROBE_DEFER && !scratch_calls);
    domain_result = ERR_PTR(-EIO);
    assert(cam_smmu_setup_cb(&cb, &device) == -EIO && !scratch_calls);
    domain_result = &domain; scratch_error = -ENOMEM;
    assert(cam_smmu_setup_cb(&cb, &device) == -ENOMEM && scratch_calls == 1);
    scratch_error = 0;
    assert(cam_smmu_setup_cb(&cb, &device) == 0 && cb.dev == &device && cb.domain == &domain);
    puts("PASS: actual context setup waits for domain before allocating scratch resources");
}
'''
with tempfile.TemporaryDirectory(prefix='camera-smmu-ready-') as tmp:
    path, binary = Path(tmp) / 'smmu.c', Path(tmp) / 'smmu'
    path.write_text(fixture)
    subprocess.run(['gcc', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                    '-Wno-sign-compare', '-Wno-unused-function', '-Wno-unused-parameter',
                    str(path), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)

populate = function(smmu, 'cam_populate_smmu_context_banks')
assert re.search(r'rc = cam_smmu_setup_cb\(.*?if \(rc < 0\) \{[^}]*goto cb_init_fail;', populate, re.S)
assert 'iommu_cb_set.cb_info = NULL;' not in populate
probe = function(smmu, 'cam_smmu_probe')
assert 'return -ENOMEM;' not in probe
for path, call in [('jpeg_10/msm_jpeg_platform.c', 'msm_camera_get_clk_info'),
                   ('jpeg_10/msm_jpeg_platform.c', 'msm_camera_get_regulator_info'),
                   ('ispif/msm_ispif.c', 'msm_ispif_get_clk_info')]:
    source = (camera / path).read_text()
    failure = re.search(r'rc = ' + call + r'\(.*?if \(rc < 0\) \{(.*?)\n\t\}', source, re.S).group(1)
    assert not re.search(r'rc = -E\w+;', failure), path
print('PASS: context probe and JPEG/ISPIF resource errors retain driver-core deferral')
