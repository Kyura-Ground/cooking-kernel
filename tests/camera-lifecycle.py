#!/usr/bin/env python3
"""Exercise real MSM core probe and subdevice lifetime against the V4L2 contract."""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

kernel = Path(sys.argv[1]).resolve()
camera = kernel / 'drivers/media/platform/msm/camera_v2'
source = (camera / 'msm.c').read_text()


def function(name):
    return re.search(r'^(?:static )?(?:inline )?int ' + name +
                     r'\([^;{}]*\)\n\{.*?\n\}', source, re.M | re.S).group()


v4l2 = (kernel / 'drivers/media/v4l2-core/v4l2-dev.c').read_text()
contract = v4l2[v4l2.index('\t/* the release callback MUST be present */'):]
contract = contract[:contract.index('\t/* v4l2_fh support */')]
fixture = r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define CONFIG_MEDIA_CONTROLLER 1
#define GFP_KERNEL 0
#define EPROBE_DEFER 517
#define WARN_ON(x) test_warn(!!(x))
#define VFL_TYPE_GRABBER 0
#define VFL_TYPE_SUBDEV 3
#define V4L2_SUBDEV_FL_HAS_DEVNODE 4
#define V4L2_CAP_VIDEO_CAPTURE_MPLANE 0x1000
#define V4L2_CAP_STREAMING 0x4000000
#define VIDEO_MAJOR 81
#define QCAMERA_VNODE_GROUP_ID 1
#define MSM_CONFIGURATION_NAME "msm-config"
#define MSM_CAM_LOGSYNC_FILE_BASEDIR "camera"
#define MSM_CAM_LOGSYNC_FILE_NAME "logsync"
#define pr_err(...) ((void)0)
#define pr_warn(...) ((void)0)
#define spin_lock_init(p) (*(p) = 1)
#define atomic_set(p, value) (*(p) = (value))
#define INIT_LIST_HEAD(p) (*(p) = 1)
struct device { void *of_node; };
struct platform_device { struct device dev; };
struct media_device { char model[32]; struct device *dev; };
struct entity { unsigned function; const char *name; struct { struct {int major, minor;} dev; } info; };
struct v4l2_device { struct device *dev; struct media_device *mdev; void (*notify)(void); };
struct video_device {
    struct entity entity;
    struct v4l2_device *v4l2_dev;
    char name[32];
    void (*release)(struct video_device *);
    const void *fops, *ioctl_ops;
    int minor, vfl_type;
    bool registered;
    unsigned device_caps;
};
struct msm_video_device { struct video_device *vdev; int opened; };
struct v4l2_subdev {
    struct v4l2_device *v4l2_dev;
    struct video_device *devnode;
    struct entity entity;
    char name[32]; unsigned flags; void *owner;
};
struct msm_sd_subdev { struct v4l2_subdev sd; int list; };
struct dentry { int unused; };
static struct v4l2_device *msm_v4l2_dev;
static int ordered_sd_list, ordered_sd_mtx, v4l2_event_mtx, msm_eventq_lock, msm_pid_lock;
static struct {int unused;} *msm_session_q;
static uint32_t gpu_limit;
static const int msm_fops, g_msm_ioctl_ops, logsync_fops;
static int allocation, fail_allocation, video_error, ahb_error, register_error;
static int ordered_adds, ordered_removes, subdevs, live_video_nodes;
static void *allocated[64];
static int test_warn(bool condition) { return condition; }
static void *kzalloc(size_t size, int flags) {
    (void)flags;
    assert(++allocation < 64);
    if (allocation == fail_allocation) return NULL;
    return allocated[allocation] = calloc(1, size);
}
static void kfree(void *p) {
    if (!p) return;
    for (int i = 1; i < 64; i++) if (allocated[i] == p) {
        free(p); allocated[i] = NULL; return;
    }
    assert(!"free of unknown allocation");
}
#define kzfree kfree
static void mutex_init(int *p) { *p = 1; }
static void mutex_lock(int *p) { assert(*p); }
static void mutex_unlock(int *p) { assert(*p); }
static void list_del_init(int *p) { assert(*p); *p = 0; ordered_removes++; }
static void msm_add_sd_in_position(struct msm_sd_subdev *s, int *head) {
    assert(*head); s->list = 1; ordered_adds++;
}
static void msm_sd_notify(void) {}
#define strlcpy test_strlcpy
static size_t test_strlcpy(char *dst, const char *src, size_t size) {
    size_t n = strlen(src);
    if (size) { size_t copy = n < size - 1 ? n : size - 1; memcpy(dst, src, copy); dst[copy] = 0; }
    return n;
}
static struct video_device *video_device_alloc(void) { return kzalloc(sizeof(struct video_device), 0); }
static void video_device_release(struct video_device *v) { kfree(v); }
static int media_device_register(struct media_device *m) { assert(m->dev); return 0; }
static void media_device_init(struct media_device *m) { (void)m; }
static void media_device_unregister(struct media_device *m) { (void)m; assert(!live_video_nodes); }
static void media_entity_cleanup(struct entity *e) { (void)e; }
static int media_entity_pads_init(struct entity *e, int n, void *pads) { (void)e; (void)n; (void)pads; return 0; }
static int v4l2_device_register(struct device *dev, struct v4l2_device *v) { v->dev = dev; return 0; }
static void v4l2_device_unregister(struct v4l2_device *v) { v->dev = NULL; }
static int __video_register_device(struct video_device *vdev, int type, int nr, int warn, void *owner) {
    (void)nr; (void)warn; (void)owner;
''' + contract + r'''
    if (!video_error) { vdev->registered = true; live_video_nodes++; }
    return video_error;
}
static int video_register_device(struct video_device *v, int type, int nr) {
    return __video_register_device(v, type, nr, 1, NULL);
}
static void video_set_drvdata(struct video_device *v, void *p) { (void)v; (void)p; }
static const char *video_device_node_name(struct video_device *v) { (void)v; return "video0"; }
static bool video_is_registered(struct video_device *v) { return v->registered; }
static void video_unregister_device(struct video_device *v) { assert(v->registered); live_video_nodes--; kfree(v); }
static void msm_init_queue(void *q) { assert(q); }
static struct dentry *debugfs_create_dir(const char *name, void *parent) {
    (void)name; (void)parent; static struct dentry d; return &d;
}
static struct dentry *debugfs_create_file(const char *name, int mode, struct dentry *dir,
                                          void *data, const void *ops) {
    (void)mode; (void)dir; (void)data; (void)ops; return debugfs_create_dir(name, NULL);
}
static int cam_ahb_clk_init(struct platform_device *p) { (void)p; return ahb_error; }
static int of_property_read_u32(void *node, const char *key, uint32_t *value) {
    (void)node; (void)key; *value = 0; return 0;
}
static int v4l2_device_register_subdev(struct v4l2_device *v, struct v4l2_subdev *s) {
    if (register_error) return register_error;
    assert(v && v->dev && !s->v4l2_dev); s->v4l2_dev = v; subdevs++; return 0;
}
static void v4l2_device_unregister_subdev(struct v4l2_subdev *s) {
    if (!s->v4l2_dev) return;
    s->v4l2_dev = NULL; subdevs--;
    if (s->devnode) { video_unregister_device(s->devnode); s->devnode = NULL; }
}
static void msm_sd_unregister_subdev(struct video_device *v) { kfree(v); }
static const void *msm_cam_get_v4l2_subdev_fops_ptr(void) { return &msm_fops; }
''' + '\n'.join(function(n) for n in ['__msm_sd_register_subdev', 'msm_sd_register',
                                      'msm_sd_unregister', 'msm_probe']) + r'''
