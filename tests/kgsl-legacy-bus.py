#!/usr/bin/env python3
"""Run actual KGSL bus and A5xx initialization with host API fixtures in CI."""

from pathlib import Path
import subprocess
import sys
import tempfile


kernel = Path(sys.argv[1])


def function(path, name, signature="static int"):
    source = (kernel / "drivers/gpu/msm" / path).read_text()
    start = source.index(signature + " " + name + "(")
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

#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
#define ADRENO_GPMU 1
#define ADRENO_FEATURE(a, f) ((void)(a), (void)(f), has_gpmu)
#define KGSL_MEMFLAGS_GPUREADONLY 1
#define KGSL_MEMDESC_PRIVILEGED 2
#define IS_ERR(p) ((intptr_t)(p) < 0)
#define REG_PAIR_COUNT(a, i) ((a)[2 * (i) + 1] - (a)[2 * (i)] + 1)
#define A5XX_NUM_SHADER_BANKS 4
struct kgsl_memdesc { u64 gpuaddr; void *hostptr; };
struct a5xx_shader_block { unsigned int sz; };
struct a5xx_hlsq_sp_tp_regs { unsigned int size; };
static struct kgsl_memdesc *capturescript, *registers, *owned[2];
static int has_gpmu, global_attempts, global_successes, fail_global;
static const unsigned int a5xx_registers[] = {0x10, 0x11};
static const unsigned int a5xx_gpmu_registers[] = {0x20, 0x21};
static struct a5xx_shader_block a5xx_shader_blocks[] = {{2}};
static struct a5xx_hlsq_sp_tp_regs a5xx_hlsq_sp_tp_registers[] = {{2}};
static struct kgsl_memdesc *kgsl_allocate_global(struct kgsl_device *device,
        u64 size, u32 padding, u64 flags, u32 priv, const char *name) {
    assert(device && size && padding == 0 && priv == KGSL_MEMDESC_PRIVILEGED);
    assert(flags == (strcmp(name, "capturescript") ? 0 : KGSL_MEMFLAGS_GPUREADONLY));
    if (++global_attempts == fail_global) return (void *)(intptr_t)-ENOMEM;
    assert(global_successes < 2);
    struct kgsl_memdesc *m = calloc(1, sizeof(*m));
    assert(m); m->hostptr = calloc(1, size); assert(m->hostptr);
    m->gpuaddr = 0x1000 * (global_successes + 1);
    owned[global_successes++] = m;
    return m;
}
static int _a5xx_crashdump_init_shader(struct a5xx_shader_block *block,
        uint64_t *ptr, uint64_t *offset) {
    memset(ptr, 0, 32 * A5XX_NUM_SHADER_BANKS);
    *offset += block->sz * sizeof(unsigned int) * A5XX_NUM_SHADER_BANKS;
    return 4 * A5XX_NUM_SHADER_BANKS;
}
static int _a5xx_crashdump_init_hlsq(struct a5xx_hlsq_sp_tp_regs *regs,
        uint64_t *ptr, uint64_t *offset) {
    memset(ptr, 0, 32);
    *offset += regs->size * sizeof(unsigned int);
    return 4;
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
    for (has_gpmu = 0; has_gpmu <= 1; has_gpmu++) {
        for (fail_global = 0; fail_global <= 2; fail_global++) {
            int failure = fail_global;
            global_attempts = global_successes = 0;
            capturescript = registers = NULL;
            a5xx_crashdump_init(&adreno);
            if (failure == 1) {
                assert(IS_ERR(capturescript) && registers == NULL);
                assert(global_attempts == 1 && global_successes == 0);
            } else if (failure == 2) {
                assert(!IS_ERR_OR_NULL(capturescript) && IS_ERR(registers));
                assert(global_attempts == 2 && global_successes == 1);
            }
            struct kgsl_memdesc *saved = capturescript;
            fail_global = 0;
            a5xx_crashdump_init(&adreno);
            assert(!IS_ERR_OR_NULL(capturescript) && !IS_ERR_OR_NULL(registers));
            assert(capturescript->hostptr && registers->hostptr);
            assert(global_successes == 2 && global_attempts == (failure ? 3 : 2));
            if (failure == 2) assert(capturescript == saved);
            a5xx_crashdump_init(&adreno);
            assert(global_attempts == (failure ? 3 : 2));
            for (int i = 0; i < global_successes; i++) {
                free(owned[i]->hostptr); free(owned[i]);
            }
            fail_global = failure;
        }
    }
    puts("PASS: actual A5xx crashdump first init, allocation failures, retries and reuse");
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
        + function("adreno_a5xx_snapshot.c", "a5xx_crashdump_init", "void")
        + "\n"
        + tests
    )
    subprocess.run(["gcc", "-std=gnu11", "-Wall", "-Wextra", "-Werror",
                    str(source), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)

# SDM660 keeps its fabrics under the downstream msm_bus driver, so the SCM PAS
# bus vote must stay optional and the crypto PAS device must exist for any
# qcom,pil-tz-generic node (kgsl-hyp included) to leave EPROBE_DEFER.
pil_tz = (kernel / "drivers/soc/qcom/subsys-pil-tz.c").read_text()
assert "IS_ERR_OR_NULL(scm_perf_client)" in pil_tz, "SCM PAS bus vote is mandatory"
assert 'compatible = "qcom,pil-tz-scm-pas"' in (
    kernel / "arch/arm64/boot/dts/vendor/qcom/sdm660.dtsi").read_text(), \
    "pil-tz-scm-pas node missing"
print("PASS: SCM PAS bus voting optional and pil-tz-scm-pas node present")
