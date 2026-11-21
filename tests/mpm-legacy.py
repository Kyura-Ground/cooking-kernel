#!/usr/bin/env python3
"""Compile the real MPM translation, allocation, wake mapping and domain init."""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

kernel = Path(sys.argv[1]).resolve()
source = (kernel / 'drivers/irqchip/qcom-mpm.c').read_text()


def function(name):
    return re.search(r'^static [^;{}]*\b' + name + r'\([^;{}]*\)\n\{.*?\n\}',
                     source, re.M | re.S).group()


table = re.search(r'static const struct of_device_id mpm_gic_chip_data_table\[\] = '
                  r'\{.*?\n\};', source, re.S).group()
pin_file = kernel / 'drivers/irqchip/qcom-mpm-sdm660.c'
pins = (re.search(r'const struct mpm_pin .*?\n\};', pin_file.read_text(), re.S).group()
        if pin_file.exists() else
        'const struct mpm_pin mpm_sdm660_gic_chip_data[] = {{-1, 0}};')
other_tables = '\n'.join(
    f'const struct mpm_pin {name}[] = {{{{-1, 0}}}};'
    for name in re.findall(r'\.data\s*=\s*(mpm_\w+)', table)
    if name != 'mpm_sdm660_gic_chip_data')
fixture = r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define __init
#define GFP_KERNEL 0
#define IRQ_TYPE_SENSE_MASK 15
#define MAX_MPM_PIN_PER_IRQ 2
#define GPIO_NO_WAKE_IRQ (~0U)
#define MPM_NO_PARENT_IRQ (~0U)
#define DOMAIN_BUS_WAKEUP 1
#define pr_err(...) ((void)0)
typedef unsigned long irq_hw_number_t;
struct device_node { const char *full_name; unsigned count; bool of; };
#define fwnode_handle device_node
struct irq_domain {
    struct irq_domain *parent;
    struct fwnode_handle *fwnode;
    void *host_data;
    const char *name;
    unsigned size, token;
};
struct irq_fwspec {
    struct fwnode_handle *fwnode;
    unsigned param_count, param[4];
};
struct irq_data { struct irq_domain *domain; irq_hw_number_t hwirq; unsigned irq; };
struct mpm_pin { int pin; irq_hw_number_t hwirq; };
struct of_device_id { const char *compatible; const void *data; };
static struct device_node legacy = {"qcom,mpm-gic-sdm660", 96, true};
static struct device_node modern = {"qcom,mpm-gic-blair", 64, true};
static struct device_node gpio = {"qcom,mpm-gpio", 0, true};
static struct device_node parent = {"gic", 0, true}, non_of = {"acpi", 0, false};
static struct irq_domain parent_domain = {.fwnode = &parent};
static struct {
    struct irq_domain *gic_chip_domain, *gpio_chip_domain;
} msm_mpm_dev_data;
static int num_mpm_irqs = 64;
static unsigned int *mpm_to_irq;
static int msm_mpm_gic_chip, msm_mpm_gic_chip_domain_ops, msm_mpm_gpio_chip_domain_ops;
static int parent_calls, parent_error, init_error, allocation, fail_at;
static int live_domains, live_maps, refs;
static bool missing_gpio;
static irq_hw_number_t assigned;
static struct irq_fwspec forwarded;
static bool is_of_node(struct device_node *n) { return n && n->of; }
static struct device_node *irq_domain_get_of_node(struct irq_domain *d) { return d->fwnode; }
static bool of_device_is_compatible(struct device_node *n, const char *s) {
    return n && (!strcmp(n->full_name, s) ||
                 (n == &legacy && !strcmp(s, "qcom,mpm-gic")));
}
static struct device_node *of_node_get(struct device_node *n) { if (n) refs++; return n; }
static void of_node_put(struct device_node *n) { if (n) { assert(refs > 0); refs--; } }
static struct device_node *of_find_compatible_node(struct device_node *from,
                                                  const char *type, const char *s) {
    assert(!from && !type && !strcmp(s, "qcom,mpm-gpio"));
    return of_node_get(missing_gpio ? NULL : &gpio);
}
static struct device_node *of_node_to_fwnode(struct device_node *n) { return n; }
static struct irq_domain *irq_find_host(struct device_node *n) {
    return n == &parent ? &parent_domain : NULL;
}
static int of_property_read_u32(struct device_node *n, const char *s, int *v) {
    assert(!strcmp(s, "qcom,num-mpm-irqs"));
    if (!n->count) return -EINVAL;
    *v = n->count;
    return 0;
}
static const struct of_device_id *of_match_node(const struct of_device_id *ids,
                                               struct device_node *n) {
    for (; ids->compatible; ids++)
        if (of_device_is_compatible(n, ids->compatible)) return ids;
    return NULL;
}
static void *kcalloc(size_t n, size_t size, int flags) {
    (void)flags;
    if (++allocation == fail_at) return NULL;
    void *p = calloc(n, size);
    if (p) live_maps++;
    return p;
}
static void kfree(void *p) { if (p) { assert(live_maps > 0); live_maps--; free(p); } }
static struct irq_domain *irq_domain_create_linear(struct device_node *n, unsigned size,
                                                   void *ops, void *data) {
    (void)ops;
    if (++allocation == fail_at) return NULL;
    struct irq_domain *d = calloc(1, sizeof(*d));
    assert(d);
    *d = (struct irq_domain){.fwnode = n, .size = size, .host_data = data};
    live_domains++;
    return d;
}
static struct irq_domain *irq_domain_add_hierarchy(struct irq_domain *p, unsigned flags,
        unsigned size, struct device_node *n, void *ops, void *data) {
    assert(!flags);
    struct irq_domain *d = irq_domain_create_linear(n, size, ops, data);
    if (d) d->parent = p;
    return d;
}
static void irq_domain_remove(struct irq_domain *d) {
    assert(d && live_domains > 0);
    live_domains--;
    free(d);
}
static void irq_domain_update_bus_token(struct irq_domain *d, unsigned token) { d->token = token; }
static int msm_mpm_init(struct device_node *n) {
    assert(n == &legacy || n == &modern);
    assert(msm_mpm_dev_data.gic_chip_domain && msm_mpm_dev_data.gpio_chip_domain);
    return init_error;
}
static int irq_domain_set_hwirq_and_chip(struct irq_domain *d, unsigned virq,
        irq_hw_number_t hwirq, void *chip, void *data) {
    assert(d && virq == 123 && chip == &msm_mpm_gic_chip && !data);
    assigned = hwirq;
    return 0;
}
static int irq_domain_alloc_irqs_parent(struct irq_domain *d, unsigned virq,
                                       unsigned count, struct irq_fwspec *spec) {
    assert(d->parent && virq == 123 && count == 1);
    parent_calls++;
    forwarded = *spec;
    return parent_error;
}
''' + pins + '\n' + other_tables + '\n' + table + '\n' + '\n'.join(
    function(name) for name in ['get_parent_hwirq', 'msm_get_mpm_pin',
                              'msm_mpm_gic_chip_translate', 'msm_mpm_gic_chip_alloc',
                              'msm_mpm_irqchip_init']) + r'''
