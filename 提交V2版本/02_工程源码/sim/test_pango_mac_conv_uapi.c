#include <stddef.h>
#include <stdio.h>

#include "../linux/mac_accel/pango_mac_uapi.h"

_Static_assert(PANGO_MAC_ABI_VERSION == 1u, "legacy ABI must stay available");
_Static_assert(PANGO_MAC_CONV_ABI_VERSION == 2u, "conv ABI version changed");
_Static_assert(PANGO_MAC_CONV_COMPUTE_ABI_VERSION == 3u,
               "compute ABI version changed");
_Static_assert(PANGO_MAC_CONV_FLAG_WINDOW_ONLY == 1u,
               "stage-2 window mode changed");
_Static_assert(PANGO_MAC_CONV_FLAG_COMPUTE == 2u,
               "stage-2 compute mode changed");
_Static_assert(offsetof(struct pango_mac_conv_job, input_offset) == 20,
               "conv descriptor layout changed");
_Static_assert(offsetof(struct pango_mac_conv_job, output_offset) == 28,
               "legacy OUTPUT_DST must keep its own address field");
_Static_assert(sizeof(struct pango_mac_conv_job) == 112,
               "conv job size changed");

int main(void)
{
    struct pango_mac_conv_job job = {0};

    job.abi_version = PANGO_MAC_CONV_ABI_VERSION;
    job.flags = PANGO_MAC_CONV_FLAG_WINDOW_ONLY;
    job.kernel = 6;
    job.stride = 2;
    job.padding = 2;
    job.width = 320;
    job.height = 320;
    job.channels = 3;
    job.weight_lines = 27;
    if (job.abi_version != 2 || job.weight_lines < 27 ||
        PANGO_MAC_IOC_RUN_CONV == PANGO_MAC_IOC_RUN)
        return 1;
    job.abi_version = PANGO_MAC_CONV_COMPUTE_ABI_VERSION;
    job.flags = PANGO_MAC_CONV_FLAG_COMPUTE;
    job.reserved[0] = 0x90000; /* 16 signed INT32 bias values */
    job.reserved[1] = 0x90040; /* 16 right-shift bytes */
    if (job.abi_version != 3 || job.flags != 2 ||
        !(PANGO_MAC_FEATURE_CONV_COMPUTE & (1u << 4)))
        return 1;
    puts("PANGO_MAC_CONV_UAPI_PASS");
    return 0;
}
