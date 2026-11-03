#include "pango_mac_uapi.h"
#include <assert.h>
#include <stdio.h>
int main(void){
 struct pango_vision32_job j={0};unsigned sizes[5];
 _Static_assert(sizeof(j)==112,"Existing ioctl layout retained");
 j.abi_version=1;j.width=3;j.height=2;j.cin=7;j.cout=9;j.kernel=j.stride=1;
 j.weights=0x2000;j.params=0x3000;j.lut=0x4000;j.output=0x20000;j.timeout_cycles=16;
 j.flags=4;assert(pango_vision32_sizes(&j,0x100000,sizes));assert(sizes[2]==108 && sizes[4]==0);
 j.flags=5;assert(pango_vision32_sizes(&j,0x100000,sizes));assert(sizes[2]==108 && sizes[4]==65536);
 j.output=j.lut+65532;assert(!pango_vision32_sizes(&j,0x100000,sizes));
 j.output=0x20000;j.lut=0xf0004;assert(!pango_vision32_sizes(&j,0x100000,sizes));
 j.lut=0x4000;
 for(unsigned f=0;f<32;f++){
  j.flags=f;int valid=pango_vision32_sizes(&j,0x100000,sizes);
  assert(valid==(f==0 || f==1 || f==2 || f==4 || f==5));
 }
 j.flags=4;j.output=0xffffc;assert(!pango_vision32_sizes(&j,0x100000,sizes));
 puts("VISION32_EXACT_UAPI_LAYOUT_RANGE_FLAGS_PASS");return 0;
}
