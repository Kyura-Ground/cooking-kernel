#!/usr/bin/env python3
"""Replay firmware GPIO reservations through real pinctrl/gpiolib helpers."""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

kernel = Path(sys.argv[1]).resolve()
source = (kernel / 'drivers/pinctrl/qcom/pinctrl-msm.c').read_text()
core = (kernel / 'drivers/gpio/gpiolib.c').read_text()
board = (kernel / 'arch/arm64/boot/dts/vendor/qcom/sdm636-qrd-X00TD.dts').read_text()
reserved = re.search(r'&tlmm\s*\{[^}]*qcom,gpios-reserved\s*=\s*<([^>]+)>', board).group(1)
assert [int(value, 0) for value in reserved.split()] == [8, 9, 10, 11]


def function(text, name):
    return re.search(r'^(?:static )?(?:int|bool) ' + name +
                     r'\([^;{}]*\)\n\{.*?\n\}', text, re.M | re.S).group()


a = core.index('\tret = gpiochip_init_valid_mask(chip);', core.index('int gpiochip_add_data_with_key('))
a = core.index('\tfor (i = 0; i < chip->ngpio; i++) {', a)
b = core.index('\n\tacpi_gpiochip_add(chip);', a)
direction_loop = core[a:b]
fixture = r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint16_t u16;
typedef uint32_t __be32;
#define GFP_KERNEL 0
#define FLAG_IS_OUT 0
#define likely(x) (x)
#define dev_err(...) ((void)0)
#define dev_warn(...) ((void)0)
struct property { int length; const __be32 *cells; };
struct device_node { bool present; struct property reserved; };
struct device { struct device_node *of_node; int count, error; u16 *allow; };
struct msm_pinctrl_soc_data { const int *reserved_gpios; };
struct gpio_chip {
    unsigned ngpio;
    struct device_node *of_node;
    unsigned long *valid_mask;
    void *data;
    int (*get_direction)(struct gpio_chip *, unsigned);
    bool direction_input;
    int (*init_valid_mask)(struct gpio_chip *, unsigned long *, unsigned);
};
struct msm_pinctrl { struct device *dev; const struct msm_pinctrl_soc_data *soc; struct gpio_chip chip; };
struct gpio_desc { unsigned long flags; };
struct gpio_device { struct gpio_desc descs[114]; };
static bool standard_reserved, fail_alloc, forbidden[114];
static unsigned reads[114];
static void bitmap_fill(unsigned long *p,unsigned n) { for(unsigned i=0;i<(n+63)/64;i++)p[i]=~0UL; }
static void bitmap_zero(unsigned long *p,unsigned n) { for(unsigned i=0;i<(n+63)/64;i++)p[i]=0; }
static void set_bit(unsigned n,unsigned long *p) { p[n/64]|=1UL<<(n%64); }
static void clear_bit(unsigned n,unsigned long *p) { p[n/64]&=~(1UL<<(n%64)); }
static bool test_bit(unsigned n,const unsigned long *p) { return !!(p[n/64]&(1UL<<(n%64))); }
static void *gpiochip_get_data(struct gpio_chip *gc) { return gc->data; }
static struct property *of_find_property(struct device_node *n,const char *key,int *len) {
    (void)len; assert(!strcmp(key,"qcom,gpios-reserved"));
    return n && n->present ? &n->reserved : NULL;
}
static int of_property_count_u32_elems(struct device_node *n,const char *key) {
    struct property *p=of_find_property(n,key,NULL);
    if(!p) return -EINVAL; if(!p->cells) return -ENODATA;
    return p->length%4 ? -EINVAL : p->length/4;
}
#define of_property_for_each_u32(n,k,prop,p,value) \
 for(prop=of_find_property(n,k,NULL),p=prop->cells; \
     p<prop->cells+prop->length/4 && ((value)=*p,1);p++)
static int device_property_count_u16(struct device *d,const char *key) { assert(!strcmp(key,"gpios"));return d->count; }
static int device_property_read_u16_array(struct device *d,const char *key,u16 *p,unsigned len) {
    (void)key; if(d->error)return d->error; memcpy(p,d->allow,len*sizeof(*p));return 0;
}
static void *kmalloc_array(unsigned n,size_t size,int flags) { (void)flags;return fail_alloc ? NULL : calloc(n?n:1,size); }
#define kfree free
static bool of_gpio_need_valid_mask(struct gpio_chip *gc) { (void)gc;return standard_reserved; }
static unsigned long *gpiochip_allocate_mask(struct gpio_chip *gc) {
    if(fail_alloc)return NULL;
    unsigned long *p=calloc(3,sizeof(*p)); assert(p);bitmap_fill(p,gc->ngpio);p[2]=0x12345678;return p;
}
''' + '\n'.join([function(source, 'msm_gpio_init_valid_mask'),
    function(source, 'msm_gpio_needs_valid_mask'), function(core, 'gpiochip_alloc_valid_mask'),
    function(core, 'gpiochip_init_valid_mask'), function(core, 'gpiochip_line_is_valid')]) + r'''