static void clean_domains(void) {
    irq_domain_remove(msm_mpm_dev_data.gpio_chip_domain);
    irq_domain_remove(msm_mpm_dev_data.gic_chip_domain);
    kfree(mpm_to_irq);
    memset(&msm_mpm_dev_data, 0, sizeof(msm_mpm_dev_data));
    mpm_to_irq = NULL;
    assert(!live_domains && !live_maps && !refs);
}
static void check_pins(struct irq_domain *domain, unsigned hwirq, int a, int b) {
    struct irq_data d = {.domain = domain, .hwirq = hwirq, .irq = 123};
    int result[2] = {-1, -1};
    msm_get_mpm_pin(&d, result, true);
    assert(result[0] == a && result[1] == b);
    if (a >= 0) assert(mpm_to_irq[a] == 123);
    if (b >= 0) assert(mpm_to_irq[b] == 123);
}
int main(void) {
    struct irq_domain d = {.fwnode = &legacy, .parent = &parent_domain,
                           .host_data = (void *)mpm_sdm660_gic_chip_data};
    struct irq_fwspec f = {.fwnode = &legacy, .param_count = 3,
                           .param = {0, 184, 0x104}};
    irq_hw_number_t hwirq;
    unsigned type;
    assert(msm_mpm_gic_chip_translate(&d, &f, &hwirq, &type) == 0);
    assert(hwirq == 216 && type == 4);
    f.param[0] = 1; f.param[1] = 13; f.param[2] = 0xf08;
    assert(msm_mpm_gic_chip_translate(&d, &f, &hwirq, &type) == 0);
    assert(hwirq == 29 && type == 8);
    f.param[0] = 2;
    assert(msm_mpm_gic_chip_translate(&d, &f, &hwirq, &type) == -EINVAL);
    for (unsigned count = 0; count <= 4; count++) {
        if (count == 2 || count == 3) continue;
        f.param_count = count;
        assert(msm_mpm_gic_chip_translate(&d, &f, &hwirq, &type) == -EINVAL);
    }
    f.param_count = 3; f.param[0] = 0; f.fwnode = &non_of;
    assert(msm_mpm_gic_chip_translate(&d, &f, &hwirq, &type) == -EINVAL);
    f.fwnode = &legacy; f.param[1] = 171; f.param[2] = 0x104;
    parent_error = -ENOMEM;
    assert(msm_mpm_gic_chip_alloc(&d, 123, 1, &f) == -ENOMEM);
    assert(assigned == 203 && parent_calls == 1);
    assert(forwarded.fwnode == &parent && forwarded.param_count == 3);
    assert(!memcmp(forwarded.param, f.param, sizeof(f.param)) && f.fwnode == &legacy);
    parent_error = 0; f.param[0] = 1; f.param[1] = 13;
    assert(msm_mpm_gic_chip_alloc(&d, 123, 1, &f) == 0 && assigned == 29);
    assert(forwarded.param[0] == 1 && forwarded.param[1] == 13);
    f.fwnode = &modern; f.param_count = 2; f.param[0] = 2; f.param[1] = 4;
    d.fwnode = &modern;
    assert(msm_mpm_gic_chip_translate(&d, &f, &hwirq, &type) == 0);
    assert(hwirq == 2 && type == 4);
    assert(msm_mpm_gic_chip_alloc(&d, 123, 1, &f) == 0);
    assert(assigned == 2 && forwarded.param_count == 3);
    assert(forwarded.param[0] == 0 && forwarded.param[1] == 216 && forwarded.param[2] == 4);
    f.param[0] = 90;
    int calls = parent_calls;
    assert(msm_mpm_gic_chip_alloc(&d, 123, 1, &f) == 0 && parent_calls == calls);
    unsigned map[96] = {0}; mpm_to_irq = map;
    d.fwnode = &legacy;
    check_pins(&d, 216, 2, -1);
    check_pins(&d, 379, 79, 81);
    check_pins(&d, 380, 80, 82);
    check_pins(&d, 519, 91, -1);
    check_pins(&d, 2, -1, -1);
    const struct mpm_pin collision[] = {{2, 216}, {52, 275}, {3, 52}, {-1, 0}};
    d.host_data = (void *)collision;
    check_pins(&d, 52, 3, -1);
    d.fwnode = &modern;
    check_pins(&d, 52, 52, -1);
    check_pins(&d, 90, -1, -1);
    puts("PASS: legacy SPI/PPI, invalid specs, parent forwarding and wake-pin mapping");
    mpm_to_irq = NULL;
    assert(msm_mpm_irqchip_init(&legacy, &parent) == 0);
    assert(num_mpm_irqs == 96 && live_domains == 2 && !refs);
    assert(msm_mpm_dev_data.gic_chip_domain->fwnode == &legacy);
    assert(msm_mpm_dev_data.gpio_chip_domain->fwnode == &gpio);
    assert(msm_mpm_dev_data.gpio_chip_domain->size == 96);
    assert(msm_mpm_dev_data.gpio_chip_domain->token == DOMAIN_BUS_WAKEUP);
    clean_domains();
    assert(msm_mpm_irqchip_init(&modern, &parent) == 0);
    assert(msm_mpm_dev_data.gpio_chip_domain->fwnode == &modern);
    assert(msm_mpm_dev_data.gpio_chip_domain->size == 64);
    clean_domains();
    assert(msm_mpm_irqchip_init(&legacy, NULL) == -ENXIO);
    assert(!live_domains && !live_maps && !refs);
    for (int fail = 1; fail <= 3; fail++) {
        allocation = 0; fail_at = fail;
        assert(msm_mpm_irqchip_init(&legacy, &parent) == -ENOMEM);
        assert(!live_domains && !live_maps && !refs);
    }
    fail_at = 0; missing_gpio = true;
    assert(msm_mpm_irqchip_init(&legacy, &parent) == -ENODEV);
    assert(!live_domains && !live_maps && !refs);
    missing_gpio = false; init_error = -EIO;
    assert(msm_mpm_irqchip_init(&legacy, &parent) == -EIO);
    assert(!live_domains && !live_maps && !refs);
    puts("PASS: separate legacy GPIO node, shared modern node, 96 pins and failure unwind");
}
'''
with tempfile.TemporaryDirectory(prefix='mpm-legacy-') as tmp:
    path, binary = Path(tmp) / 'mpm.c', Path(tmp) / 'mpm'
    path.write_text(fixture)
    subprocess.run(['gcc', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                    '-Wno-unused-parameter', '-Wno-unused-function', '-Wno-sign-compare',
                    '-Wno-missing-field-initializers', str(path), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)

assert re.search(r'IRQCHIP_DECLARE\([^,]+,\s*"qcom,mpm-gic",\s*msm_mpm_irqchip_init\)', source)
assert re.search(r'IRQCHIP_DECLARE\([^,]+,\s*"qcom,mpm",\s*msm_mpm_irqchip_init\)', source)
assert '.compatible = "qcom,mpm-gic-blair"' in source
assert re.search(r'extern const struct mpm_pin mpm_sdm660_gic_chip_data\[\];',
                 (kernel / 'include/soc/qcom/mpm.h').read_text())
expected = [(2, 216), (52, 275), (61, 209), (79, 379), (80, 380),
            (81, 379), (82, 380), (87, 358), (91, 519)]
assert [(int(a), int(b)) for a, b in re.findall(r'\{(\d+),\s*(\d+)\}', pins)] == expected
result = subprocess.run(['make', '-s', '-f', '-', 'check', 'CONFIG_QCOM_MPM=y'],
                        input=f'include {kernel}/drivers/irqchip/Makefile\n'
                              'check:\n\t@echo $(obj-y) $(mpm-objs)\n',
                        capture_output=True, text=True, check=True)
assert {'mpm.o', 'qcom-mpm.o', 'qcom-mpm-sdm660.o', 'qcom-mpm-blair.o'} <= set(result.stdout.split())
print('PASS: legacy early binding, unchanged modern binding, SDM660 table and Kbuild linkage')
