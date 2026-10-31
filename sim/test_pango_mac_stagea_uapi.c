#include <assert.h>
#include <stddef.h>
#include <stdio.h>
#include "pango_mac_uapi.h"

_Static_assert(sizeof(struct pango_mac_info)==64,"old info ABI");
_Static_assert(sizeof(struct pango_mac_job)==64,"old dense ABI");
_Static_assert(sizeof(struct pango_mac_stagea_job)==64,"Stage A ABI");
_Static_assert(offsetof(struct pango_mac_stagea_job,cycles)==32,"Stage A counters");
int main(void)
{
    struct pango_mac_stagea_job good={.abi_version=PANGO_MAC_STAGEA_ABI_VERSION,
        .terms=256,.base_offset=0xa0000,.descriptor_offset=0xa1000,
        .output_offset=0xb2000,.timeout_us=100000};
    struct pango_mac_stagea_job bad;
    assert(pango_mac_stagea_job_valid(&good,0x100000));
    bad=good;bad.terms=0;assert(!pango_mac_stagea_job_valid(&bad,0x100000));
    bad=good;bad.terms=257;assert(!pango_mac_stagea_job_valid(&bad,0x100000));
    bad=good;bad.terms=0x201;assert(!pango_mac_stagea_job_valid(&bad,0x100000));
    bad=good;bad.base_offset=0xfffffff0;assert(!pango_mac_stagea_job_valid(&bad,0x100000));
    bad=good;bad.output_offset=0xff804;assert(!pango_mac_stagea_job_valid(&bad,0x100000));
    bad.output_offset=0xff800;assert(pango_mac_stagea_job_valid(&bad,0x100000));
    bad=good;bad.descriptor_offset=0xffc04;assert(!pango_mac_stagea_job_valid(&bad,0x100000));
    bad.descriptor_offset=0xffc00;assert(pango_mac_stagea_job_valid(&bad,0x100000));
    bad=good;bad.output_offset=good.base_offset+4;assert(!pango_mac_stagea_job_valid(&bad,0x100000));
    bad=good;bad.output_offset=good.descriptor_offset;assert(!pango_mac_stagea_job_valid(&bad,0x100000));
    bad=good;bad.descriptor_offset=good.base_offset+4;assert(!pango_mac_stagea_job_valid(&bad,0x100000));
    bad=good;bad.flags=1;assert(!pango_mac_stagea_job_valid(&bad,0x100000));
    bad=good;bad.reserved[3]=1;assert(!pango_mac_stagea_job_valid(&bad,0x100000));
    bad=good;bad.timeout_us=1000001;assert(!pango_mac_stagea_job_valid(&bad,0x100000));
    assert(pango_mac_stagea_descriptor_valid(45546));
    assert(!pango_mac_stagea_descriptor_valid(45547));
    assert(pango_mac_stagea_descriptor_valid(0xc0000000u|16535));
    assert(!pango_mac_stagea_descriptor_valid(0xc0000000u|16536));
    assert(!pango_mac_stagea_descriptor_valid(0x00010000));
    puts("PANGO_MAC_STAGEA_UAPI_PASS");return 0;
}
