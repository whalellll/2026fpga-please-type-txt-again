#include "pango_mac_uapi.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
int main(void)
{
    struct pango_mac_model model = { .abi_version=PANGO_MAC_MODEL_ABI_VERSION,
        .offset=0x1000, .bytes=0x2000 };
    _Static_assert(sizeof(model)==64,"model registration ABI");
    assert(pango_mac_model_valid(&model,0x100000));
    assert(pango_mac_resident_sources_valid(0x1000,0x2000,0x1000,0x2000,0,0,0x9000,512,0xa000,64));
    assert(!pango_mac_resident_sources_valid(0x1000,0x2000,0x2ffc,8,0,0,0x9000,512,0xa000,64));
    assert(!pango_mac_resident_sources_valid(0x1000,0x2000,0x1000,128,0x2ffc,8,0x9000,512,0xa000,64));
    assert(!pango_mac_resident_sources_valid(0x1000,0x2000,0x1000,128,0,0,0x0ffc,8,0xa000,64));
    assert(!pango_mac_resident_sources_valid(0x1000,0x2000,0x1000,128,0,0,0x9000,512,0x2ffc,8));
    model.bytes=0;assert(!pango_mac_model_valid(&model,0x100000));
    model.bytes=0x100000;model.offset=4;assert(!pango_mac_model_valid(&model,0x100000));
    model.offset=0xfffffffcu;model.bytes=8;assert(!pango_mac_model_valid(&model,0x100000));
    model.offset=0;model.bytes=0x100000;assert(pango_mac_model_valid(&model,0x100000));
    model.reserved[11]=1;assert(!pango_mac_model_valid(&model,0x100000));
    puts("PANGO_MAC_RESIDENT_UAPI_PASS");return 0;
}
