#!/usr/bin/env python3
"""Compile real SDM660 groups/accessors against the board's single TLMM map."""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

kernel = Path(sys.argv[1]).resolve()
source = (kernel / 'drivers/pinctrl/qcom/pinctrl-sdm660.c').read_text()
core = (kernel / 'drivers/pinctrl/qcom/pinctrl-msm.c').read_text()
header = (kernel / 'drivers/pinctrl/qcom/pinctrl-msm.h').read_text()
dt = (kernel / 'arch/arm64/boot/dts/vendor/qcom/sdm660-pinctrl.dtsi').read_text()
assert re.search(r'reg\s*=\s*<0x0?3000000\s+0xc00000>', dt)
groups = re.search(r'^static const struct msm_pingroup sdm660_groups\[\].*?^\};', source, re.M | re.S).group()
structure = re.search(r'^struct msm_pingroup \{.*?^\};', header, re.M | re.S).group()
mux = re.search(r'^enum sdm660_functions \{.*?^\};', source, re.M | re.S).group()
macros = source[source.index('enum {'):source.index('static const struct pinctrl_pin_desc')]
pins = source[source.index('#define DECLARE_MSM_GPIO_PINS'):source.index('enum sdm660_functions')]
accessors = core[core.index('#define MSM_ACCESSOR'):core.index('static int msm_get_groups_count')]
base = {'NORTH': 0x900000, 'CENTER': 0x500000, 'SOUTH': 0x100000}
gpio = re.findall(r'^\s*PINGROUP\((\d+),\s*(NORTH|CENTER|SOUTH),', groups, re.M)
sdc = re.findall(r'^\s*SDC_QDSD_PINGROUP\(\w+,\s*(0x[\da-f]+),\s*(\d+),\s*(\d+)\)', groups, re.M)
assert len(gpio) == 114 and len(sdc) == 7
offsets = [base[t] + int(n) * 0x1000 for n, t in gpio]
offsets += [base['NORTH'] + int(v, 0) for v, _, _ in sdc]
expected = ','.join(hex(v) for v in offsets)
pulls = ','.join(p for _, p, _ in sdc)
drives = ','.join(d for _, _, d in sdc)
fixture = r'''
#include <assert.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
typedef uint32_t u32;
#define ARRAY_SIZE(a) (sizeof(a)/sizeof(*(a)))
static unsigned char *mmio;
static u32 readl(void *p) { assert((unsigned char *)p>=mmio && (unsigned char *)p+4<=mmio+0xc00000); return *(u32 *)p; }
static void writel(u32 v, void *p) { assert((unsigned char *)p>=mmio && (unsigned char *)p+4<=mmio+0xc00000); *(u32 *)p=v; }
struct msm_pinctrl { void *regs[4]; };
''' + structure + '\n' + macros + '\n' + pins + '\n' + mux + '\n' + groups + '\n' + accessors + r'''
int main(void) {
    static const u32 expected[]={''' + expected + r'''};
    static const unsigned pulls[]={''' + pulls + r'''};
    static const unsigned drives[]={''' + drives + r'''};
    mmio=calloc(1,0xc00000); assert(mmio);
    struct msm_pinctrl p={.regs[0]=mmio};
    assert(ARRAY_SIZE(sdm660_groups)==ARRAY_SIZE(expected));
    for(unsigned i=0;i<ARRAY_SIZE(sdm660_groups);i++) {
        const struct msm_pingroup *g=&sdm660_groups[i];
        assert(g->tile==0 && "single DT resource only maps regs[0]");
        assert(g->ctl_reg==expected[i]);
        msm_writel_ctl(0x12345678,&p,g); assert(msm_readl_ctl(&p,g)==0x12345678);
        if(i<114) {
            assert(g->io_reg==expected[i]+4 && g->intr_cfg_reg==expected[i]+8);
            assert(g->intr_status_reg==expected[i]+12 && g->intr_target_reg==expected[i]+8);
            assert(g->mux_bit==2 && g->pull_bit==0 && g->drv_bit==6 && g->oe_bit==9);
            msm_writel_io(1,&p,g); assert(msm_readl_io(&p,g)==1);
            msm_writel_intr_cfg(2,&p,g); assert(msm_readl_intr_cfg(&p,g)==2);
            msm_writel_intr_status(3,&p,g); assert(msm_readl_intr_status(&p,g)==3);
            msm_writel_intr_target(4,&p,g); assert(msm_readl_intr_target(&p,g)==4);
        } else {
            assert(g->pull_bit==pulls[i-114] && g->drv_bit==drives[i-114]);
        }
    }
    free(mmio);
    puts("PASS: all 114 real GPIO groups and 7 SD/eMMC groups address the single TLMM mapping; mux/pull/drive bits and real read/write accessors preserved");
}
'''
with tempfile.TemporaryDirectory(prefix='pinctrl-sdm660-') as tmp:
    path, binary = Path(tmp) / 'pinctrl.c', Path(tmp) / 'pinctrl'
    path.write_text(fixture)
    subprocess.run(['gcc', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                    '-Wno-pointer-sign', str(path), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
soc = re.search(r'^static const struct msm_pinctrl_soc_data sdm660_pinctrl.*?^\};', source, re.M | re.S).group()
assert not re.search(r'\.n?tiles\s*=', soc), 'Generic probe must map the existing single resource'
