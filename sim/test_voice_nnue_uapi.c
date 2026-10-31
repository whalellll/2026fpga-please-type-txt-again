#include "pango_mac_uapi.h"
#include "pango_voice_uapi.h"
#include <assert.h>
#include <stdio.h>
_Static_assert(sizeof(struct pango_mac_stagea_job)==64,"legacy StageA ABI");
_Static_assert(sizeof(struct pango_mac_stagea_link)==80,"linked StageA ABI");
_Static_assert(sizeof(struct pango_mac_nnue_upload)==32,"upload ABI");
_Static_assert(sizeof(struct pango_mac_nnue_job)==48,"NNUE ABI");
_Static_assert(sizeof(struct pango_voice_info)==64,"voice info ABI");
_Static_assert(sizeof(struct pango_voice_frame)==836,"voice frame ABI");
_Static_assert(sizeof(struct pango_voice_infer)==188,"voice inference ABI");
_Static_assert(sizeof(struct pango_voice_stream)==608,"voice stream ABI");
_Static_assert(((PANGO_VOICE_IOC_MODE>>16)&0x3fffu)==4,"voice mode ABI");
int main(void)
{
 struct pango_mac_nnue_upload u={.abi_version=6};
 struct pango_mac_nnue_job j={.abi_version=6,.tag0=1,.tag1=2};
 unsigned i;
 assert(pango_mac_nnue_upload_valid(&u,1048576));
 u.source_offset=1048576-2048;assert(pango_mac_nnue_upload_valid(&u,1048576));
 for(i=1;i<4;i++){u.source_offset=1048576-2048+i;assert(!pango_mac_nnue_upload_valid(&u,1048576));}
 u.source_offset=1048576;assert(!pango_mac_nnue_upload_valid(&u,1048576));
 u.source_offset=~0u;assert(!pango_mac_nnue_upload_valid(&u,1048576));
 u.source_offset=0;u.tag=1;assert(!pango_mac_nnue_upload_valid(&u,1048576));u.tag=0;
 u.view=2;assert(!pango_mac_nnue_upload_valid(&u,1048576));u.view=0;
 for(i=0;i<4;i++){u.reserved[i]=1;assert(!pango_mac_nnue_upload_valid(&u,1048576));u.reserved[i]=0;}
 u.abi_version=1;assert(!pango_mac_nnue_upload_valid(&u,1048576));
 for(i=0;i<16;i++){j.bucket=i;assert(pango_mac_nnue_job_valid(&j));}
 j.bucket=16;assert(!pango_mac_nnue_job_valid(&j));j.bucket=0;
 j.tag0=0;assert(!pango_mac_nnue_job_valid(&j));j.tag0=1;
 j.tag1=0;assert(!pango_mac_nnue_job_valid(&j));j.tag1=2;
 j.first_view=2;assert(!pango_mac_nnue_job_valid(&j));j.first_view=1;
 j.timeout_us=1000000;assert(pango_mac_nnue_job_valid(&j));
 j.timeout_us=1000001;assert(!pango_mac_nnue_job_valid(&j));j.timeout_us=0;
 for(i=0;i<2;i++){j.reserved[i]=1;assert(!pango_mac_nnue_job_valid(&j));j.reserved[i]=0;}
 j.abi_version=5;assert(!pango_mac_nnue_job_valid(&j));
 puts("VOICE_NNUE_UAPI_LAYOUT_RANGE_ALIGNMENT_TAGS_RESERVED_TIMEOUT_PASS");return 0;
}
