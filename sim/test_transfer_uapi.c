#include "pango_mac_uapi.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
_Static_assert(sizeof(struct pango_vision32_job)==112,"Vision ABI size");
_Static_assert(sizeof(struct pango_mac_batch)==144,"Batch ABI size");
int main(void){
 struct pango_mac_batch b={0};b.abi_version=1;
 for(unsigned n=1;n<=8;n++){
  b.count=n;for(unsigned i=0;i<n;i++)b.update[i].parent=PANGO_MAC_BATCH_EXTERNAL;
  b.flags=PANGO_MAC_BATCH_COPYOUT_MASK;
  for(unsigned m=0;m<(1u<<n);m++){b.reserved[0]=m;assert(pango_mac_batch_valid(&b));}
  b.reserved[0]=1u<<n;assert(!pango_mac_batch_valid(&b));
  b.reserved[0]=0;b.flags=0;assert(pango_mac_batch_valid(&b));
  b.reserved[0]=1;assert(!pango_mac_batch_valid(&b));
 }
 struct pango_vision32_job j={0};unsigned sizes[5];
 j.abi_version=1;j.width=j.height=j.cin=j.cout=j.kernel=j.stride=1;
 j.weights=256;j.params=512;j.output=1024;j.flags=4;j.timeout_cycles=16;
 j.model_generation=37;j.frame_id=19;assert(pango_vision32_sizes(&j,1048576,sizes));
 j.reserved[0]=PANGO_VISION32_REUSE_PARAMS;assert(pango_vision32_sizes(&j,1048576,sizes));
 j.model_generation=0;assert(!pango_vision32_sizes(&j,1048576,sizes));
 j.model_generation=1;j.reserved[0]=123;assert(!pango_vision32_sizes(&j,1048576,sizes));
 puts("TRANSFER_UAPI_112_144_BYTES_MASK_ENUMERATION_AND_LEGACY_METADATA_PASS");return 0;
}
