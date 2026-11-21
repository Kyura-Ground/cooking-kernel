#!/usr/bin/env python3
"""Compile the real LPM parser against SDM660's unchanged idle-state tree."""
from pathlib import Path
import json
import re
import subprocess
import sys
import tempfile

kernel = Path(sys.argv[1]).resolve()
source = (kernel / 'drivers/cpuidle/lpm-levels-of.c').read_text()
header = (kernel / 'drivers/cpuidle/lpm-levels.h').read_text()
header = re.sub(r'^#include .*\n', '', header, flags=re.M)


def function(name):
    return re.search(r'^(?:static )?(?:int|void|struct lpm_cluster \*)\s*' +
                     name + r'\([^;{}]*\)\n\{.*?\n\}', source,
                     re.M | re.S).group()


# Preserve every DT value; only resolve the eight local CPU phandles for the fixture.
dt = (kernel / 'arch/arm64/boot/dts/vendor/qcom/sdm660-pm.dtsi').read_text()
dt = re.sub(r'/\*.*?\*/', '', dt, flags=re.S)
dt = dt[dt.index('qcom,lpm-levels {'):]
nodes, stack, props = [], [], []
for match in re.finditer(r'([\w,#@-]+)\s*\{|([\w,#-]+)(?:\s*=\s*([^;]+))?;|}', dt):
    name, key, value = match.groups()
    if name:
        parent = stack[-1] if stack else -1
        nodes.append((name.split('@')[0], parent))
        stack.append(len(nodes) - 1)
    elif key:
        value = (value or '').strip()
        if value.startswith('"'):
            props.append((stack[-1], key, value, 0))
        elif value.startswith('<'):
            values = value.strip('<>').split()
            number = (sum(1 << int(v[4:]) for v in values)
                      if values[0].startswith('&CPU') else int(values[0], 0))
            props.append((stack[-1], key, 'NULL', number))
        else:
            props.append((stack[-1], key, 'NULL', 1))
    else:
        stack.pop()
        if not stack:
            break
assert len(nodes) == 22 and len(props) > 100, 'Incomplete SDM660 LPM fixture'
node_data = ',\n'.join('{%s, %s, %d, 0}' % (json.dumps(n), json.dumps(n), p)
                        for n, p in nodes)
prop_data = ',\n'.join('{%d, %s, %s, %d}' % (n, json.dumps(k), s, v)
                        for n, k, s, v in props)