static int get_direction(struct gpio_chip *gc,unsigned gpio) {
    (void)gc; assert(gpio<114);
    if(forbidden[gpio]) fprintf(stderr,"forbidden firmware GPIO%u direction read\n",gpio);
    assert(!forbidden[gpio]);reads[gpio]++;return 1;
}
static int register_directions(struct msm_pinctrl *pctrl) {
    struct gpio_chip *chip=&pctrl->chip;
    struct gpio_device storage={0},*gdev=&storage;
    int ret; unsigned i;
    if(msm_gpio_needs_valid_mask(pctrl))
        chip->init_valid_mask=msm_gpio_init_valid_mask;
    ret=gpiochip_alloc_valid_mask(chip); if(ret)return ret;
    if(standard_reserved)clear_bit(50,chip->valid_mask);
    ret=gpiochip_init_valid_mask(chip); if(ret)return ret;
''' + direction_loop + r'''
    return 0;
}
static void reset(struct msm_pinctrl *p) {
    if(p->chip.valid_mask) { assert(p->chip.valid_mask[2]==0x12345678);free(p->chip.valid_mask); }
    p->chip=(struct gpio_chip){.ngpio=114,.data=p,.of_node=p->dev->of_node,.get_direction=get_direction,.direction_input=true};
    *p->dev=(struct device){.of_node=p->dev->of_node,.count=-EINVAL};
    *p->dev->of_node=(struct device_node){0};
    memset(reads,0,sizeof(reads));memset(forbidden,0,sizeof(forbidden));
    standard_reserved=fail_alloc=false;
}
int main(void) {
    struct device_node node={0};struct device dev={.of_node=&node};
    struct msm_pinctrl_soc_data soc={0};struct msm_pinctrl p={.dev=&dev,.soc=&soc};
    const __be32 blocked[]={8,9,10,11};
    reset(&p);node=(struct device_node){true,{sizeof(blocked),blocked}};
    for(unsigned i=8;i<=11;i++)forbidden[i]=true;
    assert(register_directions(&p)==0);
    for(unsigned i=0;i<114;i++)assert(reads[i]==(i<8 || i>11));
    reset(&p);node=(struct device_node){true,{sizeof(blocked),blocked}};
    for(unsigned i=8;i<=11;i++)forbidden[i]=true;
    standard_reserved=true;assert(register_directions(&p)==0 && !reads[50]);
    reset(&p);node=(struct device_node){true,{sizeof(blocked),blocked}};
    for(unsigned i=8;i<=11;i++)forbidden[i]=true;
    u16 conflicting_allow[]={8,12};dev.allow=conflicting_allow;dev.count=2;
    assert(register_directions(&p)==0 && !reads[8] && reads[113]);
    reset(&p);const __be32 invalid[]={114};node=(struct device_node){true,{4,invalid}};
    assert(register_directions(&p)==-EINVAL);
    reset(&p);node=(struct device_node){true,{3,blocked}};
    assert(register_directions(&p)==-EINVAL);
    reset(&p);node=(struct device_node){true,{4,NULL}};
    assert(register_directions(&p)==-ENODATA);
    reset(&p);node=(struct device_node){true,{0,NULL}};
    assert(register_directions(&p)==0);
    reset(&p);assert(register_directions(&p)==0 && reads[8]==1);
    reset(&p);u16 allow[]={0,7,12,113};dev.allow=allow;dev.count=4;
    assert(register_directions(&p)==0 && reads[0] && reads[113] && !reads[8]);
    reset(&p);u16 invalid_allow[]={114};dev.allow=invalid_allow;dev.count=1;
    assert(register_directions(&p)==-EINVAL);
    reset(&p);const int driver_reserved[]={8,-1};soc.reserved_gpios=driver_reserved;forbidden[8]=true;
    assert(register_directions(&p)==0 && !reads[8] && reads[9]);soc.reserved_gpios=NULL;
    reset(&p);node=(struct device_node){true,{sizeof(blocked),blocked}};fail_alloc=true;
    assert(register_directions(&p)==-ENOMEM);fail_alloc=false;
    reset(&p);
    puts("PASS: real mask helpers and gpiolib direction loop never read firmware-reserved GPIO8-11; standard reservations, bounds, empty/malformed properties, existing SoC/ACPI paths and allocation errors");
}
'''
with tempfile.TemporaryDirectory(prefix='gpio-reserved-mask-') as tmp:
    path, binary = Path(tmp) / 'mask.c', Path(tmp) / 'mask'
    path.write_text(fixture)
    subprocess.run(['gcc', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                    '-Wno-misleading-indentation', '-Wno-unused-function',
                    '-Wno-sign-compare',
                    str(path), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
