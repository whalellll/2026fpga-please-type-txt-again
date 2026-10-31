#define _POSIX_C_SOURCE 200809L
#include "xq_sha256.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define main xi8_provider_main
#include "integer_bench.c"
#undef main

/* The provider graph/tiler is unchanged. Link to the host-only independent
 * device oracle, which emulates exact hardware dots with scalar CPU math. */
int main(int argc,char **argv)
{
    if(argc<3)return xi8_provider_main(argc,argv);
    FILE *f=fopen(argv[1],"rb");
    const size_t bytes=5582128;
    unsigned char *data=malloc(bytes);char digest[65];
    int okay=f && data && fread(data,1,bytes,f)==bytes && fgetc(f)==EOF && !ferror(f);
    if(f)fclose(f);
    if(okay){xq_sha256_hex(data,bytes,digest);okay=!strcmp(digest,
        "d72d039041b41310f037344772eb75ce895ec6fe678bbb31ed547a7ad7453942");}
    free(data);
    if(!okay){fputs("HWC_HOST_FROZEN_MODEL_REJECTED\n",stderr);return 2;}
    puts("HOST_FUNCTIONAL_CPU_ORACLE no_fpga=1 timing_is_not_board_latency=1");
    return xi8_provider_main(argc,argv);
}
