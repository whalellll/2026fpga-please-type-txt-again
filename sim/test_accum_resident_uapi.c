#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "pango_mac_uapi.h"
int main(void){
 struct pango_mac_batch b;unsigned count,job,slot,cases=0;
 _Static_assert(sizeof(b)==144,"Existing batch ABI size changed");
 for(count=1;count<=8;count++)for(job=0;job<count;job++)for(slot=0;slot<8;slot++){
  unsigned i;memset(&b,0,sizeof(b));b.abi_version=1;b.count=count;
  for(i=0;i<count;i++)b.update[i].parent=PANGO_MAC_BATCH_EXTERNAL;
  b.update[job].parent=PANGO_MAC_BATCH_RESIDENT_PARENT(slot);
  assert(!pango_mac_batch_valid(&b));b.flags=PANGO_MAC_BATCH_RESIDENT;
  assert(!!pango_mac_batch_valid(&b)==(slot>=job));b.reserved[1]=123;
  assert(!!pango_mac_batch_valid(&b)==(slot>=job));
  b.reserved[2]=1;assert(!pango_mac_batch_valid(&b));
  b.reserved[2]=0;b.reserved[3]=1;assert(!pango_mac_batch_valid(&b));
  b.reserved[3]=0;b.update[job].parent=PANGO_MAC_BATCH_RESIDENT_PARENT(8);
  assert(!pango_mac_batch_valid(&b));cases++;
 }
 memset(&b,0,sizeof(b));b.abi_version=1;b.count=1;b.update[0].parent=PANGO_MAC_BATCH_EXTERNAL;
 assert(pango_mac_batch_valid(&b));b.reserved[1]=1;assert(!pango_mac_batch_valid(&b));
 printf("ACCUM_RESIDENT_UAPI_OLD_ABI_PARENT_OVERWRITE_AND_RESERVED_PASS cases=%u bytes=%zu\n",cases,sizeof(b));return 0;
}
