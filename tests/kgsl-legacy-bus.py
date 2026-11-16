#!/usr/bin/env python3
"""Run the actual kernel legacy-bus functions with host-side API fixtures in CI."""

from pathlib import Path
import subprocess
import sys
import tempfile


kernel = Path(sys.argv[1])


def function(path, name):
    source = (kernel / "drivers/gpu/msm" / path).read_text()
    start = source.index("static int " + name + "(")
    opening = source.index("{", start)
    depth = 1
    end = opening + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


fixture = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
typedef uint32_t u32;
typedef uint64_t u64;
#define U32_MAX UINT32_MAX
#define GFP_KERNEL 0
#define EPROBE_DEFER 517
#define IS_ERR_OR_NULL(p) (!(p) || (intptr_t)(p) < 0)
#define PTR_ERR(p) ((int)(intptr_t)(p))
#define KGSL_DEVICE(a) (&(a)->dev)
#define MBps_to_icc(x) ((x) * 1000U)
#define kBps_to_icc(x) (x)
#define trace_kgsl_buslevel(d, p, l) ((void)(d), (void)(p), (void)(l))
struct platform_device { int unused; };
struct msm_bus_client_handle { int unused; };
struct msm_bus_vectors { int src, dst; u64 ab, ib; };
struct msm_bus_paths { int num_paths; struct msm_bus_vectors *vectors; };
struct msm_bus_scale_pdata {
    struct msm_bus_paths *usecase;
    int num_usecases;
    unsigned int active_only;
};
struct kgsl_pwrctrl {
    struct msm_bus_client_handle *legacy_bus;
    u32 *ddr_table;
    int ddr_table_count, cur_buslevel, active_pwrlevel;
    u32 cur_ab;
    void *icc_path;
};
struct kgsl_device { struct kgsl_pwrctrl pwrctrl; };
struct adreno_device { struct kgsl_device dev; };
static struct msm_bus_vectors vectors[3];
static struct msm_bus_paths paths[3];
static struct msm_bus_scale_pdata pdata, *input;
static struct msm_bus_client_handle client;
static int allocations, fail_alloc, register_error, registrations, validations;
static int vote_error, legacy_votes, icc_votes;
static u64 last_ab, last_ib;
static void *kcalloc(size_t count, size_t size, int flags) {
    (void)flags;
    if (fail_alloc) return NULL;
    void *p = calloc(count, size);
    if (p) allocations++;
    return p;
}
static void kfree(void *p) { if (p) { allocations--; free(p); } }
static u64 div_u64(u64 value, u32 divisor) { return value / divisor; }
static struct msm_bus_scale_pdata *msm_bus_cl_get_pdata(struct platform_device *p) {
    (void)p; return input;
}
static struct msm_bus_client_handle *msm_bus_scale_register(
        u32 src, u32 dst, char *name, bool active_only) {
    assert(src == 26 && dst == 512 && !strcmp(name, "kgsl") && !active_only);
    registrations++;
    return register_error ? (void *)(intptr_t)register_error : &client;
}
static void validate_pwrlevels(struct kgsl_device *device, u32 *levels, int count) {
    assert(device && levels && count == 3); validations++;
}
static int msm_bus_scale_update_bw(struct msm_bus_client_handle *p, u64 ab, u64 ib) {
    assert(p == &client); legacy_votes++; last_ab = ab; last_ib = ib;
    return vote_error;
}
static int icc_set_bw(void *p, u32 ab, u32 ib) {
    assert(p == (void *)1); icc_votes++; last_ab = ab; last_ib = ib;
    return vote_error;
}
'''

tests = r'''
static void reset(void) {
    assert(allocations == 0);
    for (int i = 0; i < 3; i++) {
        vectors[i] = (struct msm_bus_vectors){26, 512, 0, (u64)i * 300000000};
        paths[i] = (struct msm_bus_paths){1, &vectors[i]};
    }
    pdata = (struct msm_bus_scale_pdata){paths, 3, 0}; input = &pdata;
    fail_alloc = register_error = registrations = validations = 0;
    vote_error = legacy_votes = icc_votes = 0;
}
int main(void) {
    struct adreno_device adreno = {0};
    struct kgsl_pwrctrl *pwr = &adreno.dev.pwrctrl;
    struct platform_device pdev = {0};
    reset();
    assert(kgsl_bus_init_legacy(&adreno.dev, &pdev) == 0);
    assert(pwr->ddr_table_count == 3 && pwr->ddr_table[1] == 300000);
    assert(pwr->ddr_table[2] == 600000 && registrations == 1 && validations == 1);
    assert(adreno_interconnect_bus_set(&adreno, 1, 5000) == 0);
    assert(last_ab == 5000000000ULL && last_ib == 300000000 && legacy_votes == 1);
    assert(adreno_interconnect_bus_set(&adreno, 1, 5000) == 0 && legacy_votes == 1);
    vote_error = -EIO;
    assert(adreno_interconnect_bus_set(&adreno, 2, 20) == -EIO);
    assert(pwr->cur_buslevel == 1 && pwr->cur_ab == 5000);
    vote_error = 0;
    assert(adreno_interconnect_bus_set(&adreno, 2, 20) == 0 && legacy_votes == 3);
    assert(adreno_interconnect_bus_set(&adreno, 0, 0) == 0);
    assert(last_ab == 0 && last_ib == 0);
    kfree(pwr->ddr_table);
    for (int invalid = 0; invalid < 5; invalid++) {
        reset(); memset(pwr, 0, sizeof(*pwr));
        if (invalid == 0) input = NULL;
        if (invalid == 1) pdata.num_usecases = 0;
        if (invalid == 2) paths[1].num_paths = 2;
        if (invalid == 3) vectors[1].dst++;
        if (invalid == 4) vectors[1].ib = ((u64)U32_MAX + 1) * 1000;
        assert(kgsl_bus_init_legacy(&adreno.dev, &pdev) == -EINVAL);
        assert(allocations == 0 && registrations == 0 && !pwr->legacy_bus);
    }
    reset(); register_error = -EPROBE_DEFER;
    assert(kgsl_bus_init_legacy(&adreno.dev, &pdev) == -EPROBE_DEFER);
    assert(allocations == 0 && !pwr->legacy_bus);
    reset(); fail_alloc = 1;
    assert(kgsl_bus_init_legacy(&adreno.dev, &pdev) == -ENOMEM);
    assert(allocations == 0 && registrations == 0);
    reset();
    u32 native_levels[] = {0, 300000};
    pwr->ddr_table = native_levels; pwr->icc_path = (void *)1;
    assert(adreno_interconnect_bus_set(&adreno, 1, 25) == 0);
    assert(icc_votes == 1 && legacy_votes == 0 && last_ab == 25000 && last_ib == 300000);
    vote_error = -EIO;
    assert(adreno_interconnect_bus_set(&adreno, 0, 0) == -EIO);
    assert(pwr->cur_buslevel == 1 && pwr->cur_ab == 25);
    puts("PASS: actual KGSL legacy table parsing, BW units, bounds, cleanup and vote retries");
}
'''

with tempfile.TemporaryDirectory(prefix="kgsl-legacy-test-") as directory:
    source = Path(directory) / "test.c"
    binary = Path(directory) / "test"
    source.write_text(
        fixture
        + function("kgsl_bus.c", "kgsl_bus_init_legacy")
        + "\n"
        + function("adreno.c", "adreno_interconnect_bus_set")
        + "\n"
        + tests
    )
    subprocess.run(["gcc", "-std=gnu11", "-Wall", "-Wextra", "-Werror",
                    str(source), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