fixture = r'''
#include <assert.h>
#include <errno.h>
#include <limits.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint32_t u32;
typedef int spinlock_t;
struct hrtimer { int unused; };
struct kobj_attribute { int unused; };
struct cpumask { unsigned bits; };
struct list_head { struct list_head *next, *prev; };
#define INIT_LIST_HEAD(h) ((h)->next = (h)->prev = (h))
static void list_add(struct list_head *n, struct list_head *h) {
    assert(h->next && h->prev); n->next = h->next; n->prev = h;
    h->next->prev = n; h->next = n;
}
static void list_del(struct list_head *n) {
    assert(n->next && n->prev); n->prev->next = n->next; n->next->prev = n->prev;
}
#define entry(p,t,m) ((t *)((char *)(p) - offsetof(t,m)))
#define list_for_each_entry_safe(p,n,h,m) \
 for (p=entry((h)->next,typeof(*p),m), n=entry(p->m.next,typeof(*p),m); \
      &p->m!=(h); p=n,n=entry(n->m.next,typeof(*n),m))
#define GFP_KERNEL 0
#define __iomem
#define pr_err(...) ((void)0)
#define ERR_PTR(e) ((void *)(intptr_t)(e))
#define IS_ERR(p) ((uintptr_t)(p) >= (uintptr_t)-4095)
#define spin_lock_init(p) (*(p)=1)
static struct cpumask online = {255};
#define cpu_online_mask (&online)
static void cpumask_or(struct cpumask *d, const struct cpumask *a, const struct cpumask *b) { d->bits=a->bits|b->bits; }
static bool cpumask_intersects(const struct cpumask *a, const struct cpumask *b) { return !!(a->bits & b->bits); }
struct device_node { const char *name, *full_name; int parent, refs; };
struct device { struct device_node *of_node; };
struct platform_device { struct device dev; };
static struct platform_device *lpm_pdev;
''' + header + '\nstatic struct device_node nodes[] = {\n' + node_data + r'''
};
static struct {int node; const char *key, *string; u32 number;} props[] = {
''' + prop_data + r'''
};
static bool modern;
static int missing_node = -1, allocations, fail_alloc, timers;
static const char *missing_key;
static void *allocated[64];
static int property(struct device_node *n, const char *key) {
    int index = n - nodes;
    if (index == missing_node && missing_key && !strcmp(key, missing_key)) return -1;
    for (size_t i=0; i<sizeof(props)/sizeof(*props); i++) {
        const char *k = props[i].key;
        if (modern) {
            if (!strcmp(k, "label")) k = "idle-state-name";
            else if (!strcmp(k, "qcom,entry-latency-us") ||
                     !strcmp(k, "qcom,exit-latency-us") ||
                     !strcmp(k, "qcom,min-residency-us")) k += 5;
        }
        if (props[i].node == index && !strcmp(k,key)) return i;
    }
    return -1;
}
static int of_property_read_string(struct device_node *n, const char *k, const char **v) {
    int i=property(n,k); if (i<0 || !props[i].string) return -EINVAL;
    *v=props[i].string; return 0;
}
static int lpm_of_read_u32(struct device_node *n, const char *k, u32 *v, bool log) {
    (void)log;
    if (modern && !strcmp(k,"arm,psci-suspend-param") && n-nodes != missing_node) { *v=1; return 0; }
    int i=property(n,k); if (i<0) return -EINVAL; *v=props[i].number; return 0;
}
static bool of_property_read_bool(struct device_node *n, const char *k) { return property(n,k)>=0; }
static bool of_node_name_eq(struct device_node *n, const char *name) { return !strcmp(n->name,name); }
static bool of_device_is_compatible(struct device_node *n, const char *name) {
    return modern && of_node_name_eq(n,"qcom,pm-cpu-level") && !strcmp(name,"arm,idle-state");
}
static int of_node_cmp(const char *a, const char *b) { return strcmp(a,b); }
static void of_node_put(struct device_node *n) { if(n) { assert(n->refs>0); n->refs--; } }
static struct device_node *child(struct device_node *parent, struct device_node *previous) {
    int start=previous ? previous-nodes+1 : parent-nodes+1;
    of_node_put(previous);
    for(size_t i=start;i<sizeof(nodes)/sizeof(*nodes);i++)
        if(nodes[i].parent==parent-nodes) { nodes[i].refs++; return &nodes[i]; }
    return NULL;
}
#define for_each_child_of_node(p,n) for(n=child(p,NULL);n;n=child(p,n))
static struct device_node *of_find_node_by_name(struct device_node *p, const char *name) {
    (void)p; for(size_t i=0;i<sizeof(nodes)/sizeof(*nodes);i++)
        if(of_node_name_eq(&nodes[i],name)) { nodes[i].refs++; return &nodes[i]; }
    return NULL;
}
static void *devm_kzalloc(struct device *d, size_t size, int flags) {
    (void)d; (void)flags; if(++allocations==fail_alloc) return NULL;
    void *p=calloc(1,size); assert(p); allocated[allocations]=p; return p;
}
static int get_cpumask_for_node(struct device_node *n, struct cpumask *mask) {
    return lpm_of_read_u32(n,"qcom,cpu",&mask->bits,true);
}
static void add_rimps_tmr_register(struct device_node *dn, struct lpm_cluster *c) {
    (void)dn; assert(c && !IS_ERR(c)); assert(c->child.next && c->cpu.next); timers++;
}
''' + '\n'.join(function(n) for n in ['parse_cluster_params', 'parse_power_params',
    'parse_cluster_level', 'parse_cpu_mode', 'parse_cpu', 'parse_cpu_levels',
    'free_cluster_node', 'parse_cluster', 'lpm_of_parse_cluster']) + r'''
static void reset(void) {
    for(size_t i=0;i<sizeof(nodes)/sizeof(*nodes);i++) assert(nodes[i].refs==0);
    for(size_t i=0;i<sizeof(allocated)/sizeof(*allocated);i++) { free(allocated[i]); allocated[i]=NULL; }
    missing_node=-1; missing_key=NULL; allocations=fail_alloc=timers=0;
}
int main(void) {
    struct platform_device p={.dev.of_node=&nodes[0]};
    for(int mode=0;mode<2;mode++) {
        modern=mode; reset();
        struct lpm_cluster *c=lpm_of_parse_cluster(&p);
        assert(c && !IS_ERR(c) && timers==1 && c->nlevels==2);
        assert(!strcmp(c->cluster_name,"system") && c->list.next==&c->list);
        assert(c->levels[0].pwr.entry_latency==640 && c->levels[0].pwr.exit_latency==1654);
        assert(c->levels[1].pwr.min_residency==15337);
        struct lpm_cluster *cl=entry(c->child.next,struct lpm_cluster,list);
        assert(cl->nlevels==4 && cl->child_cpus.bits==240);
        struct lpm_cpu *cpu=entry(cl->cpu.next,struct lpm_cpu,list);
        assert(cpu->nlevels==3 && cpu->related_cpus.bits==240);
        assert(cpu->levels[2].psci_id==3 && cpu->levels[2].is_reset && cpu->levels[2].use_bc_timer);
        assert(cpu->levels[2].pwr.entry_latency==297 && cpu->levels[2].pwr.max_residency==UINT_MAX);
        reset(); missing_node=1; missing_key=modern ? "idle-state-name" : "label";
        assert(IS_ERR(lpm_of_parse_cluster(&p)) && !timers); reset();
        int failures[]={2,5,10};
        for(size_t i=0;i<sizeof(failures)/sizeof(*failures);i++) {
            missing_node=failures[i]; missing_key=modern ? "entry-latency-us" : "qcom,entry-latency-us";
            assert(IS_ERR(lpm_of_parse_cluster(&p)) && !timers); reset();
        }
        missing_node=10; missing_key="qcom,psci-cpu-mode";
        assert(IS_ERR(lpm_of_parse_cluster(&p)) && !timers); reset();
        if(modern) {
            missing_node=10; missing_key="arm,psci-suspend-param";
            assert(IS_ERR(lpm_of_parse_cluster(&p)) && !timers); reset();
        }
        for(int fail=1;fail<=5;fail++) {
            fail_alloc=fail; assert(IS_ERR(lpm_of_parse_cluster(&p)) && !timers); reset();
        }
    }
    puts("PASS: real LPM parser, complete legacy/modern SDM660 trees, unchanged calibration, allocation/parse failures, list cleanup and node references");
}
'''
with tempfile.TemporaryDirectory(prefix='lpm-compat-') as tmp:
    path, binary = Path(tmp) / 'lpm.c', Path(tmp) / 'lpm'
    path.write_text(fixture)
    subprocess.run(['gcc', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                    '-Wno-unused-function', '-Wno-pointer-sign',
                    str(path), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