static void reset(void) {
    for (int i = 1; i < 64; i++) if (allocated[i]) { free(allocated[i]); allocated[i] = NULL; }
    msm_v4l2_dev = NULL; msm_session_q = NULL;
    allocation = fail_allocation = video_error = ahb_error = register_error = 0;
    ordered_adds = ordered_removes = subdevs = ordered_sd_mtx = ordered_sd_list = 0;
    live_video_nodes = 0;
}
int main(void) {
    struct platform_device p = {0};
    struct msm_sd_subdev s = {.sd = {.name = "csiphy", .flags = V4L2_SUBDEV_FL_HAS_DEVNODE}};
    assert(msm_probe(&p) == 0);
    assert(msm_v4l2_dev && msm_v4l2_dev->dev == &p.dev && ordered_sd_list);
    register_error = -EIO;
    assert(msm_sd_register(&s) == -EIO && !ordered_adds && !subdevs);
    register_error = 0; fail_allocation = allocation + 1;
    assert(msm_sd_register(&s) == -ENOMEM && !ordered_adds && !subdevs);
    fail_allocation = 0; video_error = -EINVAL;
    assert(msm_sd_register(&s) == -EINVAL && !ordered_adds && !subdevs);
    video_error = 0;
    assert(msm_sd_register(&s) == 0 && ordered_adds == 1 && subdevs == 1);
    assert(msm_sd_unregister(&s) == 0 && ordered_removes == 1 && !subdevs);
    assert(msm_sd_unregister(&s) == 0 && ordered_removes == 1);
    reset();
    assert(msm_sd_register(&s) == -EPROBE_DEFER && !ordered_adds);
    for (int fail = 1; fail <= 5; fail++) {
        fail_allocation = fail;
        assert(msm_probe(&p) == -ENOMEM);
        assert(msm_v4l2_dev == NULL);
        assert(msm_sd_register(&s) == -EPROBE_DEFER && !ordered_adds);
        reset();
    }
    video_error = -EINVAL;
    assert(msm_probe(&p) == -EINVAL && msm_v4l2_dev == NULL);
    reset(); ahb_error = -EPROBE_DEFER;
    assert(msm_probe(&p) == -EPROBE_DEFER && msm_v4l2_dev == NULL);
    assert(msm_session_q == NULL);
    reset();
    puts("PASS: V4L2 capabilities, core failure cleanup, deferred registration and subdevice unwind");
}
'''
with tempfile.TemporaryDirectory(prefix='camera-lifecycle-') as tmp:
    path, binary = Path(tmp) / 'camera.c', Path(tmp) / 'camera'
    path.write_text(fixture)
    subprocess.run(['gcc', '-std=gnu11', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function',
                    str(path), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)

csiphy = (camera / 'sensor/csiphy/msm_csiphy.c').read_text()
probe = re.search(r'static int csiphy_probe\(.*?\n\}', csiphy, re.S).group()
register = re.search(r'rc = msm_sd_register\(&new_csiphy_dev->msm_sd\);\s*'
                     r'if \(rc < 0\)\s*goto csiphy_unregister_irq;', probe)
assert register and probe.index('msm_camera_register_irq(') < register.start()
clock_failure = re.search(r'rc = msm_csiphy_get_clk_info\(.*?\n\t\}', probe, re.S).group()
assert 'rc =  -EFAULT' not in clock_failure
assert re.search(r'csiphy_unregister_irq:\s*msm_camera_unregister_irq\(', probe)
assert 'platform_set_drvdata(pdev, NULL);' in probe
remove = re.search(r'static int msm_csiphy_exit\(.*?\n\}', csiphy, re.S).group()
assert remove.index('msm_sd_unregister(') < remove.index('kfree(csiphy_dev)')
assert 'msm_camera_unregister_irq(' in remove
print('PASS: CSIPHY publishes after resources and unwinds IRQ/subdevice on failure/removal')
