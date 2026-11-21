#!/usr/bin/env python3
"""Compile the APCS match table and sender against the actual SDM660 binding."""
from pathlib import Path
import json
import re
import subprocess
import sys
import tempfile

kernel = Path(sys.argv[1]).resolve()
source = (kernel / 'drivers/mailbox/qcom-apcs-ipc-mailbox.c').read_text()
dt = (kernel / 'arch/arm64/boot/dts/vendor/qcom/sdm660.dtsi').read_text()
node = re.search(r'apcs_glb:\s*mailbox@17911000\s*\{(.*?)\};', dt, re.S).group(1)
compatible = re.search(r'compatible\s*=\s*"([^"]+)"', node).group(1)
assert re.search(r'rpm-glink\s*\{[^}]*mboxes\s*=\s*<&apcs_glb\s+0>', dt)
assert 'CONFIG_QCOM_APCS_IPC=y' in (kernel / 'arch/arm64/configs/vendor/asus/X00TD_defconfig').read_text().splitlines()
table = re.search(r'^static const struct of_device_id qcom_apcs_ipc_of_match\[\].*?^\};', source, re.M | re.S).group()
structure = re.search(r'^struct qcom_apcs_ipc \{.*?^\};', source, re.M | re.S).group()
sender = re.search(r'^static int qcom_apcs_ipc_send_data\([^;{}]*\)\n\{.*?\n\}', source, re.M | re.S).group()
bits = re.search(r'^#define QCOM_APCS_IPC_BITS\s+\d+', source, re.M).group()
fixture = r'''
#include <assert.h>
#include <errno.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define BIT(n) (1UL << (n))
#define container_of(p,t,m) ((t *)((char *)(p) - offsetof(t,m)))
struct regmap { unsigned long offset, value; int error, writes; };
struct mbox_controller { int unused; };
struct mbox_chan { struct mbox_controller *mbox; void *con_priv; };
struct of_device_id { const char *compatible; const void *data; };
static int regmap_write(struct regmap *m, unsigned long offset, unsigned long value) {
    m->offset=offset; m->value=value; m->writes++; return m->error;
}
''' + bits + '\n' + structure + '\n' + table + '\n' + sender + r'''
static const struct of_device_id *match(const char *name) {
    for (const struct of_device_id *m=qcom_apcs_ipc_of_match; m->compatible; m++)
        if (!strcmp(m->compatible,name)) return m;
    return NULL;
}
int main(void) {
    const struct of_device_id *m=match(''' + json.dumps(compatible) + r''');
    assert(m && "SDM660 APCS provider must bind before GLINK RPM can acquire its mailbox");
    assert((uintptr_t)m->data==8);
    assert((uintptr_t)match("qcom,msm8996-apcs-hmss-global")->data==16);
    assert((uintptr_t)match("qcom,sdm845-apss-shared")->data==12);
    assert(match("qcom,sm8150-spcs-global") && !match("qcom,unknown-apcs"));
    struct regmap map={0};
    struct qcom_apcs_ipc apcs={.regmap=&map,.offset=(uintptr_t)m->data};
    assert(QCOM_APCS_IPC_BITS==32);
    for (unsigned i=0;i<QCOM_APCS_IPC_BITS;i++) {
        apcs.mbox_chans[i]=(struct mbox_chan){.mbox=&apcs.mbox,.con_priv=(void *)(uintptr_t)i};
        assert(qcom_apcs_ipc_send_data(&apcs.mbox_chans[i],NULL)==0);
        assert(map.offset==8 && map.value==BIT(i) && map.writes==(int)i+1);
    }
    map.error=-EIO;
    assert(qcom_apcs_ipc_send_data(&apcs.mbox_chans[0],NULL)==-EIO);
    puts("PASS: actual SDM660 DT binding matches APCS, offset 8, all 32 doorbells and regmap errors; other SoC offsets preserved");
}
'''
with tempfile.TemporaryDirectory(prefix='apcs-sdm660-') as tmp:
    path, binary = Path(tmp) / 'apcs.c', Path(tmp) / 'apcs'
    path.write_text(fixture)
    subprocess.run(['gcc', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                    '-Wno-unused-parameter', str(path), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
